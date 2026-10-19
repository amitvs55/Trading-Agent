"""Option Check: type a contract and an amount, get a verdict, what the money can become, and why.

During market hours the live engine inside the recorder answers (the same snapshot, chain and quotes
the signals use): the API saves a pending request, NOTIFYs the recorder and waits for its market
facts. Outside market hours, or if the recorder doesn't answer within a few seconds, the facts are
rebuilt here from saved data and the report says so. The report itself is computed here from the
facts and the parameters, so what-ifs are instant and never touch the recorder.
"""

import asyncio
import threading
import time as _clock
import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from api.deps import current_user, get_calendar, get_cfg, get_store
from options.check import offline, outcomes
from options.check.facts import market_facts
from options.check.parse import describe, parse_query, resolve
from options.check.report import Params, build
from options.check.worker import CHANNEL
from options.config import OptionsSettings
from options.core.calendar import IST, NseCalendar, now_ist
from options.storage import Store
from utils.logger import setup_logger

logger = setup_logger("api.check")
router = APIRouter(tags=["option-check"])

WAIT_LIVE_S = 4.0                 # the recorder answers in well under a second; then fall back
WAIT_WORKING_S = 4.0              # it has picked the request up: give it a little longer
HEARTBEAT_FRESH_S = 60


class CheckIn(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    amount: float = Field(25_000, gt=0, le=100_000_000)
    entry: float | None = Field(None, gt=0, le=1_000_000)
    horizon: Literal["intraday", "expiry"] = "intraday"


class WhatIf(BaseModel):
    amount: float | None = Field(None, gt=0, le=100_000_000)
    entry: float | None = Field(None, gt=0, le=1_000_000)
    horizon: Literal["intraday", "expiry"] | None = None
    iv_shift: float = Field(0.0, ge=-20, le=20)
    slippage_pct: float = Field(0.0, ge=0, le=10)


def _opt_json(o) -> dict:
    return {"symbol": o.tradingsymbol, "token": o.token, "expiry": o.expiry.isoformat(), "strike": o.strike,
            "right": o.right, "lot_size": o.lot_size, "label": describe(o)}


def _refs(store: Store, cfg: OptionsSettings, now: datetime):
    day = offline.last_session(store, now.astimezone(IST).date())
    if day is None:
        raise HTTPException(503, {"code": "no_contracts", "message": "No contract list saved yet: it arrives with the "
                                  "first recording session."})
    refs, vix = offline.references(store, cfg.OPTIONS_INDICES, day)
    return refs, vix, day


@router.get("/api/options/check/resolve", dependencies=[Depends(current_user)])
def resolve_contract(q: str = Query(..., min_length=1, max_length=120), store: Store = Depends(get_store),
                     cfg: OptionsSettings = Depends(get_cfg)) -> dict:
    """What a typed query means: the exact contract, or the problem and the nearest real ones."""
    now = now_ist()
    refs, _, _ = _refs(store, cfg, now)
    res = resolve(parse_query(q, now.date()), refs, now)
    return {"ok": res.option is not None and res.problem is None, "problem": res.problem,
            "contract": _opt_json(res.option) if res.option else None,
            "suggestions": [_opt_json(o) for o in res.suggestions[:6]]}


def _recorder_live(store: Store, now: datetime, cal: NseCalendar) -> bool:
    if not cal.is_market_open(now):
        return False
    st = store.get_meta_json("recorder_status") or {}
    try:
        fresh = (now - datetime.fromisoformat(st["ts"])).total_seconds() <= HEARTBEAT_FRESH_S
    except (KeyError, ValueError, TypeError):
        return False
    return fresh and st.get("state") == "running"


async def _wait(store: Store, check_id: str, seconds: float, statuses: set[str]) -> dict | None:
    deadline = _clock.monotonic() + seconds
    while _clock.monotonic() < deadline:
        row = await run_in_threadpool(store.check_get, check_id)
        if row and row["status"] in statuses:
            return row
        await asyncio.sleep(0.1)
    return None


def _offline_facts(store: Store, cfg: OptionsSettings, cal: NseCalendar, index: str, day: date, opt, horizon: str) -> dict:
    from options.session import load_events
    snap = offline.snapshot(store, cal, index, day, cfg.OPTIONS_RISK_FREE_RATE, load_events(store),
                            ttl=60 if day == now_ist().date() else offline.CACHE_S)
    if snap is None:
        raise HTTPException(503, {"code": "no_data", "message": f"No saved market data for {day:%d %b}."})
    when, real = snap.ctx.now, now_ist()
    open_now = day == real.date() and cal.is_market_open(real)
    label = "saved data" + ("" if open_now else f" (as of {when.astimezone(IST):%a %d %b %H:%M})")
    return market_facts(snap, opt, horizon, when, None, store.open_signals(), source=label,
                        checked_at=real, market_open=open_now)


def _history(store: Store, refs: dict, vix: int | None, index: str):
    ref = refs.get(index)
    if ref is None:
        return None
    try:
        return offline.history(store, ref.spot_token, vix, now_ist().date())
    except Exception:
        logger.exception("History view unavailable")
        return None


def _params(raw: dict, cfg: OptionsSettings, **over) -> Params:
    base = {k: raw.get(k) for k in ("amount", "entry", "horizon") if raw.get(k) is not None}
    base.update({k: v for k, v in over.items() if v is not None})
    return Params(capital=cfg.OPTIONS_CAPITAL, risk_pct=cfg.OPTIONS_RISK_PER_TRADE_PCT, **base)


def _summary(report: dict, refs: dict, index: str) -> dict:
    v = report.get("verdict") or {}
    pos = report.get("position") or {}
    hist = report.get("history") or {}
    view = (hist.get("similar") if (hist.get("similar") or {}).get("hold") else None) or (hist if hist.get("hold") else None)
    odds = (view or report.get("market") or {}).get("hold") or {}
    hz = report.get("horizon") or {}
    return {"verdict": v.get("call"), "tone": v.get("tone"), "score": v.get("score"), "entry": pos.get("entry"),
            "lots": pos.get("lots"), "units": pos.get("units"), "capital_used": pos.get("capital_used"),
            "p_profit": odds.get("p_profit"), "expected": odds.get("expected"),
            "odds_from": "similar sessions" if view is not None and view is hist.get("similar") else
                         "past sessions" if view is not None else "market view",
            "horizon_start": hz.get("start"), "horizon_end": hz.get("end"), "settles": hz.get("settles"),
            "spot_token": refs[index].spot_token if index in refs else None,
            "market_open": (report.get("facts") or {}).get("market_open")}


def _owned(row: dict | None, user: dict) -> dict:
    if row is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such check."})
    if user["role"] != "admin" and row.get("username") != user.get("username"):
        raise HTTPException(404, {"code": "not_found", "message": "No such check."})
    return row


@router.post("/api/options/check")
async def run_check(body: CheckIn, user: dict = Depends(current_user), store: Store = Depends(get_store),
                    cfg: OptionsSettings = Depends(get_cfg), cal: NseCalendar = Depends(get_calendar)) -> dict:
    now = now_ist()
    refs, vix, day = await run_in_threadpool(_refs, store, cfg, now)
    res = resolve(parse_query(body.query, now.date()), refs, now)
    if res.option is None or res.problem:
        raise HTTPException(422, {"code": "contract", "message": res.problem or "Couldn't read that contract",
                                  "suggestions": [_opt_json(o) for o in res.suggestions[:6]]})
    opt, index = res.option, res.query.index
    check_id = uuid.uuid4().hex[:12]
    params = body.model_dump()
    live = await run_in_threadpool(_recorder_live, store, now, cal)
    await run_in_threadpool(store.check_add, {
        "id": check_id, "created_at": now, "username": user.get("username"), "query": body.query,
        "index_name": index, "symbol": opt.tradingsymbol, "token": opt.token, "expiry": opt.expiry,
        "strike": opt.strike, "option_right": opt.right, "lot_size": opt.lot_size,
        "status": "pending" if live else "offline", "params": params, "outcome_done": 0, "paper": 0})

    facts = None
    if live:
        await run_in_threadpool(store.notify, CHANNEL, check_id)
        row = await _wait(store, check_id, WAIT_LIVE_S, {"facts", "error", "working"})
        if row and row["status"] == "working":
            row = await _wait(store, check_id, WAIT_WORKING_S, {"facts", "error"})
        if row and row["status"] == "facts":
            facts = row["facts"]
        elif row is None and not await run_in_threadpool(store.check_claim, check_id, "pending", "offline"):
            row = await _wait(store, check_id, WAIT_WORKING_S, {"facts", "error"})
            facts = row["facts"] if row and row["status"] == "facts" else None
    if facts is None:
        try:
            facts = await run_in_threadpool(_offline_facts, store, cfg, cal, index, day, opt, body.horizon)
        except HTTPException as e:
            await run_in_threadpool(store.check_update, check_id, status="error", error=str(e.detail))
            raise
    history = await run_in_threadpool(_history, store, refs, vix, index)
    report = await run_in_threadpool(build, facts, _params(params, cfg), history, cal)
    await run_in_threadpool(store.check_update, check_id, status="done", facts=facts,
                            summary=_summary(report, refs, index))
    return {"id": check_id, "created_at": now.isoformat(), "query": body.query, "report": report}


@router.get("/api/options/check/{check_id}")
async def get_check(check_id: str, user: dict = Depends(current_user), store: Store = Depends(get_store),
                    cfg: OptionsSettings = Depends(get_cfg), cal: NseCalendar = Depends(get_calendar)) -> dict:
    row = _owned(await run_in_threadpool(store.check_get, check_id), user)
    if row["status"] != "done" or not row.get("facts"):
        raise HTTPException(409, {"code": "not_ready", "message": row.get("error") or "This check didn't finish."})
    refs, vix, _ = await run_in_threadpool(_refs, store, cfg, now_ist())
    history = await run_in_threadpool(_history, store, refs, vix, row["index_name"])
    report = await run_in_threadpool(build, row["facts"], _params(row["params"] or {}, cfg), history, cal)
    return {"id": check_id, "created_at": row["created_at"].isoformat(), "query": row["query"], "report": report,
            "paper": _paper_json(row), "outcome": row.get("outcome")}


@router.post("/api/options/check/{check_id}/whatif")
async def what_if(check_id: str, body: WhatIf, user: dict = Depends(current_user), store: Store = Depends(get_store),
                  cfg: OptionsSettings = Depends(get_cfg), cal: NseCalendar = Depends(get_calendar)) -> dict:
    row = _owned(await run_in_threadpool(store.check_get, check_id), user)
    if not row.get("facts"):
        raise HTTPException(409, {"code": "not_ready", "message": "This check didn't finish."})
    refs, vix, _ = await run_in_threadpool(_refs, store, cfg, now_ist())
    history = await run_in_threadpool(_history, store, refs, vix, row["index_name"])
    params = _params(row["params"] or {}, cfg, amount=body.amount, entry=body.entry, horizon=body.horizon,
                     iv_shift=body.iv_shift, slippage_pct=body.slippage_pct)
    report = await run_in_threadpool(build, row["facts"], params, history, cal)
    return {"id": check_id, "report": report}


def _paper_json(row: dict) -> dict | None:
    if not row.get("paper"):
        return None
    closed = row.get("paper_closed_at")
    out = {"entry": row.get("paper_entry"), "units": row.get("paper_units"), "exit": row.get("paper_exit"),
           "closed_at": closed.isoformat() if closed else None, "symbol": row.get("symbol")}
    if row.get("paper_exit") is not None and row.get("paper_entry") and row.get("paper_units"):
        out["pnl"] = round(outcomes._pnl(row["paper_entry"], row["paper_exit"], row["paper_units"]), 0)
    return out


def _refresh_outcomes(store: Store, rows: list[dict], now: datetime) -> None:
    for r in rows:
        try:
            if not r.get("outcome_done"):
                out, done = outcomes.evaluate(r, store, now)
                if out != (r.get("outcome") or {}) or done:
                    store.check_update(r["id"], outcome=out, outcome_done=1 if done else 0)
                    r["outcome"], r["outcome_done"] = out, int(done)
            settled = outcomes.settle_paper(r, store, now)
            if settled:
                store.check_update(r["id"], **settled)
                r.update(settled)
        except Exception:
            logger.exception("Scoring check %s failed", r.get("id"))


def _row_json(r: dict) -> dict:
    return {"id": r["id"], "created_at": r["created_at"].isoformat(), "query": r["query"], "symbol": r.get("symbol"),
            "token": r.get("token"), "expiry": r["expiry"].isoformat() if r.get("expiry") else None,
            "username": r.get("username"), "summary": r.get("summary"), "outcome": r.get("outcome"),
            "paper": _paper_json(r)}


@router.get("/api/options/checks")
async def list_checks(limit: int = Query(30, ge=1, le=200), user: dict = Depends(current_user),
                      store: Store = Depends(get_store)) -> dict:
    """Your recent checks with what happened since, and the checker's record across everyone's checks."""
    now = now_ist()
    mine = await run_in_threadpool(store.checks_recent, user.get("username"), limit)
    everyone = await run_in_threadpool(store.checks_since, now - timedelta(days=365))
    await run_in_threadpool(_refresh_outcomes, store, [r for r in everyone if not r.get("outcome_done") or
                                                     (r.get("paper") and not r.get("paper_closed_at"))], now)
    by_id = {r["id"]: r for r in everyone}
    mine = [by_id.get(r["id"], r) for r in mine]
    return {"checks": [_row_json(r) for r in mine], "record": outcomes.record(everyone)}


@router.get("/api/options/checks/paper")
async def paper_checks(user: dict = Depends(current_user), store: Store = Depends(get_store)) -> dict:
    """Paper trades followed from Option Check (yours; an admin sees everyone's)."""
    rows = await run_in_threadpool(store.checks_recent, None if user["role"] == "admin" else user.get("username"), 200)
    rows = [r for r in rows if r.get("paper")]
    await run_in_threadpool(_refresh_outcomes, store, rows, now_ist())
    return {"trades": [_row_json(r) for r in rows]}


@router.post("/api/options/check/{check_id}/paper")
async def follow_paper(check_id: str, user: dict = Depends(current_user), store: Store = Depends(get_store)) -> dict:
    row = _owned(await run_in_threadpool(store.check_get, check_id), user)
    summ = row.get("summary") or {}
    if row["status"] != "done" or not summ.get("entry") or not summ.get("units"):
        raise HTTPException(409, {"code": "not_priced", "message": "This check has no price to follow."})
    if row.get("paper"):
        return {"paper": _paper_json(row)}
    await run_in_threadpool(store.check_update, check_id, paper=1, paper_entry=summ["entry"],
                            paper_units=summ["lots"] * row["lot_size"] if summ.get("lots") else summ["units"])
    return {"paper": _paper_json(await run_in_threadpool(store.check_get, check_id))}


def _current_bid(store: Store, row: dict) -> tuple[float | None, str]:
    snap = store.live_snapshot() or {}
    for item in snap.get("items", []):
        if item.get("symbol") == row.get("symbol") and (item.get("bid") or item.get("ltp")):
            return float(item.get("bid") or item["ltp"]), "live " + ("bid" if item.get("bid") else "price")
    last = store.latest_bar(row["token"]) if row.get("token") else None
    if last:
        return float(last.get("bid") or last["close"]), "last recorded minute"
    return None, ""


@router.post("/api/options/check/{check_id}/paper/close")
async def close_paper(check_id: str, user: dict = Depends(current_user), store: Store = Depends(get_store)) -> dict:
    row = _owned(await run_in_threadpool(store.check_get, check_id), user)
    if not row.get("paper") or row.get("paper_closed_at"):
        raise HTTPException(409, {"code": "not_open", "message": "No open paper trade on this check."})
    price, src = await run_in_threadpool(_current_bid, store, row)
    if price is None:
        raise HTTPException(409, {"code": "no_price", "message": "No price to close at right now."})
    await run_in_threadpool(store.check_update, check_id, paper_exit=price, paper_closed_at=now_ist())
    out = _paper_json(await run_in_threadpool(store.check_get, check_id))
    return {"paper": {**out, "closed_with": src}}


# ── Warm caches so the first check of the day is instant ──────────────────────

_warmed: dict[str, date] = {}


def warm(store: Store, cfg: OptionsSettings) -> None:
    """Load the contract list and the two-year history once a day, off the request path."""
    today = now_ist().date()
    if _warmed.get("day") == today:
        return
    _warmed["day"] = today
    try:
        refs, vix, _ = _refs(store, cfg, now_ist())
        for index in refs:
            _history(store, refs, vix, index)
    except Exception:
        logger.info("Option Check warm-up skipped (no saved data yet)")


def start_warmer(store_fn, cfg_fn) -> threading.Event:
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                warm(store_fn(), cfg_fn())
            except Exception:
                logger.exception("Option Check warm-up failed")
            stop.wait(600)
    threading.Thread(target=loop, name="check-warm", daemon=True).start()
    return stop

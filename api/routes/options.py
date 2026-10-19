"""Options tool endpoints: Kite login flow and recorder status.

/kite/login and /kite/callback sit outside /api because the callback URL is registered
in the Kite developer console (plan Appendix A).
"""

import threading
import time as clock
from datetime import datetime, time, timedelta
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from api.deps import current_user, get_calendar, get_cfg, get_store
from api.live import LiveHub, stream as live_stream, with_market
from options.config import OptionsSettings
from options.core.calendar import NseCalendar, at_ist, now_ist
from options.core.schemas import OPEN_STATES, Signal
from options.engine import confidence, controls, performance, statistics
from options.notify import make_notifier
from options.notify.base import Notifier
from options.setups import SETUP_LABELS
from options.storage import Store
from utils.logger import setup_logger

logger = setup_logger("options.api")
router = APIRouter(tags=["options"])


def get_notifier(cfg: OptionsSettings = Depends(get_cfg)) -> Notifier:
    return make_notifier(cfg)


def get_broker(cfg: OptionsSettings = Depends(get_cfg)):
    if not (cfg.KITE_API_KEY and cfg.KITE_API_SECRET):
        raise HTTPException(503, "Kite Connect is not configured: add its keys on the Connectors page.")
    from options.brokers.kite import KiteBroker
    return KiteBroker(cfg.KITE_API_KEY, cfg.KITE_API_SECRET)


def get_allowed_user(cfg: OptionsSettings = Depends(get_cfg)) -> str:
    return cfg.KITE_USER_ID


def _page(title: str, message: str, ok: bool) -> str:
    accent = "#22c55e" if ok else "#ef4444"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>
  body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0f17;color:#e5e7eb;
       font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
  .card{{max-width:420px;margin:16px;padding:32px;border-radius:16px;background:#111827;
         border:1px solid #1f2937;box-shadow:0 20px 60px rgba(0,0,0,.45);text-align:center}}
  .dot{{width:56px;height:56px;margin:0 auto 18px;border-radius:50%;display:grid;place-items:center;
        background:{accent}22;color:{accent};font-size:28px;font-weight:700}}
  h1{{margin:0 0 8px;font-size:20px}} p{{margin:0;color:#9ca3af;line-height:1.5}}
</style></head><body><div class="card"><div class="dot">{"✓" if ok else "!"}</div>
<h1>{escape(title)}</h1><p>{escape(message)}</p></div></body></html>"""


@router.get("/kite/login")
def kite_login(broker=Depends(get_broker)) -> RedirectResponse:
    return RedirectResponse(broker.login_url())


@router.get("/kite/callback", response_class=HTMLResponse)
def kite_callback(request_token: str | None = None, status: str | None = None,
                  broker=Depends(get_broker), store: Store = Depends(get_store),
                  notifier: Notifier = Depends(get_notifier),
                  allowed_user: str = Depends(get_allowed_user)) -> HTMLResponse:
    if status != "success" or not request_token:
        return HTMLResponse(_page("Login not completed", "Zerodha did not confirm the login. "
                                  "Open the login link from Telegram or the Connectors page and try again.", ok=False), 400)
    try:
        access_token, user_id = broker.create_session(request_token)
    except Exception as e:
        logger.warning("Kite session exchange failed: %s", type(e).__name__)
        return HTMLResponse(_page("Login failed", "Kite rejected the login request. It may have "
                                  "expired; please log in again.", ok=False), 502)

    if allowed_user and (user_id or "").upper() != allowed_user.upper():
        logger.warning("Rejected Kite login from an account other than KITE_USER_ID")
        return HTMLResponse(_page("Wrong account", "This Zerodha account isn't the one configured "
                                  "for this tool.", ok=False), 403)

    now = now_ist()
    store.save_access_token(now.date(), access_token, user_id, now)
    notifier.send(f"✅ <b>Kite connected</b> for {now:%d %b %Y}. Recording runs 09:15–15:30.")
    return HTMLResponse(_page("Kite connected", "Today's session is saved. You can close this tab.", ok=True))


@router.get("/api/time")
def server_time() -> dict:
    """Public and tiny: the dashboard's clock syncs to this, so a phone with a drifting clock still shows exchange time."""
    return {"epoch_ms": int(clock.time() * 1000), "ist": now_ist().isoformat(timespec="seconds")}


@router.get("/api/options/status", dependencies=[Depends(current_user)])
def options_status(store: Store = Depends(get_store), settings: OptionsSettings = Depends(get_cfg),
                   cal: NseCalendar = Depends(get_calendar)) -> dict:
    now = now_ist()
    today = now.date()
    trading_day = cal.is_trading_day(today)
    last_bar = store.last_bar_ts()
    session_day = today if trading_day and now.time() < time(15, 30) else cal.next_trading_day(today)
    return {
        "now_ist": now.isoformat(timespec="seconds"),
        "trading_day": trading_day,
        "next_trading_day": (today if trading_day and now.time() < time(15, 30)
                             else cal.next_trading_day(today)).isoformat(),
        "session_phase": cal.session_phase(now),
        "market_opens_at": at_ist(session_day, time(9, 15)).isoformat(),
        "market_closes_at": at_ist(session_day, time(15, 30)).isoformat(),
        "indices": settings.OPTIONS_INDICES,
        "data_provider": settings.provider,
        "data_provider_name": settings.provider_name,
        "data_configured": not settings.missing_provider_keys(),
        "data_connected_today": store.load_access_token(today) is not None,
        "data_needs_manual_login": settings.provider == "kite",
        "kite_configured": bool(settings.KITE_API_KEY and settings.KITE_API_SECRET),
        "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
        "kite_connected_today": store.load_access_token(today) is not None,
        "bars_today": store.count_bars_since(at_ist(today, time(0, 0))),
        "last_bar_at": last_bar.isoformat() if last_bar else None,
        "risk": {
            "capital": settings.OPTIONS_CAPITAL,
            "risk_per_trade_pct": settings.OPTIONS_RISK_PER_TRADE_PCT,
            "daily_loss_stop_pct": settings.OPTIONS_DAILY_LOSS_STOP_PCT,
        },
        "signals_paused": _paused(store),
    }


def _paused(store: Store) -> dict | None:
    """Everyone sees when new signals are paused (who and why), not just admins."""
    state = controls.read(store)
    if not state.get("paused"):
        return None
    return {"by": state.get("paused_by"), "at": state.get("paused_at"), "reason": state.get("reason") or None}


# ── Dashboard data ───────────────────────────────────────────────────────────

_bands_cache: dict[int, tuple[float, dict]] = {}
_bands_lock = threading.Lock()
BANDS_TTL_S = 60


def _bands(store: Store) -> dict[str, dict]:
    """Track record per grade, recomputed at most once a minute (the signals list is polled every 5 s)."""
    with _bands_lock:
        hit = _bands_cache.get(id(store.engine))
        if hit and clock.monotonic() - hit[0] < BANDS_TTL_S:
            return hit[1]
    bands = confidence.band_stats(store.signals_since(now_ist() - timedelta(days=3650)))
    with _bands_lock:
        _bands_cache[id(store.engine)] = (clock.monotonic(), bands)
    return bands


def _signal_json(sig: Signal, bands: dict[str, dict] | None = None) -> dict:
    out = sig.model_dump(mode="json")
    out["confidence"] = confidence.with_band(confidence.breakdown(sig), bands or {})
    return out


# ── Live NIFTY 50 / SENSEX (pushed; see api/live.py) ────────────────────────

_live_hub: LiveHub | None = None


def live_hub() -> LiveHub:
    global _live_hub
    if _live_hub is None:
        _live_hub = LiveHub(get_store)
    return _live_hub


def stop_live_hub() -> None:
    if _live_hub is not None:
        _live_hub.stop()


@router.get("/api/options/live/indices", dependencies=[Depends(current_user)])
def live_indices(store: Store = Depends(get_store), cal: NseCalendar = Depends(get_calendar)) -> dict:
    """The latest levels at once (first paint, and the fallback while a stream reconnects)."""
    return with_market(store.live_snapshot(), cal)


@router.get("/api/options/live/indices/stream", dependencies=[Depends(current_user)])
async def live_indices_stream(request: Request, cal: NseCalendar = Depends(get_calendar)) -> StreamingResponse:
    """Server-sent events: `levels` with every update (≤ 4 a second), `ping` every 15 s when quiet."""
    return StreamingResponse(live_stream(live_hub(), lambda: cal, request.is_disconnected),
                             media_type="text/event-stream",
                             # no-transform: proxies (and Next's gzip) must not compress, which holds small events back
                             headers={"Cache-Control": "no-cache, no-store, no-transform", "X-Accel-Buffering": "no"})


@router.get("/api/options/board", dependencies=[Depends(current_user)])
def options_board(store: Store = Depends(get_store), settings: OptionsSettings = Depends(get_cfg)) -> dict:
    boards = {i: b for i in settings.OPTIONS_INDICES if (b := store.load_board(i))}
    return {"boards": boards, "now_ist": now_ist().isoformat(timespec="seconds")}


@router.get("/api/options/signals", dependencies=[Depends(current_user)])
def options_signals(days: int = Query(7, ge=1, le=3650), store: Store = Depends(get_store)) -> dict:
    today = now_ist().date()
    found = {s.signal_id: s for s in store.signals_since(at_ist(today - timedelta(days=days - 1), time(0, 0)))}
    for s in store.open_signals():                 # positional signals opened before the window
        found.setdefault(s.signal_id, s)
    ordered = sorted(found.values(), key=lambda s: s.created_at, reverse=True)
    quotes = {}
    for s in ordered:
        if s.state in OPEN_STATES and (bar := store.latest_bar(s.contract.token)):
            quotes[s.signal_id] = {"ts": bar["ts"].isoformat(), "ltp": bar["close"], "bid": bar["bid"],
                                   "ask": bar["ask"]}
    bands = _bands(store) if ordered else {}
    return {"signals": [_signal_json(s, bands) for s in ordered], "quotes": quotes, "setup_labels": SETUP_LABELS}


@router.get("/api/options/signals/{signal_id}", dependencies=[Depends(current_user)])
def options_signal(signal_id: str, store: Store = Depends(get_store)) -> dict:
    sig = store.get_signal(signal_id)
    if sig is None:
        raise HTTPException(404, "Signal not found")
    events = [{**e, "ts": e["ts"].isoformat() if e.get("ts") else None} for e in store.signal_history(signal_id)]
    return {"signal": _signal_json(sig, _bands(store)), "events": events,
            "setup_label": SETUP_LABELS.get(sig.setup, sig.setup)}


_stats_cache: dict[int, tuple[float, dict]] = {}
STATS_TTL_S = 60


def _benchmark(store: Store, first: datetime | None, last: datetime | None) -> dict | None:
    """NIFTY buy-and-hold over the same span as the track record, for comparison."""
    if not first or not last:
        return None
    token = store.latest_token("NIFTY 50")
    if token is None:
        return None
    start, end = store.close_near(token, first, before=True) or store.close_near(token, first, before=False), \
        store.close_near(token, last, before=True)
    if not start or not end:
        return None
    return {"index": "NIFTY 50", "from": first.isoformat(), "to": last.isoformat(), "start": start, "end": end,
            "return_pct": (end / start - 1) * 100}


def _statistics(store: Store, everything: list[Signal], capital: float, cal: NseCalendar) -> dict:
    """Uncertainty, risk-adjusted returns, a benchmark and calibration, recomputed at most once a minute."""
    key = id(store.engine)
    with _bands_lock:
        hit = _stats_cache.get(key)
        if hit and clock.monotonic() - hit[0] < STATS_TTL_S:
            return hit[1]
    done = sorted(performance.traded(everything), key=lambda s: s.closed_at)
    first, last = (done[0].created_at, done[-1].closed_at) if done else (None, None)
    days: list = []
    if first:
        d, end = first.date(), max(last.date(), now_ist().date())
        while d <= end:
            if cal.is_trading_day(d):
                days.append(d)
            d += timedelta(days=1)
    out = {
        "overall": statistics.record_stats(everything),
        "by_setup": statistics.setup_report(everything),
        "account": statistics.account_stats(everything, capital, days),
        "benchmark": _benchmark(store, first, last),
        "calibration": statistics.calibration(everything),
    }
    with _bands_lock:
        _stats_cache[key] = (clock.monotonic(), out)
    return out


@router.get("/api/options/performance", dependencies=[Depends(current_user)])
def options_performance(store: Store = Depends(get_store), settings: OptionsSettings = Depends(get_cfg),
                        cal: NseCalendar = Depends(get_calendar)) -> dict:
    everything = store.signals_since(now_ist() - timedelta(days=3650))
    done = sorted(performance.traded(everything), key=lambda s: s.closed_at)
    equity, curve = 0.0, []
    for s in done:
        equity += s.pnl_rupees
        curve.append({"t": s.closed_at.isoformat(), "equity": round(equity, 2), "pnl": s.pnl_rupees,
                      "id": s.signal_id, "mode": s.mode})
    return {
        "overall": performance.stats(everything),
        "by_setup": performance.by(everything, "setup"),
        "by_grade": performance.by(everything, "grade"),
        "by_mode": performance.by(everything, "mode"),
        "by_horizon": performance.by(everything, "horizon"),
        "equity": curve,
        "r_values": [s.r_multiple for s in done if s.r_multiple is not None],
        "counts": {"signals": len(everything), "traded": len(done),
                   "expired": sum(s.exit_reason == "EXPIRED" for s in everything),
                   "cancelled": sum(s.state.value == "CANCELLED" for s in everything)},
        "setup_labels": SETUP_LABELS,
        "capital": settings.OPTIONS_CAPITAL,
        "statistics": _statistics(store, everything, settings.OPTIONS_CAPITAL, cal),
    }


@router.get("/api/options/backtest", dependencies=[Depends(current_user)])
def options_backtest(store: Store = Depends(get_store)) -> dict:
    """The last proxy backtest saved with `python -m options.backtest.proxy run … --save`, if any."""
    return {"report": store.get_meta_json("backtest_report")}


@router.get("/api/options/evaluations", dependencies=[Depends(current_user)])
def options_evaluations(hours: int = Query(8, ge=1, le=24 * 30), store: Store = Depends(get_store)) -> dict:
    rows = store.evaluations_since(now_ist() - timedelta(hours=hours))
    return {"evaluations": [{**r, "ts": r["ts"].isoformat()} for r in rows], "setup_labels": SETUP_LABELS}

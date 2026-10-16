"""Options tool endpoints: Kite login flow and recorder status.

/kite/login and /kite/callback sit outside /api because the callback URL is registered
in the Kite developer console (plan Appendix A).
"""

import secrets
from datetime import time, timedelta
from functools import lru_cache
from html import escape

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from options.config import settings
from options.core.calendar import NseCalendar, at_ist, now_ist
from options.core.schemas import OPEN_STATES, Signal
from options.engine import performance
from options.notify import make_notifier
from options.notify.base import Notifier
from options.setups import SETUP_LABELS
from options.storage import Store, make_engine
from utils.logger import setup_logger

logger = setup_logger("options.api")
router = APIRouter(tags=["options"])


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(make_engine(settings.DATABASE_URL))


@lru_cache(maxsize=1)
def get_notifier() -> Notifier:
    return make_notifier(settings)


def get_broker():
    if not (settings.KITE_API_KEY and settings.KITE_API_SECRET):
        raise HTTPException(503, "Kite Connect is not configured: set KITE_API_KEY and KITE_API_SECRET.")
    from options.brokers.kite import KiteBroker
    return KiteBroker(settings.KITE_API_KEY, settings.KITE_API_SECRET)


def get_allowed_user() -> str:
    return settings.KITE_USER_ID


def get_dashboard_token() -> str:
    return settings.DASHBOARD_TOKEN


def require_dashboard(authorization: str | None = Header(None), token: str = Depends(get_dashboard_token)) -> None:
    if not token:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(401, "Dashboard login required")


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
                                  "Open the login link from Telegram and try again.", ok=False), 400)
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


@router.get("/api/options/status", dependencies=[Depends(require_dashboard)])
def options_status(store: Store = Depends(get_store)) -> dict:
    now = now_ist()
    cal = NseCalendar()
    today = now.date()
    trading_day = cal.is_trading_day(today)
    last_bar = store.last_bar_ts()
    return {
        "now_ist": now.isoformat(timespec="seconds"),
        "trading_day": trading_day,
        "next_trading_day": (today if trading_day and now.time() < time(15, 30)
                             else cal.next_trading_day(today)).isoformat(),
        "session_phase": cal.session_phase(now),
        "indices": settings.OPTIONS_INDICES,
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
    }


# ── Dashboard data ───────────────────────────────────────────────────────────

def _signal_json(sig: Signal) -> dict:
    return sig.model_dump(mode="json")


@router.get("/api/options/board", dependencies=[Depends(require_dashboard)])
def options_board(store: Store = Depends(get_store)) -> dict:
    boards = {i: b for i in settings.OPTIONS_INDICES if (b := store.load_board(i))}
    return {"boards": boards, "now_ist": now_ist().isoformat(timespec="seconds")}


@router.get("/api/options/signals", dependencies=[Depends(require_dashboard)])
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
    return {"signals": [_signal_json(s) for s in ordered], "quotes": quotes, "setup_labels": SETUP_LABELS}


@router.get("/api/options/signals/{signal_id}", dependencies=[Depends(require_dashboard)])
def options_signal(signal_id: str, store: Store = Depends(get_store)) -> dict:
    sig = store.get_signal(signal_id)
    if sig is None:
        raise HTTPException(404, "Signal not found")
    events = [{**e, "ts": e["ts"].isoformat() if e.get("ts") else None} for e in store.signal_history(signal_id)]
    return {"signal": _signal_json(sig), "events": events, "setup_label": SETUP_LABELS.get(sig.setup, sig.setup)}


@router.get("/api/options/performance", dependencies=[Depends(require_dashboard)])
def options_performance(store: Store = Depends(get_store)) -> dict:
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
    }


@router.get("/api/options/evaluations", dependencies=[Depends(require_dashboard)])
def options_evaluations(hours: int = Query(8, ge=1, le=24 * 30), store: Store = Depends(get_store)) -> dict:
    rows = store.evaluations_since(now_ist() - timedelta(hours=hours))
    return {"evaluations": [{**r, "ts": r["ts"].isoformat()} for r in rows], "setup_labels": SETUP_LABELS}

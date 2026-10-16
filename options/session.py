"""One trading day: wait for the Kite login, load contracts, record the market, report.

Railway runs this as a cron service at 08:30 IST on weekdays (railway.recorder.json); it
exits after the close, so every day starts with a fresh process and WebSocket.

    python -m options.session
"""

import sys
import time as _time
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Callable

import pandas as pd

from options.agents.context import Constituent
from options.agents.macro import MacroFetcher
from options.config import OptionsSettings, settings as default_settings
from options.core.calendar import IST, NseCalendar, at_ist, now_ist
from options.core.constituents import HEAVYWEIGHTS
from options.engine.engine import SignalEngine
from options.engine.state import MarketState
from options.market_data.recorder import Recorder
from options.notify import make_notifier
from options.notify.base import Notifier
from options.reference import (INDEX_SPOT_SYMBOLS, VIX_SYMBOL, IndexReference, build_reference,
                               find_token, index_rows)
from options.storage import Store, make_engine
from utils.logger import setup_logger

logger = setup_logger("options.session")

LOGIN_REMINDERS = (time(9, 5), time(9, 20))
LOGIN_DEADLINE = time(15, 0)
RECORD_UNTIL = time(15, 31)
MAX_LOGIN_ATTEMPTS = 3


def wait_for_login(store: Store, notifier: Notifier, login_url: str, today: date,
                   now_fn: Callable[[], datetime], sleep: Callable[[float], None],
                   reject: str | None = None, poll_s: float = 15) -> str | None:
    """Return today's access token, prompting on Telegram until one arrives or the deadline.

    `reject` is a token already found invalid; a token equal to it is not accepted again.
    """
    token = store.load_access_token(today)
    if token and token != reject:
        return token

    button = [("Login to Kite", login_url)]
    notifier.send("🌅 <b>Good morning!</b> Log in to Kite to start today's NIFTY session.", button)
    reminders = [at_ist(today, t) for t in LOGIN_REMINDERS if at_ist(today, t) > now_fn()]
    deadline = at_ist(today, LOGIN_DEADLINE)

    while now_fn() < deadline:
        sleep(poll_s)
        token = store.load_access_token(today)
        if token and token != reject:
            return token
        if reminders and now_fn() >= reminders[0]:
            reminders.pop(0)
            notifier.send("⏰ Still waiting for your Kite login. No data is being recorded yet.", button)
    return None


def format_contracts(ref: IndexReference) -> str:
    expiries = ", ".join(f"{e:%d %b}" for e in ref.expiries[:3])
    return (f"<b>{escape(ref.index)}</b>: lot {ref.lot_size}, strike step {ref.strike_step:g}, "
            f"expiries {expiries}, future {escape(ref.future_symbol)}")


def format_summary(today: date, s: dict) -> str:
    health = "✅" if s["disconnects"] == 0 and s["stale_alerts"] == 0 and s["bars_unsaved"] == 0 else "⚠️"
    return (f"📊 <b>Recording summary · {today:%d %b %Y}</b> {health}\n"
            f"Bars saved: {s['bars_written']:,} · Instruments: {s['instruments']}\n"
            f"Ticks: {s['ticks']:,} · Late ticks: {s['late_ticks']}\n"
            f"Disconnects: {s['disconnects']} · Data gaps: {s['stale_alerts']}"
            + (f"\n🔴 Unsaved bars: {s['bars_unsaved']:,}" if s["bars_unsaved"] else ""))


def run(cfg: OptionsSettings = default_settings, *, now_fn: Callable[[], datetime] = now_ist,
        sleep: Callable[[float], None] = _time.sleep, store: Store | None = None,
        notifier: Notifier | None = None, broker=None, calendar: NseCalendar | None = None) -> int:
    calendar = calendar or NseCalendar()
    today = now_fn().astimezone(IST).date()
    if not calendar.is_trading_day(today):
        logger.info("%s is not a trading day; nothing to do", today)
        return 0

    notifier = notifier or make_notifier(cfg)
    if broker is None:
        if not (cfg.KITE_API_KEY and cfg.KITE_API_SECRET):
            notifier.send("⚠️ KITE_API_KEY / KITE_API_SECRET are not set, so today's session can't start.")
            return 2
        from options.brokers.kite import KiteBroker
        broker = KiteBroker(cfg.KITE_API_KEY, cfg.KITE_API_SECRET)
    store = store or Store(make_engine(cfg.DATABASE_URL))

    # Log in, and make sure the token actually works before relying on it
    rejected = None
    for _ in range(MAX_LOGIN_ATTEMPTS):
        token = wait_for_login(store, notifier, broker.login_url(), today, now_fn, sleep, reject=rejected)
        if token is None:
            notifier.send("🔴 No Kite login by 15:00, so nothing was recorded today.")
            return 1
        broker.set_access_token(token)
        try:
            broker.profile()
            break
        except Exception as e:
            logger.warning("Saved Kite token rejected: %s", type(e).__name__)
            rejected = token
    else:
        notifier.send("🔴 Kite kept rejecting the login, so nothing was recorded today.")
        return 1

    # Contracts for today, straight from the instrument dump
    nse, nfo = broker.instruments("NSE"), broker.instruments("NFO")
    symbols = [INDEX_SPOT_SYMBOLS[i] for i in cfg.OPTIONS_INDICES]
    levels = broker.index_prices(symbols)
    prices = {i: levels[INDEX_SPOT_SYMBOLS[i]] for i in cfg.OPTIONS_INDICES}
    refs = [build_reference(i, nse, nfo, today, prices[i]) for i in cfg.OPTIONS_INDICES]

    heavy = {sym for i in cfg.OPTIONS_INDICES for sym, _ in HEAVYWEIGHTS.get(i, [])}
    snapshot = [r for r in nse if (r.get("segment") == "INDICES" and r["tradingsymbol"] in {*symbols, VIX_SYMBOL})
                or (r.get("segment") == "NSE" and r["tradingsymbol"] in heavy)]     # lets replays rebuild breadth
    for i in cfg.OPTIONS_INDICES:
        snapshot += index_rows(nfo, i, today)
    store.save_instruments(today, snapshot)

    vix_token = find_token(nse, VIX_SYMBOL)
    state = MarketState(today)
    vix_history = load_history(broker, refs, vix_token, state, calendar, now_fn(), pause=sleep)
    constituents = load_constituents(broker, nse, cfg.OPTIONS_INDICES)
    macro = MacroFetcher(now_fn=now_fn)
    macro.start()

    engine_tokens = {c.token for cs in constituents.values() for c in cs}
    open_signals = store.open_signals()
    engine_tokens |= {s.contract.token for s in open_signals}
    recorder = Recorder(broker.ticker(), refs, store, notifier, vix_token=vix_token,
                        window=cfg.OPTIONS_STRIKE_WINDOW, n_expiries=cfg.OPTIONS_EXPIRIES_TRACKED,
                        stale_after_s=cfg.OPTIONS_STALE_AFTER_S, calendar=calendar, now_fn=now_fn,
                        extra_tokens=engine_tokens)
    engine = SignalEngine({r.index: r for r in refs}, state, store, notifier, cfg, calendar, vix_token=vix_token,
                          constituents=constituents, vix_history=vix_history, macro=macro.snapshot,
                          quote_fn=recorder.agg.quote, now_fn=now_fn)
    recorder.on_bars, recorder.on_tick = engine.on_bars, engine.on_tick

    recorder.start(prices)
    notifier.send("📡 <b>Recording started</b>\n" + "\n".join(format_contracts(r) for r in refs)
                  + f"\nTracking {len(recorder.subscribed)} instruments"
                  + (f" · {len(open_signals)} open signal(s) carried over" if open_signals else ""))
    try:
        notifier.send(engine.morning_brief(now_fn()))
    except Exception:
        logger.exception("Morning brief failed")

    recorder.run_until(at_ist(today, RECORD_UNTIL), sleep=sleep)
    macro.stop()
    try:
        engine.close_session(now_fn())
    except Exception:
        logger.exception("Closing intraday signals failed")
    summary = recorder.summary()
    store.log_event("session_summary", str(summary), now_fn())
    try:
        notifier.send(engine.end_of_day(now_fn()))
    except Exception:
        logger.exception("End-of-day report failed")
    notifier.send(format_summary(today, summary))
    return 0


HISTORY_SESSIONS = 10        # 1m history: enough for EMA50 on 60m bars and 3 days of swings
DAILY_DAYS = 400             # ~1 year of daily candles for VIX percentile, RV20 and P1 trends


def load_history(broker, refs: list[IndexReference], vix_token: int, state: MarketState,
                 calendar: NseCalendar, now: datetime, pause: Callable[[float], None] = _time.sleep) -> list[float]:
    """Warm the market state from Kite historical data; returns VIX daily closes (~1y).

    Failures are logged, not fatal: without history the agents report "warming up" and the
    engine sends no signals until enough live data has built up.
    """
    start = now.date()
    for _ in range(HISTORY_SESSIONS):
        start = calendar.previous_trading_day(start)
    since, daily_since = at_ist(start, time(9, 15)), now - timedelta(days=DAILY_DAYS)
    jobs = []
    for ref in refs:
        jobs += [(ref.spot_token, "minute", False, since), (ref.future_token, "minute", True, since),
                 (ref.spot_token, "day", False, daily_since)]
    jobs += [(vix_token, "minute", False, since), (vix_token, "day", False, daily_since)]

    vix_closes: list[float] = []
    for token, interval, oi, frm in jobs:
        try:
            candles = broker.historical(token, frm, now, interval, oi=oi)
        except Exception as e:
            logger.warning("History for %s (%s) failed: %s", token, interval, type(e).__name__)
            continue
        if interval == "day":
            state.load_daily(token, candles)
            if token == vix_token:
                vix_closes = [float(c["close"]) for c in candles if pd.Timestamp(c["date"]).date() < now.date()]
        else:
            state.load_history(token, [c for c in candles if pd.Timestamp(c["date"]) < pd.Timestamp(now).floor("min")])
        pause(0.4)              # Kite allows ~3 historical requests per second
    return vix_closes


def load_constituents(broker, nse_rows: list[dict], indices: list[str]) -> dict[str, list[Constituent]]:
    out: dict[str, list[Constituent]] = {}
    tokens = {r["tradingsymbol"]: int(r["instrument_token"]) for r in nse_rows if r.get("segment") == "NSE"}
    for index in indices:
        listed = [(sym, w) for sym, w in HEAVYWEIGHTS.get(index, []) if sym in tokens]
        try:
            closes = broker.previous_closes([sym for sym, _ in listed])
        except Exception as e:
            logger.warning("Previous closes failed: %s", type(e).__name__)
            closes = {}
        out[index] = [Constituent(sym, w, tokens[sym], closes.get(sym)) for sym, w in listed]
    return out


def main() -> int:
    try:
        return run()
    except Exception as e:
        logger.exception("Session crashed")
        make_notifier(default_settings).send(f"🔴 <b>Session crashed</b>: {escape(type(e).__name__)}. "
                                             "Check the recorder logs on Railway.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""One trading day: log in to the data provider, load contracts, record the market, report.

Angel One logs in by itself (MPIN + TOTP). Kite needs the person's daily login, prompted on
Telegram.

options.daemon starts this in a fresh process at 08:30 IST on each trading day; it exits
after the close, so every day starts with a fresh process and WebSocket.

    python -m options.session
"""

import sys
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Callable

import pandas as pd

from options.agents.context import Constituent
from options.agents.macro import MacroFetcher
from options.agents.news_feed import NewsFetcher
from options.config import OptionsSettings, settings as default_settings
from options.core.calendar import IST, MARKET_CLOSE, MARKET_OPEN, NseCalendar, at_ist, now_ist
from options.core.constituents import HEAVYWEIGHTS
from options.daemon import EXIT_CONFIG, EXIT_FAILED, EXIT_LOGIN, EXIT_OK
from options.engine.engine import SignalEngine
from options.engine.state import MarketState
from options.market_data.recorder import Recorder
from options.notify import OutboxNotifier, make_notifier, make_outbox
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
AUTO_LOGIN_RETRY_S = (30, 60, 120, 300, 600)    # waits between automatic login attempts
LOG_RETENTION = timedelta(days=90)              # delivered alerts and session events
ALERT_DRAIN_S = 90                              # wait this long for the last alerts before exiting


def auto_login(broker, store: Store, notifier: Notifier, today: date, now_fn: Callable[[], datetime],
               sleep: Callable[[float], None]) -> bool:
    """Log in without the person (Angel One), retrying with backoff until the deadline."""
    deadline = at_ist(today, LOGIN_DEADLINE)
    reason = "no attempt made"
    for attempt, wait in enumerate((0, *AUTO_LOGIN_RETRY_S), start=1):
        if wait:
            if now_fn() + timedelta(seconds=wait) >= deadline:
                break
            sleep(wait)
        try:
            user_id = broker.login()
        except Exception as e:
            reason = str(e)[:200] or type(e).__name__
            logger.warning("%s login attempt %d failed: %s", broker.name, attempt, reason)
            if attempt == 2:
                notifier.send(f"⚠️ {escape(broker.name)} login failed ({escape(reason)}). Retrying.")
            continue
        store.save_access_token(today, "auto-login", user_id, now_fn())   # marks the day as connected
        return True
    notifier.send(f"🔴 <b>{escape(broker.name)} login failed</b>: {escape(reason)}. "
                  "Nothing is being recorded today. Check Angel One on the Connectors page.")
    return False


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
    gaps = [c for c in s.get("coverage", []) if c["recorded"] < c["expected"] * 0.995]
    health = ("✅" if s["disconnects"] == 0 and s["stale_alerts"] == 0 and s["bars_unsaved"] == 0
              and s.get("rejected_ticks", 0) == 0 and not gaps else "⚠️")
    coverage = " · ".join(f"{c['label']} {c['recorded']}/{c['expected']}" for c in s.get("coverage", []))
    return (f"📊 <b>Recording summary · {today:%d %b %Y}</b> {health}\n"
            f"Bars saved: {s['bars_written']:,} · Instruments: {s['instruments']}\n"
            f"Ticks: {s['ticks']:,} · Late ticks: {s['late_ticks']}"
            + (f" · Bad ticks rejected: {s['rejected_ticks']}" if s.get("rejected_ticks") else "") + "\n"
            f"Disconnects: {s['disconnects']} · Data gaps: {s['stale_alerts']}"
            + (f"\nMinutes recorded: {escape(coverage)}" if coverage else "")
            + (f"\n🔴 Unsaved bars: {s['bars_unsaved']:,}" if s["bars_unsaved"] else ""))


def coverage(store: Store, refs: list[IndexReference], vix_token: int | None, today: date,
             started_at: datetime | None) -> list[dict]:
    """Minutes recorded today for the series every signal depends on, against the minutes expected."""
    first = max(at_ist(today, MARKET_OPEN), (started_at or at_ist(today, MARKET_OPEN)).replace(second=0, microsecond=0))
    expected = max(0, int((at_ist(today, MARKET_CLOSE) - first).total_seconds() // 60))
    counts = store.bar_counts_between(at_ist(today, MARKET_OPEN), at_ist(today, MARKET_CLOSE))
    series = [(f"{r.index} fut", r.future_token) for r in refs] + [(f"{r.index} spot", r.spot_token) for r in refs]
    if vix_token:
        series.append(("VIX", vix_token))
    return [{"label": label, "token": token, "recorded": counts.get(token, 0), "expected": expected}
            for label, token in series]


def run(cfg: OptionsSettings = default_settings, *, now_fn: Callable[[], datetime] = now_ist,
        sleep: Callable[[float], None] = _time.sleep, store: Store | None = None,
        notifier: Notifier | None = None, broker=None, calendar: NseCalendar | None = None) -> int:
    store = store or Store(make_engine(cfg.DATABASE_URL))
    calendar = calendar or load_calendar(store)
    today = now_fn().astimezone(IST).date()
    if not calendar.is_trading_day(today):
        logger.info("%s is not a trading day; nothing to do", today)
        return EXIT_OK

    own_outbox = notifier is None
    notifier = notifier or make_outbox(cfg, store)          # alerts never block the engine
    try:
        return _run(cfg, now_fn, sleep, store, notifier, broker, calendar, today)
    finally:
        if own_outbox and isinstance(notifier, OutboxNotifier):
            if not notifier.close(ALERT_DRAIN_S):
                logger.error("Some alerts were still undelivered at exit; they stay queued in the database")


def _run(cfg: OptionsSettings, now_fn, sleep, store: Store, notifier: Notifier, broker,
         calendar: NseCalendar, today: date) -> int:
    if broker is None:
        missing = cfg.missing_provider_keys()
        if missing:
            notifier.send(f"⚠️ {' / '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set, "
                          "so today's session can't start. Add them on the Connectors page.")
            return EXIT_CONFIG
        from options.brokers import make_broker
        broker = make_broker(cfg)

    if getattr(broker, "auto_login", False):
        if not auto_login(broker, store, notifier, today, now_fn, sleep):
            return EXIT_LOGIN
    else:
        # Kite: wait for the person's login, and make sure the token works before relying on it
        rejected = None
        for _ in range(MAX_LOGIN_ATTEMPTS):
            token = wait_for_login(store, notifier, broker.login_url(), today, now_fn, sleep, reject=rejected)
            if token is None:
                notifier.send("🔴 No Kite login by 15:00, so nothing was recorded today.")
                return EXIT_LOGIN
            broker.set_access_token(token)
            try:
                broker.profile()
                break
            except Exception as e:
                logger.warning("Saved Kite token rejected: %s", type(e).__name__)
                rejected = token
        else:
            notifier.send("🔴 Kite kept rejecting the login, so nothing was recorded today.")
            return EXIT_LOGIN

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
    history = load_history(broker, refs, vix_token, state, calendar, now_fn(), pause=sleep, store=store)
    if history.failed:
        notifier.send(f"⚠️ <b>Historical data incomplete</b>: {escape(', '.join(history.failed))} failed to load "
                      f"after {HISTORY_ATTEMPTS} tries. "
                      + ("Trend and momentum stay <i>warming up</i>, so <b>no signals today</b> until enough "
                         "live data builds up." if history.critical_failed else
                         "Signals still run; the affected inputs show as missing."))
    constituents = load_constituents(broker, nse, cfg.OPTIONS_INDICES)
    macro = MacroFetcher(now_fn=now_fn)
    macro.start()
    news = NewsFetcher(now_fn=now_fn)
    news.start()

    engine_tokens = {c.token for cs in constituents.values() for c in cs}
    open_signals = store.open_signals()
    engine_tokens |= {s.contract.token for s in open_signals}
    recorder = Recorder(broker.ticker(), refs, store, notifier, vix_token=vix_token,
                        window=cfg.OPTIONS_STRIKE_WINDOW, n_expiries=cfg.OPTIONS_EXPIRIES_TRACKED,
                        stale_after_s=cfg.OPTIONS_STALE_AFTER_S, calendar=calendar, now_fn=now_fn,
                        extra_tokens=engine_tokens)
    engine = SignalEngine({r.index: r for r in refs}, state, store, notifier, cfg, calendar, vix_token=vix_token,
                          constituents=constituents, vix_history=history.vix_closes, macro=macro.snapshot,
                          events=load_events(store), news=news.snapshot, quote_fn=recorder.agg.quote, now_fn=now_fn)
    recorder.on_bars, recorder.on_tick = engine.on_bars, engine.on_tick

    recorder.start(prices)
    notifier.send("📡 <b>Recording started</b>\n" + "\n".join(format_contracts(r) for r in refs)
                  + f"\nTracking {len(recorder.subscribed)} instruments"
                  + (f" · {len(open_signals)} open signal(s) carried over" if open_signals else ""))
    try:
        notifier.send(engine.morning_brief(now_fn(), notes=[history.line, *calendar_notes(calendar, today)]))
    except Exception:
        logger.exception("Morning brief failed")

    recorder.run_until(at_ist(today, RECORD_UNTIL), sleep=sleep)
    macro.stop()
    news.stop()
    try:
        engine.close_session(now_fn())
    except Exception:
        logger.exception("Closing intraday signals failed")
    summary = recorder.summary()
    try:
        summary["coverage"] = coverage(store, refs, vix_token, today, recorder.started_at)
    except Exception:
        logger.exception("Coverage report failed")
    store.log_event("session_summary", str({k: v for k, v in summary.items() if k != "coverage"}), now_fn())
    try:
        notifier.send(engine.end_of_day(now_fn()))
    except Exception:
        logger.exception("End-of-day report failed")
    notifier.send(format_summary(today, summary))
    purge_old_data(store, cfg, now_fn())
    return EXIT_OK


def purge_old_data(store: Store, cfg: OptionsSettings, now: datetime) -> None:
    try:
        removed = store.purge_before(now - timedelta(days=cfg.OPTIONS_BARS_RETENTION_DAYS), now - LOG_RETENTION)
        if any(removed.values()):
            logger.info("Retention: removed %s", removed)
    except Exception:
        logger.exception("Retention clean-up failed")


def calendar_notes(calendar: NseCalendar, today: date) -> list[str]:
    """Warn ahead of the holiday list running out (NSE publishes the next year's in December)."""
    nxt = today.year + 1
    if not calendar.has_year(nxt) and (date(nxt, 1, 1) - today).days <= 30:
        return [f"⚠️ No NSE holiday list for {nxt} yet: add it on the Connectors page before 1 Jan"]
    return []


HISTORY_SESSIONS = 20        # 1m history: ~140 60-min bars, so EMA50 and ADX have settled before they're used
DAILY_DAYS = 400             # ~1 year of daily candles for VIX percentile, RV20 and P1 trends
HISTORY_ATTEMPTS = 3
HISTORY_RETRY_S = (2.0, 6.0)  # Angel sometimes answers AB1021 (rate limit) when well under it


@dataclass
class HistoryReport:
    loaded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    critical_failed: bool = False          # futures 1-min: trend, momentum and levels all come from it
    vix_closes: list[float] = field(default_factory=list)

    @property
    def line(self) -> str:
        total = len(self.loaded) + len(self.failed)
        if not self.failed:
            return f"History: {total}/{total} series loaded ✅"
        return f"History: {len(self.loaded)}/{total} loaded ⚠️ missing {', '.join(self.failed)}"


def history_rows(token: int, candles: list[dict]) -> list[dict]:
    """Historical candles as bars_1m rows: per-minute volume becomes cumulative day volume, as the
    recorder writes it, and ticks=0 marks the row as history rather than a recorded bar."""
    rows, day, cum = [], None, 0
    for c in sorted(candles, key=lambda c: pd.Timestamp(c["date"])):
        ts = pd.Timestamp(c["date"]).to_pydatetime()
        ts = ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)
        if ts.date() != day:
            day, cum = ts.date(), 0
        cum += int(c.get("volume") or 0)
        rows.append({"instrument_token": token, "ts": ts, "open": float(c["open"]), "high": float(c["high"]),
                     "low": float(c["low"]), "close": float(c["close"]), "volume_day": cum or None,
                     "oi": int(c["oi"]) if c.get("oi") is not None else None, "bid": None, "ask": None,
                     "bid_qty": None, "ask_qty": None, "ticks": 0})
    return rows


def load_history(broker, refs: list[IndexReference], vix_token: int, state: MarketState,
                 calendar: NseCalendar, now: datetime, pause: Callable[[float], None] = _time.sleep,
                 store: Store | None = None) -> HistoryReport:
    """Warm the market state from the broker's historical data (each request retried twice).

    A series that still fails is reported, not fatal: without it the agents report "warming up"
    and the engine sends no signals until enough live data has built up. With `store`, the
    1-minute history is also saved (never over recorded bars) so replays warm up the same way.
    """
    start = now.date()
    for _ in range(HISTORY_SESSIONS):
        start = calendar.previous_trading_day(start)
    since, daily_since = at_ist(start, time(9, 15)), now - timedelta(days=DAILY_DAYS)
    jobs = []
    for ref in refs:
        jobs += [(f"{ref.index} futures 1-min", ref.future_token, "minute", True, since, True),
                 (f"{ref.index} spot 1-min", ref.spot_token, "minute", False, since, False),
                 (f"{ref.index} spot daily", ref.spot_token, "day", False, daily_since, False)]
    jobs += [("India VIX 1-min", vix_token, "minute", False, since, False),
             ("India VIX daily", vix_token, "day", False, daily_since, False)]

    report = HistoryReport()
    for label, token, interval, oi, frm, critical in jobs:
        candles = None
        for attempt in range(1, HISTORY_ATTEMPTS + 1):
            try:
                candles = broker.historical(token, frm, now, interval, oi=oi)
                break
            except Exception as e:
                logger.warning("History for %s failed (attempt %d): %s", label, attempt, type(e).__name__)
                if attempt < HISTORY_ATTEMPTS:
                    pause(HISTORY_RETRY_S[attempt - 1])
        pause(0.4)              # Kite and Angel allow ~3 historical requests per second
        if candles is None:
            report.failed.append(label)
            report.critical_failed |= critical
            continue
        report.loaded.append(label)
        if interval == "day":
            state.load_daily(token, candles)
            if token == vix_token:
                report.vix_closes = [float(c["close"]) for c in candles if pd.Timestamp(c["date"]).date() < now.date()]
        else:
            done = [c for c in candles if pd.Timestamp(c["date"]) < pd.Timestamp(now).floor("min")]
            state.load_history(token, done)
            if store is not None:
                try:
                    store.insert_bars_if_missing(history_rows(token, done))
                except Exception:
                    logger.exception("Saving history for %s failed", label)
    return report


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
    from options.admin.connectors import load_effective_settings

    cfg = load_effective_settings()          # environment + whatever was saved on the Connectors page
    try:
        return run(cfg)
    except Exception as e:
        logger.exception("Session crashed")
        make_notifier(cfg).send(f"🔴 <b>Session crashed</b>: {escape(type(e).__name__)}. "
                                "It is restarted automatically; check the recorder logs on Railway if it repeats.")
        return EXIT_FAILED


def load_calendar(store: Store) -> NseCalendar:
    """Built-in holidays plus any added on the Connectors page."""
    try:
        from options.core.calendar_store import calendar_from_db
        return calendar_from_db(store.engine)
    except Exception:
        logger.exception("Couldn't read saved holidays; using the built-in list")
        return NseCalendar()


def load_events(store: Store) -> list:
    from options.core.events import EVENTS
    try:
        from options.core.calendar_store import events_from_db
        return events_from_db(store.engine)
    except Exception:
        logger.exception("Couldn't read saved events; using the built-in list")
        return list(EVENTS)


if __name__ == "__main__":
    sys.exit(main())

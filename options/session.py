"""One trading day: log in to the data provider, load contracts, record the market, report.

Angel One logs in by itself (MPIN + TOTP). Kite needs the person's daily login, prompted on
Telegram.

options.daemon starts this in a fresh process at 08:30 IST on each trading day; it exits
after the close, so every day starts with a fresh process and WebSocket.

    python -m options.session
"""

import sys
import time as _time
from collections import Counter
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
from options.check.worker import CHANNEL as CHECK_CHANNEL, CheckWorker
from options.core.pglisten import Listener
from options.desk.worker import CHANNEL as DESK_CHANNEL, DeskWorker
from options.market_data.live import CloseKeeper, LiveIndexFeed
from options.market_data.metrics import SessionMetrics
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
    logger.info("%s", history.line)
    if history.alert():
        notifier.send(history.alert())
    constituents = load_constituents(broker, nse, cfg.OPTIONS_INDICES, closes=False)   # closes once recording runs
    macro = MacroFetcher(now_fn=now_fn)
    macro.start()
    news = NewsFetcher(now_fn=now_fn)
    news.start()

    engine_tokens = {c.token for cs in constituents.values() for c in cs}
    open_signals = store.open_signals()
    engine_tokens |= {s.contract.token for s in open_signals}
    live = make_live_feed(broker, refs, store, today, now_fn, calendar)
    recorder = Recorder(broker.ticker(), refs, store, notifier, vix_token=vix_token,
                        window=cfg.OPTIONS_STRIKE_WINDOW, n_expiries=cfg.OPTIONS_EXPIRIES_TRACKED,
                        stale_after_s=cfg.OPTIONS_STALE_AFTER_S, calendar=calendar, now_fn=now_fn,
                        extra_tokens=engine_tokens, live=live)
    engine = SignalEngine({r.index: r for r in refs}, state, store, notifier, cfg, calendar, vix_token=vix_token,
                          constituents=constituents, vix_history=history.vix_closes, macro=macro.snapshot,
                          events=load_events(store), news=news.snapshot, quote_fn=recorder.agg.quote, now_fn=now_fn)
    checks = CheckWorker(engine, recorder, broker, store, live)
    desk = DeskWorker(recorder, broker, store, calendar, live)

    def on_tick(now: datetime) -> None:
        try:
            engine.on_tick(now)
        finally:
            checks.maybe(now)                   # Option Check requests, on the main thread
            try:
                desk.maybe(now)                 # paper desk orders: fills, stops, square-off
            except Exception:
                logger.exception("Desk orders failed")
    recorder.on_bars, recorder.on_tick = engine.on_bars, on_tick
    metrics = SessionMetrics(store, recorder, engine, notifier)
    retry = HistoryRetry(broker, history, state, store, notifier, today)
    closes = CloseKeeper(broker, live, constituents, calendar)
    recorder.on_minute = lambda now: (metrics.sample(now), retry.maybe(now), closes.maybe(now))

    recorder.start(prices)
    checks.follow_open(now_fn())
    desk.follow_open()
    listener = Listener(store.engine, CHECK_CHANNEL, checks.poke)
    listener.start()
    desk_listener = Listener(store.engine, DESK_CHANNEL, desk.poke)
    desk_listener.start()
    fill_previous_closes(broker, constituents, store=store, calendar=calendar, today=today)
    try:
        closes.maybe(now_fn())                  # a restart mid-session gets the rest from quotes at once
    except Exception:
        logger.exception("Previous closes from quotes failed")
    notifier.send("📡 <b>Recording started</b>\n" + "\n".join(format_contracts(r) for r in refs)
                  + f"\nTracking {len(recorder.subscribed)} instruments"
                  + (f" · {len(open_signals)} open signal(s) carried over" if open_signals else ""))
    try:
        notifier.send(engine.morning_brief(now_fn(), notes=[history.line, *calendar_notes(calendar, today)]))
    except Exception:
        logger.exception("Morning brief failed")

    recorder.run_until(at_ist(today, RECORD_UNTIL), sleep=sleep)
    listener.stop()
    desk_listener.stop()
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
    if live is not None:
        close_out_live(broker, live, today, now_fn, sleep)
    return EXIT_OK


LIVE_CLOSE_AT = time(15, 36)     # NSE and BSE have published the closing index values by then


def make_live_feed(broker, refs: list[IndexReference], store: Store, today: date, now_fn,
                   calendar: NseCalendar) -> LiveIndexFeed | None:
    """NIFTY 50 and SENSEX for the dashboard's ticker, plus the NIFTY future so the Signals card can
    show spot, future and basis from the same moment. Never stops the session if it can't be set up."""
    try:
        tokens = dict(broker.live_index_tokens()) if hasattr(broker, "live_index_tokens") else {}
    except Exception as e:
        logger.warning("Live index tokens failed: %s", _reason(e))
        tokens = {}
    nifty = next((r for r in refs if r.index == "NIFTY"), None)
    if nifty is not None:
        tokens.setdefault("NIFTY 50", nifty.spot_token)
        tokens["NIFTY FUT"] = nifty.future_token
    if not tokens:
        return None
    try:
        live = LiveIndexFeed(store, tokens, today, now_fn=now_fn)
        live.resume()
        live.load_saved_closes(calendar)
        return live
    except Exception:
        logger.exception("Live index feed didn't start")
        return None


def close_out_live(broker, live: LiveIndexFeed, today: date, now_fn, sleep) -> None:
    """The official closing levels, so the evening ticker shows exactly what the exchanges published."""
    if not hasattr(broker, "quotes"):
        return
    wait = (at_ist(today, LIVE_CLOSE_AT) - now_fn()).total_seconds()
    if 0 < wait <= 15 * 60:
        sleep(wait)
    try:
        live.close_out(broker.quotes(live.tokens), now_fn())
    except Exception as e:
        logger.warning("Closing index levels failed: %s", _reason(e))


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


FULL_SESSION_MINUTES = 300   # of 375: a saved session with fewer minutes counts as a gap


def _reason(e: Exception) -> str:
    from options.brokers.angel import brief_error
    return brief_error(e)


def _as_ist(ts) -> datetime:
    return ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)


@dataclass
class HistoryReport:
    loaded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    critical_failed: bool = False          # futures 1-min: trend, momentum and levels all come from it
    vix_closes: list[float] = field(default_factory=list)
    failed_jobs: list[tuple] = field(default_factory=list)      # to retry while the session runs
    from_saved: list[str] = field(default_factory=list)         # loaded from our own bars, no request made
    stand_in: dict[str, str] = field(default_factory=dict)      # refused, but filled well enough to use

    @property
    def line(self) -> str:
        total = len(self.loaded) + len(self.stand_in) + len(self.failed)
        if not self.failed and not self.stand_in:
            return f"History: {total}/{total} series loaded ✅" + (" (some from saved data)" if self.from_saved else "")
        parts = [f"History: {len(self.loaded)}/{total} loaded ⚠️"]
        if self.stand_in:
            parts.append(f"stand-in for {', '.join(self.stand_in)}")
        if self.failed:
            parts.append(f"missing {', '.join(self.failed)}")
        return " · ".join(parts)

    def alert(self) -> str | None:
        """The Telegram warning when the warm-up wasn't complete; None when it was."""
        if not self.failed and not self.stand_in:
            return None
        refused = [*self.stand_in, *self.failed]
        lines = [f"⚠️ <b>Historical data incomplete</b>: Angel didn't return {escape(', '.join(refused))} "
                 f"after {HISTORY_ATTEMPTS} tries."]
        lines += [f"• {escape(label)}: {escape(note)}" for label, note in self.stand_in.items()]
        if self.failed:
            lines.append(f"Missing: {escape(', '.join(self.failed))}.")
        if self.critical_failed:
            lines.append("Trend and momentum stay <i>warming up</i>, so <b>no signals</b> until the history "
                         "loads (retried every 10 minutes) or enough live data builds up.")
        else:
            lines.append("Signals run as normal. Angel is asked again every 10 minutes and its data replaces "
                         "the stand-ins when it answers.")
        return "\n".join(lines)


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
    """Warm the market state: our own saved 1-minute bars first, the broker for whatever they lack.

    1-minute series whose saved bars already cover every session are loaded without a request (a
    restart mid-session then never depends on the broker). Otherwise the broker is asked, each
    request retried twice; if it still refuses, the saved bars are used as they are, and futures
    sessions that are still missing are filled from the index spot shifted by the basis (the same
    moves; only volume and OI are unknown). Anything else that fails is reported, not fatal: the
    agents report "warming up" and no signals are sent until enough data has built up. With
    `store`, broker history is also saved (never over recorded bars) so replays warm up the same way.
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
    saved_only: dict[str, tuple[int, int]] = {}         # refused series loaded from partial saved bars
    for label, token, interval, oi, frm, critical in jobs:
        saved = _saved_minutes(store, token, frm, now) if interval == "minute" else []
        if saved and not _gaps(saved, calendar, frm.date(), now):
            state.add_bars(saved)
            report.loaded.append(label)
            report.from_saved.append(label)
            continue
        candles = None
        for attempt in range(1, HISTORY_ATTEMPTS + 1):
            try:
                candles = broker.historical(token, frm, now, interval, oi=oi)
                break
            except Exception as e:
                logger.warning("History for %s failed (attempt %d): %s", label, attempt, _reason(e))
                if attempt < HISTORY_ATTEMPTS:
                    pause(HISTORY_RETRY_S[attempt - 1])
            finally:
                for note in getattr(broker, "history_notes", None) or []:
                    logger.warning("History for %s: %s", label, note)
        pause(0.4)              # Kite allows ~3 history requests a second (Angel's adapter spaces its own ≥ 1 s)
        if candles is None:
            report.failed_jobs.append((label, token, interval, oi, frm, critical))
            if saved:
                state.add_bars(saved)                   # what we have beats nothing
                saved_only[label] = (len({r["ts"].date() for r in saved}), HISTORY_SESSIONS)
            report.failed.append(label)
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

    # Refused futures: fill the sessions they lack from spot, then judge whether trend can run
    for ref in refs:
        label = f"{ref.index} futures 1-min"
        if label not in report.failed:
            continue
        sessions, basis = _spot_stand_in(state, ref.future_token, ref.spot_token, now.date())
        if _warm(state, ref.future_token):
            report.failed.remove(label)
            have = f"saved futures bars ({saved_only[label][0]} sessions)" if label in saved_only else ""
            spot = (f"{ref.index} spot shifted by the basis ({basis:+.1f}) for {sessions} sessions"
                    if sessions else "")
            report.stand_in[label] = "using " + " plus ".join(p for p in (have, spot) if p)
    for label, (have, want) in saved_only.items():
        if label in report.failed and not label.endswith("futures 1-min"):
            report.failed.remove(label)
            report.stand_in[label] = f"using saved bars ({have} of {want} sessions)"
    report.critical_failed = any(f"{r.index} futures 1-min" in report.failed for r in refs)
    return report


def _saved_minutes(store: Store | None, token: int, since: datetime, now: datetime) -> list[dict]:
    if store is None:
        return []
    try:
        rows = store.bars_between(since, pd.Timestamp(now).floor("min").to_pydatetime(), {token})
    except Exception:
        logger.exception("Reading saved bars for %s failed", token)
        return []
    return [{**r, "ts": _as_ist(r["ts"])} for r in rows]


def _gaps(rows: list[dict], calendar: NseCalendar, first_day: date, now: datetime) -> list[date]:
    """Sessions the saved bars don't cover; today allows a few minutes lost to a restart."""
    counts = Counter(r["ts"].date() for r in rows)
    today, out, d = now.date(), [], first_day
    while d < today:
        if calendar.is_trading_day(d) and counts[d] < FULL_SESSION_MINUTES:
            out.append(d)
        d += timedelta(days=1)
    opened = at_ist(today, MARKET_OPEN)
    end = min(pd.Timestamp(now).floor("min").to_pydatetime(), at_ist(today, MARKET_CLOSE))
    elapsed = int((end - opened).total_seconds() // 60) if end > opened else 0
    if elapsed and counts[today] < elapsed - max(5, elapsed // 20):
        out.append(today)
    return out


def _spot_stand_in(state: MarketState, fut_token: int, spot_token: int, today: date) -> tuple[int, float]:
    """Fill the futures' missing past minutes with spot + basis; returns (sessions filled, basis).

    Trend and momentum read the same moves from either series; levels are off by however much the
    basis drifted. Volume is 0 and OI unknown, which the volume-surge checks ignore. Kept in memory
    only, never saved, so a replay can't mistake it for the futures."""
    spot, fut = state.frame(spot_token, "1min"), state.frame(fut_token, "1min")
    both = pd.concat({"f": fut["close"], "s": spot["close"]}, axis=1, join="inner").dropna()
    basis = 0.0
    if not both.empty:
        last_day = both[both.index.normalize() == both.index[-1].normalize()]
        basis = round(float((last_day["f"] - last_day["s"]).median()), 2)
    gaps = spot[(spot.index < pd.Timestamp(at_ist(today, time(0)))) & ~spot.index.isin(fut.index)]
    if gaps.empty:
        return 0, basis
    state.load_history(fut_token, [
        {"date": ts, "open": round(r.open + basis, 2), "high": round(r.high + basis, 2),
         "low": round(r.low + basis, 2), "close": round(r.close + basis, 2), "volume": 0, "oi": None}
        for ts, r in zip(gaps.index, gaps.itertuples())])
    return len(set(gaps.index.date)), basis


def _warm(state: MarketState, token: int) -> bool:
    from options.agents.technical import TREND_MIN_BARS
    return len(state.frame(token, "60min")) >= TREND_MIN_BARS


class HistoryRetry:
    """Series that failed to load before the open are retried every RETRY_EVERY while the session runs,
    so one bad answer from the provider at 08:30 doesn't cost the whole day's signals."""

    RETRY_EVERY = timedelta(minutes=10)

    def __init__(self, broker, report: HistoryReport, state: MarketState, store: Store, notifier: Notifier,
                 today: date):
        self.broker, self.report, self.state, self.store, self.notifier = broker, report, state, store, notifier
        self.today = today
        self.pending = list(report.failed_jobs)
        self.blocked = report.critical_failed           # signals held until the futures history loads
        self._last: datetime | None = None

    def maybe(self, now: datetime) -> None:
        if not self.pending or (self._last and now - self._last < self.RETRY_EVERY):
            return
        self._last = now
        before_today = at_ist(self.today, time(0))     # today's minutes are already recorded live
        recovered = []
        for job in list(self.pending):
            label, token, interval, oi, frm, critical = job
            try:
                candles = self.broker.historical(token, frm, now, interval, oi=oi)
            except Exception as e:
                logger.warning("History retry for %s failed: %s", label, _reason(e))
                continue
            if interval == "day":
                self.state.load_daily(token, candles)
            else:
                done = [c for c in candles if pd.Timestamp(c["date"]) < pd.Timestamp(before_today)]
                self.state.load_history(token, done)
                try:
                    self.store.insert_bars_if_missing(history_rows(token, done))
                except Exception:
                    logger.exception("Saving history for %s failed", label)
            self.pending.remove(job)
            recovered.append(label)
        if recovered:
            still = [j[0] for j in self.pending]
            tail = []
            if self.blocked and not any(j[5] for j in self.pending):
                self.blocked = False
                tail.append("Signals can start from the next 5-minute check.")
            elif any(label in self.report.stand_in for label in recovered):
                tail.append("It replaces the stand-in used since the start.")
            if still:
                tail.append(f"Still missing: {escape(', '.join(still))}.")
            self.notifier.send(f"✅ <b>Historical data recovered</b>: {escape(', '.join(recovered))} loaded at "
                               f"{now:%H:%M}. " + " ".join(tail))


def load_constituents(broker, nse_rows: list[dict], indices: list[str], store: Store | None = None,
                      calendar: NseCalendar | None = None, today: date | None = None,
                      closes: bool = True) -> dict[str, list[Constituent]]:
    """The breadth heavyweights; with `closes`, their previous closes too (see fill_previous_closes)."""
    tokens = {r["tradingsymbol"]: int(r["instrument_token"]) for r in nse_rows if r.get("segment") == "NSE"}
    out = {index: [Constituent(sym, w, tokens[sym]) for sym, w in HEAVYWEIGHTS.get(index, []) if sym in tokens]
           for index in indices}
    if closes:
        fill_previous_closes(broker, out, store=store, calendar=calendar, today=today)
    return out


def fill_previous_closes(broker, constituents: dict[str, list[Constituent]], store: Store | None = None,
                         calendar: NseCalendar | None = None, today: date | None = None) -> None:
    """Daily candles from the broker, else the previous session's saved bars. The session calls this
    after the recorder has started: with history requests a second apart, ten stocks take ten seconds,
    which must not delay the recording after a restart. Whatever is still missing at the open is
    priced from quotes by CloseKeeper."""
    for cs in constituents.values():
        want = [c for c in cs if c.prev_close is None]
        if not want:
            continue
        try:
            closes = broker.previous_closes([c.symbol for c in want])
        except Exception as e:
            logger.warning("Previous closes failed: %s", _reason(e))
            closes = {}
        for note in getattr(broker, "history_notes", None) or []:
            logger.warning("Previous closes: %s", note)
        missing = {c.token: c.symbol for c in want if closes.get(c.symbol) is None}
        if missing and store is not None and calendar is not None and today is not None:
            closes = {**closes, **_saved_closes(store, missing, calendar.previous_trading_day(today), today)}
        for c in want:
            if closes.get(c.symbol):
                c.prev_close = closes[c.symbol]


def _saved_closes(store: Store, missing: dict[int, str], prev_day: date, today: date) -> dict[str, float]:
    """Previous-session closes from our own recorded bars; only bars from that session count, so a
    stock that wasn't recorded then stays without one rather than getting a stale close."""
    try:
        rows = store.bars_between(at_ist(prev_day, time(0)), at_ist(today, time(0)), set(missing))
    except Exception:
        logger.exception("Reading saved closes failed")
        return {}
    last = {r["instrument_token"]: float(r["close"]) for r in rows}        # rows come oldest first
    if last:
        logger.info("Previous closes for %d of %d stocks taken from saved bars", len(last), len(missing))
    return {missing[token]: close for token, close in last.items()}


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

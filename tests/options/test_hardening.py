"""Production hardening (Phase G): durable alerts, supervisor restarts, warm-up history,
admin controls, auto-demotion, broker stop guidance, editable calendars and retention."""

import smtplib
import threading
import time as _time
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import inspect

from options import session
from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.core import calendar_store
from options.core.calendar import NseCalendar
from options.core.schemas import SignalState
from options.daemon import EXIT_CONFIG, EXIT_FAILED, Supervisor
from options.delivery import cards
from options.engine import controls
from options.engine.engine import SignalEngine
from options.engine.state import MarketState
from options.notify.base import Delivery
from options.notify.email import EmailNotifier
from options.notify.outbox import OutboxNotifier
from options.storage import Store, make_engine
from tests.options.fixtures import FUT_TOKEN, NIFTY_SPOT_TOKEN, Clock, ist
from tests.options.market import build_market
from tests.options.test_setups_engine import AlwaysBull

CAL = NseCalendar()


@pytest.fixture
def store(tmp_path):
    return Store(make_engine(f"sqlite:///{tmp_path}/h.db"))


# ── Alert outbox ─────────────────────────────────────────────────────────────

class FakeChannel:
    def __init__(self, name="telegram", results=None, delay=0.0):
        self.name = name
        self.results = list(results or [])
        self.delivered: list[str] = []
        self.delay = delay

    def deliver(self, text, buttons=None):
        if self.delay:
            _time.sleep(self.delay)
        result = self.results.pop(0) if self.results else Delivery(True)
        if result.ok:
            self.delivered.append(text)
        return result


def outbox(store, clock, channel, fallback=None, **kw):
    return OutboxNotifier(store, channel, fallback, now_fn=clock, min_gap_s=0, start=False, **kw)


def test_outbox_delivers_in_order_and_records_it(store):
    clock, ch = Clock(ist(2026, 10, 19, 10, 0)), FakeChannel()
    ob = outbox(store, clock, ch)
    ob.send("one")
    ob.send("two", [("Open", "https://example.com")])
    assert ob.process() is None
    assert ch.delivered == ["one", "two"]
    assert [r["status"] for r in store.outbox_recent()] == ["sent", "sent"]
    assert store.outbox_recent()[0]["channel"] == "telegram"


def test_outbox_retries_transient_failures_with_backoff(store):
    clock = Clock(ist(2026, 10, 19, 10, 0))
    ch = FakeChannel(results=[Delivery(False, retry_after=7, error="Telegram busy (429)"), Delivery(True)])
    ob = outbox(store, clock, ch)
    ob.send("card")
    ob.send("follow-up")
    assert ob.process() == 7                         # waits as asked, and keeps the order
    assert ch.delivered == [] and store.outbox_recent()[-1]["attempts"] == 1
    clock.sleep(7)
    assert ob.process() is None
    assert ch.delivered == ["card", "follow-up"]


def test_outbox_uses_the_fallback_when_the_channel_rejects_or_times_out(store):
    clock = Clock(ist(2026, 10, 19, 10, 0))
    tg = FakeChannel(results=[Delivery(False, permanent=True, error="400 chat not found")])
    mail = FakeChannel("email")
    ob = outbox(store, clock, tg, mail)
    ob.send("rejected by telegram")
    ob.process()
    assert mail.delivered == ["rejected by telegram"]
    assert store.outbox_recent()[0]["channel"] == "email"

    down = FakeChannel(results=[Delivery(False, error="network")] * 50)
    ob2 = outbox(store, clock, down)                 # no fallback: expires after 15 minutes
    ob2.send("never delivered")
    for _ in range(40):
        clock.sleep(30)
        ob2.process()
    assert store.outbox_recent()[0]["status"] == "expired" and ob2.expired == 1


def test_outbox_drops_duplicates_and_recovers_pending_alerts(store):
    clock = Clock(ist(2026, 10, 19, 10, 0))
    first = outbox(store, clock, FakeChannel())
    first.send("same text")
    first.send("same text")                          # within 2 minutes: dropped
    assert len(store.outbox_recent()) == 1
    store.outbox_add("x" * 64, "old", None, clock() - timedelta(hours=1))   # left by a crashed process

    ch = FakeChannel()
    second = outbox(store, clock, ch)                # picks up what the first never sent
    second.process()
    assert ch.delivered == ["same text"]
    assert {r["text"]: r["status"] for r in store.outbox_recent()} == {"same text": "sent", "old": "expired"}


def test_send_never_waits_for_a_slow_channel(store):
    ch = FakeChannel(delay=0.5)
    ob = OutboxNotifier(store, ch, min_gap_s=0)      # real sender thread
    t0 = _time.monotonic()
    ob.send("a")
    ob.send("b")
    assert _time.monotonic() - t0 < 0.3              # the engine is never held up
    assert ob.close(timeout=5) and ch.delivered == ["a", "b"]


# ── E-mail fallback ──────────────────────────────────────────────────────────

class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, fail=None):
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        if password == "bad":
            raise smtplib.SMTPAuthenticationError(535, b"no")

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_email_channel_formats_html_and_classifies_errors():
    FakeSMTP.sent = []
    mail = EmailNotifier("smtp.example.com", 587, "me@example.com", "app-pass", "me@example.com, you@example.com",
                         smtp_factory=FakeSMTP)
    assert mail.deliver("🟢 <b>BUY CE · NIFTY</b>\nEntry 100", [("Open <x>", "https://e.com/?a=1&b=2")]).ok
    msg = FakeSMTP.sent[-1]
    assert msg["Subject"] == "[TradingAgents] 🟢 BUY CE · NIFTY" and msg["To"] == "me@example.com, you@example.com"
    html = msg.get_body(("html",)).get_content()
    assert "<b>BUY CE · NIFTY</b><br>Entry 100" in html and "Open &lt;x&gt;" in html and "a=1&amp;b=2" in html
    assert "<b>" not in msg.get_body(("plain",)).get_content()
    bad = EmailNotifier("smtp.example.com", 587, "me@example.com", "bad", "me@example.com", smtp_factory=FakeSMTP)
    result = bad.deliver("x")
    assert not result.ok and result.permanent


# ── Supervisor: crash restarts ───────────────────────────────────────────────

class Proc:
    def __init__(self):
        self.code = None

    def poll(self):
        return self.code

    def terminate(self):
        self.code = -15

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.code = -9


@pytest.fixture
def sup(tmp_path):
    repo = AdminRepo(make_engine(f"sqlite:///{tmp_path}/d.db"), secret_key="k")
    clock = Clock(ist(2026, 10, 19, 10, 0))
    procs, alerts, open_intraday = [], [], {"v": False}

    def spawn():
        procs.append(Proc())
        return procs[-1]

    s = Supervisor(repo, spawn=spawn, now_fn=clock, calendar=CAL, notify=alerts.append,
                   has_open_intraday=lambda: open_intraday["v"])
    return s, clock, procs, alerts, open_intraday, repo


def test_a_crashed_session_is_restarted_with_backoff_then_given_up(sup):
    s, clock, procs, alerts, _, repo = sup
    s.step(clock())
    assert len(procs) == 1
    for attempt, wait in enumerate((30, 120, 300), start=1):
        procs[-1].code = EXIT_FAILED
        s.step(clock())
        assert "Restarting in" in alerts[-1] and f"attempt {attempt} of 3" in alerts[-1]
        assert repo.get_meta_json("recorder_status")["state"] == "restarting"
        clock.sleep(wait - 1)
        s.step(clock())
        assert len(procs) == attempt                 # not yet
        clock.sleep(1)
        s.step(clock())
        assert len(procs) == attempt + 1             # restarted
    procs[-1].code = EXIT_FAILED
    s.step(clock())
    assert "no longer restarted" in alerts[-1] and "not being monitored" in alerts[-1]
    clock.sleep(600)
    s.step(clock())
    assert len(procs) == 4 and repo.get_meta_json("recorder_status")["gave_up"] is True


def test_clean_exits_missing_keys_and_late_crashes_are_not_restarted(sup):
    s, clock, procs, alerts, _, _ = sup
    s.step(clock())
    procs[-1].code = EXIT_CONFIG                     # keys missing: saving them sends a restart command
    s.step(clock())
    clock.sleep(600)
    s.step(clock())
    assert len(procs) == 1 and alerts == []

    s2_clock = clock
    s.last_run = None
    s2_clock.now = ist(2026, 10, 19, 15, 25)
    s.restart_at = None
    s.proc = Proc()
    s.proc.code = EXIT_FAILED
    s.step(s2_clock())
    assert "Too close to the end of the day" in alerts[-1] and s.restart_at is None


def test_a_late_container_start_still_manages_open_intraday_signals(sup):
    s, clock, procs, _, open_intraday, _ = sup
    clock.now = ist(2026, 10, 19, 15, 5)
    s.step(clock())
    assert procs == []                               # nothing open: wait for tomorrow
    open_intraday["v"] = True
    s.step(clock())
    assert len(procs) == 1                           # short session to square them off


# ── Warm-up history ──────────────────────────────────────────────────────────

class FlakyHistoryBroker:
    def __init__(self, fail: dict[int, int]):
        self.fail = dict(fail)          # token -> failures before success (99 = never)
        self.calls: list[tuple] = []

    def historical(self, token, start, end, interval="minute", oi=False):
        self.calls.append((token, interval))
        if self.fail.get(token, 0) > 0:
            self.fail[token] -= 1
            raise RuntimeError("AB1021 Too many requests")
        if interval == "day":
            return [{"date": date(2026, 10, 16), "open": 1, "high": 1, "low": 1, "close": 13.0, "volume": 0}]
        return [{"date": ist(2026, 10, 16, 9, 15), "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10, "oi": 5},
                {"date": ist(2026, 10, 16, 9, 16), "open": 2, "high": 3, "low": 2, "close": 3, "volume": 15}]


def _refs():
    return [build_market().ref]


def test_history_is_retried_reported_and_saved_for_replays(store):
    ref = _refs()[0]
    broker = FlakyHistoryBroker({ref.future_token: 2, 264969: 99})       # futures recovers, VIX never does
    pauses = []
    rep = session.load_history(broker, [ref], 264969, MarketState(date(2026, 10, 19)), CAL,
                               ist(2026, 10, 19, 8, 45), pause=pauses.append, store=store)
    assert rep.failed == ["India VIX 1-min", "India VIX daily"] and not rep.critical_failed
    assert "NIFTY futures 1-min" in rep.loaded and "3/5 loaded" in rep.line
    assert broker.calls.count((ref.future_token, "minute")) == 3 and 2.0 in pauses and 6.0 in pauses
    rows = store.bars_between(ist(2026, 10, 16, 9, 0), ist(2026, 10, 16, 10, 0), {ref.future_token})
    assert [r["volume_day"] for r in rows] == [10, 25] and rows[0]["ticks"] == 0     # cumulative, marked as history

    recorded = {**rows[0], "close": 99.0, "bid": 98.9, "ticks": 40}
    store.write_bars([recorded])
    store.insert_bars_if_missing(session.history_rows(ref.future_token, [
        {"date": ist(2026, 10, 16, 9, 15), "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]))
    kept = store.bars_between(ist(2026, 10, 16, 9, 15), ist(2026, 10, 16, 9, 16), {ref.future_token})[0]
    assert kept["close"] == 99.0 and kept["bid"] == 98.9                         # a recorded bar is never overwritten

    lost = session.load_history(FlakyHistoryBroker({ref.future_token: 99}), [ref], 264969,
                                MarketState(date(2026, 10, 19)), CAL, ist(2026, 10, 19, 8, 45), pause=lambda s: None)
    assert lost.critical_failed and "NIFTY futures 1-min" in lost.failed


def test_summary_reports_minutes_recorded(store):
    ref = _refs()[0]
    store.write_bars([{"instrument_token": ref.future_token, "ts": ist(2026, 10, 19, 9, 15) + timedelta(minutes=i),
                       "open": 1, "high": 1, "low": 1, "close": 1, "ticks": 3} for i in range(370)])
    cov = session.coverage(store, [ref], 264969, date(2026, 10, 19), ist(2026, 10, 19, 8, 45))
    assert {c["label"]: (c["recorded"], c["expected"]) for c in cov} == {
        "NIFTY fut": (370, 375), "NIFTY spot": (0, 375), "VIX": (0, 375)}
    text = session.format_summary(date(2026, 10, 19), {"bars_written": 1, "instruments": 3, "ticks": 9,
                                                       "late_ticks": 0, "disconnects": 0, "stale_alerts": 0,
                                                       "bars_unsaved": 0, "coverage": cov})
    assert "⚠️" in text and "NIFTY fut 370/375" in text


# ── Engine: restarts, controls and the kill rule ─────────────────────────────

def make_engine_for(store, ctx, quotes, notifier, cfg=None):
    return SignalEngine({"NIFTY": ctx.ref}, ctx.state, store, notifier, cfg or OptionsSettings(), ctx.calendar,
                        vix_token=ctx.vix_token, constituents={"NIFTY": ctx.constituents},
                        vix_history=ctx.vix_history, events=[], quote_fn=lambda t: quotes.get(t, (None, None)),
                        now_fn=lambda: ctx.now, setups=[AlwaysBull()])


class Notes:
    def __init__(self):
        self.texts: list[str] = []

    def send(self, text, buttons=None):
        self.texts.append(text)
        return True


def test_a_restarted_engine_does_not_repeat_todays_signals(store):
    ctx, quotes = build_market(trend=1), {}
    first = make_engine_for(store, ctx, quotes, Notes())
    first.evaluate(ctx.now)
    assert len(store.signals_since(ctx.now - timedelta(hours=1))) == 1
    second = make_engine_for(store, ctx, quotes, Notes())          # e.g. after a crash restart
    second.evaluate(ctx.now + timedelta(minutes=5))
    assert len(store.signals_since(ctx.now - timedelta(hours=1))) == 1


def test_pause_blocks_new_signals_and_exit_all_closes_open_ones_once(store):
    ctx, quotes, notes = build_market(trend=1), {}, Notes()
    controls.set_paused(store, True, "amit", "RBI surprise", ctx.now)
    eng = make_engine_for(store, ctx, quotes, notes)
    eng.on_tick(ctx.now)
    eng.evaluate(ctx.now)
    assert store.signals_since(ctx.now - timedelta(hours=1)) == []
    [ev] = store.evaluations_since(ctx.now - timedelta(hours=1))
    assert ev["outcome"] == "NO_TRADE" and "paused by amit" in ev["reasons"]
    assert "New signals are paused" in eng.morning_brief(ctx.now)

    controls.set_paused(store, False, "amit", "", ctx.now)
    eng._read_controls(ctx.now, force=True)
    eng.evaluate(ctx.now)                                                  # resumed: the same candidate now goes out
    sig = eng.open[0]
    quotes[sig.contract.token] = (sig.entry_high - 1, sig.entry_high - 0.5)
    eng.on_tick(ctx.now + timedelta(seconds=10))                          # filled
    controls.request_exit_all(store, "amit", ctx.now)
    eng._read_controls(ctx.now + timedelta(minutes=6), force=True)
    final = store.get_signal(sig.signal_id)
    assert final.state is SignalState.CLOSED and final.exit_reason == "KILL" and eng.open == []
    assert any("Exit all" in t and "1 open signal(s) closed" in t for t in notes.texts)
    n = len(notes.texts)
    eng._read_controls(ctx.now + timedelta(minutes=7), force=True)       # acknowledged: never repeated
    assert len(notes.texts) == n and controls.pending_exit_all(store) is None


def test_a_live_setup_with_30_losing_trades_is_demoted(store):
    ctx, quotes, notes = build_market(trend=1), {}, Notes()
    eng = make_engine_for(store, ctx, quotes, notes, OptionsSettings(OPTIONS_LIVE_SETUPS=["S1_TREND_PULLBACK"]))
    eng.evaluate(ctx.now)
    sig = eng.open[0]
    assert sig.mode == "LIVE"
    for i in range(29):
        lost = sig.model_copy(update={"signal_id": f"NF-260101-{i:03d}", "state": SignalState.CLOSED,
                                      "closed_at": ctx.now - timedelta(days=30 - i), "pnl_rupees": -500.0,
                                      "r_multiple": -0.5, "fill_price": sig.entry_high, "exit_price": 1.0})
        store.save_signal(lost, ctx.now)
    eng._review_setup("S1_TREND_PULLBACK", ctx.now)
    assert "S1_TREND_PULLBACK" in eng.live_setups                      # 29 trades: too early to judge
    quotes[sig.contract.token] = (sig.entry_high - 1, sig.entry_high - 0.5)
    eng.on_tick(ctx.now + timedelta(seconds=10))
    quotes[sig.contract.token] = (sig.stop_loss - 1, sig.stop_loss - 0.5)
    eng.on_tick(ctx.now + timedelta(seconds=20))                        # 30th trade: a loss
    assert "S1_TREND_PULLBACK" not in eng.live_setups
    assert AdminRepo(store.engine).setting_values()["OPTIONS_LIVE_SETUPS"] == []
    assert any("moved back to SHADOW" in t for t in notes.texts)
    assert store.audit_recent()[0]["action"] == "setup_demoted"


# ── Broker stop guidance ─────────────────────────────────────────────────────

def test_live_cards_tell_you_to_place_a_broker_stop(store):
    ctx = build_market(trend=1)
    eng = make_engine_for(store, ctx, {}, Notes(), OptionsSettings(OPTIONS_LIVE_SETUPS=["S1_TREND_PULLBACK"]))
    eng.evaluate(ctx.now)
    sig = eng.open[0]
    trig, limit = cards.broker_stop(sig.stop_loss)
    assert limit < trig and round(limit / 0.05) * 0.05 == pytest.approx(limit)
    card = cards.signal_card(sig, 100_000)
    assert f"SL order at your broker (trigger {trig:.2f}, limit {limit:.2f})" in card
    assert "SL order" not in cards.signal_card(sig.model_copy(update={"mode": "SHADOW"}), 100_000)
    assert "GTT stop" in cards.stop_instruction(sig.model_copy(update={"horizon": "positional"}))
    assert "Move your broker stop up" in cards.update_message(sig, "T1_HIT", "T1 hit")
    assert "Exit at your broker now" in cards.update_message(sig, "SL_HIT", "closed")
    assert cards.broker_stop(1.0) == (1.0, 0.95) and cards.broker_stop(0.05) == (0.05, 0.05)


# ── Calendars edited from the UI ─────────────────────────────────────────────

def test_holidays_and_events_added_from_the_ui(store):
    repo = AdminRepo(store.engine)
    assert not calendar_store.calendar_from_db(store.engine).has_year(2027)
    calendar_store.add_holiday(repo, date(2027, 1, 26), "Republic Day")
    cal = calendar_store.calendar_from_db(store.engine)
    assert not cal.is_trading_day(date(2027, 1, 26)) and cal.is_trading_day(date(2027, 1, 27))
    assert not cal.has_year(2027)                                      # a partial list still warns
    calendar_store.set_year_complete(repo, 2027, True)
    assert calendar_store.calendar_from_db(store.engine).has_year(2027)
    with pytest.raises(ValueError):
        calendar_store.add_holiday(repo, date(2027, 1, 30), "Saturday")
    with pytest.raises(ValueError):
        calendar_store.add_holiday(repo, date(2026, 10, 20), "Dussehra again")
    calendar_store.remove_holiday(repo, date(2027, 1, 26))
    assert calendar_store.calendar_from_db(store.engine).is_trading_day(date(2027, 1, 26))

    ev = calendar_store.add_event(repo, "RBI MPC decision", ist(2027, 4, 7, 10, 0), "high")
    assert any(e.name == "RBI MPC decision" and e.at == ist(2027, 4, 7, 10, 0)
               for e in calendar_store.events_from_db(store.engine))
    calendar_store.set_year_complete(repo, 2027, False)
    view = calendar_store.calendar_view(repo, date(2026, 12, 5))
    assert "No NSE holiday list for 2027" in view["warning"]
    assert any(e["id"] == ev["id"] and e["source"] == "added" for e in view["events"])
    calendar_store.remove_event(repo, ev["id"])
    assert all(e["source"] == "built-in" for e in calendar_store.calendar_view(repo, date(2026, 10, 1))["events"])
    assert session.calendar_notes(CAL, date(2026, 12, 10)) and not session.calendar_notes(CAL, date(2026, 10, 10))


# ── Storage: index, retention ────────────────────────────────────────────────

def test_bars_have_a_time_index_and_old_data_is_purged(store):
    assert "ix_bars_1m_ts" in {i["name"] for i in inspect(store.engine).get_indexes("bars_1m")}
    old, new = ist(2024, 1, 2, 9, 15), ist(2026, 10, 19, 9, 15)
    store.write_bars([{"instrument_token": 1, "ts": t, "open": 1, "high": 1, "low": 1, "close": 1, "ticks": 1}
                      for t in (old, new)])
    store.log_event("ws_close", "x", old)
    store.outbox_add("d", "sent long ago", None, old)
    store.outbox_update(store.outbox_recent()[0]["id"], status="sent")
    removed = store.purge_before(new - timedelta(days=730), new - timedelta(days=90))
    assert removed == {"bars": 1, "alerts": 1, "session_events": 1, "llm_calls": 0}
    assert store.bar_counts_between(new - timedelta(days=1), new + timedelta(days=1)) == {1: 1}


# ── Session metrics (R-28) ───────────────────────────────────────────────────

def test_session_metrics_record_each_minute_and_slow_checks_are_reported(store):
    from types import SimpleNamespace

    from options.market_data.bars import BarAggregator
    from options.market_data.metrics import SessionMetrics

    rec = SimpleNamespace(agg=BarAggregator(), bars_written=0)
    eng = SimpleNamespace(eval_ms_peak=0.0, open=[1, 2])
    note = SimpleNamespace(delay_peak=0.0)
    m = SessionMetrics(store, rec, eng, note)
    rec.agg.tick_count, rec.bars_written, rec.agg.rejected_ticks = 120, 40, 1
    eng.eval_ms_peak, note.delay_peak = 412.0, 1.8
    row = m.sample(ist(2026, 10, 19, 10, 1, 7))
    assert row == {"ts": ist(2026, 10, 19, 10, 1), "ticks": 120, "bars": 40, "rejected_ticks": 1, "eval_ms": 412.0,
                   "alert_delay_s": 1.8, "open_signals": 2, "live_lag_ms": None}
    assert eng.eval_ms_peak == 0 and note.delay_peak == 0          # peaks reset for the next minute
    rec.agg.tick_count = 150
    assert m.sample(ist(2026, 10, 19, 10, 2, 7))["ticks"] == 30
    assert len(store.metrics_since(ist(2026, 10, 19, 10, 0))) == 2

    ctx, notes = build_market(trend=1), Notes()
    eng2 = make_engine_for(store, ctx, {}, notes)
    import options.engine.engine as engine_mod
    real = engine_mod.SignalEngine._evaluate
    engine_mod.SignalEngine._evaluate = lambda self, now: _time.sleep(0.01)
    try:
        engine_mod.SLOW_EVAL_MS, saved = 1, engine_mod.SLOW_EVAL_MS
        eng2.evaluate(ctx.now)
        eng2.evaluate(ctx.now + timedelta(minutes=5))                  # within the hour: reported once
    finally:
        engine_mod.SignalEngine._evaluate, engine_mod.SLOW_EVAL_MS = real, saved
    assert sum("Signal check took" in t for t in notes.texts) == 1 and eng2.eval_ms_peak >= 10


# ── 19 Oct 2026: futures history failed at 08:30 and cost the day's signals ─────────

def test_a_failing_oi_history_call_no_longer_drops_the_futures_candles():
    from options.brokers.angel import AngelBroker

    class Api:
        def getCandleData(self, params):
            return {"status": True, "data": [[f"{params['fromdate'][:10]}T09:15:00+05:30", 1, 2, 0.5, 1.5, 100]]}

        def getOIData(self, params):
            return {"status": False, "errorcode": "AB2001", "message": "Internal Error"}

    b = AngelBroker.__new__(AngelBroker)
    b.api, b.history_api, b._pause = Api(), None, lambda s: None
    candles = b.historical(2_000_000_000 + 57130, ist(2026, 10, 1, 9, 15), ist(2026, 10, 16, 15, 30), "minute", oi=True)
    assert candles and all(c["oi"] is None for c in candles)        # kept, OI unknown (not 0)
    assert any("no OI history" in n and "AB2001" in n for n in b.history_notes)


def test_a_refused_long_span_is_retried_in_smaller_pieces():
    from options.brokers.angel import AngelBroker

    class Api:
        calls = []

        def getCandleData(self, params):
            Api.calls.append(params["fromdate"])
            frm, to = datetime.strptime(params["fromdate"], "%Y-%m-%d %H:%M"), datetime.strptime(params["todate"], "%Y-%m-%d %H:%M")
            if to - frm > timedelta(days=7):
                return {"status": False, "errorcode": "AB1004", "message": "Something Went Wrong"}
            return {"status": True, "data": [[f"{params['fromdate'][:10]}T10:00:00+05:30", 1, 1, 1, 1, 1]]}

    b = AngelBroker.__new__(AngelBroker)
    b.api, b.history_api, b._pause = Api(), None, lambda s: None
    candles = b.historical(99926000, ist(2026, 9, 20, 9, 15), ist(2026, 10, 16, 15, 30), "minute")
    assert len(candles) == 4 and len(Api.calls) == 5               # one refusal, then four 7-day pieces


def test_failed_history_is_retried_during_the_session_and_announced(store):
    class Broker:
        def __init__(self):
            self.fail = True

        def historical(self, token, start, end, interval="minute", oi=False):
            if self.fail:
                raise RuntimeError("still down")
            return [{"date": ist(2026, 10, 16, 9, 15), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 5},
                    {"date": ist(2026, 10, 19, 9, 15), "open": 2, "high": 2, "low": 2, "close": 2, "volume": 5}]

    rep = session.HistoryReport(failed=["NIFTY futures 1-min"], critical_failed=True,
                                failed_jobs=[("NIFTY futures 1-min", 9001, "minute", True, ist(2026, 9, 18, 9, 15), True)])
    state, notes, broker = MarketState(date(2026, 10, 19)), Notes(), Broker()
    retry = session.HistoryRetry(broker, rep, state, store, notes, date(2026, 10, 19))
    retry.maybe(ist(2026, 10, 19, 9, 31))
    assert retry.pending and notes.texts == []
    broker.fail = False
    retry.maybe(ist(2026, 10, 19, 9, 35))                          # within 10 minutes: not yet
    assert retry.pending
    retry.maybe(ist(2026, 10, 19, 9, 41))
    assert not retry.pending and "Historical data recovered" in notes.texts[-1] and "Signals can start" in notes.texts[-1]
    rows = store.bars_between(ist(2026, 10, 16, 0, 0), ist(2026, 10, 20, 0, 0), {9001})
    assert [r["ts"].day for r in rows] == [16]                     # today's minutes are left to the live feed


# ── 19 Oct 2026, 09:33: every history request refused, so warm up from our own bars ─────

VIX = 264969


def _sessions(n: int, before: date = date(2026, 10, 19)) -> list[date]:
    days, d = [], before
    for _ in range(n):
        d = CAL.previous_trading_day(d)
        days.append(d)
    return sorted(days)


def _save_minutes(store, token, days, base=100.0, shift=0.0, minutes=375):
    candles = []
    for d in days:
        for i in range(minutes):
            p = base + d.toordinal() % 50 + (i % 30) * 0.1 + shift
            candles.append({"date": ist(d.year, d.month, d.day, 9, 15) + timedelta(minutes=i),
                            "open": p, "high": p + 0.5, "low": p - 0.5, "close": p, "volume": 10})
    store.insert_bars_if_missing(session.history_rows(token, candles))


class RefusingBroker:
    """Every history request fails, as Angel's did after the 09:33 restart."""
    def __init__(self, works: bool = False):
        self.works, self.calls = works, []

    def historical(self, token, start, end, interval="minute", oi=False):
        self.calls.append((token, interval))
        if not self.works:
            raise RuntimeError("DataException")
        return [{"date": ist(2026, 10, 15, 10, 0), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 5}] \
            if interval == "minute" else [{"date": date(2026, 10, 16), "open": 1, "high": 1, "low": 1, "close": 13.0, "volume": 0}]


def test_saved_bars_warm_up_a_restart_without_asking_the_broker(store):
    ref = _refs()[0]
    days = _sessions(session.HISTORY_SESSIONS)
    for token in (ref.future_token, ref.spot_token, VIX):
        _save_minutes(store, token, days)
        _save_minutes(store, token, [date(2026, 10, 19)], minutes=44)        # today 09:15–09:58, recorded live
    broker, state = RefusingBroker(works=True), MarketState(date(2026, 10, 19))
    rep = session.load_history(broker, [ref], VIX, state, CAL, ist(2026, 10, 19, 10, 0), pause=lambda s: None, store=store)
    assert {i for _, i in broker.calls} == {"day"}                         # no minute request at all
    assert set(rep.from_saved) == {"NIFTY futures 1-min", "NIFTY spot 1-min", "India VIX 1-min"}
    assert not rep.failed and not rep.stand_in and not rep.critical_failed and "✅" in rep.line
    assert rep.alert() is None
    assert len(state.today(ref.future_token, "1min")) == 44 and session._warm(state, ref.future_token)


def test_refused_futures_are_filled_from_spot_and_signals_still_run(store):
    ref = _refs()[0]
    days = _sessions(session.HISTORY_SESSIONS)
    _save_minutes(store, ref.spot_token, days)
    _save_minutes(store, ref.future_token, days[-1:], shift=50.0)         # only Friday's futures were recorded
    state, notes = MarketState(date(2026, 10, 19)), Notes()
    rep = session.load_history(RefusingBroker(), [ref], VIX, state, CAL, ist(2026, 10, 19, 8, 45),
                               pause=lambda s: None, store=store)
    assert not rep.critical_failed and "NIFTY futures 1-min" not in rep.failed
    note = rep.stand_in["NIFTY futures 1-min"]
    assert "saved futures bars (1 sessions)" in note and "spot shifted by the basis (+50.0) for 19 sessions" in note
    assert rep.from_saved == ["NIFTY spot 1-min"] and set(rep.failed) == {"India VIX 1-min", "India VIX daily", "NIFTY spot daily"}
    assert "Signals run as normal" in rep.alert() and "stand-in for NIFTY futures 1-min" in rep.line
    fut, spot = state.frame(ref.future_token, "1min"), state.frame(ref.spot_token, "1min")
    first = spot.index[0]
    assert fut.loc[first, "close"] == spot.loc[first, "close"] + 50.0 and fut.loc[first, "volume"] == 0
    assert session._warm(state, ref.future_token)
    saved_fut = store.bars_between(ist(2026, 9, 1, 0, 0), ist(2026, 10, 20, 0, 0), {ref.future_token})
    assert {r["ts"].date() for r in saved_fut} == {days[-1]}               # the stand-in is never saved

    retry = session.HistoryRetry(RefusingBroker(works=True), rep, state, store, notes, date(2026, 10, 19))
    retry.maybe(ist(2026, 10, 19, 9, 30))
    assert not retry.pending and "replaces the stand-in" in notes.texts[-1] and "Signals can start" not in notes.texts[-1]


def test_futures_too_short_even_with_the_stand_in_still_hold_signals(store):
    ref = _refs()[0]
    _save_minutes(store, ref.spot_token, _sessions(3))
    rep = session.load_history(RefusingBroker(), [ref], VIX, MarketState(date(2026, 10, 19)), CAL,
                               ist(2026, 10, 19, 8, 45), pause=lambda s: None, store=store)
    assert rep.critical_failed and "NIFTY futures 1-min" in rep.failed and "no signals" in rep.alert()
    assert rep.stand_in == {"NIFTY spot 1-min": "using saved bars (3 of 20 sessions)"}


def test_the_main_login_takes_over_when_the_history_key_fails():
    from SmartApi.smartExceptions import DataException

    from options.brokers.angel import AngelBroker

    class Main:
        calls = 0

        def getCandleData(self, params):
            Main.calls += 1
            return {"status": True, "data": [[f"{params['fromdate'][:10]}T09:15:00+05:30", 1, 2, 0.5, 1.5, 100]]}

    class HistoryKey:
        calls = 0

        def getCandleData(self, params):
            HistoryKey.calls += 1
            raise DataException("Couldn't parse the JSON response received from the server: "
                                "b'Access denied because of exceeding access rate'")

    b = AngelBroker.__new__(AngelBroker)
    b.api, b.history_api, b._pause = Main(), HistoryKey(), lambda s: None
    assert b.historical(99926000, ist(2026, 10, 15, 9, 15), ist(2026, 10, 16, 15, 30), "minute")
    assert any("historical-data key failed (DataException: Couldn't parse" in n and "exceeding access rate" in n
               for n in b.history_notes)
    b.historical(99926000, ist(2026, 10, 15, 9, 15), ist(2026, 10, 16, 15, 30), "minute")
    assert HistoryKey.calls == 1 and Main.calls == 2                       # the main login stays in use


def test_error_messages_logged_are_angels_reply_never_a_requests_url():
    import requests
    from SmartApi.smartExceptions import DataException

    from options.brokers.angel import AngelError, brief_error
    assert brief_error(DataException("Couldn't parse … b''")) == "DataException: Couldn't parse … b''"
    assert brief_error(AngelError("historical candles failed (AB1004): x")).startswith("AngelError: historical")
    assert brief_error(requests.ConnectionError("https://host/path?key=secret")) == "ConnectionError"


def test_previous_closes_come_from_saved_bars_when_the_broker_refuses(store):
    class Broker:
        def previous_closes(self, symbols):
            raise RuntimeError("DataException")

    nse = [{"tradingsymbol": "HDFCBANK", "instrument_token": 341249, "segment": "NSE"},
           {"tradingsymbol": "ICICIBANK", "instrument_token": 1270529, "segment": "NSE"}]
    store.insert_bars_if_missing(session.history_rows(341249, [
        {"date": ist(2026, 10, 16, 15, 28), "open": 1, "high": 1, "low": 1, "close": 991.0, "volume": 1},
        {"date": ist(2026, 10, 16, 15, 29), "open": 1, "high": 1, "low": 1, "close": 992.5, "volume": 1}]))
    store.insert_bars_if_missing(session.history_rows(1270529, [                 # stale: a week old
        {"date": ist(2026, 10, 9, 15, 29), "open": 1, "high": 1, "low": 1, "close": 1400.0, "volume": 1}]))
    out = session.load_constituents(Broker(), nse, ["NIFTY"], store=store, calendar=CAL, today=date(2026, 10, 19))
    closes = {c.symbol: c.prev_close for c in out["NIFTY"]}
    assert closes == {"HDFCBANK": 992.5, "ICICIBANK": None}

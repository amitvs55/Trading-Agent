from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from options.agents.option_chain import Chain, ChainRow
from options.agents.technical import TechView
from options.config import OptionsSettings
from options.core.schemas import PillarView, SignalState
from options.engine.engine import SignalEngine, bucket_end
from options.engine.state import MarketState
from options.setups.base import Candidate, bounded_invalidation, candle_quality
from options.setups.intraday import OIWallBreak, OpeningRangeBreakout, TrendPullback
from options.setups.positional import DailyTrendContinuation
from options.storage import Store, make_engine
from tests.options.fixtures import NIFTY_SPOT_TOKEN, TODAY, RecordingNotifier, ist
from tests.options.market import build_market


def tech(bar, prev=None, **kw):
    base = dict(ready=True, htf_trend="up", trend=PillarView("trend", ""), momentum=PillarView("momentum", ""),
                bar=bar, prev_bar=prev or bar, vwap=25000.0, ema20_5m=25010.0, atr_5m=30.0,
                or_high=25050.0, or_low=24980.0, volume_ratio_5m=2.0)
    base.update(kw)
    return TechView(**base)


def snap_for(t: TechView, now=ist(2026, 10, 16, 10, 0), flow_bias=1, oi_features=None, chain=None, state=None):
    ref = SimpleNamespace(future_token=9001, spot_token=NIFTY_SPOT_TOKEN)
    ctx = SimpleNamespace(now=now, ref=ref, state=state or MarketState(TODAY))
    return SimpleNamespace(tech=t, ctx=ctx, flow=PillarView("futures_flow", "", bias=flow_bias, strength=0.8),
                           oi=PillarView("option_chain", "", features=oi_features or {}), chain=chain, basis=60.0)


def test_candle_quality_and_bounded_invalidation():
    assert candle_quality({"open": 100, "high": 110, "low": 99, "close": 109}, 1) == "pass"
    assert candle_quality({"open": 100, "high": 110, "low": 95, "close": 105}, 1) == "warn"   # body 33% of range
    assert candle_quality({"open": 104, "high": 110, "low": 95, "close": 100}, 1) == "fail"
    assert bounded_invalidation(100, 99.5, 1, atr=10) == 95          # at least 0.5 ATR away
    assert bounded_invalidation(100, 60, 1, atr=10) == 85            # at most 1.5 ATR away
    assert bounded_invalidation(100, 112, -1, atr=10) == 112


def test_s1_trend_pullback_both_directions():
    bull = TrendPullback().detect(snap_for(tech({"open": 25002, "high": 25040, "low": 24998, "close": 25036})))
    assert bull.side == 1 and bull.invalidation < bull.trigger and bull.tf == "5min"
    bear_t = tech({"open": 25008, "high": 25012, "low": 24960, "close": 24965}, htf_trend="down")
    bear = TrendPullback().detect(snap_for(bear_t))
    assert bear.side == -1 and bear.invalidation > bear.trigger
    no_touch = tech({"open": 25080, "high": 25120, "low": 25070, "close": 25110})
    assert TrendPullback().detect(snap_for(no_touch)) is None
    assert TrendPullback().detect(snap_for(tech({"open": 25002, "high": 25040, "low": 24998, "close": 25036},
                                                htf_trend="flat"))) is None


def test_s2_orb_needs_a_fresh_cross_inside_the_window():
    bar, prev = {"open": 25040, "high": 25075, "low": 25038, "close": 25070}, {"open": 25030, "high": 25048, "low": 25020, "close": 25045}
    c = OpeningRangeBreakout().detect(snap_for(tech(bar, prev)))
    assert c.side == 1 and c.trigger_quality == "pass" and "opening range 25,050" in c.note
    assert OpeningRangeBreakout().detect(snap_for(tech(bar, bar))) is None                       # already above
    assert OpeningRangeBreakout().detect(snap_for(tech(bar, prev), now=ist(2026, 10, 16, 12, 0))) is None
    weak = OpeningRangeBreakout().detect(snap_for(tech(bar, prev, volume_ratio_5m=1.0)))
    assert weak.trigger_quality == "warn"


def _spot_state(prev_close, close):
    s = MarketState(TODAY)
    s.add_bars([{"instrument_token": NIFTY_SPOT_TOKEN, "ts": ist(2026, 10, 16, 10, 0) + timedelta(minutes=i),
                 "open": px, "high": px, "low": px, "close": px, "volume_day": None, "oi": None}
                for i, px in enumerate([prev_close] * 5 + [close] * 5)])
    return s


def test_s3_oi_wall_break_requires_writers_covering():
    def chain(oi, oi_15m):
        row = ChainRow(25100, "CE", 1, "NIFTY26OCT25100CE", 65, 50, 49.9, 50.1, oi, oi, oi_15m, oi_15m)
        return Chain(None, 25100, 50, {(25100, "CE"): row})

    t = tech({"open": 25140, "high": 25175, "low": 25138, "close": 25170})
    feats = {"call_wall_30m": 25100, "call_wall": 25150}
    covering = snap_for(t, oi_features=feats, chain=chain(900_000, 1_000_000), state=_spot_state(25090, 25110))
    c = OIWallBreak().detect(covering)
    assert c.side == 1 and "25100 CE wall" in c.note and c.trigger_quality == "pass"
    defending = snap_for(t, oi_features=feats, chain=chain(1_100_000, 1_000_000), state=_spot_state(25090, 25110))
    assert OIWallBreak().detect(defending) is None
    no_cross = snap_for(t, oi_features=feats, chain=chain(900_000, 1_000_000), state=_spot_state(25110, 25120))
    assert OIWallBreak().detect(no_cross) is None


def test_p1_daily_trend_continuation():
    s = MarketState(TODAY)
    days = [date(2026, 7, 1) + timedelta(days=i) for i in range(70)]
    s.load_daily(NIFTY_SPOT_TOKEN, [{"date": d, "open": 24000 + 10 * i, "high": 24050 + 10 * i, "low": 23950 + 10 * i,
                                     "close": 24020 + 10 * i, "volume": 0} for i, d in enumerate(days)])
    prev_high = 24050 + 10 * 69
    s.add_bars([{"instrument_token": NIFTY_SPOT_TOKEN, "ts": ist(2026, 10, 16, 9, 15), "open": prev_high - 20,
                 "high": prev_high + 60, "low": prev_high - 40, "close": prev_high + 50, "volume_day": None, "oi": None}])
    ctx = SimpleNamespace(now=ist(2026, 10, 16, 15, 10), ref=SimpleNamespace(spot_token=NIFTY_SPOT_TOKEN, future_token=9001),
                          state=s, day_open_value=lambda *a: None, value_at=lambda *a: None)
    snap = SimpleNamespace(ctx=ctx, flow=PillarView("futures_flow", "", bias=1, strength=0.8))
    c = DailyTrendContinuation().detect(snap)
    assert c.side == 1 and c.horizon == "positional" and c.tf == "day" and c.room_unit > 0
    ctx.now = ist(2026, 10, 16, 11, 0)
    assert DailyTrendContinuation().detect(snap) is None                  # only near the close


def test_bucket_end():
    assert bucket_end(ist(2026, 10, 16, 9, 20, 5)) == ist(2026, 10, 16, 9, 20)
    assert bucket_end(ist(2026, 10, 16, 9, 20, 2)) is None                 # bars not flushed yet
    assert bucket_end(ist(2026, 10, 16, 9, 17)) is None
    assert bucket_end(ist(2026, 10, 16, 10, 33, 30)) == ist(2026, 10, 16, 10, 30)


# ── End to end ───────────────────────────────────────────────────────────────

class AlwaysBull:
    id, label, horizon = "S1_TREND_PULLBACK", "S1 Trend pullback", "intraday"
    regimes = frozenset({"trend", "range", "neutral", "chop"})

    def detect(self, snap):
        f = snap.ctx.fut
        return Candidate(self.id, 1, "intraday", f, f - 30, snap.ctx.ref.future_token, "5min", "pass", "test trigger",
                         room=150, room_unit=30, room_label="test level")


@pytest.fixture
def engine(tmp_path):
    ctx = build_market(trend=1)
    quotes = {}
    store = Store(make_engine(f"sqlite:///{tmp_path}/o.db"))
    notifier = RecordingNotifier()
    eng = SignalEngine({"NIFTY": ctx.ref}, ctx.state, store, notifier, OptionsSettings(), ctx.calendar,
                       vix_token=ctx.vix_token, constituents={"NIFTY": ctx.constituents},
                       vix_history=ctx.vix_history, events=[], quote_fn=lambda t: quotes.get(t, (None, None)),
                       now_fn=lambda: ctx.now, setups=[AlwaysBull()])
    return eng, ctx, store, notifier, quotes


def test_engine_creates_saves_and_tracks_a_signal(engine):
    eng, ctx, store, notifier, quotes = engine
    eng.evaluate(ctx.now)
    [sig] = store.signals_since(ctx.now - timedelta(hours=1))
    assert sig.signal_id == "NF-261016-001" and sig.grade.value == "A" and sig.mode == "SHADOW"
    assert sig.action.value == "BUY_CE" and sig.contract.right == "CE" and sig.contract.expiry == ctx.ref.expiries[0]
    assert sig.lots == 1 and not sig.over_budget and sig.risk_rupees <= 3000
    card = notifier.texts()[-1]
    assert "BUY CE · NIFTY" in card and sig.contract.tradingsymbol in card and "Analysis" in card
    assert store.load_board("NIFTY")["pillars"]

    eng.evaluate(ctx.now)                                                  # same setup/side: not repeated
    assert len(store.signals_since(ctx.now - timedelta(hours=1))) == 1

    tok = sig.contract.token
    quotes[tok] = (sig.entry_high - 1, sig.entry_high - 0.5)
    eng.on_tick(ctx.now + timedelta(seconds=10))
    assert eng.open[0].state is SignalState.ACTIVE
    quotes[tok] = (sig.t2 + 1, sig.t2 + 1.5)
    eng.on_tick(ctx.now + timedelta(seconds=20))                           # T1 first …
    eng.on_tick(ctx.now + timedelta(seconds=21))                           # … then T2 on the next quote
    final = store.get_signal(sig.signal_id)
    assert final.state is SignalState.CLOSED and final.exit_reason == "T2_HIT" and final.pnl_rupees > 0
    kinds = [e["kind"] for e in store.signal_history(sig.signal_id)]
    assert kinds == ["CREATED", "ENTRY_FILLED", "T1_HIT", "T2_HIT"]
    assert eng.open == []
    assert "1 trades" in eng.end_of_day(ctx.now + timedelta(hours=5))


def test_engine_logs_no_trade_reasons(engine):
    eng, ctx, store, notifier, _ = engine
    late = ctx.now.replace(hour=15, minute=5)
    eng.evaluate(late)                                                     # outside the intraday entry window
    assert store.signals_since(ctx.now - timedelta(hours=8)) == []
    [ev] = store.evaluations_since(ctx.now - timedelta(hours=8))
    assert ev["outcome"] == "NO_TRADE" and "outside the entry window" in ev["reasons"]


def test_close_session_never_carries_intraday_signals_overnight(engine):
    eng, ctx, store, _, quotes = engine
    eng.evaluate(ctx.now)
    sig = eng.open[0]
    quotes[sig.contract.token] = (sig.entry_high - 1, sig.entry_high - 0.5)
    eng.on_tick(ctx.now + timedelta(seconds=10))                           # filled
    eng.close_session(ctx.now.replace(hour=15, minute=31))
    final = store.get_signal(sig.signal_id)
    assert final.state is SignalState.CLOSED and final.exit_reason == "SQUARE_OFF"
    assert eng.open == [] and store.open_signals() == []

from datetime import timedelta

import pytest

from options.agents import breadth, events, futures_flow, macro, option_chain, regime, technical, volatility
from options.agents.option_chain import Chain, ChainRow
from options.agents.technical import TechView
from options.core.events import Event
from options.core.schemas import PillarView
from tests.options.fixtures import ist
from tests.options.market import IV, build_market


@pytest.fixture(scope="module")
def bull():
    return build_market(trend=1, oi_flow=1, writing=1, breadth=1)


@pytest.fixture(scope="module")
def bear():
    return build_market(trend=-1, oi_flow=1, writing=-1, breadth=-1, seed=3, drift_day=0.008)


def test_pillar_view_check_for_side():
    v = PillarView("trend", "x", bias=1, strength=0.8)
    assert v.check_for(1).status == "pass" and v.check_for(-1).status == "fail"
    assert PillarView("trend", "x", bias=1, strength=0.3).check_for(1).status == "warn"
    assert PillarView("trend", "x").check_for(1).status == "warn"
    assert PillarView("events", "x", status="fail").check_for(1).status == "fail"


def test_technical_reads_trend_levels_and_momentum(bull, bear):
    tv = technical.analyse(bull)
    assert tv.ready and tv.htf_trend == "up" and tv.trend.check_for(1).status == "pass"
    assert {"PDH", "PDL", "PDC", "CPR top", "OR high", "OR low", "VWAP"} <= tv.levels.keys()
    assert tv.atr_5m > 0 and tv.vwap
    dist, name = tv.room(1, bull.fut)
    assert dist is None or dist > 0
    assert technical.analyse(bear).htf_trend == "down"


def test_technical_warms_up_without_history():
    ctx = build_market(today_minutes=20)
    ctx.state._rows.pop(ctx.ref.future_token)
    tv = technical.analyse(ctx)
    assert not tv.ready and tv.trend.bias == 0


@pytest.mark.parametrize("dp,doi,label,bias", [
    (0.2, 0.5, "long buildup", 1), (0.2, -0.5, "short covering", 1),
    (-0.2, 0.5, "short buildup", -1), (-0.2, -0.5, "long unwinding", -1),
    (0.01, 0.5, "no clear flow", 0),
])
def test_buildup_classification(dp, doi, label, bias):
    got = futures_flow.classify(dp, doi)
    assert got[0] == label and got[1] == bias


def test_futures_flow_and_basis(bull):
    v = futures_flow.analyse(bull)
    assert v.bias == 1 and "long buildup" in v.detail
    assert v.features["basis"] == pytest.approx(60, abs=1)


def test_chain_volatility_and_writing(bull, bear):
    chain = option_chain.build_chain(bull, bull.ref.expiries[0])
    vol = volatility.analyse(bull, chain)
    assert vol.atm_iv == pytest.approx(IV, abs=0.005)
    assert vol.vix_pct == pytest.approx(20, abs=2) and vol.pillar.status == "pass"
    atm = chain.get(chain.atm, "CE")
    assert 0.4 < atm.greeks["delta"] < 0.6
    v = option_chain.analyse(bull, chain, vol.expected_move_1d)
    assert v.bias == 1 and "put writing" in v.detail
    bear_chain = option_chain.build_chain(bear, bear.ref.expiries[0])
    volatility.analyse(bear, bear_chain)
    assert option_chain.analyse(bear, bear_chain).bias == -1


def test_max_pain():
    rows = {(k, rt): ChainRow(k, rt, 1, "X", 65, 1, 1, 1, oi, oi, oi, oi)
            for k, rt, oi in [(100, "CE", 10), (110, "CE", 100), (90, "PE", 100), (100, "PE", 10)]}
    assert option_chain.max_pain(Chain(None, 100, 10, rows)) == 100


def test_option_quality():
    row = ChainRow(25000, "CE", 1, "X", 65, 100, 99.5, 100.5, 1, 1, 1, 1, greeks={"theta_day": -5})
    assert volatility.option_quality(row).status == "pass"                  # 0.4% decay per 2h
    row.bid, row.ask = 98.8, 101.2                                         # 2.4% spread
    assert volatility.option_quality(row).status == "warn"
    row.bid, row.ask = 99.5, 100.5
    row.greeks["theta_day"] = -60                                          # 5% per 2h: expiry-week ATM
    assert volatility.option_quality(row).status == "fail"
    row.greeks["theta_day"] = -10                                          # 10% per day held
    assert volatility.option_quality(row, "positional").status == "warn"


def test_breadth(bull, bear):
    assert breadth.analyse(bull).bias == 1
    assert breadth.analyse(bear).bias == -1


def test_macro_snapshot_and_fetcher(bull):
    assert macro.analyse(bull).status == "na"
    fetcher = macro.MacroFetcher(fetch=lambda: {"S&P 500 fut": 0.8, "Nikkei": 0.6, "Brent": -0.5},
                                 now_fn=lambda: bull.now)
    fetcher.refresh()
    bull.macro = fetcher.snapshot()
    v = macro.analyse(bull)
    assert v.bias == 1 and "S&P 500 fut +0.8%" in v.detail
    bull.macro = None


def test_events_windows(bull):
    now = bull.now
    bull.events = [Event("RBI MPC decision", now + timedelta(minutes=20))]
    v = events.analyse(bull)
    assert v.window_active and v.pillar.status == "fail" and v.blocks_positional
    bull.events = [Event("RBI MPC decision", now + timedelta(hours=2))]
    assert events.analyse(bull).pillar.status == "warn"
    bull.events = [Event("US FOMC decision", ist(2026, 10, 19, 23, 30))]     # after hours, within 2 sessions
    v = events.analyse(bull)
    assert v.pillar.status == "pass" and v.blocks_positional
    bull.events = []


def test_regime_classification_and_timing(bull):
    base = dict(ready=True, trend=PillarView("trend", ""), momentum=PillarView("momentum", ""))
    assert regime.classify(TechView(htf_trend="up", adx_15m=30, **base)) == "trend"
    assert regime.classify(TechView(htf_trend="flat", adx_15m=15, bb_width_15m=0.002, bb_width_median=0.003, **base)) == "range"
    assert regime.classify(TechView(htf_trend="flat", adx_15m=12, bb_width_15m=0.004, bb_width_median=0.003, **base)) == "chop"
    assert regime.classify(TechView(htf_trend="flat", adx_15m=None, **base)) == "neutral"
    rv = regime.analyse(bull, technical.analyse(bull))
    assert rv.phase == "main" and rv.timing.status == "pass" and not rv.expiry_day


def _vol_with(bull, vix_pct, atm_iv, rv20, monkeypatch):
    """The volatility pillar for a given VIX rank, ATM IV and realised vol."""
    monkeypatch.setattr(volatility, "percentile_rank", lambda v, h: vix_pct)
    monkeypatch.setattr(volatility, "realized_vol", lambda closes, window=20: rv20)
    chain = option_chain.build_chain(bull, bull.ref.expiries[0])
    real = volatility.price_chain

    def priced(ctx, ch):
        fwd, t = real(ctx, ch)
        for row in ch.rows.values():
            if row.greeks:
                row.greeks["iv"] = atm_iv
        return fwd, t
    monkeypatch.setattr(volatility, "price_chain", priced)
    return volatility.analyse(bull, chain).pillar


def test_a_high_vix_rank_alone_no_longer_blocks_a_buy(bull, monkeypatch):
    # 5 Nov 2026: VIX at its 73rd percentile, ATM IV 15.6% below realised 16.0%: fairly priced
    p = _vol_with(bull, 73, 0.156, 0.160, monkeypatch)
    assert p.status == "warn" and "IV/RV 0.97" in p.detail


def test_premium_well_above_realised_moves_still_blocks_a_buy(bull, monkeypatch):
    assert _vol_with(bull, 40, 0.20, 0.14, monkeypatch).status == "fail"               # IV/RV 1.43
    assert _vol_with(bull, 30, 0.12, 0.13, monkeypatch).status == "pass"               # cheap and calm
    assert _vol_with(bull, 30, 0.155, 0.13, monkeypatch).status == "warn"              # IV/RV 1.19


def test_without_realised_vol_only_an_extreme_vix_rank_blocks(bull, monkeypatch):
    assert _vol_with(bull, 80, 0.15, None, monkeypatch).status == "warn"
    assert _vol_with(bull, 95, 0.15, None, monkeypatch).status == "fail"


def test_target_one_skips_levels_closer_than_one_atr():
    from options.agents.technical import TechView
    from options.engine.levels import target_room
    t = TechView.__new__(TechView)
    t.atr_5m, t.levels = 20.0, {"minor swing": 24_505.0, "PDH": 24_560.0}
    assert t.room(1, 24_500.0) == (5.0, "minor swing")                  # the levels pillar still sees it
    assert target_room(t, 1, 24_500.0) == 60.0                         # the target goes to the next real level

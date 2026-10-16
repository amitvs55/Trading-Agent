from datetime import date, time

import pytest

from options.agents.option_chain import build_chain
from options.agents.volatility import price_chain
from options.core.calendar import NseCalendar
from options.core.schemas import Action, Contract, Grade, PillarCheck, Signal, SignalState
from options.delivery import cards
from options.engine import costs, grading, lifecycle, performance
from options.engine.levels import TICK, plan
from options.engine.risk import RiskConfig, budget_gate, size
from options.engine.selection import pick_expiry, pick_strike
from tests.options.fixtures import MONTHLY, WEEKLY, ist
from tests.options.market import build_market

CAL = NseCalendar()


# ── Costs and risk ───────────────────────────────────────────────────────────

def test_round_trip_charges():
    c = costs.charges(buy_value=10_000, sell_value=12_000, orders=2)
    assert c.brokerage == 40 and c.stt == pytest.approx(18.0) and c.stamp == pytest.approx(0.3)
    assert c.exchange == pytest.approx(22_000 * 0.03503 / 100)
    assert c.gst == pytest.approx((40 + c.exchange + c.sebi) * 0.18)
    assert c.total == pytest.approx(74.62, abs=0.05)


def test_sizing_and_over_budget():
    cfg = RiskConfig()                                   # ₹1L, 3% → ₹3,000 per trade
    s = size(cfg, entry_high=116, stop=100, lot_size=65)
    assert (s.lots, s.over_budget) == (1, False) and s.risk_rupees == pytest.approx(16 * 65)
    big = size(cfg, entry_high=150, stop=100, lot_size=65)
    assert big.over_budget and big.lots == 1 and big.risk_rupees == pytest.approx(3250)
    assert size(cfg, 135, 100, 65, positional=True).over_budget         # 35 × 65 × 1.5 gap buffer = ₹3,412
    assert size(cfg, 120, 100, 65, positional=True).over_budget is False  # 20 × 65 × 1.5 = ₹1,950


def test_budget_gate():
    cfg = RiskConfig()                                   # daily stop ₹10,000
    assert budget_gate(cfg, -10_000, 0, 1000, 0, 0, False).startswith("daily loss stop hit")
    assert "could breach" in budget_gate(cfg, -8_000, 0, 2_500, 0, 0, False)
    assert budget_gate(cfg, -3_000, 0, 2_500, 1, 0, False) == "an intraday signal is already open"
    assert budget_gate(cfg, -3_000, 0, 2_500, 1, 0, True) is None
    assert budget_gate(cfg, 5_000, 0, 2_500, 0, 1, True) == "a positional signal is already open"


# ── Selection and levels ─────────────────────────────────────────────────────

def test_pick_expiry_respects_trading_days_left():
    exps = [WEEKLY, MONTHLY]
    assert pick_expiry(exps, date(2026, 10, 16), "intraday", CAL) == WEEKLY
    assert pick_expiry(exps, date(2026, 10, 16), "positional", CAL) == MONTHLY
    assert pick_expiry(exps, WEEKLY, "intraday", CAL) == MONTHLY             # expiry day → next expiry
    assert pick_expiry(exps, MONTHLY, "intraday", CAL) is None


@pytest.fixture(scope="module")
def priced():
    ctx = build_market()
    chain = build_chain(ctx, WEEKLY)
    fwd, t = price_chain(ctx, chain)
    return ctx, chain, fwd, t


def test_pick_strike_in_delta_band(priced):
    _, chain, *_ = priced
    ce, why = pick_strike(chain, 1)
    assert ce.right == "CE" and 0.40 <= ce.greeks["delta"] <= 0.55 and why == ""
    pe, _ = pick_strike(chain, -1)
    assert pe.right == "PE" and 0.40 <= -pe.greeks["delta"] <= 0.55
    none, why = pick_strike(chain, 1, min_oi=10 ** 12)
    assert none is None and "illiquid" in why


def test_trade_plan_in_premium_terms(priced):
    ctx, chain, fwd, t = priced
    row, _ = pick_strike(chain, 1)
    p = plan(row, 1, "intraday", trigger=ctx.fut, invalidation=ctx.fut - 30, forward=fwd, t=t, r=ctx.r, room=120)
    assert p.entry_low <= row.mid <= p.entry_high
    assert p.stop >= p.entry_high * 0.70 - 1e-9 and p.stop < p.entry_high
    assert p.entry_high < p.t1 < p.t2
    assert p.rr1 > 1.3 and p.t1_points == 120 and p.t2_points == max(1.6 * 120, 2.5 * 30)
    for x in (p.entry_low, p.entry_high, p.stop, p.t1, p.t2):
        assert round(x / TICK, 6).is_integer()


# ── Grading ──────────────────────────────────────────────────────────────────

def pc(status, pillar="x"):
    return PillarCheck(pillar=pillar, status=status, detail="")


def all_pillars(status="pass", **over):
    names = list(grading.PILLAR_WEIGHTS) + ["option_quality", "events", "news"]
    return {n: pc(over.get(n, status), n) for n in names}


def test_grade_thresholds_and_hard_conflicts():
    ok = [grading.Gate("x", True)]
    assert grading.grade(all_pillars(), ok)[:2] == (Grade.A, 100)
    b = all_pillars(option_chain="fail", breadth="warn", volatility="warn")   # 100 − 15 − 5 − 5 = 75 → A
    assert grading.grade(b, ok)[0] is Grade.A
    b2 = all_pillars(option_chain="fail", breadth="fail", volatility="warn")  # 70 → B
    assert grading.grade(b2, ok)[0] is Grade.B
    assert grading.grade(all_pillars(trend="fail"), ok)[0] is Grade.C
    assert grading.grade(all_pillars(futures_flow="fail"), ok)[0] is Grade.C
    g, _, reasons = grading.grade(all_pillars(), [grading.Gate("min_rr", False, "reward:risk too low")])
    assert g is None and reasons == ["reward:risk too low"]


# ── Lifecycle ────────────────────────────────────────────────────────────────

def make_signal(lots=1, horizon="intraday", **kw) -> Signal:
    base = dict(
        signal_id="NF-261016-001", created_at=ist(2026, 10, 16, 10, 0), index="NIFTY", setup="S1_TREND_PULLBACK",
        horizon=horizon, action=Action.BUY_CE, grade=Grade.A, score=80,
        contract=Contract(index="NIFTY", tradingsymbol="NIFTY26OCT25300CE", token=1, expiry=WEEKLY, strike=25300,
                          right="CE", lot_size=65),
        entry_low=139, entry_high=144, stop_loss=104, invalidation=25200, invalidation_rule="fut 5m close below 25,200",
        t1=190, t2=238, valid_until=ist(2026, 10, 16, 10, 15), time_stop=time(14, 45), lots=lots,
        risk_rupees=40 * 65 * lots, checks=[])
    base.update(kw)
    return Signal(**base)


def test_fill_t1_trail_and_target():
    s = make_signal()
    t = ist(2026, 10, 16, 10, 1)
    assert lifecycle.on_quote(s, 141, 145, t) is None                       # ask above the entry band
    assert lifecycle.on_quote(s, 141, 143, t).kind == "ENTRY_FILLED" and s.fill_price == 143
    u = lifecycle.on_quote(s, 192, 193, t)
    assert u.kind == "T1_HIT" and s.state is SignalState.T1_HIT
    assert s.stop_loss == pytest.approx(143 + 0.5 * (192 - 143))            # 1 lot: half the gain locked
    lifecycle.on_quote(s, 230, 231, t)
    assert s.stop_loss == pytest.approx(max(167.5, 230 * 0.8))
    done = lifecycle.on_quote(s, 239, 240, t)
    assert done.kind == "T2_HIT" and s.state is SignalState.CLOSED
    gross = (239 - 143) * 65
    assert s.pnl_rupees == pytest.approx(gross - costs.charges(143 * 65, 239 * 65, 2).total)
    assert s.r_multiple == pytest.approx(s.pnl_rupees / ((143 - 104) * 65), abs=0.01)


def test_stop_loss_and_two_lot_partial_booking():
    s = make_signal()
    lifecycle.on_quote(s, 140, 142, ist(2026, 10, 16, 10, 1))
    u = lifecycle.on_quote(s, 103, 104, ist(2026, 10, 16, 10, 20))
    assert u.kind == "SL_HIT" and s.pnl_rupees < 0 and s.r_multiple < -0.9

    two = make_signal(lots=2)
    lifecycle.on_quote(two, 140, 142, ist(2026, 10, 16, 10, 1))
    lifecycle.on_quote(two, 191, 192, ist(2026, 10, 16, 10, 30))
    assert two.booked_t1 == 191 and two.stop_loss == 142
    u = lifecycle.on_quote(two, 141, 142, ist(2026, 10, 16, 11, 0))
    assert u.kind == "TRAIL_STOP"
    gross = (191 - 142) * 65 + (141 - 142) * 65
    assert two.pnl_rupees == pytest.approx(gross - costs.charges(142 * 130, 191 * 65 + 141 * 65, 3).total)


def test_expiry_cancellation_and_exits():
    s = make_signal()
    assert lifecycle.on_quote(s, 150, 151, ist(2026, 10, 16, 10, 16)).kind == "EXPIRED"
    c = make_signal()
    assert lifecycle.on_close_check(c, 25190, 140, ist(2026, 10, 16, 10, 5)).kind == "CANCELLED"

    a = make_signal()
    lifecycle.on_quote(a, 140, 142, ist(2026, 10, 16, 10, 1))
    assert lifecycle.on_close_check(a, 25250, 150, ist(2026, 10, 16, 11, 0)) is None
    assert lifecycle.on_close_check(a, 25195, 120, ist(2026, 10, 16, 11, 5)).kind == "INVALIDATED"
    b = make_signal()
    lifecycle.on_quote(b, 140, 142, ist(2026, 10, 16, 10, 1))
    assert lifecycle.on_close_check(b, 25250, 150, ist(2026, 10, 16, 14, 45)).kind == "TIME_STOP"
    p = make_signal(horizon="positional", time_stop=None, exit_by=date(2026, 10, 21),
                    valid_until=ist(2026, 10, 16, 15, 25))
    lifecycle.on_quote(p, 140, 142, ist(2026, 10, 16, 15, 12))
    assert lifecycle.on_close_check(p, 25250, 150, ist(2026, 10, 19, 15, 20)) is None
    assert lifecycle.on_close_check(p, 25250, 150, ist(2026, 10, 21, 15, 15)).kind == "TIME_STOP"
    e = make_signal()
    assert lifecycle.exit_now(e, 140, ist(2026, 10, 16, 10, 2), "EXIT_SIGNAL").kind == "CANCELLED"


# ── Performance and cards ────────────────────────────────────────────────────

def closed(pnl, r, minute, setup="S1_TREND_PULLBACK"):
    s = make_signal(setup=setup)
    s.state, s.pnl_rupees, s.r_multiple = SignalState.CLOSED, pnl, r
    s.closed_at = ist(2026, 10, 16, 10, minute)
    return s


def test_performance_stats():
    sigs = [closed(3000, 1.2, 1), closed(-2000, -1.0, 2), closed(-1500, -0.6, 3), closed(4000, 1.6, 4),
            closed(1000, 0.4, 5, setup="S2_ORB")]
    sigs.append(make_signal())                                             # open: ignored
    st = performance.stats(sigs)
    assert st["trades"] == 5 and st["wins"] == 3 and st["win_rate"] == pytest.approx(0.6)
    assert st["total_rupees"] == 4500 and st["max_drawdown_rupees"] == 3500
    assert st["profit_factor"] == pytest.approx(8000 / 3500)
    assert set(performance.by(sigs, "setup")) == {"S1_TREND_PULLBACK", "S2_ORB"}
    assert performance.stats([])["trades"] == 0
    assert "5 trades" in performance.summary_line(st)


def test_signal_card_content():
    s = make_signal(checks=[PillarCheck(pillar="trend", status="pass", detail="15m ↑ <b>"),
                            PillarCheck(pillar="macro", status="na", detail="No data")])
    text = cards.signal_card(s, 100_000, "42 trades · 52% wins")
    assert "BUY CE · NIFTY" in text and "Grade A" in text and "SHADOW TEST" in text
    assert "NIFTY26OCT25300CE" in text and "104.00" in text and "lock half the gain" in text
    assert "&lt;b&gt;" in text                                              # details are escaped
    assert "42 trades" in text and "2.6% of capital" in text
    upd = cards.update_message(s, "T1_HIT", "T1 hit @ 190")
    assert upd.startswith("🎯")

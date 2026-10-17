"""Confluence grading: every pillar checked for the candidate's direction (plan §5).

Gates are pass/fail with a reason; any failure means NO TRADE. The score weights
direction-confirming pillars; Trend or Futures flow against the trade caps it at C.
"""

from dataclasses import dataclass

from options.agents.option_chain import ChainRow
from options.agents.volatility import option_quality
from options.core.schemas import Grade, PillarCheck
from options.engine.levels import TradePlan
from options.setups.base import Candidate

PILLAR_WEIGHTS = {"trend": 15, "futures_flow": 15, "option_chain": 15, "trigger": 10, "levels": 10,
                  "volatility": 10, "breadth": 10, "momentum": 5, "macro": 5, "timing": 5}
STATUS_POINTS = {"pass": 1.0, "warn": 0.5, "na": 0.5, "fail": 0.0}
DISPLAY_ORDER = ["trend", "trigger", "levels", "momentum", "futures_flow", "option_chain", "volatility",
                 "option_quality", "breadth", "macro", "events", "news", "timing"]
GRADE_A, GRADE_B = 75, 60
MIN_RR = 1.3
MAX_DATA_AGE_S = 180


def levels_check(snap, cand: Candidate) -> PillarCheck:
    if cand.room_unit:                          # positional setups measure room in daily ATRs
        room, unit, label = cand.room, cand.room_unit, cand.room_label
    else:
        room, label = snap.tech.room(cand.side, cand.trigger)
        unit = snap.tech.atr_5m
    if room is None:
        return PillarCheck(pillar="levels", status="pass", detail="open space: no level in the way")
    ratio = room / unit if unit else 0
    status = "pass" if ratio >= 1.0 else "warn" if ratio >= 0.5 else "fail"
    return PillarCheck(pillar="levels", status=status, detail=f"room to {label}: {room:,.0f} pts ({ratio:.1f}× ATR)")


def checks(snap, cand: Candidate, row: ChainRow) -> dict[str, PillarCheck]:
    s = cand.side
    out = {
        "trend": snap.tech.trend.check_for(s),
        "trigger": PillarCheck(pillar="trigger", status=cand.trigger_quality, detail=cand.note),
        "levels": levels_check(snap, cand),
        "momentum": snap.tech.momentum.check_for(s),
        "futures_flow": snap.flow.check_for(s),
        "option_chain": snap.oi.check_for(s),
        "volatility": snap.vol.pillar.check_for(s),
        "option_quality": option_quality(row, cand.horizon),
        "breadth": snap.breadth.check_for(s),
        "macro": snap.macro.check_for(s),
        "events": snap.events.pillar.check_for(s),
        "news": snap.news.check_for(s),
        "timing": snap.regime.timing.check_for(s),
    }
    return out


@dataclass(frozen=True)
class Gate:
    name: str
    ok: bool
    reason: str = ""


def gates(snap, cand: Candidate, setup_regimes: frozenset[str], pillar: dict[str, PillarCheck],
          trade: TradePlan, budget_reason: str | None) -> list[Gate]:
    ctx = snap.ctx
    as_of = ctx.state.as_of()
    age = (ctx.now - as_of).total_seconds() if as_of else None
    now_t = ctx.now.time()
    if cand.horizon == "intraday":
        session_ok = snap.regime.phase in ("opening", "main", "late") and now_t.hour < 15
        event_ok = not snap.events.window_active
    else:
        session_ok = snap.regime.phase == "closing"
        event_ok = not snap.events.blocks_positional
    return [
        Gate("data_fresh", age is not None and age <= MAX_DATA_AGE_S, "market data is stale"),
        Gate("session_open", session_ok, "outside the entry window"),
        Gate("no_event_window", event_ok, "high-impact event window"),
        Gate("no_fresh_news", pillar["news"].status != "fail", pillar["news"].detail),
        Gate("liquidity", pillar["option_quality"].status != "fail", "contract spread or decay too high"),
        Gate("premium_not_rich", pillar["volatility"].status != "fail", "option premium too expensive to buy"),
        Gate("min_rr", trade.rr1 >= MIN_RR, f"reward:risk to T1 {trade.rr1:.2f} < {MIN_RR}"),
        Gate("risk_budget", budget_reason is None, budget_reason or ""),
        Gate("regime_allows_setup", snap.regime.regime in setup_regimes, f"{snap.regime.regime} regime"),
    ]


def grade(pillar: dict[str, PillarCheck], gate_list: list[Gate]) -> tuple[Grade | None, float, list[str]]:
    failed = [g.reason for g in gate_list if not g.ok]
    score = sum(w * STATUS_POINTS[pillar[p].status] for p, w in PILLAR_WEIGHTS.items())
    if failed:
        return None, score, failed
    if pillar["trend"].status == "fail" or pillar["futures_flow"].status == "fail" or score < GRADE_B:
        return Grade.C, score, []
    return (Grade.A if score >= GRADE_A else Grade.B), score, []


def ordered(pillar: dict[str, PillarCheck]) -> list[PillarCheck]:
    return [pillar[p] for p in DISPLAY_ORDER if p in pillar]

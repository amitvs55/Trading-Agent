"""Regime & session agent: market regime, session phase, expiry-day flags, timing pillar."""

from dataclasses import dataclass

from options.agents.context import AgentContext
from options.agents.technical import TechView
from options.core.schemas import PillarView


@dataclass
class RegimeView:
    regime: str             # trend | range | chop | neutral
    phase: str
    expiry_day: bool        # nearest NIFTY weekly expires today
    monthly_expiry: bool    # last Tuesday: all three indices expire
    timing: PillarView
    detail: str


def classify(tech: TechView) -> str:
    adx, bbw, med = tech.adx_15m, tech.bb_width_15m, tech.bb_width_median
    if adx is None:
        return "neutral"
    if adx >= 25 and tech.htf_trend in ("up", "down"):
        return "trend"
    if adx < 20 and bbw is not None and med is not None and bbw <= med:
        return "range"
    if adx < 15 and bbw is not None and med is not None and bbw > med:
        return "chop"
    return "neutral"


def analyse(ctx: AgentContext, tech: TechView) -> RegimeView:
    regime = classify(tech)
    phase = ctx.calendar.session_phase(ctx.now)
    today = ctx.now.date()
    expiry_day = bool(ctx.ref.expiries) and ctx.ref.expiries[0] == today
    monthly = ctx.ref.future_expiry == today

    status = {"main": "pass", "opening": "warn", "late": "warn"}.get(phase, "fail")
    notes = [phase.replace("_", " ")]
    if monthly:
        notes.append("monthly expiry day")
        status = "warn" if status == "pass" else status
    elif expiry_day:
        notes.append("weekly expiry day")
        status = "warn" if status == "pass" else status
    adx = f", ADX {tech.adx_15m:.0f}" if tech.adx_15m is not None else ""
    detail = f"{regime}{adx}"
    return RegimeView(regime, phase, expiry_day, monthly,
                      PillarView("timing", " · ".join(notes), status=status), detail)

"""Events agent (pillar 11): scheduled-event windows. Pillar 12 (news) has no feed yet."""

from dataclasses import dataclass
from datetime import timedelta

from options.agents.context import AgentContext
from options.core.calendar import IST, MARKET_CLOSE, at_ist
from options.core.events import Event
from options.core.schemas import PillarView

BEFORE = timedelta(minutes=30)
AFTER = timedelta(minutes=15)


@dataclass
class EventView:
    pillar: PillarView
    window_active: bool
    next_event: Event | None
    blocks_positional: bool


def analyse(ctx: AgentContext, positional_days: int = 2) -> EventView:
    now = ctx.now.astimezone(IST)
    upcoming = sorted((e for e in ctx.events if e.at + AFTER >= now), key=lambda e: e.at)
    active = next((e for e in upcoming if e.during_market and e.at - BEFORE <= now <= e.at + AFTER), None)
    later_today = next((e for e in upcoming if e.at.astimezone(IST).date() == now.date()
                        and e.during_market and e.at > now), None)

    horizon_day = now.date()
    for _ in range(positional_days):
        horizon_day = ctx.calendar.next_trading_day(horizon_day)
    horizon_end = at_ist(horizon_day, MARKET_CLOSE)
    blocks_positional = any(e.impact == "high" and now <= e.at <= horizon_end for e in upcoming)

    if active:
        pillar = PillarView("events", f"{active.name} at {active.at:%H:%M}: no new entries", status="fail")
    elif later_today:
        pillar = PillarView("events", f"{later_today.name} at {later_today.at:%H:%M} today", status="warn")
    else:
        nxt = upcoming[0] if upcoming else None
        pillar = PillarView("events", "No events until the close" +
                            (f" (next: {nxt.name} {nxt.at:%d %b})" if nxt else ""), status="pass")
    return EventView(pillar, active is not None, upcoming[0] if upcoming else None, blocks_positional)


def news(ctx: AgentContext) -> PillarView:
    return PillarView("news", "No news feed connected", status="na")

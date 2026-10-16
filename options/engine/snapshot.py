"""Run every analysis agent once for an index at one point in time."""

from dataclasses import dataclass

from options.agents import breadth, events, futures_flow, macro, option_chain, regime, technical, volatility
from options.agents.context import AgentContext
from options.agents.events import EventView
from options.agents.option_chain import Chain
from options.agents.regime import RegimeView
from options.agents.technical import TechView
from options.agents.volatility import VolView
from options.core.schemas import PillarView


@dataclass
class Snapshot:
    ctx: AgentContext
    tech: TechView
    flow: PillarView
    chain: Chain | None          # nearest expiry, used for OI analysis
    vol: VolView
    oi: PillarView
    breadth: PillarView
    macro: PillarView
    events: EventView
    news: PillarView
    regime: RegimeView

    @property
    def basis(self) -> float:
        spot, fut = self.ctx.spot, self.ctx.fut
        return fut - spot if spot and fut else 0.0

    def pillars(self) -> list[PillarView]:
        """Direction-independent board view of every pillar, for the dashboard."""
        return [self.tech.trend, self.tech.momentum, self.flow, self.oi, self.vol.pillar, self.breadth,
                self.macro, self.events.pillar, self.news, self.regime.timing]


def take(ctx: AgentContext) -> Snapshot:
    tech = technical.analyse(ctx)
    chain = option_chain.build_chain(ctx, ctx.ref.expiries[0]) if ctx.ref.expiries else None
    vol = volatility.analyse(ctx, chain)
    return Snapshot(
        ctx=ctx, tech=tech, flow=futures_flow.analyse(ctx), chain=chain, vol=vol,
        oi=option_chain.analyse(ctx, chain, vol.expected_move_1d), breadth=breadth.analyse(ctx),
        macro=macro.analyse(ctx), events=events.analyse(ctx), news=events.news(ctx),
        regime=regime.analyse(ctx, tech),
    )

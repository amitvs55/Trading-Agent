"""Run every analysis agent once for an index at one point in time."""

from dataclasses import dataclass, field

from options.agents import breadth, events, futures_flow, macro, option_chain, regime, technical, volatility
from options.agents.context import AgentContext
from options.agents.events import EventView
from options.agents.health import AgentRun, guard, pillar_detail
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
    runs: list[AgentRun] = field(default_factory=list)

    @property
    def basis(self) -> float:
        spot, fut = self.ctx.spot, self.ctx.fut
        return fut - spot if spot and fut else 0.0

    @property
    def failed(self) -> list[str]:
        """Agents that raised this time: no new signal may be built on a partial picture."""
        return [r.agent for r in self.runs if r.status == "error"]

    def pillars(self) -> list[PillarView]:
        """Direction-independent board view of every pillar, for the dashboard."""
        return [self.tech.trend, self.tech.momentum, self.flow, self.oi, self.vol.pillar, self.breadth,
                self.macro, self.events.pillar, self.news, self.regime.timing]


class SnapshotError(RuntimeError):
    """The technical agent failed: without it there is nothing to evaluate."""

    def __init__(self, runs: list[AgentRun]):
        self.runs = runs
        super().__init__(next((r.error for r in runs if r.status == "error"), "agent error"))


def _na(pillar: str):
    return lambda error: PillarView(pillar, f"Agent error: {error}", status="na")


def take(ctx: AgentContext) -> Snapshot:
    runs: list[AgentRun] = []

    def tech_fail(error: str):
        raise SnapshotError(runs)

    tech = guard(runs, "technical", lambda: technical.analyse(ctx), tech_fail,
                 lambda t: (f"{t.trend.detail} · {t.momentum.detail}", not t.ready))

    chain_runs: list[AgentRun] = []
    chain = guard(chain_runs, "option_chain",
                  lambda: option_chain.build_chain(ctx, ctx.ref.expiries[0]) if ctx.ref.expiries else None,
                  lambda error: None)
    vol = guard(runs, "volatility", lambda: volatility.analyse(ctx, chain),
                lambda error: VolView(PillarView("volatility", f"Agent error: {error}", status="na")),
                lambda v: pillar_detail(v.pillar))
    if chain_runs and chain_runs[0].status == "error":
        runs.append(chain_runs[0])                       # building the chain failed: report it as the agent's run
        oi = _na("option_chain")(chain_runs[0].error or "")
    else:
        oi = guard(runs, "option_chain", lambda: option_chain.analyse(ctx, chain, vol.expected_move_1d),
                   _na("option_chain"), pillar_detail)
        runs[-1].ms = round(runs[-1].ms + (chain_runs[0].ms if chain_runs else 0), 1)

    flow = guard(runs, "futures_flow", lambda: futures_flow.analyse(ctx), _na("futures_flow"), pillar_detail)
    brd = guard(runs, "breadth", lambda: breadth.analyse(ctx), _na("breadth"), pillar_detail)
    mac = guard(runs, "macro", lambda: macro.analyse(ctx), _na("macro"), pillar_detail)
    evt = guard(runs, "events", lambda: events.analyse(ctx),
                lambda error: EventView(PillarView("events", f"Agent error: {error}", status="na"),
                                        window_active=False, next_event=None, blocks_positional=True),
                lambda e: (e.pillar.detail, False))
    nws = guard(runs, "news", lambda: events.news(ctx), _na("news"), lambda p: (p.detail, False))
    reg = guard(runs, "regime", lambda: regime.analyse(ctx, tech),
                lambda error: RegimeView("neutral", ctx.calendar.session_phase(ctx.now), False, False,
                                         PillarView("timing", f"Agent error: {error}", status="na"),
                                         f"Agent error: {error}"),
                lambda r: (f"{r.regime} regime · {r.timing.detail}", False))
    return Snapshot(ctx=ctx, tech=tech, flow=flow, chain=chain, vol=vol, oi=oi, breadth=brd, macro=mac,
                    events=evt, news=nws, regime=reg, runs=runs)

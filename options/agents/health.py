"""Which analysis agents ran, how long they took, and what they concluded.

Every agent call in `snapshot.take` goes through `guard`: an exception no longer aborts the
whole 5-minute evaluation. The failing agent's pillar degrades to n/a, and the engine sends
no new signal while any agent is failing (open trades are still managed). `AgentTracker`
keeps per-session counters for the Agents page and decides when Telegram should be told.
"""

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable, TypeVar

from utils.logger import setup_logger

logger = setup_logger("options.agents")
T = TypeVar("T")

# id → (label, what it reads, the board pillars it produces)
AGENTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "technical":    ("Technical", "NIFTY futures 5/15/60-min candles, VWAP", ("trend", "momentum")),
    "futures_flow": ("Futures flow", "Futures price and open interest, last 15 min", ("futures_flow",)),
    "option_chain": ("Option chain", "Strikes around the money: OI, bid/ask", ("option_chain",)),
    "volatility":   ("Volatility", "ATM implied vol (Black-76), India VIX, realised vol", ("volatility",)),
    "breadth":      ("Breadth", "NIFTY heavyweights vs their previous close", ("breadth",)),
    "macro":        ("Global markets", "Asian, US and commodity moves (Yahoo)", ("macro",)),
    "events":       ("Events calendar", "RBI, Fed, Budget and expiry dates", ("events",)),
    "news":         ("News", "Scheduled event windows today", ("news",)),
    "regime":       ("Regime & timing", "Trend/range/chop classification, session phase", ("timing",)),
}

FAILURE_ALERT_AFTER = 2          # consecutive failed evaluations before Telegram is told


@dataclass
class AgentRun:
    agent: str
    status: str                  # ok | degraded (ran, but its data was missing) | error
    ms: float
    detail: str = ""
    error: str | None = None


def guard(runs: list[AgentRun], agent: str, fn: Callable[[], T], fallback: Callable[[str], T],
          detail: Callable[[T], tuple[str, bool]] | None = None) -> T:
    """Run one agent, record the outcome, and return its result or `fallback(error)`.

    `detail(result)` gives the summary shown on the Agents page and whether the agent was
    starved of data (its pillar came back n/a or "waiting")."""
    started = time.perf_counter()
    try:
        out = fn()
    except Exception as e:                                   # one broken agent must not stop the rest
        ms = (time.perf_counter() - started) * 1000
        error = f"{type(e).__name__}: {e}"[:300]
        logger.exception("Agent %s failed", agent)
        runs.append(AgentRun(agent, "error", round(ms, 1), "", error))
        return fallback(error)
    ms = (time.perf_counter() - started) * 1000
    text, starved = detail(out) if detail else ("", False)
    runs.append(AgentRun(agent, "degraded" if starved else "ok", round(ms, 1), text))
    return out


def pillar_detail(view) -> tuple[str, bool]:
    starved = view.status == "na" or view.detail.lower().startswith(("waiting", "no "))
    return view.detail, starved


@dataclass
class AgentState:
    status: str = "idle"
    detail: str = ""
    error: str | None = None
    ms: float | None = None
    last_run_at: str | None = None
    last_ok_at: str | None = None
    runs: int = 0
    errors: int = 0
    failing_in_row: int = 0
    alerted: bool = False


@dataclass
class AgentTracker:
    """Per-index counters for one session (the recorder restarts every trading day)."""
    agents: dict[str, AgentState] = field(default_factory=lambda: {a: AgentState() for a in AGENTS})

    def update(self, runs: list[AgentRun], now: datetime) -> list[str]:
        """Record one evaluation; returns Telegram messages to send (new failures, recoveries)."""
        messages = []
        stamp = now.isoformat(timespec="seconds")
        for r in runs:
            st = self.agents.setdefault(r.agent, AgentState())
            st.status, st.detail, st.error, st.ms, st.last_run_at = r.status, r.detail, r.error, r.ms, stamp
            st.runs += 1
            if r.status == "error":
                st.errors += 1
                st.failing_in_row += 1
                if st.failing_in_row >= FAILURE_ALERT_AFTER and not st.alerted:
                    st.alerted = True
                    messages.append(f"⚠️ <b>{AGENTS.get(r.agent, (r.agent,))[0]} agent failing</b> "
                                    f"({st.failing_in_row} checks in a row): {r.error}. "
                                    "No new signals until it recovers; open trades are still managed.")
            else:
                st.last_ok_at = stamp
                if st.alerted:
                    messages.append(f"✅ <b>{AGENTS.get(r.agent, (r.agent,))[0]} agent recovered</b>. "
                                    "Signals resume on the next 5-minute close.")
                st.failing_in_row, st.alerted = 0, False
        return messages

    def payload(self, now: datetime, failed: list[str]) -> dict:
        return {"as_of": now.isoformat(timespec="seconds"), "signals_paused": bool(failed), "failed": failed,
                "agents": {a: asdict(s) for a, s in self.agents.items()}}


def describe() -> list[dict]:
    """Static facts about each agent, for the Agents page."""
    return [{"id": a, "label": label, "reads": reads, "pillars": list(pillars)}
            for a, (label, reads, pillars) in AGENTS.items()]

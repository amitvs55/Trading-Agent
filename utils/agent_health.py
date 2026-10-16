"""Last outcome of each research-pipeline agent, for the Agents page.

Every agent's `run` is wrapped (see agents/base.py): it records whether the call returned or
raised, and how long it took. The API installs a sink that saves the state to the database,
so it survives redeploys; without a sink (CLI runs, tests) it just stays in memory.
"""

import functools
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

# Pipeline order: (agent name as recorded, label, stage)
RESEARCH_AGENTS: list[tuple[str, str, int]] = [
    ("market_data_analyst", "Market data analyst", 1),
    ("fundamentals_analyst", "Fundamentals analyst", 1),
    ("news_analyst", "News analyst", 1),
    ("sentiment_analyst", "Sentiment analyst", 1),
    ("bull_researcher", "Bull researcher", 2),
    ("bear_researcher", "Bear researcher", 2),
    ("debate_moderator", "Debate moderator", 2),
    ("trader", "Trader", 3),
    ("risk_manager_aggressive", "Risk manager (aggressive)", 4),
    ("risk_manager_neutral", "Risk manager (neutral)", 4),
    ("risk_manager_conservative", "Risk manager (conservative)", 4),
    ("portfolio_manager", "Portfolio manager", 5),
    ("execution_engine", "Execution engine", 6),
]

_state: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_active = threading.local()
_sink: Callable[[dict[str, dict[str, Any]]], None] | None = None


def set_sink(sink: Callable[[dict[str, dict[str, Any]]], None] | None, initial: dict | None = None) -> None:
    global _sink
    with _lock:
        _sink = sink
        if initial:
            _state.update(initial)


def snapshot() -> dict[str, dict[str, Any]]:
    with _lock:
        return {k: dict(v) for k, v in _state.items()}


def record(agent: str, ok: bool, seconds: float, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        st = _state.setdefault(agent, {"runs": 0, "errors": 0})
        st.update(status="ok" if ok else "error", last_run_at=now, seconds=round(seconds, 2),
                  error=None if ok else (error or "")[:300])
        st["runs"] = st.get("runs", 0) + 1
        if ok:
            st["last_ok_at"] = now
        else:
            st["errors"] = st.get("errors", 0) + 1
        state, sink = {k: dict(v) for k, v in _state.items()}, _sink
    if sink:
        try:
            sink(state)
        except Exception:                      # health bookkeeping must never break an analysis
            pass


def tracked(name: str, fn: Callable) -> Callable:
    """Wrap an agent's run(): the outermost call per agent and thread is recorded once."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        active = getattr(_active, "names", None)
        if active is None:
            active = _active.names = set()
        if name in active:                     # a subclass run() calling super().run()
            return fn(*args, **kwargs)
        active.add(name)
        started = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            record(name, False, time.perf_counter() - started, f"{type(e).__name__}: {e}")
            raise
        finally:
            active.discard(name)
        record(name, True, time.perf_counter() - started)
        return result

    wrapper.__agent_tracked__ = True
    return wrapper

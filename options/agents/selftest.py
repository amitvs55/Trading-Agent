"""Self-test for the signal agents, runnable at any time (the Agents page's "Run self-test").

With a recorded session in the database, the first 45 minutes of the latest one are replayed
through the real engine into a throwaway in-memory database, so the agents run on real
market data exactly as they would live. Before anything has been recorded, the agents run
on the synthetic market instead: that proves the code works, not that live data arrives.
Nothing is sent to Telegram and nothing touches the live track record.
"""

from datetime import datetime, time

from options.agents.health import AGENTS, AgentTracker
from options.config import OptionsSettings
from options.core.calendar import NseCalendar
from options.storage import Store, make_engine

SELFTEST_KEY = "selftest"
REPLAY_UNTIL = time(10, 0)


def _summary(agents: dict) -> dict:
    statuses = [a.get("status") for a in agents.values()]
    return {"passed": bool(statuses) and "error" not in statuses and "idle" not in statuses,
            "errors": sum(s == "error" for s in statuses), "degraded": sum(s == "degraded" for s in statuses)}


def _recorded(store: Store, cfg: OptionsSettings, calendar: NseCalendar) -> dict | None:
    from options.backtest.replay import SilentNotifier, replay_day

    days = store.recorded_days()
    if not days:
        return None
    day = max(days)
    scratch = Store(make_engine("sqlite://"))           # in memory: replay output never mixes with live data
    replay_day(store, scratch, day, cfg, calendar, notifier=SilentNotifier(), until=REPLAY_UNTIL)
    by_index = {i: st for i in cfg.OPTIONS_INDICES if (st := scratch.load_agent_status(i))}
    if not by_index:
        return None
    index, status = next(iter(by_index.items()))
    return {"source": "recorded", "day": day.isoformat(), "index": index, "agents": status["agents"]}


def _synthetic(now: datetime) -> dict:
    from options.backtest.synthetic import TODAY, build_market
    from options.engine.snapshot import SnapshotError, take

    ctx = build_market()
    tracker = AgentTracker()
    try:
        runs = take(ctx).runs
    except SnapshotError as e:
        runs = e.runs
    tracker.update(runs, now)
    return {"source": "synthetic", "day": TODAY.isoformat(), "index": "NIFTY",
            "agents": tracker.payload(now, [])["agents"]}


def run(store: Store, cfg: OptionsSettings, now: datetime, calendar: NseCalendar | None = None) -> dict:
    calendar = calendar or NseCalendar()
    try:
        result = _recorded(store, cfg, calendar)
    except Exception as e:                                # a broken recording shouldn't hide the code check
        result = None
        note = f"Replaying the last recorded session failed ({type(e).__name__}: {str(e)[:120]}); ran on synthetic data."
    else:
        note = None
    if result is None:
        result = _synthetic(now)
        result["note"] = note or "No session recorded yet: the agents ran on a synthetic NIFTY market."
    for agent in AGENTS:
        result["agents"].setdefault(agent, {"status": "idle", "detail": "did not run"})
    result.update(_summary(result["agents"]), ran_at=now.isoformat(timespec="seconds"))
    store.save_agent_status(SELFTEST_KEY, result, now)
    return result

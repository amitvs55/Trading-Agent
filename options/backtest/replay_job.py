"""A replay started from the Operations page, run by the recorder outside market hours.

The API saves the request (REQUEST_KEY); the recorder supervisor (options/daemon.py) starts this in a
fresh process when no session is running. It replays every recorded day in the range through the live
engine with today's rules (options/backtest/replay.py) into a throwaway database, so a replay can never
mix with the live record, and saves progress and the report (REPORT_KEY) for the page.

    python -m options.backtest.replay_job
"""

import collections
import re
import sys
import tempfile
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

from options.core.calendar import IST, NseCalendar, now_ist
from options.engine import performance
from options.setups import SETUP_LABELS
from options.storage import Store, make_engine
from utils.logger import setup_logger

logger = setup_logger("options.replay_job")

REQUEST_KEY, REPORT_KEY = "replay_request", "replay_report"
MAX_DAYS = 120                    # calendar days in one replay
NOT_REPLAYED = ["Global markets and news are not replayed (no saved history), so those pillars count as "
                "unknown; everything else is exactly what the live engine would have seen."]


def _signal_row(s) -> dict:
    return {"id": s.signal_id, "created_at": s.created_at.astimezone(IST).isoformat(), "setup": s.setup,
            "horizon": s.horizon, "action": s.action.value, "grade": s.grade.value, "score": s.score,
            "symbol": s.contract.tradingsymbol, "entry_high": s.entry_high, "stop": s.initial_stop or s.stop_loss,
            "t1": s.t1, "t2": s.t2, "fill": s.fill_price, "exit": s.exit_price, "exit_reason": s.exit_reason,
            "state": s.state.value, "pnl": s.pnl_rupees, "r": s.r_multiple, "over_budget": s.over_budget,
            "risk": s.risk_rupees}


def _reason_key(part: str) -> str:
    """One label per kind of rejection, whatever its numbers."""
    if part.startswith("score "):
        return "grade C (score below 60)"
    if part.startswith("reward:risk"):
        return "reward:risk to target 1 below 1.3"
    return re.sub(r"\s+", " ", re.sub(r"₹?\d[\d.,]*", "#", part)).strip()


def _outcomes(target: Store, since: datetime) -> dict:
    """What the engine decided about every candidate, and why the rejected ones were rejected."""
    rows = target.evaluations_since(since, limit=100_000)
    by = collections.Counter(r["outcome"] for r in rows)
    why = collections.Counter()
    for r in rows:
        if r["outcome"] in ("NO_TRADE", "GRADE_C"):
            for part in (r["reasons"] or "").split("; "):
                why[_reason_key(part)] += 1
    return {"candidates": len(rows), "by_outcome": dict(by), "reasons": why.most_common(12)}


def run(store: Store, request: dict, now_fn=now_ist, calendar: NseCalendar | None = None, cfg=None,
        workdir: str | None = None) -> dict:
    from options.backtest.replay import replay
    start, end = date.fromisoformat(request["from"]), date.fromisoformat(request["to"])
    report = {"status": "running", "request": request, "started_at": now_fn().isoformat(timespec="seconds"),
              "done": 0, "total": None, "current": None}
    store.set_meta_json(REPORT_KEY, report, now_fn())

    def progress(done: int, total: int, day: date) -> None:
        report.update(done=done, total=total, current=day.isoformat())
        store.set_meta_json(REPORT_KEY, report, now_fn())

    if cfg is None:
        from options.admin.connectors import load_effective_settings
        cfg = load_effective_settings()
    if calendar is None:
        from options.session import load_calendar
        calendar = load_calendar(store)
    folder = Path(workdir or tempfile.mkdtemp(prefix="replay-"))
    target = Store(make_engine(f"sqlite:///{(folder / 'replay.db').as_posix()}"))
    result = replay(store, target, start, end, cfg, calendar, on_day=progress)
    since = datetime.combine(start, datetime.min.time(), IST)
    signals = target.signals_since(since, since + timedelta(days=(end - start).days + 1))
    report.update(status="done", finished_at=now_fn().isoformat(timespec="seconds"), days=result["days"],
                  signals=[_signal_row(s) for s in signals], overall=result["overall"],
                  by_setup=result["by_setup"], decisions=_outcomes(target, since),
                  rules={"risk_per_trade_pct": cfg.OPTIONS_RISK_PER_TRADE_PCT, "capital": cfg.OPTIONS_CAPITAL,
                         "indices": cfg.OPTIONS_INDICES}, notes=NOT_REPLAYED, setup_labels=SETUP_LABELS)
    store.set_meta_json(REPORT_KEY, report, now_fn())
    return report


def main() -> int:
    from options.config import OptionsSettings
    store = Store(make_engine(OptionsSettings().DATABASE_URL))
    request = store.get_meta_json(REQUEST_KEY)
    if not request:
        logger.info("No replay requested")
        return 0
    try:
        report = run(store, request)
        logger.info("Replay %s – %s: %d day(s), %d signal(s)", request["from"], request["to"],
                    len(report["days"]), len(report["signals"]))
        return 0
    except Exception as e:
        logger.exception("Replay failed")
        store.set_meta_json(REPORT_KEY, {"status": "error", "request": request, "error": f"{type(e).__name__}: {e}"[:500],
                                         "trace": traceback.format_exc()[-2000:],
                                         "finished_at": now_ist().isoformat(timespec="seconds")}, now_ist())
        return 1


if __name__ == "__main__":
    sys.exit(main())

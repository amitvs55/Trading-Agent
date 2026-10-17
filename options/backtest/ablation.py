"""Pillar ablation (roadmap R-17): does each pillar earn its weight?

Re-runs the proxy backtest once per pillar with that pillar's weight removed (the rest scaled
back up to 100, so the grade thresholds keep their meaning) and compares each run with the
full model. A pillar whose removal doesn't hurt, or helps, is a candidate to drop or re-weight.
Weights are only changed inside this process, for the duration of each run.

    python -m options.backtest.ablation --from 2025-06-01 --to 2026-10-16 \
        --history sqlite:///data/history.db --workdir data/ablation
"""

import argparse
import json
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Callable

from options.backtest import proxy
from options.engine import grading
from options.storage import Store, make_engine


@contextmanager
def weights_without(pillar: str | None):
    """PILLAR_WEIGHTS with one pillar removed and the others rescaled to 100 (in place, then restored)."""
    original = dict(grading.PILLAR_WEIGHTS)
    try:
        if pillar is not None:
            kept = {k: v for k, v in original.items() if k != pillar}
            scale = 100 / sum(kept.values())
            grading.PILLAR_WEIGHTS.clear()
            grading.PILLAR_WEIGHTS.update({k: v * scale for k, v in kept.items()})
            grading.PILLAR_WEIGHTS[pillar] = 0.0
        yield dict(grading.PILLAR_WEIGHTS)
    finally:
        grading.PILLAR_WEIGHTS.clear()
        grading.PILLAR_WEIGHTS.update(original)


def _summary(rep: dict) -> dict:
    ev = rep["evidence"]
    return {"trades": ev["trades"], "mean_r": ev["mean_r"], "ci_r": ev["ci_r"], "win_rate": rep["overall"]["win_rate"],
            "total_rupees": rep["overall"]["total_rupees"]}


def ablate(history: Store, start: date, end: date, workdir: Path,
           run: Callable[..., dict] = proxy.run, pillars: list[str] | None = None) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    pillars = pillars or list(grading.PILLAR_WEIGHTS)
    results = {}
    for name in [None, *pillars]:
        label = name or "full model"
        db = workdir / f"ablation-{name or 'baseline'}.db"
        db.unlink(missing_ok=True)
        with weights_without(name):
            results[label] = _summary(run(history, Store(make_engine(f"sqlite:///{db}")), start, end))
    base = results["full model"]["mean_r"]
    for label, r in results.items():
        r["delta_r"] = (r["mean_r"] - base) if (r["mean_r"] is not None and base is not None) else None
    return {"from": start.isoformat(), "to": end.isoformat(), "results": results,
            "read_me": "delta_r < 0: removing the pillar hurt (it helps). delta_r ≥ 0: it didn't help in this sample."}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pillar ablation on the proxy backtest")
    ap.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    ap.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    ap.add_argument("--history", required=True)
    ap.add_argument("--workdir", default="data/ablation")
    args = ap.parse_args(argv)
    out = ablate(Store(make_engine(args.history)), args.start, args.end, Path(args.workdir))
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

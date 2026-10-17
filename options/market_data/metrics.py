"""Per-minute session metrics (roadmap R-28): is the recording machine keeping up?

The recorder calls `sample()` once a minute. It stores how many ticks arrived and bars were
saved, how many bad ticks were dropped, the slowest signal evaluation and the slowest alert
delivery in that minute, and the open signals. The Operations page shows the latest values;
a stalled feed shows up as zero ticks, an overloaded machine as slow evaluations.
"""

from datetime import datetime

from utils.logger import setup_logger

logger = setup_logger("options.metrics")


class SessionMetrics:
    def __init__(self, store, recorder, engine, notifier=None):
        self.store, self.recorder, self.engine, self.notifier = store, recorder, engine, notifier
        self._last = (recorder.agg.tick_count, recorder.bars_written, recorder.agg.rejected_ticks)

    def sample(self, now: datetime) -> dict:
        ticks, bars, rejected = self.recorder.agg.tick_count, self.recorder.bars_written, self.recorder.agg.rejected_ticks
        eval_ms, self.engine.eval_ms_peak = self.engine.eval_ms_peak, 0.0
        delay = getattr(self.notifier, "delay_peak", None)
        if delay is not None:
            self.notifier.delay_peak = 0.0
        row = {"ts": now.replace(second=0, microsecond=0), "ticks": ticks - self._last[0], "bars": bars - self._last[1],
               "rejected_ticks": rejected - self._last[2], "eval_ms": round(eval_ms, 1) if eval_ms else None,
               "alert_delay_s": round(delay, 2) if delay else None, "open_signals": len(self.engine.open)}
        self._last = (ticks, bars, rejected)
        try:
            self.store.metrics_add(row)
        except Exception:
            logger.exception("Saving session metrics failed")
        return row

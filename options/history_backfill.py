"""Two years of NIFTY spot and India VIX minutes for the Option Check history view.

Run by the recorder's supervisor outside market hours (at start-up and once each evening), as
part of `python -m options.offhours`.

It fills only what's missing: each 30-day span already covered by saved bars is skipped, so after
the first run it asks Angel for a few days at most. Requests go through the adapter's one-second
gate (Angel refused faster history requests on 19 Oct 2026). Saved bars are marked as history
(ticks=0) and never overwrite recorded ones. Between 09:00 and 15:31 it does nothing.
"""

import sys
from datetime import date, datetime, time, timedelta

from options.core.calendar import IST, NseCalendar, at_ist
from utils.logger import setup_logger

logger = setup_logger("options.backfill")

YEARS = 2
SPAN_DAYS = 30
FULL_DAY = 300                  # minutes; a saved session with fewer counts as missing
QUIET_FROM, QUIET_UNTIL = time(9, 0), time(15, 31)
META_KEY = "history_backfill"


def spans(start: date, end: date) -> list[tuple[date, date]]:
    out, d = [], start
    while d < end:
        out.append((d, min(d + timedelta(days=SPAN_DAYS), end)))
        d = out[-1][1]
    return out


def missing_spans(store, token: int, start: date, end: date, calendar: NseCalendar) -> list[tuple[date, date]]:
    """Spans with at least one trading day that has fewer than FULL_DAY saved minutes."""
    counts = store.bar_counts_per_day(token, at_ist(start, time(0)), at_ist(end, time(0)))
    out = []
    for a, b in spans(start, end):
        d = a
        while d < b:
            if calendar.is_trading_day(d) and counts.get(d, 0) < FULL_DAY:
                out.append((a, b))
                break
            d += timedelta(days=1)
    return out


def backfill(store, broker, tokens: dict[str, int], calendar: NseCalendar, now: datetime) -> dict:
    from options.session import history_rows

    end = now.astimezone(IST).date()
    start = end - timedelta(days=365 * YEARS)
    report = {}
    for name, token in tokens.items():
        todo = missing_spans(store, token, start, end, calendar)
        saved = failed = 0
        for a, b in todo:
            try:
                candles = broker.historical(token, at_ist(a, time(9, 15)), at_ist(b, time(0)), "minute")
            except Exception as e:
                from options.brokers.angel import brief_error
                failed += 1
                logger.warning("Backfill %s %s–%s failed: %s", name, a, b, brief_error(e))
                if failed >= 3:
                    break                                   # Angel is refusing: try again another evening
                continue
            rows = history_rows(token, [c for c in candles if c["date"] < at_ist(end, time(0))])
            saved += store.insert_bars_if_missing(rows)
        report[name] = {"spans_missing": len(todo), "rows_sent": saved, "failed": failed}
        logger.info("Backfill %s: %d spans missing, %d rows saved, %d failed", name, len(todo), saved, failed)
    store.set_meta_json(META_KEY, {"at": now.isoformat(timespec="seconds"), "report": report}, now)
    return report


def main() -> int:
    from options.offhours import main as run
    return run()                                     # one login for all the evening jobs


if __name__ == "__main__":
    sys.exit(main())

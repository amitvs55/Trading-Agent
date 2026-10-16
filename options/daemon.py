"""Long-running recorder: starts each trading day's session at 08:30 IST in a fresh process.

Railway's config-as-code is deprecated for new services, so instead of a cron service the
recorder container runs this scheduler (Dockerfile: SERVICE_ROLE=recorder). A fresh
process per session also matters: KiteTicker's Twisted reactor cannot be restarted.

    python -m options.daemon
"""

import subprocess
import sys
import time as _time
from datetime import date, datetime, time
from typing import Callable

from options.core.calendar import IST, NseCalendar, at_ist, now_ist
from utils.logger import setup_logger

logger = setup_logger("options.daemon")

SESSION_START = time(8, 30)
LATE_START_UNTIL = time(15, 0)       # (re)started during the day: still run today's session
MAX_SLEEP_S = 3600                   # wake up hourly so clock jumps can't oversleep a session


def next_start(now: datetime, calendar: NseCalendar, last_run: date | None) -> datetime:
    now = now.astimezone(IST)
    today = now.date()
    if calendar.is_trading_day(today) and last_run != today:
        if now.time() < SESSION_START:
            return at_ist(today, SESSION_START)
        if now.time() < LATE_START_UNTIL:
            return now
    return at_ist(calendar.next_trading_day(today), SESSION_START)


def run_session() -> int:
    return subprocess.run([sys.executable, "-m", "options.session"]).returncode


def main(now_fn: Callable[[], datetime] = now_ist, sleep: Callable[[float], None] = _time.sleep,
         session: Callable[[], int] = run_session, calendar: NseCalendar | None = None,
         max_sessions: int | None = None) -> int:
    calendar = calendar or NseCalendar()
    last_run: date | None = None
    done = 0
    while max_sessions is None or done < max_sessions:
        target = next_start(now_fn(), calendar, last_run)
        wait = (target - now_fn()).total_seconds()
        if wait > 0:
            logger.info("Next session %s (in %.1f h)", target.isoformat(timespec="minutes"), wait / 3600)
            sleep(min(wait, MAX_SLEEP_S))
            continue
        last_run = target.date()
        logger.info("Starting session for %s", last_run)
        code = session()
        logger.info("Session for %s exited with code %s", last_run, code)
        done += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

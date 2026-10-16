"""Long-running recorder: starts each trading day's session at 08:30 IST in a fresh process.

Railway's config-as-code is deprecated for new services, so instead of a cron service the
recorder container runs this scheduler (Dockerfile: SERVICE_ROLE=recorder). A fresh
process per session also matters: the market-data WebSocket libraries can't restart in-process.

It also writes a heartbeat to the database (shown on the Connectors page) and obeys a
"restart" command from there, so a session can be started right after saving credentials.

    python -m options.daemon
"""

import json
import subprocess
import sys
import time as _time
from datetime import date, datetime, time
from typing import Callable, Protocol

from options.core.calendar import IST, NseCalendar, at_ist, now_ist
from utils.logger import setup_logger

logger = setup_logger("options.daemon")

SESSION_START = time(8, 30)
LATE_START_UNTIL = time(15, 0)       # (re)started during the day: still run today's session
POLL_S = 15                          # heartbeat and command check interval
STATUS_KEY, COMMAND_KEY = "recorder_status", "recorder_command"


class Process(Protocol):
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...


def next_start(now: datetime, calendar: NseCalendar, last_run: date | None) -> datetime:
    now = now.astimezone(IST)
    today = now.date()
    if calendar.is_trading_day(today) and last_run != today:
        if now.time() < SESSION_START:
            return at_ist(today, SESSION_START)
        if now.time() < LATE_START_UNTIL:
            return now
    return at_ist(calendar.next_trading_day(today), SESSION_START)


def spawn_session() -> Process:
    return subprocess.Popen([sys.executable, "-m", "options.session"])


def can_start_now(now: datetime, calendar: NseCalendar) -> bool:
    return calendar.is_trading_day(now.date()) and now.time() < LATE_START_UNTIL


class Supervisor:
    def __init__(self, repo=None, spawn: Callable[[], Process] = spawn_session,
                 now_fn: Callable[[], datetime] = now_ist, calendar: NseCalendar | None = None):
        self.repo = repo                       # AdminRepo; None when the database is unreachable
        self.spawn = spawn
        self.now_fn = now_fn
        self.calendar = calendar or NseCalendar()
        self.proc: Process | None = None
        self.last_run: date | None = None
        self.session_started_at: datetime | None = None
        self.last_exit_code: int | None = None
        self.last_command: str | None = None
        self._handled_command: str | None = None

    # ── Database (best effort: scheduling must survive a database outage) ──

    def _read_command(self) -> dict | None:
        try:
            return self.repo.get_meta_json(COMMAND_KEY) if self.repo else None
        except Exception:
            logger.exception("Reading the recorder command failed")
            return None

    def _heartbeat(self, now: datetime) -> None:
        if not self.repo:
            return
        state = "running" if self.proc else "waiting"
        status = {"ts": now.isoformat(), "state": state,
                  "next_start": None if self.proc else next_start(now, self.calendar, self.last_run).isoformat(),
                  "session_started_at": self.session_started_at.isoformat() if self.session_started_at else None,
                  "last_exit_code": self.last_exit_code, "last_command": self.last_command}
        try:
            self.repo.set_meta(STATUS_KEY, json.dumps(status))
        except Exception:
            logger.exception("Writing the recorder heartbeat failed")

    # ── Session control ──────────────────────────────────────────────────

    def _start(self, now: datetime) -> None:
        self.last_run = now.date()
        self.session_started_at = now
        logger.info("Starting session for %s", self.last_run)
        self.proc = self.spawn()

    def _stop(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except Exception:
            self.proc.kill()
        self.last_exit_code = self.proc.poll()
        self.proc = None

    def handle_command(self, now: datetime) -> None:
        cmd = self._read_command()
        if not cmd or cmd.get("requested_at") == self._handled_command:
            return
        self._handled_command = cmd.get("requested_at")
        if cmd.get("action") != "restart":
            return
        if not can_start_now(now, self.calendar):
            self.last_command = f"restart ignored at {now:%d %b %H:%M}: no session to run now"
            return
        self._stop()
        self._start(now)
        self.last_command = f"restarted at {now:%d %b %H:%M} by {cmd.get('by') or 'admin'}"

    def step(self, now: datetime) -> None:
        if self.proc is not None and (code := self.proc.poll()) is not None:
            logger.info("Session for %s exited with code %s", self.last_run, code)
            self.last_exit_code, self.proc = code, None
        self.handle_command(now)
        if self.proc is None and next_start(now, self.calendar, self.last_run) <= now:
            self._start(now)
        self._heartbeat(now)

    def run(self, sleep: Callable[[float], None] = _time.sleep, steps: int | None = None) -> None:
        n = 0
        while steps is None or n < steps:
            self.step(self.now_fn())
            n += 1
            sleep(POLL_S)


def main() -> int:
    repo = None
    try:
        from options.admin.repo import AdminRepo
        from options.config import OptionsSettings
        from options.storage import make_engine
        repo = AdminRepo(make_engine(OptionsSettings().DATABASE_URL))
    except Exception:
        logger.exception("Database unavailable; scheduling without heartbeat or commands")
    sup = Supervisor(repo)
    if cmd := sup._read_command():
        # A restart requested while this container was down is stale: start-up runs today's session anyway
        sup._handled_command = cmd.get("requested_at")
    sup.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

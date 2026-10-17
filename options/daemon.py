"""Long-running recorder: starts each trading day's session at 08:30 IST in a fresh process.

Railway's config-as-code is deprecated for new services, so instead of a cron service the
recorder container runs this scheduler (Dockerfile: SERVICE_ROLE=recorder). A fresh
process per session also matters: the market-data WebSocket libraries can't restart in-process.

It also writes a heartbeat to the database (shown on the Connectors page) and obeys a
"restart" command from there, so a session can be started right after saving credentials.

A session that stops unexpectedly during market hours is restarted (30 s, 2 min, then 5 min
later; at most 3 times a day), because while it is down open signals get no stop-loss or
target alerts. Each restart, and giving up, is reported on Telegram.

    python -m options.daemon
"""

import json
import subprocess
import sys
import threading
import time as _time
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Callable, Protocol

from options.core.calendar import IST, NseCalendar, at_ist, now_ist
from utils.logger import setup_logger

logger = setup_logger("options.daemon")

SESSION_START = time(8, 30)
LATE_START_UNTIL = time(15, 0)       # (re)started during the day: still run today's session
MANAGE_ONLY_UNTIL = time(15, 20)     # …and until here when intraday signals are still open
CRASH_RESTART_UNTIL = time(15, 20)   # a session that dies before this is restarted
RESTART_BACKOFF_S = (30, 120, 300)   # waits before the 1st, 2nd and 3rd restart of the day
POLL_S = 15                          # heartbeat and command check interval
STATUS_KEY, COMMAND_KEY = "recorder_status", "recorder_command"

# Session exit codes (options.session)
EXIT_OK, EXIT_FAILED, EXIT_CONFIG, EXIT_LOGIN = 0, 1, 2, 3
NO_RESTART = {EXIT_OK, EXIT_CONFIG}  # missing keys won't fix themselves; saving them sends a restart


class Process(Protocol):
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...


def next_start(now: datetime, calendar: NseCalendar, last_run: date | None,
               late_until: time = LATE_START_UNTIL) -> datetime:
    now = now.astimezone(IST)
    today = now.date()
    if calendar.is_trading_day(today) and last_run != today:
        if now.time() < SESSION_START:
            return at_ist(today, SESSION_START)
        if now.time() < late_until:
            return now
    return at_ist(calendar.next_trading_day(today), SESSION_START)


def spawn_session() -> Process:
    return subprocess.Popen([sys.executable, "-m", "options.session"])


def can_start_now(now: datetime, calendar: NseCalendar) -> bool:
    return calendar.is_trading_day(now.date()) and now.time() < LATE_START_UNTIL


def _send_alert(text: str) -> None:
    """Supervisor alerts go straight to the configured channel, on a thread of their own so a slow
    Telegram never delays the heartbeat."""
    def run():
        try:
            from options.admin.connectors import load_effective_settings
            from options.notify import make_notifier
            make_notifier(load_effective_settings()).send(text)
        except Exception:
            logger.exception("Supervisor alert failed")
    threading.Thread(target=run, name="supervisor-alert", daemon=True).start()


class Supervisor:
    def __init__(self, repo=None, spawn: Callable[[], Process] = spawn_session,
                 now_fn: Callable[[], datetime] = now_ist, calendar: NseCalendar | None = None,
                 notify: Callable[[str], None] = _send_alert,
                 has_open_intraday: Callable[[], bool] | None = None):
        self.repo = repo                       # AdminRepo; None when the database is unreachable
        self.spawn = spawn
        self.now_fn = now_fn
        self.calendar = calendar or NseCalendar()
        self.notify = notify
        self._has_open_intraday = has_open_intraday or self._open_intraday_in_db
        self.proc: Process | None = None
        self.last_run: date | None = None
        self.session_started_at: datetime | None = None
        self.last_exit_code: int | None = None
        self.last_command: str | None = None
        self._handled_command: str | None = None
        self._announced: datetime | None = None     # next start already written to the log
        self.restarts_today = 0
        self._restart_day: date | None = None
        self.restart_at: datetime | None = None     # a crashed session is due to restart then
        self.gave_up = False

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
        state = "running" if self.proc else ("restarting" if self.restart_at else "waiting")
        upcoming = self.restart_at or next_start(now, self.calendar, self.last_run)
        status = {"ts": now.isoformat(), "state": state,
                  "next_start": None if self.proc else upcoming.isoformat(),
                  "session_started_at": self.session_started_at.isoformat() if self.session_started_at else None,
                  "last_exit_code": self.last_exit_code, "last_command": self.last_command,
                  "restarts_today": self.restarts_today if self._restart_day == now.date() else 0,
                  "gave_up": self.gave_up and self._restart_day == now.date()}
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
        self.restart_at, self.gave_up = None, False          # a person took over: the crash budget resets
        self.restarts_today = 0
        self._start(now)
        self.last_command = f"restarted at {now:%d %b %H:%M} by {cmd.get('by') or 'admin'}"

    def _open_intraday_in_db(self) -> bool:
        if not self.repo:
            return False
        try:
            from options.storage import Store
            return any(s.horizon == "intraday" for s in Store(self.repo.engine).open_signals())
        except Exception:
            logger.exception("Couldn't check for open signals")
            return False

    def _after_exit(self, now: datetime, code: int) -> None:
        """Decide whether a session that just ended should be restarted today."""
        today = now.date()
        if self._restart_day != today:
            self._restart_day, self.restarts_today, self.gave_up = today, 0, False
        if code in NO_RESTART:
            return
        if not self.calendar.is_trading_day(today) or now.time() >= CRASH_RESTART_UNTIL:
            self.notify(f"⚠️ <b>Today's session stopped</b> at {now:%H:%M} (exit code {code}). "
                        "Too close to the end of the day to restart; it starts again next trading day.")
            return
        if self.restarts_today >= len(RESTART_BACKOFF_S):
            self.gave_up = True
            self.notify(f"🔴 <b>Session stopped {self.restarts_today + 1} times today</b> (last exit code {code}). "
                        "It is no longer restarted automatically, so <b>open signals are not being monitored</b>. "
                        "Check the recorder logs, then press Start today's session on the Connectors page.")
            return
        wait = RESTART_BACKOFF_S[self.restarts_today]
        self.restarts_today += 1
        self.restart_at = now + timedelta(seconds=wait)
        self.notify(f"⚠️ <b>Session stopped unexpectedly</b> at {now:%H:%M} (exit code {escape(str(code))}). "
                    f"Restarting in {wait if wait < 60 else wait // 60}{' s' if wait < 60 else ' min'} "
                    f"(attempt {self.restarts_today} of {len(RESTART_BACKOFF_S)}). Open signals are picked up again.")

    def step(self, now: datetime) -> None:
        if self.proc is not None and (code := self.proc.poll()) is not None:
            logger.info("Session for %s exited with code %s", self.last_run, code)
            self.last_exit_code, self.proc = code, None
            self._after_exit(now, code)
        self.handle_command(now)
        if self.proc is None and self.restart_at is not None:
            if now >= self.restart_at:
                self.restart_at = None
                logger.info("Restarting the session (attempt %d today)", self.restarts_today)
                self._start(now)
        elif self.proc is None and next_start(now, self.calendar, self.last_run, self._late_until(now)) <= now:
            self._start(now)
        if self.proc is None and self.restart_at is None:
            target = next_start(now, self.calendar, self.last_run)
            if target != self._announced:
                logger.info("Waiting: next session %s", target.isoformat(timespec="minutes"))
                self._announced = target
        self._heartbeat(now)

    def _late_until(self, now: datetime) -> time:
        """A container started after 15:00 still runs a short session if intraday signals are open,
        so they get their square-off instead of being left unmanaged."""
        t = now.astimezone(IST).time()
        if (self.last_run != now.date() and LATE_START_UNTIL <= t < MANAGE_ONLY_UNTIL
                and self.calendar.is_trading_day(now.date()) and self._has_open_intraday()):
            return MANAGE_ONLY_UNTIL
        return LATE_START_UNTIL

    def run(self, sleep: Callable[[float], None] = _time.sleep, steps: int | None = None) -> None:
        logger.info("Recorder supervisor started (database %s)", "connected" if self.repo else "unavailable")
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

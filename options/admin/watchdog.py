"""Out-of-band watchdog: the API keeps an eye on the recorder and alerts when it goes quiet.

The recorder reports its own problems (stale feed, crashes), but it can't report its own
death: a dead container, a hung session or a lost database connection all look like silence.
The API runs this check once a minute during trading hours and alerts once per problem,
then again when it clears.

Problems it catches:
- **heartbeat:** no supervisor heartbeat for 3 minutes (the recorder service is down).
- **session:** market hours, but today's session hasn't been running for 6 minutes.
- **data:** the session runs but no bar has been saved for 3 minutes (hung, or the feed died silently).

Its state lives in app_meta, so an API restart neither repeats nor forgets an alert.
"""

import threading
from datetime import datetime, time
from typing import Callable

from options.core.calendar import IST, NseCalendar, at_ist, now_ist
from utils.logger import setup_logger

logger = setup_logger("options.watchdog")

STATE_KEY = "watchdog_state"
CHECK_EVERY_S = 60
WATCH_FROM, WATCH_UNTIL = time(8, 40), time(15, 32)      # the supervisor starts the session at 08:30
MARKET_FROM, MARKET_UNTIL = time(9, 20), time(15, 28)
HEARTBEAT_STALE_S = 180
SESSION_GRACE_S = 360          # a crash restart takes up to 5 minutes
DATA_STALE_S = 180


class Watchdog:
    def __init__(self, repo, store, notify: Callable[[str], object], calendar_fn: Callable[[], NseCalendar],
                 now_fn: Callable[[], datetime] = now_ist):
        self.repo, self.store, self.notify = repo, store, notify
        self.calendar_fn, self.now_fn = calendar_fn, now_fn
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── One check ────────────────────────────────────────────────────────────

    def problems(self, now: datetime) -> dict[str, str]:
        """Current problems: key → the alert to send."""
        now = now.astimezone(IST)
        cal = self.calendar_fn()
        if not cal.is_trading_day(now.date()) or not WATCH_FROM <= now.time() < WATCH_UNTIL:
            return {}
        out: dict[str, str] = {}
        st = self.repo.get_meta_json("recorder_status")
        age = (now - datetime.fromisoformat(st["ts"])).total_seconds() if st and st.get("ts") else None
        if age is None or age > HEARTBEAT_STALE_S:
            when = f"{age / 60:.0f} min ago" if age is not None else "never"
            out["heartbeat"] = (f"🔴 <b>Recorder service not responding</b> (last heartbeat {when}). No market data, "
                                "no new signals and <b>no exit alerts</b> until it's back. Check the recorder "
                                "service on Railway.")
            return out                                     # nothing else can be judged without it
        market = MARKET_FROM <= now.time() < MARKET_UNTIL
        if market and st.get("state") != "running":
            reason = ("it stopped repeatedly and is no longer restarted automatically" if st.get("gave_up")
                      else f"recorder state: {st.get('state')}")
            out["session"] = (f"🔴 <b>Today's session isn't running</b> ({reason}). Open signals aren't being "
                              "monitored. Start it from the Connectors page.")
        elif market:
            last = self.store.last_bar_ts()
            if last is not None:
                last = last.replace(tzinfo=IST) if last.tzinfo is None else last
            stale = last is None or last < at_ist(now.date(), time(0)) or (now - last).total_seconds() > DATA_STALE_S
            if stale:
                when = last.astimezone(IST).strftime("%H:%M") if last and last.date() == now.date() else "none today"
                out["data"] = (f"⚠️ <b>No market data saved for 3+ minutes</b> (last bar: {when}) although the session "
                               "is running. It may be hung; restart it from the Connectors page if this persists.")
        return out

    def check(self) -> list[str]:
        """Run once; returns the alerts sent (raise and clear are both reported once)."""
        now = self.now_fn()
        state = self.repo.get_meta_json(STATE_KEY) or {}
        active: dict = state.get("active", {})             # key → {"since", "alerted"}
        found = self.problems(now)
        sent = []
        for key, message in found.items():
            entry = active.setdefault(key, {"since": now.isoformat(), "alerted": False})
            grace = SESSION_GRACE_S if key == "session" else 0
            if not entry["alerted"] and (now - datetime.fromisoformat(entry["since"])).total_seconds() >= grace:
                self.notify(message)
                entry["alerted"] = True
                sent.append(message)
        for key in [k for k in active if k not in found]:
            if active[key]["alerted"]:
                msg = {"heartbeat": "✅ Recorder service is responding again.",
                       "session": "✅ Today's session is running again.",
                       "data": "✅ Market data is being saved again."}[key]
                self.notify(msg)
                sent.append(msg)
            del active[key]
        self.repo.set_meta_json(STATE_KEY, {"active": active, "checked_at": now.isoformat()})
        return sent

    # ── Background thread (API process) ──────────────────────────────────────

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="recorder-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_EVERY_S):
            try:
                self.check()
            except Exception:
                logger.exception("Watchdog check failed")


def status(repo, store, now: datetime, calendar: NseCalendar) -> tuple[int, dict]:
    """For an external uptime monitor: 200 when the recorder is fine (or not needed now), else 503."""
    wd = Watchdog(repo, store, lambda m: None, lambda: calendar, now_fn=lambda: now)
    found = wd.problems(now)
    st = repo.get_meta_json("recorder_status") or {}
    body = {"status": "problem" if found else "ok", "problems": sorted(found),
            "recorder_state": st.get("state"), "checked_at": now.isoformat(timespec="seconds")}
    return (503 if found else 200), body

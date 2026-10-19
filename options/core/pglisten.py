"""A thread that LISTENs on a Postgres channel and calls back on every NOTIFY.

Used by the recorder to wake its main loop the moment the API asks for an Option Check, instead of
waiting for the next one-second turn. Reconnects on its own; does nothing on other databases.
"""

import threading
from collections.abc import Callable

from utils.logger import setup_logger

logger = setup_logger("options.pglisten")

RECONNECT_S = (0.5, 1, 2, 5, 10, 30)


class Listener:
    def __init__(self, engine, channel: str, on_notify: Callable[[str], None]):
        self.engine, self.channel, self.on_notify = engine, channel, on_notify
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if self.engine.dialect.name != "postgresql" or self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._run, name=f"listen-{self.channel}", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        import psycopg

        url = self.engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
        failures = 0
        while not self._stop.is_set():
            try:
                with psycopg.connect(url, autocommit=True, connect_timeout=10) as conn:
                    conn.execute(f"LISTEN {self.channel}")
                    failures = 0
                    while not self._stop.is_set():
                        for note in conn.notifies(timeout=1.0, stop_after=20):
                            try:
                                self.on_notify(note.payload)
                            except Exception:
                                logger.exception("Handling a %s notification failed", self.channel)
            except Exception as e:
                failures += 1
                if failures == 1 or failures % 20 == 0:
                    logger.warning("Listener on %s dropped (%d): %s", self.channel, failures, type(e).__name__)
            self._stop.wait(RECONNECT_S[min(failures, len(RECONNECT_S)) - 1] if failures else 0.5)

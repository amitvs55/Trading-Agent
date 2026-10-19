"""Live index levels, pushed: the recorder NOTIFYs Postgres, this hub fans out to every open page.

One listener per API process (a thread on its own psycopg connection, LISTEN live_indices) hands
each update to the event loop; every stream holds a one-slot mailbox, so a slow phone gets the
newest levels next, never a backlog of old ones. Without Postgres (local SQLite), or while the
listener reconnects, the saved copy is read every POLL_S instead, so the page never freezes.
"""

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Callable

from options.core.calendar import NseCalendar, now_ist
from options.market_data.live import market_window
from options.storage import LIVE_CHANNEL, Store
from utils.logger import setup_logger

logger = setup_logger("api.live")

POLL_S = 0.25               # fallback read of the saved copy (SQLite, or the listener is down)
CATCH_UP_S = 5.0            # with the listener up, still re-read the saved copy this often
HEARTBEAT_S = 15.0          # keeps phone networks and proxies from dropping a quiet stream
ROTATE_S = 600.0            # each stream ends after 10 min, before any proxy limit; the page reconnects at once
RECONNECT_S = (0.5, 1, 2, 5, 10)


def _newer(a: dict | None, b: dict | None) -> bool:
    """Is snapshot a newer than b? By the recorder's send time (a restarted recorder starts its
    sequence again, so the sequence only breaks ties)."""
    if not a:
        return False
    if not b:
        return True
    return (a.get("sent_ms") or 0, a.get("seq") or 0) > (b.get("sent_ms") or 0, b.get("seq") or 0)


class LiveHub:
    def __init__(self, store_fn: Callable[[], Store]):
        self.store_fn = store_fn
        self.latest: dict | None = None
        self.listening = False
        self.received = 0
        self._mailboxes: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def ensure_started(self) -> None:
        """Started by the first stream, so processes and tests that never stream never listen."""
        with self._lock:
            self._loop = asyncio.get_running_loop()             # the loop the streams run on
            if self._threads:
                return
            self._stop.clear()
            store = self.store_fn()
            self._accept(_read_saved(store))
            if store.engine.dialect.name == "postgresql":
                self._spawn(self._listen, "live-listen")
            self._spawn(self._poll, "live-poll")

    def _spawn(self, target, name: str) -> None:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)
        self._threads = []

    # ── Sources (threads) ────────────────────────────────────────────────────

    def _listen(self) -> None:
        import psycopg

        url = self.store_fn().engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
        failures = 0
        while not self._stop.is_set():
            try:
                with psycopg.connect(url, autocommit=True, connect_timeout=10) as conn:
                    conn.execute(f"LISTEN {LIVE_CHANNEL}")
                    self.listening, failures = True, 0
                    logger.info("Listening for live index levels")
                    while not self._stop.is_set():
                        for note in conn.notifies(timeout=1.0, stop_after=50):
                            self._from_thread(note.payload)
            except Exception as e:
                failures += 1
                if failures == 1 or failures % 30 == 0:
                    logger.warning("Live listener dropped (%d): %s; reading the saved copy meanwhile",
                                   failures, type(e).__name__)
            finally:
                self.listening = False
            self._stop.wait(RECONNECT_S[min(failures, len(RECONNECT_S)) - 1] if failures else 0.5)

    def _poll(self) -> None:
        store = self.store_fn()
        last_read = 0.0
        while not self._stop.wait(POLL_S):
            now = time.monotonic()
            if self.listening and now - last_read < CATCH_UP_S:
                continue
            last_read = now
            snap = _read_saved(store)
            if snap is not None:
                self._call(self._accept, snap)

    def _from_thread(self, payload: str) -> None:
        try:
            snap = json.loads(payload)
        except ValueError:
            return
        self._call(self._accept, snap)

    def _call(self, fn, arg) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(fn, arg)
            except RuntimeError:
                pass                                            # the loop is shutting down

    # ── Fan-out (event loop) ─────────────────────────────────────────────────

    def _accept(self, snap: dict | None) -> None:
        if not _newer(snap, self.latest):
            return
        self.latest = snap
        self.received += 1
        for box in list(self._mailboxes):
            if box.full():
                box.get_nowait()                                # drop the older one: newest wins
            box.put_nowait(snap)

    def subscribe(self) -> asyncio.Queue:
        box: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._mailboxes.add(box)
        return box

    def unsubscribe(self, box: asyncio.Queue) -> None:
        self._mailboxes.discard(box)


def _read_saved(store: Store) -> dict | None:
    try:
        return store.live_snapshot()
    except Exception:
        return None


def with_market(snap: dict | None, calendar: NseCalendar) -> dict:
    """What the page needs besides the levels: open/close times to count against its synced clock."""
    out = dict(snap or {"v": 1, "items": []})
    out["market"] = market_window(calendar, now_ist())
    out["server_ms"] = int(time.time() * 1000)
    return out


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def stream(hub: LiveHub, calendar_fn: Callable[[], NseCalendar], is_disconnected,
                 heartbeat_s: float = HEARTBEAT_S, rotate_s: float = ROTATE_S) -> AsyncIterator[str]:
    """SSE: the latest levels at once, then each newer one as it lands, and a heartbeat when quiet.
    After `rotate_s` it says `bye` and ends, so no proxy ever cuts it mid-update; the page reconnects
    straight away and keeps showing the levels it has."""
    hub.ensure_started()
    box = hub.subscribe()
    ends = time.monotonic() + rotate_s
    try:
        yield "retry: 1000\n\n"
        yield sse("levels", with_market(hub.latest, calendar_fn()))
        while (left := ends - time.monotonic()) > 0:
            try:
                snap = await asyncio.wait_for(box.get(), timeout=min(heartbeat_s, left))
                yield sse("levels", with_market(snap, calendar_fn()))
            except asyncio.TimeoutError:
                if await is_disconnected():
                    return
                yield sse("ping", {"market": market_window(calendar_fn(), now_ist()), "server_ms": int(time.time() * 1000)})
        yield sse("bye", {"reconnect": True})
    finally:
        hub.unsubscribe(box)

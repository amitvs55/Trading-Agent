"""Durable, non-blocking alert delivery.

`send()` stores the alert in `alerts_outbox` and returns at once, so a slow or failing Telegram
never holds up the signal engine (a send used to block for up to ~30 s per retry). One sender
thread delivers alerts strictly in order, retrying with backoff for up to MAX_AGE. An alert that
can't be delivered in time, or that the channel rejects outright, goes to the fallback channel
(e-mail) when one is configured. Alerts still pending when the process stops are picked up by the
next process; ones too old to matter are marked expired instead of being sent late.
"""

import hashlib
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from options.core.calendar import now_ist
from options.notify.base import Buttons, Channel, Delivery, logger

MAX_AGE = timedelta(minutes=15)          # a signal card older than its validity window is useless
DUPLICATE_WINDOW = timedelta(minutes=2)  # the same text twice within this is dropped
MIN_GAP_S = 0.35                         # Telegram allows ~1 message a second per chat in bursts
MAX_BACKOFF_S = 30.0


@dataclass
class _Item:
    id: int | None
    text: str
    buttons: Buttons | None
    created_at: datetime
    attempts: int = 0
    next_try: datetime | None = None


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class OutboxNotifier:
    name = "outbox"

    def __init__(self, store, channel: Channel, fallback: Channel | None = None, *,
                 now_fn: Callable[[], datetime] = now_ist, max_age: timedelta = MAX_AGE,
                 duplicate_window: timedelta = DUPLICATE_WINDOW, min_gap_s: float = MIN_GAP_S,
                 start: bool = True):
        self.store = store
        self.channel = channel
        self.fallback = fallback
        self.now_fn = now_fn
        self.max_age = max_age
        self.duplicate_window = duplicate_window
        self.min_gap_s = min_gap_s
        self._queue: deque[_Item] = deque()
        self._cond = threading.Condition()
        self._stop = False
        self._busy = False
        self._last_send = 0.0
        self.sent = self.failed = self.expired = 0
        self._recover()
        self._thread: threading.Thread | None = None
        if start:
            self._thread = threading.Thread(target=self._loop, name="alerts-outbox", daemon=True)
            self._thread.start()

    # ── Producer side (any thread) ───────────────────────────────────────────

    def send(self, text: str, buttons: Buttons | None = None) -> bool:
        """Queue an alert. Never blocks on the network and never raises."""
        now = self.now_fn()
        alert_id = None
        try:
            alert_id = self.store.outbox_add(digest(text), text, json.dumps(buttons) if buttons else None, now,
                                             duplicate_since=now - self.duplicate_window)
            if alert_id is None:
                logger.info("Duplicate alert dropped: %s", text[:80])
                return True
        except Exception:
            logger.exception("Couldn't store an alert; delivering it from memory only")
        with self._cond:
            self._queue.append(_Item(alert_id, text, buttons, now))
            self._cond.notify()
        return True

    # ── Delivery (sender thread, or the tests calling process() directly) ────

    def process(self) -> float | None:
        """Deliver every alert that is due. Returns seconds until the next retry, or None when empty."""
        while True:
            with self._cond:
                if not self._queue:
                    return None
                item = self._queue[0]
                self._busy = True
            try:
                now = self.now_fn()
                if now - item.created_at > self.max_age:
                    self._give_up(item, "expired", f"not delivered within {self.max_age.seconds // 60} min")
                    continue
                if item.next_try and now < item.next_try:
                    return (item.next_try - now).total_seconds()
                gap = self.min_gap_s - (time.monotonic() - self._last_send)
                if gap > 0:
                    time.sleep(gap)
                result = self._deliver(self.channel, item)
                self._last_send = time.monotonic()
                item.attempts += 1
                if result.ok:
                    self._done(item, "sent", self.channel.name, None, now)
                    self.sent += 1
                elif result.permanent:
                    self._give_up(item, "failed", result.error)
                else:
                    wait = min(result.retry_after or 2 ** item.attempts, MAX_BACKOFF_S)
                    item.next_try = now + timedelta(seconds=wait)
                    self._update(item, attempts=item.attempts, last_error=result.error)
                    logger.warning("Alert delivery failed (attempt %d), retrying in %.0fs: %s",
                                   item.attempts, wait, result.error)
                    return wait
            finally:
                with self._cond:
                    self._busy = False
                    self._cond.notify_all()

    def drain(self, timeout: float = 60.0) -> bool:
        """Wait until every queued alert is delivered or given up (call before the process exits)."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._queue or self._busy:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(min(left, 0.5))
        return True

    def close(self, timeout: float = 60.0) -> bool:
        drained = self.drain(timeout) if self._thread else True
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=5)
        return drained

    # ── Internals ────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._stop:
                    self._cond.wait(1.0)
                if self._stop and not self._queue:
                    return
            try:
                wait = self.process()
            except Exception:
                logger.exception("Alert sender error")
                wait = 5.0
            if wait:
                with self._cond:
                    if not self._stop:
                        self._cond.wait(min(wait, MAX_BACKOFF_S))
                    elif self._queue:
                        return                         # stopping: whatever is left stays pending in the DB

    def _deliver(self, channel: Channel, item: _Item) -> Delivery:
        try:
            return channel.deliver(item.text, item.buttons)
        except Exception as e:                        # a channel must never kill the sender
            return Delivery(False, error=f"{type(e).__name__}")

    def _give_up(self, item: _Item, status: str, error: str | None) -> None:
        """Try the fallback channel once; otherwise record why the alert was never delivered."""
        now = self.now_fn()
        if self.fallback is not None:
            res = self._deliver(self.fallback, item)
            if res.ok:
                self._done(item, "sent", self.fallback.name, error, now)
                self.sent += 1
                return
            error = f"{error}; {self.fallback.name}: {res.error}"
        if status == "expired":
            self.expired += 1
        else:
            self.failed += 1
        logger.error("Alert %s (%s): %s", status, error, item.text[:120])
        self._done(item, status, None, error, None)

    def _done(self, item: _Item, status: str, channel: str | None, error: str | None, sent_at) -> None:
        with self._cond:
            if self._queue and self._queue[0] is item:
                self._queue.popleft()
        self._update(item, status=status, channel=channel, attempts=item.attempts, last_error=error, sent_at=sent_at)

    def _update(self, item: _Item, **values) -> None:
        if item.id is None:
            return
        try:
            self.store.outbox_update(item.id, **values)
        except Exception:
            logger.exception("Couldn't update alert %s", item.id)

    def _recover(self) -> None:
        """Alerts a previous process queued but never delivered: send the fresh ones, expire the rest."""
        try:
            rows = self.store.outbox_pending()
        except Exception:
            logger.exception("Couldn't read pending alerts")
            return
        now = self.now_fn()
        stale = 0
        for r in rows:
            created = r["created_at"]
            if created.tzinfo is None:
                created = created.replace(tzinfo=now.tzinfo)
            if now - created > self.max_age:
                stale += 1
                self.store.outbox_update(r["id"], status="expired", last_error="process restarted before delivery")
                continue
            buttons = [tuple(b) for b in json.loads(r["buttons"])] if r["buttons"] else None
            self._queue.append(_Item(r["id"], r["text"], buttons, created, r["attempts"] or 0))
        if stale:
            logger.warning("%d alert(s) from an earlier run expired undelivered", stale)

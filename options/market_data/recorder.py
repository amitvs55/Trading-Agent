"""Records spot, India VIX, near-month futures and an ATM ± N option window as 1-minute bars.

The strike window follows the index: once a minute it is re-centred and any new strikes
are added (never removed, so a fast move still leaves a continuous record of earlier ATMs).
"""

import threading
import time as _time
from datetime import datetime
from typing import Callable, Protocol

from options.core.calendar import IST, MARKET_OPEN, NseCalendar, at_ist, now_ist
from options.market_data.bars import BarAggregator
from options.notify.base import Notifier
from options.reference import IndexReference
from utils.logger import setup_logger

logger = setup_logger("options.recorder")

MAX_PENDING_ROWS = 200_000      # bars kept in memory while the database is unreachable
INDEX_JUMP, VIX_JUMP = 0.05, 0.25


class Ticker(Protocol):
    def start(self, on_ticks: Callable[[list[dict]], None], on_connect: Callable[[], None],
              on_event: Callable[[str, str], None]) -> None: ...
    def subscribe(self, tokens: list[int]) -> None: ...
    def stop(self) -> None: ...


class Recorder:
    def __init__(self, ticker: Ticker, refs: list[IndexReference], store, notifier: Notifier, *,
                 vix_token: int | None = None, window: int = 15, n_expiries: int = 2,
                 stale_after_s: int = 60, calendar: NseCalendar | None = None,
                 now_fn: Callable[[], datetime] = now_ist, extra_tokens: set[int] | None = None,
                 on_bars: Callable[[list[dict]], None] | None = None,
                 on_tick: Callable[[datetime], None] | None = None,
                 on_minute: Callable[[datetime], None] | None = None, live=None):
        self.ticker = ticker
        self.refs = refs
        self.store = store
        self.notifier = notifier
        self.vix_token = vix_token
        self.window = window
        self.n_expiries = n_expiries
        self.stale_after_s = stale_after_s
        self.calendar = calendar or NseCalendar()
        self.now_fn = now_fn
        self.extra_tokens = set(extra_tokens or ())     # heavyweights, open-signal contracts, …
        self.on_bars = on_bars                          # the signal engine's feed of closed bars
        self.on_tick = on_tick                          # called every loop iteration
        self.on_minute = on_minute                      # called once a minute (metrics)
        self.live = live                                # LiveIndexFeed: index levels for the dashboard
        self._hook_errors = 0

        self.agg = BarAggregator()
        self.subscribed: set[int] = set()
        self.bars_written = 0
        self.disconnects = 0
        self.stale_alerts = 0
        self.started_at: datetime | None = None
        self._stale = False
        self._pending: list[dict] = []
        self._events: list[tuple[datetime, str, str]] = []
        self._events_lock = threading.Lock()

    # ── WebSocket callbacks (run on the ticker thread) ───────────────────────

    def _on_connect(self) -> None:
        self.ticker.subscribe(sorted(self.subscribed))     # also after every reconnect

    def _on_ticks(self, ticks: list[dict]) -> None:
        now = self.now_fn()
        live = self.live
        for tick in ticks:
            if self.agg.add(tick, now) and live is not None:
                live.on_tick(tick, now)                 # only ticks that passed the bad-print guard

    def _on_event(self, kind: str, detail: str) -> None:
        with self._events_lock:
            self._events.append((self.now_fn(), kind, detail))

    # ── Main-thread work ─────────────────────────────────────────────────────

    def window_tokens(self, prices: dict[str, float]) -> set[int]:
        tokens: set[int] = set()
        for ref in self.refs:
            price = prices.get(ref.index)
            if price:
                tokens |= {o.token for o in ref.window(price, self.window, self.n_expiries)}
        return tokens

    def start(self, prices: dict[str, float]) -> None:
        """prices: index → current level, used to centre the first strike window."""
        self.started_at = self.now_fn()
        self.subscribed = {t for ref in self.refs for t in (ref.spot_token, ref.future_token)}
        if self.vix_token:
            self.subscribed.add(self.vix_token)
        # Bad-print guard: the index and its future can't move 5% between two ticks; VIX can jump more
        self.agg.jump_limits.update({t: INDEX_JUMP for ref in self.refs for t in (ref.spot_token, ref.future_token)})
        if self.vix_token:
            self.agg.jump_limits[self.vix_token] = VIX_JUMP
        self.subscribed |= self.extra_tokens
        if self.live is not None:
            self.subscribed |= set(self.live.by_token)
            self.agg.jump_limits.update({t: INDEX_JUMP for t in self.live.by_token})
            self.live.start()
        self.subscribed |= self.window_tokens(prices)
        logger.info("Subscribing %d instruments", len(self.subscribed))
        self.ticker.start(on_ticks=self._on_ticks, on_connect=self._on_connect, on_event=self._on_event)

    def recentre(self) -> int:
        prices = {}
        for ref in self.refs:
            price = self.agg.last_price.get(ref.spot_token) or self.agg.last_price.get(ref.future_token)
            if price:
                prices[ref.index] = price
        added = self.window_tokens(prices) - self.subscribed
        if added:
            self.subscribed |= added
            self.ticker.subscribe(sorted(added))
            logger.info("Strike window moved: +%d instruments", len(added))
        return len(added)

    def flush(self, now: datetime, final: bool = False) -> None:
        bars = self.agg.pop_all() if final else self.agg.pop_closed(now)
        rows = [b.as_row() for b in bars]
        if rows and self.on_bars:
            self._safe(self.on_bars, rows)
        self._pending.extend(rows)
        if self._pending:
            try:
                self.bars_written += self.store.write_bars(self._pending)
                self._pending = []
            except Exception as e:
                logger.error("Writing %d bars failed, will retry: %s", len(self._pending), e)
                if len(self._pending) > MAX_PENDING_ROWS:
                    dropped = len(self._pending) - MAX_PENDING_ROWS
                    self._pending = self._pending[dropped:]
                    logger.error("Dropped %d oldest unsaved bars", dropped)

        with self._events_lock:
            events, self._events = self._events, []
        for ts, kind, detail in events:
            if kind == "close":
                self.disconnects += 1
            if kind == "noreconnect":
                self.notifier.send("🔴 <b>Market data disconnected</b> and could not reconnect. "
                                   "Recording has stopped for today.")
            try:
                self.store.log_event(f"ws_{kind}", detail, ts)
            except Exception as e:
                logger.error("Logging event failed: %s", e)

    def _safe(self, fn: Callable, arg) -> None:
        """Engine errors must never stop the recording."""
        try:
            fn(arg)
        except Exception:
            self._hook_errors += 1
            logger.exception("Signal engine hook failed")
            if self._hook_errors == 1:
                self.notifier.send("⚠️ <b>Signal engine error.</b> Recording continues; check the logs.")

    def check_stale(self, now: datetime) -> None:
        if not self.calendar.is_market_open(now):
            return
        last = self.agg.last_tick_at or max(self.started_at or now, at_ist(now.date(), MARKET_OPEN))
        silent_s = (now - last).total_seconds()
        if silent_s > self.stale_after_s and not self._stale:
            self._stale = True
            self.stale_alerts += 1
            self.notifier.send(f"⚠️ <b>No market data for {silent_s:.0f}s.</b> "
                               "Signals will pause until the feed recovers.")
        elif self._stale and silent_s <= self.stale_after_s:
            self._stale = False
            self.notifier.send("✅ Market data feed recovered.")

    def run_until(self, end: datetime, poll_s: float = 1.0, sleep: Callable[[float], None] = _time.sleep) -> None:
        last_recentre: datetime | None = None
        try:
            while (now := self.now_fn()) < end:
                self.flush(now)
                if last_recentre is None or (now - last_recentre).total_seconds() >= 60:
                    self.recentre()
                    if last_recentre is not None and self.on_minute:
                        self._safe(self.on_minute, now)
                    last_recentre = now
                self.check_stale(now)
                if self.on_tick:
                    self._safe(self.on_tick, now)
                sleep(poll_s)
        finally:
            self.flush(self.now_fn(), final=True)
            self.ticker.stop()
            if self.live is not None:
                self.live.stop()

    def summary(self) -> dict:
        return {
            "instruments": len(self.subscribed),
            "ticks": self.agg.tick_count,
            "bars_written": self.bars_written,
            "bars_unsaved": len(self._pending),
            "late_ticks": self.agg.late_ticks,
            "rejected_ticks": self.agg.rejected_ticks,
            "disconnects": self.disconnects,
            "stale_alerts": self.stale_alerts,
            "engine_errors": self._hook_errors,
            "started_at": self.started_at.astimezone(IST).isoformat(timespec="seconds") if self.started_at else None,
        }

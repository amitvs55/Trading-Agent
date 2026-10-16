"""Tick → 1-minute bar aggregation with top-of-book and OI.

Ticks arrive on the WebSocket thread and bars are flushed from the main thread, so all
state sits behind one lock. One bar per instrument per minute is what the analysis agents
and backtests need; raw ticks would be ~1.5M rows a day for no extra signal at 5m.
"""

import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from options.core.calendar import IST

# Exchange timestamps further than this from our clock are treated as bad and replaced
MAX_CLOCK_SKEW_S = 300


@dataclass
class Bar:
    instrument_token: int
    ts: datetime                 # minute start, IST
    open: float
    high: float
    low: float
    close: float
    volume_day: int | None = None
    oi: int | None = None
    bid: float | None = None
    ask: float | None = None
    bid_qty: int | None = None
    ask_qty: int | None = None
    ticks: int = 0

    def as_row(self) -> dict:
        return asdict(self)


def tick_time(tick: dict, received_at: datetime) -> datetime:
    """Exchange time of a tick in IST.

    kiteconnect builds exchange_timestamp with datetime.fromtimestamp(), i.e. naive in the
    server's local zone, so astimezone() converts it correctly whatever TZ the host runs in.
    """
    received = received_at.astimezone(IST)
    ts = tick.get("exchange_timestamp")
    if isinstance(ts, datetime):
        ts = ts.astimezone(IST)
        if abs((ts - received).total_seconds()) <= MAX_CLOCK_SKEW_S:
            return ts
    return received


def minute_start(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def _top(depth: dict | None, side: str) -> dict:
    levels = (depth or {}).get(side) or []
    return levels[0] if levels else {}


class BarAggregator:
    def __init__(self):
        self._lock = threading.Lock()
        self._bars: dict[tuple[int, datetime], Bar] = {}
        self._flushed_until: datetime | None = None   # minutes before this were already written
        self.last_price: dict[int, float] = {}
        self.last_quote: dict[int, tuple[float | None, float | None]] = {}   # token → (bid, ask)
        self.last_tick_at: datetime | None = None
        self.tick_count = 0
        self.late_ticks = 0

    def add(self, tick: dict, received_at: datetime) -> None:
        token, price = tick.get("instrument_token"), tick.get("last_price")
        if token is None or not price or price <= 0:
            return
        minute = minute_start(tick_time(tick, received_at))
        bid, ask = _top(tick.get("depth"), "buy"), _top(tick.get("depth"), "sell")

        with self._lock:
            self.tick_count += 1
            self.last_tick_at = received_at
            self.last_price[token] = price
            if bid.get("price") or ask.get("price"):
                self.last_quote[token] = (float(bid["price"]) if bid.get("price") else None,
                                          float(ask["price"]) if ask.get("price") else None)
            if self._flushed_until is not None and minute < self._flushed_until:
                self.late_ticks += 1
                return

            bar = self._bars.get((token, minute))
            if bar is None:
                bar = self._bars[(token, minute)] = Bar(token, minute, price, price, price, price)
            else:
                bar.high = max(bar.high, price)
                bar.low = min(bar.low, price)
                bar.close = price
            bar.ticks += 1
            if tick.get("volume_traded") is not None:
                bar.volume_day = int(tick["volume_traded"])
            if tick.get("oi") is not None:
                bar.oi = int(tick["oi"])
            if bid.get("price"):
                bar.bid, bar.bid_qty = float(bid["price"]), int(bid.get("quantity") or 0)
            if ask.get("price"):
                bar.ask, bar.ask_qty = float(ask["price"]), int(ask.get("quantity") or 0)

    def quote(self, token: int) -> tuple[float | None, float | None]:
        with self._lock:
            return self.last_quote.get(token, (None, None))

    def pop_closed(self, now: datetime, grace_s: float = 3.0) -> list[Bar]:
        """Remove and return bars whose minute ended at least `grace_s` seconds ago."""
        cutoff = minute_start((now - timedelta(seconds=grace_s)).astimezone(IST))
        with self._lock:
            bars = [self._bars.pop(k) for k in [k for k in self._bars if k[1] < cutoff]]
            if self._flushed_until is None or cutoff > self._flushed_until:
                self._flushed_until = cutoff
        return sorted(bars, key=lambda b: (b.ts, b.instrument_token))

    def pop_all(self) -> list[Bar]:
        with self._lock:
            bars = list(self._bars.values())
            self._bars.clear()
            if bars:
                end = max(b.ts for b in bars) + timedelta(minutes=1)
                if self._flushed_until is None or end > self._flushed_until:
                    self._flushed_until = end
        return sorted(bars, key=lambda b: (b.ts, b.instrument_token))

"""Live index levels for the dashboard: from the exchange tick to the screen in well under a second.

The recorder hands every accepted index tick to LiveIndexFeed on the WebSocket thread. A
publisher thread sends the latest levels on the leading edge (a lone tick goes out at once)
and at most every MIN_GAP_S (a burst is coalesced to its newest value). Store.publish_live
keeps a copy for pages that have just opened and, on Postgres, NOTIFYs the API, which pushes
the levels to every open dashboard over one stream; nobody polls.

Times are the exchange's own (each tick's exchange timestamp), so every screen shows the same
"as of" whatever its clock says; the dashboard judges staleness against the server-synced clock.
A level never goes backwards: a tick older than the one already held is ignored.

The previous close is fixed once per session (so % change can't wobble): from the broker's quote
during market hours, where it is checked against the quote's own net change, or else from the
last saved bar of the previous session.
"""

import threading
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable

from options.core.calendar import IST, MARKET_CLOSE, MARKET_OPEN, NseCalendar, at_ist, now_ist
from options.market_data.bars import tick_time
from utils.logger import setup_logger

logger = setup_logger("options.live")

MIN_GAP_S = 0.25            # at most 4 updates a second: smooth to the eye, light on the database
PERSIST_EVERY_S = 1.0       # the saved copy is refreshed at most once a second
LIVE_SYMBOLS = ("NIFTY 50", "SENSEX")


def epoch_ms(ts: datetime) -> int:
    return int(ts.timestamp() * 1000)


@dataclass
class Level:
    ltp: float
    exchange_ts: datetime


class LiveIndexFeed:
    def __init__(self, store, tokens: dict[str, int], session_date: date, *,
                 now_fn: Callable[[], datetime] = now_ist, min_gap_s: float = MIN_GAP_S,
                 persist_every_s: float = PERSIST_EVERY_S):
        self.store = store
        self.tokens = dict(tokens)                                  # "NIFTY 50" → instrument token
        self.by_token = {t: s for s, t in self.tokens.items()}
        self.session_date = session_date
        self.now_fn = now_fn
        self.min_gap_s, self.persist_every_s = min_gap_s, persist_every_s
        self.prev_close: dict[str, float] = {}
        self.prev_source: dict[str, str] = {}
        self.seq = 0
        self.published = 0
        self.errors = 0
        self._levels: dict[str, Level] = {}
        self._dirty = False
        self._lags_ms: list[float] = []
        self._last_persist: datetime | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Previous close ───────────────────────────────────────────────────────

    def resume(self) -> None:
        """After a restart mid-session: keep today's previous closes and last levels."""
        try:
            snap = self.store.live_snapshot()
        except Exception:
            logger.exception("Reading the saved live levels failed")
            return
        if not snap or snap.get("session") != self.session_date.isoformat():
            return
        for item in snap.get("items", []):
            sym = item.get("symbol")
            if sym in self.tokens and item.get("prev_close"):
                self.prev_close[sym] = float(item["prev_close"])
                self.prev_source[sym] = item.get("prev_source") or "saved"
            if sym in self.tokens and item.get("ltp") and item.get("ts"):
                self._levels[sym] = Level(float(item["ltp"]), datetime.fromtimestamp(item["ts"] / 1000, tz=IST))

    def set_prev_close(self, symbol: str, value: float | None, source: str) -> bool:
        """Fixed once per session; a quote taken in market hours outranks saved bars."""
        if symbol not in self.tokens or not value or value <= 0:
            return False
        with self._lock:
            if self.prev_source.get(symbol) == "quote" or (symbol in self.prev_close and source != "quote"):
                return False
            self.prev_close[symbol] = round(float(value), 2)
            self.prev_source[symbol] = source
            self._dirty = True
        self._wake.set()
        return True

    def missing_quote_close(self) -> list[str]:
        return [s for s in self.tokens if self.prev_source.get(s) != "quote"]

    def load_quote_closes(self, quotes: dict[str, dict], now: datetime, calendar: NseCalendar) -> list[str]:
        """quotes: symbol → {ltp, close, net_change}. Before the open a quote may still describe the
        day before, so it only counts in market hours; there, ltp − net change must agree with close."""
        if not calendar.is_market_open(now):
            return []
        return [sym for sym, q in quotes.items() if self.set_prev_close(sym, quote_close(sym, q), "quote")]

    def load_saved_closes(self, calendar: NseCalendar) -> list[str]:
        """The previous session's last recorded bar (only if it reached the close)."""
        prev_day = calendar.previous_trading_day(self.session_date)
        done = []
        for sym, token in self.tokens.items():
            if sym in self.prev_close:
                continue
            try:
                rows = self.store.bars_between(at_ist(prev_day, time(15, 25)), at_ist(prev_day, time(15, 31)), {token})
            except Exception:
                logger.exception("Reading the saved close of %s failed", sym)
                continue
            if rows and self.set_prev_close(sym, rows[-1]["close"], "saved"):
                done.append(sym)
        return done

    # ── Ticks (WebSocket thread) ─────────────────────────────────────────────

    def on_tick(self, tick: dict, received_at: datetime) -> None:
        sym = self.by_token.get(tick.get("instrument_token"))
        price = tick.get("last_price")
        if sym is None or not price:
            return
        ts = tick_time(tick, received_at)
        with self._lock:
            cur = self._levels.get(sym)
            if cur is not None and ts < cur.exchange_ts:
                return                                              # an older tick never replaces a newer one
            self._levels[sym] = Level(float(price), ts)
            self._dirty = True
        self._wake.set()

    # ── Publishing (own thread) ──────────────────────────────────────────────

    def snapshot(self, now: datetime) -> dict:
        with self._lock:
            self.seq += 1
            items = []
            for sym in self.tokens:
                lvl = self._levels.get(sym)
                items.append({"symbol": sym, "ltp": lvl.ltp if lvl else None,
                              "ts": epoch_ms(lvl.exchange_ts) if lvl else None,
                              "prev_close": self.prev_close.get(sym), "prev_source": self.prev_source.get(sym)})
            self._dirty = False
            return {"v": 1, "seq": self.seq, "session": self.session_date.isoformat(),
                    "sent_ms": epoch_ms(now), "items": items}

    def publish_once(self, force_persist: bool = False) -> dict | None:
        now = self.now_fn()
        snap = self.snapshot(now)
        persist = force_persist or self._last_persist is None or \
            (now - self._last_persist).total_seconds() >= self.persist_every_s
        try:
            self.store.publish_live(snap, now, persist=persist)
        except Exception as e:
            self.errors += 1
            if self.errors == 1 or self.errors % 600 == 0:
                logger.error("Publishing live levels failed (%d so far): %s", self.errors, type(e).__name__)
            with self._lock:
                self._dirty = True                                  # try again on the next wake
            return None
        if persist:
            self._last_persist = now
        self.published += 1
        with self._lock:
            self._lags_ms += [snap["sent_ms"] - i["ts"] for i in snap["items"] if i["ts"]]
            self._lags_ms = self._lags_ms[-5000:]
        return snap

    def _run(self) -> None:
        while not self._stop.is_set():
            woke = self._wake.wait(timeout=1.0)
            if self._stop.is_set():
                break
            if not woke:
                continue
            self._wake.clear()
            if self._dirty:
                self.publish_once()
                self._stop.wait(self.min_gap_s)                     # coalesce whatever arrives meanwhile

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="live-indices", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if self._levels or self.prev_close:
            self.publish_once(force_persist=True)

    def close_out(self, quotes: dict[str, dict], at: datetime) -> None:
        """After the close: the official closing levels (from a quote taken a few minutes later),
        stamped with the close time, so the evening shows exactly what NSE and BSE published."""
        with self._lock:
            for sym, q in quotes.items():
                if sym in self.tokens and q.get("ltp"):
                    self._levels[sym] = Level(float(q["ltp"]), at)
        self.publish_once(force_persist=True)

    def take_lag_ms(self) -> float | None:
        """95th percentile of exchange tick → published since the last call (for session metrics)."""
        with self._lock:
            lags, self._lags_ms = sorted(self._lags_ms), []
        if not lags:
            return None
        return round(lags[min(len(lags) - 1, int(len(lags) * 0.95))], 1)


def quote_close(name: str, q: dict) -> float | None:
    """A quote's previous close, cross-checked: ltp − net change must give the same number."""
    ltp, close, change = q.get("ltp"), q.get("close"), q.get("net_change")
    if not close:
        return None
    if ltp and change is not None and abs((ltp - change) - close) > max(0.05, close * 1e-5):
        logger.warning("Quote for %s: close %.2f disagrees with ltp − change %.2f; using the latter",
                       name, close, ltp - change)
        return round(ltp - change, 2)
    return close


class CloseKeeper:
    """Previous closes from the broker's quote once the market is open (a quote taken before the open
    can still describe the day before): the live ticker's, and the breadth heavyweights' that the
    warm-up couldn't price. Called once a minute until everything has one or it gives up."""

    MAX_FAILURES = 30

    def __init__(self, broker, live: LiveIndexFeed | None, constituents: dict, calendar: NseCalendar):
        self.broker, self.live, self.constituents, self.calendar = broker, live, constituents, calendar
        self.failures = 0
        self.done = not hasattr(broker, "quotes")

    def maybe(self, now: datetime) -> None:
        if self.done or not self.calendar.is_market_open(now):
            return
        want = {s: self.live.tokens[s] for s in self.live.missing_quote_close()} if self.live else {}
        stocks = {c.symbol: c for cs in self.constituents.values() for c in cs if c.prev_close is None}
        want.update({sym: c.token for sym, c in stocks.items()})
        if not want:
            self.done = True
            return
        try:
            quotes = self.broker.quotes(want)
        except Exception as e:
            self.failures += 1
            from options.brokers.angel import brief_error
            logger.warning("Quotes for previous closes failed (%d): %s", self.failures, brief_error(e))
            self.done = self.failures >= self.MAX_FAILURES
            return
        indices = self.live.load_quote_closes({s: q for s, q in quotes.items() if s in self.live.tokens},
                                              now, self.calendar) if self.live else []
        priced = []
        for sym, c in stocks.items():
            if sym in quotes and (close := quote_close(sym, quotes[sym])):
                c.prev_close = close
                priced.append(sym)
        if indices or priced:
            logger.info("Previous closes from quotes: %s", ", ".join(indices + priced))


def market_window(calendar: NseCalendar, now: datetime) -> dict:
    """Open/close times the dashboard counts against its server-synced clock, so the label flips to
    "Closed" at 15:30:00 exactly, on every screen, without waiting for a message."""
    today = now.astimezone(IST).date()
    trading = calendar.is_trading_day(today)
    opens, closes = at_ist(today, MARKET_OPEN), at_ist(today, MARKET_CLOSE)
    if not trading or now >= closes:
        nxt = calendar.next_trading_day(today)
        opens, closes = at_ist(nxt, MARKET_OPEN), at_ist(nxt, MARKET_CLOSE)
        last = today if trading else calendar.previous_trading_day(today)
    else:
        last = calendar.previous_trading_day(today) if now < opens else today
    return {"open": calendar.is_market_open(now), "opens_ms": epoch_ms(opens), "closes_ms": epoch_ms(closes),
            "last_session": last.isoformat(), "last_close_ms": epoch_ms(at_ist(last, MARKET_CLOSE))}

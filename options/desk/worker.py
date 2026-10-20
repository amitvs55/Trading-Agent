"""Fills paper desk orders inside the recorder, from the live market feed.

The API saves an order and NOTIFYs `desk_order`; the recorder's main loop wakes at once and calls
`maybe()` on the main thread. The worker starts streaming the contract, fills a market order at the
live ask (buy) or bid (sell), and checks every working limit and stop order against the newest quote
on each turn of the loop (at least once a second). A contract with no tick yet is priced from the
broker's quote. At 15:20 it squares off intraday positions at the live bid.
"""

import threading
from collections import deque
from datetime import datetime, timedelta

from options.core.calendar import MARKET_OPEN, NseCalendar, at_ist
from options.desk import service
from options.desk.ledger import book
from options.desk.rules import ACTIVE, WAITING, Quote, charges_json, market_price, step
from utils.logger import setup_logger

logger = setup_logger("options.desk")

CHANNEL = "desk_order"
REFRESH_EVERY = timedelta(seconds=3)       # re-read the working orders at least this often
NO_PRICE_AFTER = timedelta(seconds=15)     # a market order with no price by then is rejected
REST_QUOTE_EVERY = timedelta(seconds=2)
HOUSEKEEP_EVERY = timedelta(seconds=30)


class DeskWorker:
    def __init__(self, recorder, broker, store, calendar: NseCalendar, live=None):
        self.recorder, self.broker, self.store, self.calendar, self.live = recorder, broker, store, calendar, live
        self._poke = True
        self._orders: list[dict] = []
        self._read_at: datetime | None = None
        self._housekept: datetime | None = None
        self._watch: deque[tuple[str, int]] = deque()
        self._lock = threading.Lock()
        self._rest: dict[int, tuple[datetime, Quote]] = {}

    # ── From the LISTEN thread ───────────────────────────────────────────────

    def poke(self, payload: str = "") -> None:
        """An order was placed or changed, or the ticket wants a contract streamed ("watch:<token>:<symbol>")."""
        if payload.startswith("watch:"):
            _, token, symbol = payload.split(":", 2)
            with self._lock:
                self._watch.append((symbol, int(token)))
        self._poke = True
        self.recorder.wake()

    # ── Main thread ──────────────────────────────────────────────────────────

    def follow(self, symbol: str, token: int) -> None:
        try:
            self.recorder.watch(token)
            if self.live is not None:
                self.live.watch(symbol, token, pin=True)
        except Exception:
            logger.exception("Couldn't start following %s", symbol)

    def follow_open(self) -> None:
        """At session start: every contract with an open position or a working order keeps streaming."""
        try:
            orders = self.store.desk_orders_current()
        except Exception:
            logger.exception("Couldn't read desk orders to follow")
            return
        for last_buy, _ in service.open_positions(orders):
            self.follow(last_buy["symbol"], int(last_buy["token"]))
        for o in orders:
            if o["status"] in ACTIVE:
                self.follow(o["symbol"], int(o["token"]))

    def quote(self, token: int, now: datetime, rest: bool = False) -> Quote | None:
        bid, ask = self.recorder.agg.quote(token)
        ltp = self.recorder.agg.last_price.get(token)
        if bid or ask or ltp:
            return Quote(bid, ask, ltp, "live")
        if not rest or not hasattr(self.broker, "quotes"):
            return None
        hit = self._rest.get(token)
        if hit and now - hit[0] < REST_QUOTE_EVERY:
            return hit[1]
        q = None
        try:
            sym = next((o["symbol"] for o in self._orders if int(o["token"]) == token), str(token))
            raw = self.broker.quotes({sym: token}).get(sym) or {}
            if raw.get("bid") or raw.get("ask") or raw.get("ltp"):
                q = Quote(raw.get("bid"), raw.get("ask"), raw.get("ltp"), "broker quote")
        except Exception as e:
            from options.brokers.angel import brief_error
            logger.warning("Quote for %s failed: %s", token, brief_error(e))
        self._rest[token] = (now, q)
        return q

    def maybe(self, now: datetime) -> None:
        with self._lock:
            watch, self._watch = list(self._watch), deque()
        for symbol, token in watch:
            self.follow(symbol, token)
        if self._poke or self._read_at is None or now - self._read_at >= REFRESH_EVERY:
            self._poke, self._read_at = False, now
            try:
                self._orders = self.store.desk_orders_active(ACTIVE)
            except Exception:
                logger.exception("Couldn't read desk orders")
                return
        if self.calendar.is_market_open(now):
            for o in list(self._orders):
                self._work(o, now)
        if self._housekept is None or now - self._housekept >= HOUSEKEEP_EVERY:
            self._housekept = now
            try:
                if service.housekeep(self.store, now, self.calendar, self.square_off):
                    self._poke = True
            except Exception:
                logger.exception("Desk end-of-session rules failed")

    def _work(self, o: dict, now: datetime) -> None:
        token = int(o["token"])
        fresh = o["status"] in WAITING
        if fresh:
            self.follow(o["symbol"], token)
        q = self.quote(token, now, rest=fresh and o["order_type"] == "MARKET")
        if q is None:
            waiting_since = max(o["created_at"], at_ist(now.date(), MARKET_OPEN))   # an AMO waits from the open
            if fresh and o["order_type"] == "MARKET" and now - waiting_since > NO_PRICE_AFTER and \
                    service.end(self.store, o, "REJECTED", "No live price for this contract", now):
                self._drop(o)
            return
        try:
            res = step(o, q, fresh)
            if res and res[0] == "trigger":
                if not self.store.desk_order_update(o["id"], from_status=(o["status"],), status="TRIGGERED",
                                                    updated_at=now):
                    return self._drop(o)
                o = {**o, "status": "TRIGGERED"}
                self._replace(o)
                res = step(o, q, True)
            if res and res[0] == "fill":
                self._fill(o, res[1], q, now)
            elif fresh and o["status"] in WAITING:
                if self.store.desk_order_update(o["id"], from_status=(o["status"],), status="OPEN", updated_at=now):
                    self._replace({**o, "status": "OPEN"})
                else:
                    self._drop(o)
        except Exception:
            logger.exception("Desk order %s failed", o["id"])

    def _fill(self, o: dict, price: float, q: Quote, now: datetime) -> None:
        if o["side"] == "BUY":
            acct = self.store.desk_account(o["username"])
            orders = self.store.desk_orders(o["username"], o["epoch"])
            free = book(acct, orders, {}, now)["funds"]["available"] + float(o.get("block") or 0.0)
            value = price * int(o["qty"])
            need = value + charges_json("BUY", value)["total"]
            if need > free + 0.005:
                service.end(self.store, o, "REJECTED", f"Not enough funds at the fill price: need ₹{need:,.0f}, "
                                                       f"₹{free:,.0f} free", now)
                return self._drop(o)
        at_market = price == market_price(o["side"], q)
        source = f"{q.source} {'ask' if o['side'] == 'BUY' else 'bid'}" if at_market else "your limit price"
        if service.fill(self.store, o, price, source, now):
            logger.info("Desk %s %s %d %s at %.2f", o["id"], o["side"], o["qty"], o["symbol"], price)
            self.store.notify(CHANNEL + "_done", o["id"])
        self._drop(o)

    def square_off(self, o: dict, qty: int, now: datetime) -> bool:
        """Close an intraday position at the live bid (service.housekeep calls this from 15:20)."""
        q = self.quote(int(o["token"]), now, rest=True)
        if q is None or not q.bid:
            return False
        day = now.date()
        orders = self.store.desk_orders(o["username"], o["epoch"])
        service._cancel_sells(self.store, orders, o, now, "The position was squared off at 15:20")
        done = self.store.desk_order_add(service.closing_order(o, service.square_off_id(o, day), qty, float(q.bid),
                                                               "squareoff", now, f"{q.source} bid"))
        if done:
            logger.info("Squared off %s %d at %.2f for %s", o["symbol"], qty, q.bid, o["username"])
        return done

    def _replace(self, o: dict) -> None:
        self._orders = [o if x["id"] == o["id"] else x for x in self._orders]

    def _drop(self, o: dict) -> None:
        self._orders = [x for x in self._orders if x["id"] != o["id"]]

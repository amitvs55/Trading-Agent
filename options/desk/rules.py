"""Order rules for the paper trading desk: what an order may be, and what it does on a live quote.

Buy-only: you buy options and sell what you hold; selling short isn't offered. Fills are what a real
order would get: a buy at the best ask, a sell at the best bid, never the last traded price. A limit
order that can trade at once fills at the better live price; one already resting fills at its own
limit when the market reaches it (the incoming order trades at the resting price). A stop (SL, SL-M)
triggers when the last traded price crosses its trigger; SL-M then trades at market, SL becomes a
limit order at its price. Orders fill in full at the top of the book.
"""

from dataclasses import dataclass
from datetime import date, datetime, time

from options.core.calendar import IST, MARKET_CLOSE, NseCalendar, at_ist
from options.engine.costs import order_charges

TICK = 0.05
MAX_LOTS = 20                    # per order: keeps every order well under NSE's freeze quantity
SQUARE_OFF = time(15, 20)        # intraday (MIS) positions are closed at market from here
MARKET_BUFFER = 0.02             # a market buy holds 2% over the price, for the move before it fills

SIDES = ("BUY", "SELL")
PRODUCTS = {"MIS": "Intraday", "NRML": "Carry"}
ORDER_TYPES = ("MARKET", "LIMIT", "SL", "SL-M")
WAITING = ("AMO", "PENDING")                     # not yet seen by the matcher
ACTIVE = (*WAITING, "OPEN", "TRIGGERED")         # can still fill
STATUS_LABELS = {"AMO": "After-market", "PENDING": "Placing", "OPEN": "Open", "TRIGGERED": "Triggered",
                 "FILLED": "Filled", "CANCELLED": "Cancelled", "REJECTED": "Rejected"}


@dataclass(frozen=True)
class Quote:
    bid: float | None
    ask: float | None
    ltp: float | None
    source: str = "live"


def on_grid(price: float) -> bool:
    return abs(price / TICK - round(price / TICK)) < 1e-6


def round_tick(price: float) -> float:
    return round(round(price / TICK) * TICK, 2)


def session_day(ts: datetime, calendar: NseCalendar) -> date:
    """The trading session an order placed at `ts` belongs to: the same day until the close, else the next."""
    ts = ts.astimezone(IST)
    d = ts.date()
    if calendar.is_trading_day(d) and ts.time() < MARKET_CLOSE:
        return d
    return calendar.next_trading_day(d)


def expired(expiry: date | None, now: datetime) -> bool:
    return expiry is not None and now >= at_ist(expiry, MARKET_CLOSE)


def validate(o: dict, *, held: int, selling: int, ltp: float | None, now: datetime, market_open: bool) -> str | None:
    """Why this order can't be placed, or None. `held` = units you own in this contract and product,
    `selling` = units already in working sell orders for it, `ltp` = the last traded price if known."""
    side, typ, product = o.get("side"), o.get("order_type"), o.get("product")
    if side not in SIDES:
        return "Choose Buy or Sell"
    if typ not in ORDER_TYPES:
        return "Choose Market, Limit, SL or SL-M"
    if product not in PRODUCTS:
        return "Choose Intraday (MIS) or Carry (NRML)"
    lot, qty = int(o["lot_size"]), int(o.get("qty") or 0)
    if qty <= 0 or qty % lot:
        return f"Quantity must be whole lots of {lot}"
    if qty // lot > MAX_LOTS:
        return f"At most {MAX_LOTS} lots in one order"
    if expired(o.get("expiry"), now):
        return "This contract has expired"
    price, trigger = o.get("price"), o.get("trigger_price")
    if typ in ("LIMIT", "SL") and not (price and price > 0):
        return "Enter a limit price"
    if typ in ("SL", "SL-M") and not (trigger and trigger > 0):
        return "Enter a trigger price"
    if any(p is not None and not on_grid(p) for p in (price if typ in ("LIMIT", "SL") else None,
                                                       trigger if typ in ("SL", "SL-M") else None)):
        return f"Prices go in steps of ₹{TICK:.2f}"
    if typ in ("SL", "SL-M"):
        if side == "BUY":
            if ltp and trigger <= ltp:
                return (f"A buy stop triggers when the price rises: set the trigger above the last price "
                        f"₹{ltp:,.2f}, or use a limit order")
            if typ == "SL" and price < trigger:
                return "For a buy stop the limit price must be at or above the trigger"
        else:
            if ltp and trigger >= ltp:
                return f"A stop-loss sell triggers when the price falls: set the trigger below the last price ₹{ltp:,.2f}"
            if typ == "SL" and price > trigger:
                return "For a stop-loss sell the limit price must be at or below the trigger"
    if side == "SELL":
        if held <= 0:
            return (f"You don't hold this contract as {PRODUCTS[product]}. This desk is buy-only: "
                    "you can sell what you've bought, not sell short")
        if qty > held - selling:
            free = max(held - selling, 0)
            return (f"You can sell at most {free} qty" + (f" ({selling} already in open sell orders)" if selling else ""))
    elif product == "MIS" and market_open and now.astimezone(IST).time() >= SQUARE_OFF:
        return "Intraday positions are closed at 15:20, so buy as Carry (NRML) now"
    return None


def market_price(side: str, q: Quote) -> float | None:
    px = q.ask if side == "BUY" else q.bid
    return float(px) if px and px > 0 else None


def step(o: dict, q: Quote, fresh: bool) -> tuple[str, float | None] | None:
    """What a working order does on this quote: ("fill", price), ("trigger", None) or nothing.
    `fresh`: the order is reaching the market now (just placed, an after-market order at the open, or
    a stop that just triggered), so a limit that crosses trades at the live price."""
    side, typ = o["side"], o["order_type"]
    if typ in ("SL", "SL-M") and o["status"] != "TRIGGERED":
        if not q.ltp:
            return None
        t = o["trigger_price"]
        if not (q.ltp >= t if side == "BUY" else q.ltp <= t):
            return None
        return ("trigger", None)
    if typ in ("MARKET", "SL-M"):                                     # SL-M here has triggered
        px = market_price(side, q)
        return ("fill", px) if px else None
    px, limit = market_price(side, q), float(o["price"])
    if px is None:
        return None
    if (side == "BUY" and px <= limit + 1e-9) or (side == "SELL" and px >= limit - 1e-9):
        return ("fill", px if fresh else limit)
    return None


def block_for(o: dict, q: Quote | None) -> float | None:
    """Funds a buy holds until it fills or ends: its price (or the market's plus a buffer) and charges.
    None for a market buy with no price to go on."""
    if o["side"] != "BUY":
        return 0.0
    typ = o["order_type"]
    if typ in ("LIMIT", "SL"):
        est = float(o["price"])
    elif typ == "SL-M":
        est = float(o["trigger_price"]) * (1 + MARKET_BUFFER)
    else:
        base = (q.ask or q.ltp) if q else None
        if not base:
            return None
        est = float(base) * (1 + MARKET_BUFFER)
    value = est * int(o["qty"])
    return round(value + order_charges("BUY", value).total, 2)


def charges_json(side: str, value: float, orders: int = 1) -> dict:
    c = order_charges(side, value, orders)
    parts = {"brokerage": c.brokerage, "stt": c.stt, "exchange": c.exchange, "sebi": c.sebi,
             "stamp": c.stamp, "gst": c.gst}
    return {**{k: round(v, 4) for k, v in parts.items()}, "total": round(c.total, 2)}

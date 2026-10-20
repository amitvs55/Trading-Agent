"""Desk operations shared by the API and the recorder: accounts, fills, and the end-of-session rules.

The API places, modifies and cancels orders; the recorder (options/desk/worker.py), which holds the
live market feed, fills them. Every change of an order's status is conditional on the status it was
read in, so the two can never both act on one order (a cancel and a fill racing: one of them wins).

End-of-session rules run in the recorder and again on every read of the desk, so they also happen
when the recorder isn't running: a day order that didn't fill is cancelled at the close, an intraday
position is squared off at 15:20 (at the last recorded price before then, if the recorder missed
it), and a position held to expiry is settled at its intrinsic value from the index's close.
"""

from datetime import datetime, timedelta

from options.check.outcomes import settlement
from options.core.calendar import IST, MARKET_CLOSE, MARKET_OPEN, NseCalendar, at_ist
from options.desk.ledger import holdings
from options.desk.rules import ACTIVE, SQUARE_OFF, WAITING, Quote, charges_json, expired, session_day

DEFAULT_FUNDS = 100_000.0
MIN_FUNDS, MAX_FUNDS = 10_000.0, 10_000_000.0
SQUARE_OFF_GRACE = timedelta(minutes=3)      # the recorder squares off live; a read only after this
SETTLE_GRACE = timedelta(minutes=2)


def ensure_account(store, username: str, now: datetime, funds: float = DEFAULT_FUNDS) -> dict:
    acct = store.desk_account(username)
    if acct is None:
        acct = {"username": username, "funds": funds, "added": 0.0, "epoch": 1, "started_at": now}
        store.desk_account_save(acct)
    return acct


def quote_from(snapshot: dict | None, bar: dict | None, symbol: str) -> Quote | None:
    """A contract's latest price as the API sees it: the live feed's copy, else the last recorded minute."""
    for item in (snapshot or {}).get("items", []):
        if item.get("symbol") == symbol and (item.get("ltp") or item.get("bid") or item.get("ask")):
            return Quote(item.get("bid"), item.get("ask"), item.get("ltp"), "live")
    if bar:
        return Quote(bar.get("bid"), bar.get("ask"), bar.get("close"), "last recorded minute")
    return None


def fill(store, o: dict, price: float, source: str, now: datetime) -> bool:
    """Fill an order in full at `price`, with its charges; False if its status changed meanwhile."""
    value = price * int(o["qty"])
    return store.desk_order_update(o["id"], from_status=(o["status"],), status="FILLED", fill_price=round(price, 2),
                                   filled_at=now, fill_source=source, charges=charges_json(o["side"], value),
                                   block=0.0, updated_at=now)


def end(store, o: dict, status: str, reason: str, now: datetime) -> bool:
    return store.desk_order_update(o["id"], from_status=(o["status"],), status=status, reason=reason, block=0.0,
                                   updated_at=now)


def closing_order(o: dict, oid: str, qty: int, price: float, source: str, at: datetime, fill_source: str,
                  orders_charged: int = 1) -> dict:
    """A sell that closes a position by rule (square-off, settlement), already filled."""
    value = price * qty
    return {"id": oid, "username": o["username"], "epoch": o["epoch"], "created_at": at, "updated_at": at,
            "index_name": o.get("index_name"), "symbol": o["symbol"], "token": o["token"],
            "spot_token": o.get("spot_token"), "expiry": o.get("expiry"), "strike": o.get("strike"),
            "option_right": o.get("option_right"), "lot_size": o["lot_size"], "side": "SELL",
            "product": o["product"], "order_type": "MARKET", "qty": qty, "status": "FILLED", "block": 0.0,
            "fill_price": round(price, 2), "filled_at": at, "fill_source": fill_source,
            "charges": charges_json("SELL", value, orders_charged), "source": source}


def square_off_id(o: dict, day) -> str:
    return f"SQ-{o['username']}-{o['epoch']}-{o['token']}-{day:%y%m%d}"


def settle_id(o: dict) -> str:
    return f"EX-{o['username']}-{o['epoch']}-{o['token']}-{o['product']}"


def open_positions(orders: list[dict]) -> list[tuple[dict, int]]:
    """(the latest buy of the position, units held) for every open position in these orders."""
    held = holdings(orders)
    last: dict[tuple[int, str], dict] = {}
    for o in orders:
        if o["status"] == "FILLED" and o["side"] == "BUY":
            last[(int(o["token"]), o["product"])] = o
    return [(last[k], n) for k, n in held.items() if n > 0 and k in last]


def _recorded_price(store, token: int, day, until) -> float | None:
    rows = store.bars_between(at_ist(day, MARKET_OPEN), until + timedelta(minutes=1), {token})
    rows = [r for r in rows if r["ts"].astimezone(IST) <= until]
    if not rows:
        return None
    last = rows[-1]
    return float(last.get("bid") or last["close"])


def housekeep(store, now: datetime, calendar: NseCalendar, live_squareoff=None) -> int:
    """Apply the end-of-session rules to every account; returns how many orders changed.
    `live_squareoff(order, qty, now)`: the recorder's way to square off at the live bid."""
    changed = 0
    orders = store.desk_orders_current()
    for o in orders:
        if o["status"] not in ACTIVE:
            continue
        day = session_day(o["created_at"], calendar)
        if expired(o.get("expiry"), now):
            changed += end(store, o, "CANCELLED", "The contract expired", now)
        elif now >= at_ist(day, MARKET_CLOSE):
            why = ("Not filled: there were no live prices that session" if o["status"] in WAITING
                   else "Expired at the close (day order)")
            changed += end(store, o, "CANCELLED", why, now)
        elif o["product"] == "MIS" and o["side"] == "BUY" and now >= at_ist(day, SQUARE_OFF):
            changed += end(store, o, "CANCELLED", "Intraday buys end at 15:20", now)
    if changed:
        orders = store.desk_orders_current()

    by_user: dict[tuple[str, int], list[dict]] = {}
    for o in orders:
        by_user.setdefault((o["username"], o["epoch"]), []).append(o)
    for user_orders in by_user.values():
        for last_buy, qty in open_positions(user_orders):
            changed += _close_by_rule(store, user_orders, last_buy, qty, now, calendar, live_squareoff)
    return changed


def _close_by_rule(store, orders, o: dict, qty: int, now: datetime, calendar: NseCalendar, live_squareoff) -> int:
    if o.get("expiry") and now >= at_ist(o["expiry"], MARKET_CLOSE) + SETTLE_GRACE:
        value = settlement(store, o.get("spot_token"), o["expiry"], o["strike"], o["option_right"]) \
            if o.get("spot_token") else None
        if value is None:
            return 0                                     # no close recorded yet: try again on the next read
        at = at_ist(o["expiry"], MARKET_CLOSE)
        _cancel_sells(store, orders, o, now, "The position was settled at expiry")
        return int(store.desk_order_add(closing_order(o, settle_id(o), qty, value, "expiry", at,
                                                      "settlement (intrinsic value)", 1 if value > 0 else 0)))
    if o["product"] != "MIS":
        return 0
    day = session_day(o["filled_at"], calendar)
    cutoff = at_ist(day, SQUARE_OFF)
    if now < cutoff:
        return 0
    if live_squareoff is not None and now < cutoff + SQUARE_OFF_GRACE * 5:
        return int(bool(live_squareoff(o, qty, now)))
    if now < cutoff + SQUARE_OFF_GRACE:
        return 0
    price = _recorded_price(store, int(o["token"]), day, cutoff)
    if price is None:
        return 0
    _cancel_sells(store, orders, o, now, "The position was squared off at 15:20")
    return int(store.desk_order_add(closing_order(o, square_off_id(o, day), qty, price, "squareoff", cutoff,
                                                  "last recorded price before 15:20")))


def _cancel_sells(store, orders: list[dict], o: dict, now: datetime, reason: str) -> None:
    for s in orders:
        if s["status"] in ACTIVE and s["side"] == "SELL" and int(s["token"]) == int(o["token"]) \
                and s["product"] == o["product"]:
            end(store, s, "CANCELLED", reason, now)

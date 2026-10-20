"""The paper trading desk: your own orders on live prices, with real charges (options/desk).

Every signed-in user has their own virtual account. During market hours an order is handed to the
recorder, which fills it from the live feed (a market order within about a second; this call waits
for it). Outside market hours it is an after-market order (AMO) that goes in at the next open. With
the market open but no live feed, orders are refused rather than filled at a made-up price.
"""

import asyncio
import time as _clock
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from api.deps import current_user, get_calendar, get_cfg, get_store
from api.routes.check import _recorder_live, _refs
from options.config import OptionsSettings
from options.core.calendar import MARKET_OPEN, NseCalendar, at_ist, now_ist
from options.desk import service
from options.desk.ledger import book, holdings, selling
from options.desk.rules import (ACTIVE, MAX_LOTS, PRODUCTS, SQUARE_OFF, STATUS_LABELS, TICK, WAITING, Quote,
                                block_for, charges_json, session_day, validate)
from options.desk.worker import CHANNEL
from options.engine.costs import (BROKERAGE_PER_ORDER, EXCHANGE_TXN_PCT, GST_PCT, SEBI_FEE_PCT, STAMP_BUY_PCT,
                                  STT_SELL_PCT)
from options.storage import Store

router = APIRouter(tags=["desk"], dependencies=[Depends(current_user)])
WAIT_FILL_S = 4.0

RATES = {"brokerage_per_order": BROKERAGE_PER_ORDER, "stt_sell_pct": STT_SELL_PCT, "exchange_pct": EXCHANGE_TXN_PCT,
         "sebi_pct": SEBI_FEE_PCT, "stamp_buy_pct": STAMP_BUY_PCT, "gst_pct": GST_PCT}


class OrderIn(BaseModel):
    token: int = Field(gt=0)
    side: Literal["BUY", "SELL"]
    lots: int = Field(ge=1, le=MAX_LOTS)
    order_type: Literal["MARKET", "LIMIT", "SL", "SL-M"] = "MARKET"
    product: Literal["MIS", "NRML"] = "MIS"
    price: float | None = Field(None, gt=0, le=1_000_000)
    trigger_price: float | None = Field(None, gt=0, le=1_000_000)
    source: str | None = Field(None, max_length=40)


class ModifyIn(BaseModel):
    lots: int | None = Field(None, ge=1, le=MAX_LOTS)
    price: float | None = Field(None, gt=0, le=1_000_000)
    trigger_price: float | None = Field(None, gt=0, le=1_000_000)


class ExitIn(BaseModel):
    token: int
    product: Literal["MIS", "NRML"]


class AccountIn(BaseModel):
    action: Literal["reset", "add"]
    amount: float = Field(gt=0, le=service.MAX_FUNDS)


def _who(user: dict) -> str:
    return user.get("username") or f"user-{user.get('id')}"


def _contract(store: Store, cfg: OptionsSettings, token: int, now: datetime):
    refs, _, _ = _refs(store, cfg, now)
    for ref in refs.values():
        for opt in ref.options.values():
            if opt.token == token:
                return ref, opt
    raise HTTPException(404, {"code": "contract", "message": "That contract isn't in today's contract list"})


def _quote(store: Store, token: int, symbol: str, snapshot: dict | None = None) -> Quote | None:
    return service.quote_from(snapshot if snapshot is not None else store.live_snapshot(), store.latest_bar(token),
                              symbol)


def _quote_json(q: Quote | None) -> dict | None:
    return None if q is None else {"bid": q.bid, "ask": q.ask, "ltp": q.ltp, "source": q.source}


def _order_json(o: dict) -> dict:
    lot = int(o["lot_size"])
    return {"id": o["id"], "created_at": o["created_at"].isoformat(), "updated_at": o["updated_at"].isoformat(),
            "symbol": o["symbol"], "token": int(o["token"]), "index_name": o.get("index_name"),
            "expiry": o["expiry"].isoformat() if o.get("expiry") else None, "strike": o.get("strike"),
            "right": o.get("option_right"), "lot_size": lot, "side": o["side"], "product": o["product"],
            "product_label": PRODUCTS.get(o["product"], o["product"]), "order_type": o["order_type"],
            "qty": int(o["qty"]), "lots": int(o["qty"]) // lot, "price": o.get("price"),
            "trigger_price": o.get("trigger_price"), "status": o["status"],
            "status_label": STATUS_LABELS.get(o["status"], o["status"]), "reason": o.get("reason"),
            "block": o.get("block"), "fill_price": o.get("fill_price"),
            "filled_at": o["filled_at"].isoformat() if o.get("filled_at") else None,
            "fill_source": o.get("fill_source"), "charges": o.get("charges"), "source": o.get("source"),
            "active": o["status"] in ACTIVE}


def _market(store: Store, cal: NseCalendar, now: datetime) -> dict:
    open_ = cal.is_market_open(now)
    nxt = session_day(now, cal)
    return {"open": open_, "live": _recorder_live(store, now, cal) if open_ else False,
            "next_open": at_ist(nxt, MARKET_OPEN).isoformat(), "square_off": SQUARE_OFF.strftime("%H:%M")}


def _account(store: Store, user: dict, now: datetime) -> tuple[dict, list[dict]]:
    acct = service.ensure_account(store, _who(user), now)
    return acct, store.desk_orders(acct["username"], acct["epoch"])


def _state(store: Store, cal: NseCalendar, user: dict) -> dict:
    now = now_ist()
    try:
        service.housekeep(store, now, cal)
    except Exception:
        pass                                    # the account still reads; the rules run again next time
    acct, orders = _account(store, user, now)
    snap = store.live_snapshot()
    marks = {}
    for last_buy, _ in service.open_positions(orders):
        q = _quote(store, int(last_buy["token"]), last_buy["symbol"], snap)
        if q is not None:
            marks[int(last_buy["token"])] = q
    out = book(acct, orders, marks, now)
    out["orders"] = [_order_json(o) for o in sorted(orders, key=lambda o: (o["created_at"], o["id"]), reverse=True)]
    out["market"] = _market(store, cal, now)
    out["rates"] = RATES
    out["tick"] = TICK
    return out


@router.get("/api/desk")
def desk(user: dict = Depends(current_user), store: Store = Depends(get_store),
         cal: NseCalendar = Depends(get_calendar)) -> dict:
    return _state(store, cal, user)


@router.get("/api/desk/ticket")
def ticket(token: int = Query(..., gt=0), side: Literal["BUY", "SELL"] = "BUY",
           lots: int = Query(1, ge=1, le=MAX_LOTS), order_type: Literal["MARKET", "LIMIT", "SL", "SL-M"] = "MARKET",
           product: Literal["MIS", "NRML"] = "MIS", price: float | None = Query(None, gt=0),
           trigger_price: float | None = Query(None, gt=0), user: dict = Depends(current_user),
           store: Store = Depends(get_store), cfg: OptionsSettings = Depends(get_cfg),
           cal: NseCalendar = Depends(get_calendar)) -> dict:
    """Everything the order ticket shows: the contract, its live price, what you hold, and what this
    order would cost (charges itemised), with the reason it can't be placed if it can't."""
    now = now_ist()
    ref, opt = _contract(store, cfg, token, now)
    q = _quote(store, opt.token, opt.tradingsymbol)
    acct, orders = _account(store, user, now)
    held, working = holdings(orders), selling(orders)
    market = _market(store, cal, now)
    o = _draft(opt, side, lots, order_type, product, price, trigger_price)
    problem = validate(o, held=held.get((opt.token, product), 0), selling=working.get((opt.token, product), 0),
                       ltp=q.ltp if q else None, now=now, market_open=market["open"])
    funds = book(acct, orders, {}, now)["funds"]
    est = _estimate(o, q)
    if problem is None and side == "BUY":
        if est["block"] is None:
            problem = "No price for this contract yet: use a limit order"
        elif est["block"] > funds["available"] + 0.005:
            problem = f"Not enough funds: this needs ₹{est['block']:,.0f}, you have ₹{funds['available']:,.0f} free"
    if market["open"] and market["live"] and (q is None or q.source != "live"):
        store.notify(CHANNEL, f"watch:{opt.token}:{opt.tradingsymbol}")      # stream it for the ticket
    return {"contract": {"symbol": opt.tradingsymbol, "token": opt.token, "index": ref.index,
                         "expiry": opt.expiry.isoformat(), "strike": opt.strike, "right": opt.right,
                         "lot_size": opt.lot_size},
            "quote": _quote_json(q), "held": {p: held.get((opt.token, p), 0) for p in PRODUCTS},
            "selling": {p: working.get((opt.token, p), 0) for p in PRODUCTS},
            "estimate": est, "available": funds["available"], "problem": problem, "market": market}


def _draft(opt, side, lots, order_type, product, price, trigger_price) -> dict:
    return {"side": side, "order_type": order_type, "product": product, "qty": lots * opt.lot_size,
            "lot_size": opt.lot_size, "expiry": opt.expiry,
            "price": round(price, 2) if price and order_type in ("LIMIT", "SL") else None,
            "trigger_price": round(trigger_price, 2) if trigger_price and order_type in ("SL", "SL-M") else None}


def _estimate(o: dict, q: Quote | None) -> dict:
    """The expected fill price and value, this order's charges, the funds a buy holds, and the
    breakeven (the sell price that covers both sides' charges)."""
    typ, side, qty = o["order_type"], o["side"], int(o["qty"])
    if typ in ("LIMIT", "SL"):
        px = o["price"]
    elif typ == "SL-M":
        px = o["trigger_price"]
    else:
        px = ((q.ask if side == "BUY" else q.bid) or q.ltp) if q else None
    if not px:
        return {"price": None, "value": None, "charges": None, "block": None, "breakeven": None}
    value = px * qty
    ch = charges_json(side, value)
    out = {"price": round(px, 2), "value": round(value, 2), "charges": ch,
           "block": block_for(o, q) if side == "BUY" else 0.0, "breakeven": None}
    if side == "BUY":
        # Sell price where (sell − buy) × qty equals both orders' charges (solved once; the sell's charges
        # barely move with the price, so one refinement is exact to the paisa)
        be = px + ch["total"] / qty
        for _ in range(2):
            be = px + (ch["total"] + charges_json("SELL", be * qty)["total"]) / qty
        out["breakeven"] = round(be, 2)
    return out


async def _wait(store: Store, order_id: str, seconds: float) -> dict | None:
    deadline = _clock.monotonic() + seconds
    while _clock.monotonic() < deadline:
        row = await run_in_threadpool(store.desk_order, order_id)
        if row and row["status"] not in WAITING:
            return row
        await asyncio.sleep(0.1)
    return await run_in_threadpool(store.desk_order, order_id)


async def _place(store: Store, cfg: OptionsSettings, cal: NseCalendar, user: dict, body: OrderIn) -> dict:
    now = now_ist()
    ref, opt = await run_in_threadpool(_contract, store, cfg, body.token, now)
    q = await run_in_threadpool(_quote, store, opt.token, opt.tradingsymbol)
    acct, orders = await run_in_threadpool(_account, store, user, now)
    market = await run_in_threadpool(_market, store, cal, now)
    if market["open"] and not market["live"]:
        raise HTTPException(503, {"code": "no_feed", "message": "Live prices aren't streaming right now, so the order "
                                  "can't fill at a real price. Try again once the feed is back."})
    o = _draft(opt, body.side, body.lots, body.order_type, body.product, body.price, body.trigger_price)
    held, working = holdings(orders), selling(orders)
    problem = validate(o, held=held.get((opt.token, body.product), 0),
                       selling=working.get((opt.token, body.product), 0), ltp=q.ltp if q else None, now=now,
                       market_open=market["open"])
    if problem:
        raise HTTPException(422, {"code": "invalid", "message": problem})
    block = block_for(o, q)
    if block is None:
        raise HTTPException(422, {"code": "no_price", "message": "No price for this contract yet: use a limit order"})
    if body.side == "BUY":
        free = book(acct, orders, {}, now)["funds"]["available"]
        if block > free + 0.005:
            raise HTTPException(422, {"code": "funds", "message": f"Not enough funds: this needs ₹{block:,.0f}, "
                                      f"you have ₹{free:,.0f} free"})
    order_id = f"{now:%y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    row = {"id": order_id, "username": acct["username"], "epoch": acct["epoch"], "created_at": now, "updated_at": now,
           "index_name": ref.index, "symbol": opt.tradingsymbol, "token": opt.token, "spot_token": ref.spot_token,
           "expiry": opt.expiry, "strike": opt.strike, "option_right": opt.right, "lot_size": opt.lot_size,
           **{k: o[k] for k in ("side", "product", "order_type", "qty", "price", "trigger_price")},
           "status": "PENDING" if market["open"] else "AMO", "block": block, "source": body.source or "ticket"}
    await run_in_threadpool(store.desk_order_add, row)
    if market["open"]:
        await run_in_threadpool(store.notify, CHANNEL, order_id)
        if body.order_type == "MARKET":
            row = await _wait(store, order_id, WAIT_FILL_S) or row
        else:
            row = await _wait(store, order_id, 1.5) or row
    else:
        row = await run_in_threadpool(store.desk_order, order_id)
    return _order_json(row)


@router.post("/api/desk/orders")
async def place(body: OrderIn, user: dict = Depends(current_user), store: Store = Depends(get_store),
                cfg: OptionsSettings = Depends(get_cfg), cal: NseCalendar = Depends(get_calendar)) -> dict:
    return {"order": await _place(store, cfg, cal, user, body)}


def _mine(store: Store, user: dict, order_id: str) -> dict:
    o = store.desk_order(order_id)
    acct = store.desk_account(_who(user))
    if o is None or acct is None or o["username"] != acct["username"] or o["epoch"] != acct["epoch"]:
        raise HTTPException(404, {"code": "not_found", "message": "No such order."})
    return o


@router.post("/api/desk/orders/{order_id}/cancel")
def cancel(order_id: str, user: dict = Depends(current_user), store: Store = Depends(get_store)) -> dict:
    o = _mine(store, user, order_id)
    if o["status"] not in ACTIVE or not service.end(store, o, "CANCELLED", "You cancelled it", now_ist()):
        raise HTTPException(409, {"code": "not_active", "message": f"This order is already {o['status'].lower()}."})
    store.notify(CHANNEL, order_id)
    return {"order": _order_json(store.desk_order(order_id))}


@router.patch("/api/desk/orders/{order_id}")
def modify(order_id: str, body: ModifyIn, user: dict = Depends(current_user), store: Store = Depends(get_store),
           cal: NseCalendar = Depends(get_calendar)) -> dict:
    """Change a working order's lots, limit or trigger (not its side, type or product)."""
    now = now_ist()
    o = _mine(store, user, order_id)
    if o["status"] not in ("AMO", "OPEN", "TRIGGERED"):
        raise HTTPException(409, {"code": "not_active", "message": "Only an open order can be modified."})
    new = {**o}
    if body.lots is not None:
        new["qty"] = body.lots * int(o["lot_size"])
    if body.price is not None and o["order_type"] in ("LIMIT", "SL"):
        new["price"] = round(body.price, 2)
    if body.trigger_price is not None and o["order_type"] in ("SL", "SL-M"):
        if o["status"] == "TRIGGERED":
            raise HTTPException(409, {"code": "triggered", "message": "This stop has triggered: only its limit can change."})
        new["trigger_price"] = round(body.trigger_price, 2)
    acct, orders = _account(store, user, now)
    others = [x for x in orders if x["id"] != order_id]
    q = _quote(store, int(o["token"]), o["symbol"])
    market_open = cal.is_market_open(now)
    problem = validate(new, held=holdings(others).get((int(o["token"]), o["product"]), 0),
                       selling=selling(others).get((int(o["token"]), o["product"]), 0),
                       ltp=q.ltp if q and o["status"] != "TRIGGERED" else None, now=now, market_open=market_open)
    block = block_for(new, q) if o["side"] == "BUY" else 0.0
    if problem is None and o["side"] == "BUY":
        free = book(acct, others, {}, now)["funds"]["available"]
        if block is None or block > free + 0.005:
            problem = f"Not enough funds: this needs ₹{(block or 0):,.0f}, you have ₹{free:,.0f} free"
    if problem:
        raise HTTPException(422, {"code": "invalid", "message": problem})
    if not store.desk_order_update(order_id, from_status=(o["status"],), qty=new["qty"], price=new.get("price"),
                                   trigger_price=new.get("trigger_price"), block=block, updated_at=now):
        raise HTTPException(409, {"code": "changed", "message": "The order changed meanwhile (it may have filled)."})
    store.notify(CHANNEL, order_id)
    return {"order": _order_json(store.desk_order(order_id))}


@router.post("/api/desk/positions/exit")
async def exit_position(body: ExitIn, user: dict = Depends(current_user), store: Store = Depends(get_store),
                        cfg: OptionsSettings = Depends(get_cfg), cal: NseCalendar = Depends(get_calendar)) -> dict:
    """Sell the whole position at market; its working sell orders are cancelled first."""
    now = now_ist()
    acct, orders = await run_in_threadpool(_account, store, user, now)
    key = (body.token, body.product)
    qty = holdings(orders).get(key, 0)
    if qty <= 0:
        raise HTTPException(409, {"code": "no_position", "message": "You don't hold this position any more."})
    last = next(o for o in reversed(orders) if o["status"] == "FILLED" and (int(o["token"]), o["product"]) == key)
    for o in orders:
        if o["status"] in ACTIVE and o["side"] == "SELL" and (int(o["token"]), o["product"]) == key:
            await run_in_threadpool(service.end, store, o, "CANCELLED", "Replaced by your exit", now)
    body_ = OrderIn(token=body.token, side="SELL", lots=qty // int(last["lot_size"]), order_type="MARKET",
                    product=body.product, source="exit")
    return {"order": await _place(store, cfg, cal, user, body_)}


@router.post("/api/desk/account")
def account(body: AccountIn, user: dict = Depends(current_user), store: Store = Depends(get_store)) -> dict:
    """Add funds, or start a fresh account (working orders are cancelled; old orders stop counting)."""
    now = now_ist()
    acct, orders = _account(store, user, now)
    if body.action == "add":
        if acct["funds"] + acct["added"] + body.amount > service.MAX_FUNDS:
            raise HTTPException(422, {"code": "invalid", "message": f"At most ₹{service.MAX_FUNDS:,.0f} in one account"})
        acct = {**acct, "added": acct["added"] + body.amount}
    else:
        if body.amount < service.MIN_FUNDS:
            raise HTTPException(422, {"code": "invalid", "message": f"Start with at least ₹{service.MIN_FUNDS:,.0f}"})
        for o in orders:
            if o["status"] in ACTIVE:
                service.end(store, o, "CANCELLED", "The account was reset", now)
        acct = {**acct, "funds": body.amount, "added": 0.0, "epoch": acct["epoch"] + 1, "started_at": now}
    store.desk_account_save(acct)
    return {"ok": True}

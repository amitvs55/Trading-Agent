"""The paper trading desk: charges per order, order rules, the account, end-of-session rules, the
recorder's matcher and the API."""

from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import check as check_routes, desk as desk_routes
from options.backtest.synthetic import CAL, build_market, save_market
from options.config import OptionsSettings
from options.desk import service
from options.desk.ledger import book
from options.desk.rules import Quote, block_for, charges_json, step, validate
from options.desk.worker import DeskWorker
from options.engine.costs import charges, order_charges
from options.storage import Store, make_engine
from tests.options.fixtures import ist

DAY = date(2026, 10, 16)                 # Friday, a trading day in the synthetic calendar
EXPIRY = date(2026, 10, 27)
OPT = {"index_name": "NIFTY", "symbol": "NIFTY26OCT25000CE", "token": 101, "spot_token": 256265, "expiry": EXPIRY,
       "strike": 25000.0, "option_right": "CE", "lot_size": 65}


def t(hh, mm, ss=0, day=DAY):
    return ist(day.year, day.month, day.day, hh, mm, ss)


def order(oid, side="BUY", qty=65, order_type="MARKET", product="MIS", status="FILLED", fill=None, at=None,
          price=None, trigger=None, user="amit", epoch=1, block=None, source="ticket", **kw):
    at = at or t(10, 0)
    row = {**OPT, "id": oid, "username": user, "epoch": epoch, "created_at": at, "updated_at": at, "side": side,
           "product": product, "order_type": order_type, "qty": qty, "price": price, "trigger_price": trigger,
           "status": status, "block": block, "source": source, **kw}
    if status == "FILLED":
        row.update(fill_price=fill, filled_at=at, fill_source="live ask", charges=charges_json(side, fill * qty))
    return row


@pytest.fixture
def store(tmp_path):
    s = Store(make_engine(f"sqlite:///{tmp_path}/d.db"))
    service.ensure_account(s, "amit", t(9, 0))
    return s


# ── Charges ──────────────────────────────────────────────────────────────────

def test_one_round_trip_costs_20_rupees_an_order_plus_taxes_and_gst():
    buy, sell = charges_json("BUY", 143 * 65), charges_json("SELL", 239 * 65)
    assert buy["brokerage"] == sell["brokerage"] == 20.0
    assert buy["stt"] == 0 and sell["stamp"] == 0                            # STT on the sell, stamp on the buy
    assert buy["gst"] == pytest.approx((20 + buy["exchange"] + buy["sebi"]) * 0.18, abs=1e-4)
    assert buy["total"] + sell["total"] == pytest.approx(81.07, abs=0.01)
    whole = charges(143 * 65, 239 * 65, 2).total
    assert order_charges("BUY", 143 * 65).total + order_charges("SELL", 239 * 65).total == pytest.approx(whole)


# ── Order rules ──────────────────────────────────────────────────────────────

def _draft(**kw):
    return {"side": "BUY", "order_type": "MARKET", "product": "MIS", "qty": 65, "lot_size": 65, "expiry": EXPIRY,
            "price": None, "trigger_price": None, **kw}


@pytest.mark.parametrize("kw,held,ltp,now,problem", [
    ({"qty": 100}, 0, 140, t(10, 0), "whole lots of 65"),
    ({"qty": 65 * 21}, 0, 140, t(10, 0), "At most 20 lots"),
    ({"order_type": "LIMIT"}, 0, 140, t(10, 0), "Enter a limit price"),
    ({"order_type": "LIMIT", "price": 140.03}, 0, 140, t(10, 0), "steps of ₹0.05"),
    ({"order_type": "SL", "price": 150, "trigger_price": 138}, 0, 140, t(10, 0), "set the trigger above the last price"),
    ({"order_type": "SL", "price": 144, "trigger_price": 145}, 0, 140, t(10, 0), "at or above the trigger"),
    ({"side": "SELL"}, 0, 140, t(10, 0), "buy-only"),
    ({"side": "SELL", "qty": 130}, 65, 140, t(10, 0), "at most 65 qty"),
    ({"side": "SELL", "order_type": "SL-M", "trigger_price": 145}, 65, 140, t(10, 0), "below the last price"),
    ({}, 0, 140, t(15, 21), "Carry (NRML)"),
    ({"expiry": DAY}, 0, 140, t(15, 31), "expired"),
])
def test_orders_that_a_broker_would_refuse_are_refused_with_the_reason(kw, held, ltp, now, problem):
    found = validate(_draft(**kw), held=held, selling=0, ltp=ltp, now=now, market_open=now.hour < 16)
    assert found and problem in found


def test_valid_orders_pass():
    assert validate(_draft(), held=0, selling=0, ltp=140, now=t(10, 0), market_open=True) is None
    assert validate(_draft(product="NRML"), held=0, selling=0, ltp=140, now=t(15, 25), market_open=True) is None
    assert validate(_draft(side="SELL", order_type="SL", price=119.5, trigger_price=120), held=65, selling=0,
                    ltp=140, now=t(10, 0), market_open=True) is None
    assert validate(_draft(), held=0, selling=0, ltp=140, now=t(18, 0), market_open=False) is None   # MIS for tomorrow


def test_fills_are_at_the_ask_or_bid_and_limits_at_their_price_once_resting():
    q = Quote(bid=139.5, ask=140.5, ltp=140.0)
    assert step({"side": "BUY", "order_type": "MARKET", "status": "PENDING"}, q, True) == ("fill", 140.5)
    assert step({"side": "SELL", "order_type": "MARKET", "status": "PENDING"}, q, True) == ("fill", 139.5)
    lim = {"side": "BUY", "order_type": "LIMIT", "status": "PENDING", "price": 142.0}
    assert step(lim, q, True) == ("fill", 140.5)                             # crosses now: the better live price
    rest = {**lim, "status": "OPEN", "price": 141.0}
    assert step(rest, Quote(140, 142, 141), False) is None
    assert step(rest, Quote(139, 140.0, 139.5), False) == ("fill", 141.0)     # resting: trades at its limit
    assert step({"side": "BUY", "order_type": "MARKET", "status": "PENDING"}, Quote(None, None, 140), True) is None


def test_stops_trigger_on_the_last_price_then_trade():
    buy_stop = {"side": "BUY", "order_type": "SL", "status": "OPEN", "trigger_price": 150.0, "price": 152.0}
    assert step(buy_stop, Quote(148, 149, 149), False) is None
    assert step(buy_stop, Quote(150, 151, 150.5), False) == ("trigger", None)
    assert step({**buy_stop, "status": "TRIGGERED"}, Quote(150, 151, 150.5), True) == ("fill", 151)
    assert step({**buy_stop, "status": "TRIGGERED"}, Quote(153, 154, 153.5), True) is None   # ran past the limit
    stop_loss = {"side": "SELL", "order_type": "SL-M", "status": "OPEN", "trigger_price": 120.0}
    assert step(stop_loss, Quote(121, 122, 121.5), False) is None
    assert step(stop_loss, Quote(119, 120, 119.5), False) == ("trigger", None)
    assert step({**stop_loss, "status": "TRIGGERED"}, Quote(119, 120, 119.5), True) == ("fill", 119)


def test_a_buy_holds_its_price_and_charges_and_a_market_buy_a_buffer():
    lim = {"side": "BUY", "order_type": "LIMIT", "qty": 65, "price": 140.0}
    assert block_for(lim, None) == pytest.approx(140 * 65 + order_charges("BUY", 140 * 65).total, abs=0.01)
    mkt = {"side": "BUY", "order_type": "MARKET", "qty": 65}
    assert block_for(mkt, Quote(139, 140, 139.5)) > 140 * 65 * 1.019
    assert block_for(mkt, None) is None and block_for({"side": "SELL"}, None) == 0


# ── The account ──────────────────────────────────────────────────────────────

def test_average_price_accounting_with_charges_split_between_the_sells():
    acct = {"funds": 100_000, "added": 0, "epoch": 1, "started_at": t(9, 0)}
    orders = [order("b1", qty=130, fill=100.0, at=t(9, 30)),
              order("s1", side="SELL", qty=65, fill=120.0, at=t(10, 0)),
              order("b2", qty=65, fill=106.0, at=t(10, 30))]
    a = book(acct, orders, {101: Quote(109, 110, 110.0)}, t(11, 0))
    [trade] = a["trades"]
    b1 = charges_json("BUY", 100 * 130)["total"]
    assert trade["entry"] == 100.0 and trade["gross"] == 65 * 20
    assert trade["charges"] == pytest.approx(charges_json("SELL", 120 * 65)["total"] + b1 / 2, abs=0.01)
    [pos] = a["positions"]
    assert pos["qty"] == 130 and pos["avg"] == pytest.approx(103.0)            # 65 left at 100 + 65 at 106
    assert pos["pnl"] == pytest.approx((110 - 103) * 130)
    paid = sum(o["charges"]["total"] for o in orders)
    assert a["funds"]["cash"] == pytest.approx(100_000 - 13_000 + 7_800 - 6_890 - paid, abs=0.01)
    assert a["funds"]["equity"] == pytest.approx(a["funds"]["cash"] + 110 * 130, abs=0.01)
    assert a["stats"]["charges_paid"] == pytest.approx(paid, abs=0.01)
    assert a["today"]["pnl"] == pytest.approx(trade["net"] + pos["pnl"], abs=0.01)


def test_a_closed_position_stays_on_todays_positions_and_working_buys_hold_funds():
    acct = {"funds": 100_000, "added": 5_000, "epoch": 1, "started_at": t(9, 0)}
    orders = [order("b1", fill=100.0, at=t(9, 30)), order("s1", side="SELL", fill=90.0, at=t(10, 0)),
              order("w1", status="OPEN", order_type="LIMIT", price=95.0, block=6_200.0)]
    a = book(acct, orders, {}, t(11, 0))
    assert a["positions"][0]["qty"] == 0 and a["positions"][0]["realised_today"] < -650
    assert a["funds"]["blocked"] == 6_200 and a["funds"]["available"] == pytest.approx(a["funds"]["cash"] - 6_200)
    assert a["funds"]["start"] == 105_000 and a["stats"]["wins"] == 0 and len(a["curve"]) == 2
    tomorrow = book(acct, orders, {}, t(11, 0, day=date(2026, 10, 19)))
    assert tomorrow["positions"] == [] and tomorrow["today"]["realised"] == 0


# ── End-of-session rules ─────────────────────────────────────────────────────

def _bar(token, ts, close, bid=None):
    return {"instrument_token": token, "ts": ts, "open": close, "high": close, "low": close, "close": close,
            "volume_day": None, "oi": None, "bid": bid, "ask": None, "bid_qty": None, "ask_qty": None, "ticks": 1}


def test_day_orders_end_at_the_close_and_an_unfilled_amo_after_its_session(store):
    store.desk_order_add(order("lim", status="OPEN", order_type="LIMIT", price=90.0, block=6000))
    store.desk_order_add(order("amo", status="AMO", order_type="LIMIT", price=90.0, product="NRML", block=6000,
                               at=t(18, 0, day=date(2026, 10, 15))))
    store.desk_order_add(order("eve", status="AMO", order_type="LIMIT", price=90.0, product="NRML", block=6000,
                               at=t(18, 0)))
    assert service.housekeep(store, t(15, 30, 5), CAL) == 2
    assert store.desk_order("lim")["status"] == "CANCELLED" and "day order" in store.desk_order("lim")["reason"]
    assert "no live prices" in store.desk_order("amo")["reason"]
    assert store.desk_order("eve")["status"] == "AMO"                           # placed tonight, for Monday


def test_intraday_positions_square_off_at_1520_even_without_the_recorder(store):
    store.desk_order_add(order("b1", fill=100.0, at=t(10, 0)))
    store.desk_order_add(order("tgt", side="SELL", status="OPEN", order_type="LIMIT", price=150.0, at=t(10, 1)))
    store.write_bars([_bar(101, t(15, 19), 111.0, bid=110.5), _bar(101, t(15, 25), 130.0, bid=129.0)])
    assert service.housekeep(store, t(15, 21), CAL) == 0                        # the recorder's turn first
    service.housekeep(store, t(15, 24), CAL)
    sq = store.desk_order(service.square_off_id({**OPT, "username": "amit", "epoch": 1}, DAY))
    assert sq["fill_price"] == 110.5 and sq["filled_at"] == t(15, 20) and sq["source"] == "squareoff"
    assert store.desk_order("tgt")["status"] == "CANCELLED"
    service.housekeep(store, t(15, 40), CAL)                                    # done once
    assert len([o for o in store.desk_orders("amit", 1) if o["side"] == "SELL" and o["status"] == "FILLED"]) == 1


def test_a_carried_position_is_settled_at_expiry_from_the_index_close(store):
    store.desk_order_add(order("itm", product="NRML", fill=100.0, at=t(10, 0)))
    store.desk_order_add({**order("otm", product="NRML", fill=50.0, at=t(10, 0)), "token": 102, "strike": 25500.0,
                          "symbol": "NIFTY26OCT25500CE"})
    store.write_bars([_bar(256265, ist(2026, 10, 27, 15, 29), 25180.0)])
    service.housekeep(store, ist(2026, 10, 27, 15, 35), CAL)
    a = book(store.desk_account("amit"), store.desk_orders("amit", 1), {}, ist(2026, 10, 27, 15, 40))
    by = {tr["token"]: tr for tr in a["trades"]}
    assert by[101]["exit"] == 180.0 and by[101]["reason"] == "Settled at expiry"
    assert by[102]["exit"] == 0.0 and by[102]["charges"] == pytest.approx(charges_json("BUY", 50 * 65)["total"])
    assert not any(p["qty"] for p in a["positions"])


# ── The recorder fills orders ────────────────────────────────────────────────

class Agg:
    def __init__(self):
        self.quotes, self.last_price = {}, {}

    def quote(self, token):
        return self.quotes.get(token, (None, None))

    def set(self, token, bid, ask, ltp):
        self.quotes[token], self.last_price[token] = (bid, ask), ltp


class Rec:
    def __init__(self):
        self.agg, self.watched = Agg(), []

    def watch(self, token):
        self.watched.append(token)

    def wake(self):
        pass


class Live:
    def __init__(self):
        self.pinned = []

    def watch(self, symbol, token, pin=False):
        self.pinned.append((symbol, pin))


def worker(store, broker=None):
    rec, live = Rec(), Live()
    return DeskWorker(rec, broker or object(), store, CAL, live), rec, live


def test_the_recorder_fills_market_orders_at_the_ask_and_rests_limits(store):
    w, rec, live = worker(store)
    rec.agg.set(101, 139.5, 140.5, 140.0)
    store.desk_order_add(order("m1", status="PENDING", block=9500))
    store.desk_order_add(order("l1", status="PENDING", order_type="LIMIT", price=138.0, block=9100))
    w.maybe(t(10, 0, 1))
    m1, l1 = store.desk_order("m1"), store.desk_order("l1")
    assert m1["status"] == "FILLED" and m1["fill_price"] == 140.5 and m1["fill_source"] == "live ask"
    assert m1["charges"]["brokerage"] == 20 and m1["block"] == 0
    assert l1["status"] == "OPEN" and rec.watched == [101, 101] and ("NIFTY26OCT25000CE", True) in live.pinned
    rec.agg.set(101, 137.0, 137.5, 137.2)
    w.maybe(t(10, 0, 5))
    l1 = store.desk_order("l1")
    assert l1["status"] == "FILLED" and l1["fill_price"] == 138.0 and l1["fill_source"] == "your limit price"


def test_a_stop_loss_sell_triggers_and_sells_at_the_bid(store):
    store.desk_order_add(order("b1", fill=140.0, at=t(9, 30)))
    store.desk_order_add(order("sl", side="SELL", status="OPEN", order_type="SL-M", trigger=120.0))
    w, rec, _ = worker(store)
    rec.agg.set(101, 125, 126, 125.5)
    w.maybe(t(10, 0))
    assert store.desk_order("sl")["status"] == "OPEN"
    rec.agg.set(101, 118.5, 119.5, 119.0)
    w.maybe(t(10, 1))
    sl = store.desk_order("sl")
    assert sl["status"] == "FILLED" and sl["fill_price"] == 118.5


def test_a_buy_that_no_longer_fits_the_funds_is_rejected_at_the_fill(store):
    store.desk_account_save({**store.desk_account("amit"), "funds": 10_000})
    store.desk_order_add(order("m1", status="PENDING", block=9900))
    w, rec, _ = worker(store)
    rec.agg.set(101, 199, 200, 199.5)                                          # it jumped: 65 × 200 > 10k
    w.maybe(t(10, 0))
    m1 = store.desk_order("m1")
    assert m1["status"] == "REJECTED" and "Not enough funds" in m1["reason"]


def test_no_tick_yet_uses_the_brokers_quote_and_no_price_at_all_is_rejected(store):
    class Broker:
        calls = 0

        def quotes(self, tokens):
            Broker.calls += 1
            return {"NIFTY26OCT25000CE": {"bid": 99.0, "ask": 100.0, "ltp": 99.5}} if Broker.calls == 1 else {}

    store.desk_order_add(order("m1", status="PENDING", block=7000, at=t(10, 0)))
    w, _, _ = worker(store, Broker())
    w.maybe(t(10, 0, 1))
    assert store.desk_order("m1")["fill_price"] == 100.0 and store.desk_order("m1")["fill_source"] == "broker quote ask"
    store.desk_order_add(order("m2", status="PENDING", block=7000, at=t(10, 1)))
    w.maybe(t(10, 1, 5))
    assert store.desk_order("m2")["status"] == "PENDING"
    w.maybe(t(10, 1, 20))
    assert store.desk_order("m2")["status"] == "REJECTED"


def test_an_after_market_order_waits_from_the_open_not_from_when_it_was_placed(store):
    store.desk_order_add(order("amo", status="AMO", block=7000, at=t(18, 0, day=date(2026, 10, 15))))
    w, rec, _ = worker(store)
    w.maybe(t(9, 15, 5))
    assert store.desk_order("amo")["status"] == "AMO"                         # no tick yet: keeps waiting
    rec.agg.set(101, 99.0, 100.0, 99.5)
    w.maybe(t(9, 15, 8))
    assert store.desk_order("amo")["status"] == "FILLED" and store.desk_order("amo")["fill_price"] == 100.0


def test_the_recorder_squares_off_intraday_at_the_live_bid_at_1520(store):
    store.desk_order_add(order("b1", fill=100.0, at=t(10, 0)))
    store.desk_order_add(order("c1", product="NRML", fill=100.0, at=t(10, 0)))
    w, rec, _ = worker(store)
    rec.agg.set(101, 121.0, 122.0, 121.5)
    w.maybe(t(15, 19, 50))
    w.maybe(t(15, 20, 30))
    a = book(store.desk_account("amit"), store.desk_orders("amit", 1), {}, t(15, 30))
    [sq] = a["trades"]
    assert sq["exit"] == 121.0 and sq["product"] == "MIS" and sq["reason"] == "Auto square-off 15:20"
    assert [p["product"] for p in a["positions"] if p["qty"]] == ["NRML"]         # carry stays open


def test_a_cancel_racing_a_fill_loses_cleanly(store):
    store.desk_order_add(order("l1", status="OPEN", order_type="LIMIT", price=138.0, block=9100))
    w, rec, _ = worker(store)
    w.maybe(t(10, 0))                                                          # read while open
    assert service.end(store, store.desk_order("l1"), "CANCELLED", "You cancelled it", t(10, 0, 1))
    rec.agg.set(101, 137.0, 137.5, 137.2)
    w._work(w._orders[0], t(10, 0, 2))                                       # the matcher still thinks it is open
    assert store.desk_order("l1")["status"] == "CANCELLED"


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def market(tmp_path_factory):
    path = tmp_path_factory.mktemp("desk") / "api.db"
    s = Store(make_engine(f"sqlite:///{path}"))
    ctx = build_market()
    save_market(s, ctx, (date(2026, 12, 29),))
    return s, ctx


@pytest.fixture
def api(market, monkeypatch):
    store, ctx = market
    clock = {"now": t(18, 30)}
    monkeypatch.setattr(desk_routes, "now_ist", lambda: clock["now"])
    monkeypatch.setattr(check_routes, "now_ist", lambda: clock["now"])
    monkeypatch.setattr(desk_routes, "WAIT_FILL_S", 0.2)
    users = {"me": {"id": 2, "username": "viewer1", "role": "viewer", "token": "t"}}
    app = FastAPI()
    app.include_router(desk_routes.router)
    app.dependency_overrides[desk_routes.get_store] = lambda: store
    app.dependency_overrides[desk_routes.get_cfg] = lambda: OptionsSettings(_env_file=None)
    app.dependency_overrides[desk_routes.get_calendar] = lambda: CAL
    app.dependency_overrides[desk_routes.current_user] = lambda: users["me"]
    return TestClient(app), store, ctx, clock, users


def _atm_symbol(ctx):
    k = ctx.ref.atm_strike(ctx.spot, ctx.ref.expiries[-1])
    return ctx.ref.options[(ctx.ref.expiries[-1], k, "CE")]


def test_ticket_prices_the_order_with_every_charge_and_the_breakeven(api):
    client, _, ctx, _, _ = api
    opt = _atm_symbol(ctx)
    r = client.get("/api/desk/ticket", params={"token": opt.token, "lots": 2}).json()
    est = r["estimate"]
    assert r["contract"]["lot_size"] == opt.lot_size and r["quote"]["source"] == "last recorded minute"
    assert est["price"] == r["quote"]["ask"] and est["charges"]["brokerage"] == 20
    assert est["breakeven"] > est["price"] and r["problem"] is None and not r["market"]["open"]
    sell = client.get("/api/desk/ticket", params={"token": opt.token, "side": "SELL"}).json()
    assert "buy-only" in sell["problem"]


def test_an_evening_order_waits_for_the_open_and_can_be_modified_and_cancelled(api):
    client, store, ctx, _, _ = api
    opt = _atm_symbol(ctx)
    r = client.post("/api/desk/orders", json={"token": opt.token, "side": "BUY", "lots": 1,
                                              "order_type": "LIMIT", "price": 50.0, "product": "NRML"})
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["status"] == "AMO" and o["block"] > 50 * opt.lot_size
    m = client.patch(f"/api/desk/orders/{o['id']}", json={"price": 55.0, "lots": 2}).json()["order"]
    assert m["price"] == 55.0 and m["qty"] == 2 * opt.lot_size
    desk = client.get("/api/desk").json()
    assert desk["funds"]["blocked"] == pytest.approx(m["block"]) and desk["orders"][0]["id"] == o["id"]
    c = client.post(f"/api/desk/orders/{o['id']}/cancel").json()["order"]
    assert c["status"] == "CANCELLED" and client.post(f"/api/desk/orders/{o['id']}/cancel").status_code == 409


def test_in_market_hours_without_a_feed_orders_are_refused(api, monkeypatch):
    client, _, ctx, clock, _ = api
    clock["now"] = t(11, 0)
    r = client.post("/api/desk/orders", json={"token": _atm_symbol(ctx).token, "side": "BUY", "lots": 1})
    assert r.status_code == 503 and "aren't streaming" in r.json()["detail"]["message"]


def test_a_live_market_order_fills_through_the_recorder_and_the_position_exits(api, monkeypatch):
    client, store, ctx, clock, _ = api
    clock["now"] = t(11, 0)
    monkeypatch.setattr(desk_routes, "_recorder_live", lambda *a: True)
    opt = _atm_symbol(ctx)
    placed = client.post("/api/desk/orders", json={"token": opt.token, "side": "BUY", "lots": 1}).json()["order"]
    assert placed["status"] == "PENDING"
    w, rec, _ = worker(store)
    rec.agg.set(opt.token, 100.0, 101.0, 100.5)
    w.maybe(clock["now"])
    pos = client.get("/api/desk").json()["positions"]
    assert pos[0]["qty"] == opt.lot_size and pos[0]["avg"] == 101.0
    ex = client.post("/api/desk/positions/exit", json={"token": opt.token, "product": "MIS"}).json()["order"]
    assert ex["side"] == "SELL" and ex["source"] == "exit"
    rec.agg.set(opt.token, 110.0, 111.0, 110.5)
    w.poke(ex["id"])                                                           # the API's NOTIFY
    w.maybe(clock["now"] + timedelta(seconds=2))
    d = client.get("/api/desk").json()
    [tr] = [x for x in d["trades"] if x["token"] == opt.token]
    assert tr["exit"] == 110.0 and tr["reason"] == "You exited" and tr["net"] < (110 - 101) * opt.lot_size
    assert client.post("/api/desk/positions/exit", json={"token": opt.token, "product": "MIS"}).status_code == 409


def test_accounts_are_private_and_can_be_topped_up_or_reset(api):
    client, store, ctx, clock, users = api
    clock["now"] = t(18, 30)
    opt = _atm_symbol(ctx)
    mine = client.post("/api/desk/orders", json={"token": opt.token, "side": "BUY", "lots": 1,
                                                 "order_type": "LIMIT", "price": 40.0, "product": "NRML"}).json()["order"]
    users["me"] = {"id": 3, "username": "someone", "role": "viewer", "token": "u"}
    assert client.post(f"/api/desk/orders/{mine['id']}/cancel").status_code == 404
    assert client.get("/api/desk").json()["orders"] == []
    users["me"] = {"id": 2, "username": "viewer1", "role": "viewer", "token": "t"}
    client.post("/api/desk/account", json={"action": "add", "amount": 50_000})
    assert client.get("/api/desk").json()["funds"]["start"] == 150_000
    client.post("/api/desk/account", json={"action": "reset", "amount": 200_000})
    fresh = client.get("/api/desk").json()
    assert fresh["funds"]["start"] == 200_000 and fresh["orders"] == [] and fresh["account"]["epoch"] == 2
    assert store.desk_order(mine["id"])["status"] == "CANCELLED"

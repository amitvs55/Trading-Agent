"""Live NIFTY 50 / SENSEX: recorder feed → saved copy / NOTIFY → API hub → stream."""

import asyncio
import json
import time
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import live as hub_mod
from api.routes import options as routes
from options.brokers.angel import (BSE_CM, BSE_OFFSET, LTP_MODE, AngelBroker, subscription_groups, tick_to_kite,
                                   to_angel, to_internal)
from options.core.calendar import IST, NseCalendar
from options.agents.context import Constituent
from options.market_data.live import CloseKeeper, LiveIndexFeed, market_window, quote_close
from options.market_data.recorder import Recorder
from options.storage import Store, make_engine
from tests.options.fixtures import ist

CAL = NseCalendar()
NIFTY, SENSEX = 99926000, BSE_OFFSET + 99919000


@pytest.fixture
def store(tmp_path):
    return Store(make_engine(f"sqlite:///{tmp_path}/live.db"))


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _feed(store, clock, **kw):
    return LiveIndexFeed(store, {"NIFTY 50": NIFTY, "SENSEX": SENSEX}, date(2026, 10, 19), now_fn=clock, **kw)


def _tick(token, price, at):
    return {"instrument_token": token, "last_price": price, "exchange_timestamp": at}


# ── Angel: SENSEX on the BSE channel ─────────────────────────────────────────

def test_bse_tokens_have_their_own_range_and_stream_on_the_bse_channel():
    assert to_internal("BSE", "99919000") == SENSEX and to_angel(SENSEX) == ("BSE", "99919000")
    assert to_angel(to_internal("NFO", "57130")) == ("NFO", "57130") and to_angel(NIFTY) == ("NSE", "99926000")
    groups = subscription_groups([NIFTY, SENSEX])
    assert {"exchangeType": BSE_CM, "tokens": ["99919000"]} in groups[LTP_MODE]
    tick = tick_to_kite({"token": "99919000", "exchange_type": BSE_CM, "last_traded_price": 8_151_234,
                         "exchange_timestamp": int(ist(2026, 10, 19, 10, 0, 1).timestamp() * 1000)})
    assert tick["instrument_token"] == SENSEX and tick["last_price"] == 81512.34
    assert tick["exchange_timestamp"] == ist(2026, 10, 19, 10, 0, 1)


def test_sensex_token_comes_from_the_scrip_master_and_quotes_parse_both_exchanges():
    class Api:
        def getMarketData(self, mode, req):
            assert mode == "FULL" and req == {"NSE": ["99926000"], "BSE": ["99919001"]}
            return {"status": True, "data": {"fetched": [
                {"exchange": "NSE", "symbolToken": "99926000", "ltp": 23096.95, "close": 23010.2, "netChange": 86.75},
                {"exchange": "BSE", "symbolToken": "99919001", "ltp": 75512.1, "close": 75261.8, "netChange": 250.3}]}}

    b = AngelBroker.__new__(AngelBroker)
    b.api, b._master = Api(), [{"exch_seg": "BSE", "instrumenttype": "AMXIDX", "symbol": "SENSEX", "name": "SENSEX",
                                "token": "99919001"}]
    tokens = b.live_index_tokens()
    assert tokens == {"NIFTY 50": NIFTY, "SENSEX": BSE_OFFSET + 99919001}
    q = b.quotes(tokens)
    assert q["SENSEX"] == {"ltp": 75512.1, "close": 75261.8, "net_change": 250.3} and q["NIFTY 50"]["close"] == 23010.2


# ── The recorder's feed ──────────────────────────────────────────────────────

def test_levels_never_go_backwards_and_carry_the_exchange_time(store):
    clock = Clock(ist(2026, 10, 19, 10, 0, 2))
    feed = _feed(store, clock)
    feed.on_tick(_tick(NIFTY, 23100.0, ist(2026, 10, 19, 10, 0, 1)), clock())
    feed.on_tick(_tick(NIFTY, 23090.0, ist(2026, 10, 19, 10, 0, 0)), clock())      # late: older than what we hold
    snap = feed.publish_once()
    nifty = next(i for i in snap["items"] if i["symbol"] == "NIFTY 50")
    assert nifty["ltp"] == 23100.0 and nifty["ts"] == int(ist(2026, 10, 19, 10, 0, 1).timestamp() * 1000)
    assert store.live_snapshot()["items"][0]["ltp"] == 23100.0                      # saved for pages opening now
    assert feed.take_lag_ms() == 1000.0 and feed.take_lag_ms() is None


def test_a_burst_of_ticks_goes_out_at_once_then_coalesced(store):
    clock = Clock(ist(2026, 10, 19, 10, 0, 0))
    feed = _feed(store, clock, min_gap_s=0.3)
    sent = []
    store.publish_live = lambda snap, now, persist=True: sent.append(snap)
    feed.start()
    try:
        feed.on_tick(_tick(NIFTY, 23100.0, clock()), clock())
        deadline = datetime.now() + timedelta(seconds=2)
        while not sent and datetime.now() < deadline:
            time.sleep(0.01)
        assert len(sent) == 1                                                       # the first goes out at once
        for i in range(20):                                                         # then a burst within the gap
            feed.on_tick(_tick(NIFTY, 23101.0 + i, clock() + timedelta(milliseconds=10 * (i + 1))), clock())
        time.sleep(0.6)
    finally:
        feed.stop()
    assert 2 <= len(sent) <= 4 and sent[-1]["items"][0]["ltp"] == 23120.0           # newest wins, no backlog


def test_previous_close_quote_in_market_hours_outranks_saved_bars_and_survives_a_restart(store):
    clock = Clock(ist(2026, 10, 19, 8, 45))
    store.write_bars([{"instrument_token": NIFTY, "ts": ist(2026, 10, 16, 15, 29), "open": 1, "high": 1, "low": 1,
                       "close": 23005.5, "volume_day": None, "oi": None, "bid": None, "ask": None,
                       "bid_qty": None, "ask_qty": None, "ticks": 30}])
    feed = _feed(store, clock)
    assert feed.load_saved_closes(CAL) == ["NIFTY 50"] and feed.prev_close["NIFTY 50"] == 23005.5
    quote = {"NIFTY 50": {"ltp": 23096.95, "close": 23010.2, "net_change": 86.75}}
    assert feed.load_quote_closes(quote, ist(2026, 10, 19, 8, 45), CAL) == []      # before the open: not trusted
    assert feed.load_quote_closes(quote, ist(2026, 10, 19, 9, 16), CAL) == ["NIFTY 50"]
    assert feed.prev_close["NIFTY 50"] == 23010.2 and feed.prev_source["NIFTY 50"] == "quote"
    assert not feed.set_prev_close("NIFTY 50", 1.0, "quote")                        # fixed for the session
    feed.publish_once(force_persist=True)

    again = _feed(store, clock)                                                     # the recorder restarts
    again.resume()
    assert again.prev_close["NIFTY 50"] == 23010.2 and again.missing_quote_close() == ["SENSEX"]


def test_a_quote_whose_close_disagrees_with_its_net_change_uses_the_net_change():
    assert quote_close("X", {"ltp": 100.0, "close": 99.0, "net_change": 1.0}) == 99.0
    assert quote_close("X", {"ltp": 100.0, "close": 100.0, "net_change": 2.5}) == 97.5   # close was today's
    assert quote_close("X", {"ltp": 100.0, "close": None, "net_change": 1.0}) is None


def test_close_keeper_prices_the_ticker_and_the_breadth_heavyweights_once_open(store):
    class Broker:
        calls = []

        def quotes(self, tokens):
            self.calls.append(set(tokens))
            return {name: {"ltp": 110.0, "close": 100.0, "net_change": 10.0} for name in tokens}

    feed = _feed(store, Clock(ist(2026, 10, 19, 9, 0)))
    stocks = {"NIFTY": [Constituent("HDFCBANK", 13.0, 341249), Constituent("ICICIBANK", 9.0, 1270529, 1400.0)]}
    keeper = CloseKeeper(Broker(), feed, stocks, CAL)
    keeper.maybe(ist(2026, 10, 19, 9, 0))
    assert Broker.calls == []                                                       # pre-open: wait
    keeper.maybe(ist(2026, 10, 19, 9, 15))
    assert Broker.calls == [{"NIFTY 50", "SENSEX", "HDFCBANK"}]                     # only what is missing
    assert stocks["NIFTY"][0].prev_close == 100.0 and stocks["NIFTY"][1].prev_close == 1400.0
    assert feed.prev_close == {"NIFTY 50": 100.0, "SENSEX": 100.0}
    keeper.maybe(ist(2026, 10, 19, 9, 16))
    assert keeper.done and len(Broker.calls) == 1


def test_the_recorder_feeds_only_ticks_that_pass_the_bad_print_guard(store):
    class Ticker:
        def start(self, on_ticks, on_connect, on_event):
            self.on_ticks = on_ticks

        def subscribe(self, tokens):
            pass

        def stop(self):
            pass

    clock = Clock(ist(2026, 10, 19, 10, 0, 0))
    feed = _feed(store, clock)
    ticker = Ticker()
    rec = Recorder(ticker, [], store, None, now_fn=clock, live=feed)
    rec.start({})
    try:
        assert {NIFTY, SENSEX} <= rec.subscribed
        ticker.on_ticks([_tick(SENSEX, 75500.0, clock())])
        ticker.on_ticks([_tick(SENSEX, 7550.0, clock() + timedelta(seconds=1))])      # a 90% "drop": a bad print
    finally:
        feed.stop()
    assert feed._levels["SENSEX"].ltp == 75500.0


def test_market_window_flips_on_the_exchange_clock():
    m = market_window(CAL, ist(2026, 10, 19, 15, 29, 59))
    assert m["open"] and m["closes_ms"] == int(ist(2026, 10, 19, 15, 30).timestamp() * 1000)
    after = market_window(CAL, ist(2026, 10, 19, 15, 30))
    # Tue 20 Oct is Dussehra: the next open is Wed 21 Oct; today's close stays the last one
    assert not after["open"] and after["opens_ms"] == int(ist(2026, 10, 21, 9, 15).timestamp() * 1000)
    assert after["last_session"] == "2026-10-19"
    early = market_window(CAL, ist(2026, 10, 21, 8, 0))
    assert early["opens_ms"] == int(ist(2026, 10, 21, 9, 15).timestamp() * 1000) and early["last_session"] == "2026-10-19"


# ── API: hub and stream ──────────────────────────────────────────────────────

def _snap(seq, sent_s, ltp):
    return {"v": 1, "seq": seq, "session": "2026-10-19", "sent_ms": sent_s * 1000,
            "items": [{"symbol": "NIFTY 50", "ltp": ltp, "ts": sent_s * 1000 - 200, "prev_close": 23000.0}]}


def test_hub_keeps_only_the_newest_for_a_slow_reader_and_ignores_older_copies(store):
    async def run():
        hub = hub_mod.LiveHub(lambda: store)
        box = hub.subscribe()
        hub._accept(_snap(1, 100, 23100.0))
        hub._accept(_snap(2, 101, 23101.0))                                         # reader hasn't read yet
        hub._accept(_snap(1, 100, 23100.0))                                         # an older saved copy
        restarted = {**_snap(1, 102, 23102.0)}                                      # a restarted recorder: seq 1 again
        hub._accept(restarted)
        return box.qsize(), (await box.get())["items"][0]["ltp"], hub.latest["sent_ms"]

    size, ltp, sent = asyncio.run(run())
    assert size == 1 and ltp == 23102.0 and sent == 102_000


def test_stream_sends_the_latest_at_once_then_each_update(store):
    store.publish_live(_snap(5, 100, 23100.0), datetime.now(IST))

    async def run():
        hub = hub_mod.LiveHub(lambda: store)
        out = []

        async def never():
            return False
        gen = hub_mod.stream(hub, lambda: CAL, never, heartbeat_s=0.05)
        out.append(await gen.__anext__())                                           # retry hint
        out.append(await gen.__anext__())                                           # the saved levels at once
        hub._accept(_snap(6, 101, 23101.5))
        out.append(await gen.__anext__())
        out.append(await gen.__anext__())                                           # quiet: a heartbeat
        await gen.aclose()
        hub.stop()
        return out, hub

    out, hub = asyncio.run(run())
    assert out[0].startswith("retry:")
    first = json.loads(out[1].split("data: ")[1])
    assert out[1].startswith("event: levels") and first["items"][0]["ltp"] == 23100.0 and "market" in first
    assert json.loads(out[2].split("data: ")[1])["items"][0]["ltp"] == 23101.5
    assert out[3].startswith("event: ping") and not hub._mailboxes                 # closed streams leave no mailbox


def test_snapshot_endpoint_needs_sign_in_and_returns_levels_with_market_times(store):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_store] = lambda: store
    app.dependency_overrides[routes.get_calendar] = NseCalendar
    client = TestClient(app)
    assert client.get("/api/options/live/indices").status_code == 401
    app.dependency_overrides[routes.current_user] = lambda: {"id": 2, "username": "v", "role": "viewer", "token": "t"}
    body = client.get("/api/options/live/indices").json()
    assert body["items"] == [] and set(body["market"]) >= {"open", "opens_ms", "closes_ms", "last_close_ms"}
    store.publish_live(_snap(1, 100, 23100.0), datetime.now(IST))
    assert client.get("/api/options/live/indices").json()["items"][0]["ltp"] == 23100.0


def test_a_stream_ends_itself_with_bye_before_any_proxy_limit(store):
    async def run():
        hub = hub_mod.LiveHub(lambda: store)

        async def never():
            return False
        events = [e async for e in hub_mod.stream(hub, lambda: CAL, never, heartbeat_s=0.05, rotate_s=0.2)]
        hub.stop()
        return events

    events = asyncio.run(run())
    assert events[-1].startswith("event: bye") and any(e.startswith("event: ping") for e in events)


# ── Off hours: the last session's close for the ticker ───────────────────────

class QuoteBroker:
    calls = 0

    def live_index_tokens(self):
        return {"NIFTY 50": NIFTY, "SENSEX": SENSEX}

    def quotes(self, tokens):
        QuoteBroker.calls += 1
        return {"NIFTY 50": {"ltp": 23096.95, "close": 23096.95, "net_change": 86.75},     # after the close
                "SENSEX": {"ltp": 75512.1, "close": 75261.8, "net_change": 250.3}}


def test_an_evening_start_saves_the_sessions_close_once(store):
    from options import live_levels

    QuoteBroker.calls = 0
    evening = ist(2026, 10, 19, 15, 47)
    assert live_levels.publish_closing_levels(store, QuoteBroker(), CAL, evening)
    snap = store.live_snapshot()
    by = {i["symbol"]: i for i in snap["items"]}
    assert snap["session"] == "2026-10-19"
    assert by["NIFTY 50"]["ltp"] == 23096.95 and by["NIFTY 50"]["prev_close"] == 23010.2   # ltp − net change
    assert by["SENSEX"]["prev_close"] == 75261.8
    assert not live_levels.publish_closing_levels(store, QuoteBroker(), CAL, ist(2026, 10, 20, 11, 0))  # holiday: saved
    assert QuoteBroker.calls == 1


def test_the_closing_levels_helper_keeps_out_of_the_live_session(store):
    from options import live_levels

    assert live_levels.due(store, CAL, ist(2026, 10, 19, 10, 0)) is None             # market hours: the session's job
    assert live_levels.due(store, CAL, ist(2026, 10, 19, 9, 5)) is None              # pre-open quotes aren't a close
    assert live_levels.due(store, CAL, ist(2026, 10, 21, 8, 0)) == date(2026, 10, 19)  # before Wednesday's open

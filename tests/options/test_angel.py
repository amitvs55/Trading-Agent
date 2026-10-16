"""Angel One adapter: translation into Kite's shapes, login, history, and the stream loop."""

import threading
from datetime import date, datetime

import pytest

from options.brokers.angel import (NFO_OFFSET, AngelBroker, AngelError, AngelTickerAdapter, candles_to_kite,
                                   merge_oi, subscription_groups, tick_to_kite, to_angel, to_kite_rows)
from options.core.calendar import IST
from options.reference import VIX_SYMBOL, build_reference, find_token
from tests.options.fixtures import EXPIRED, MONTHLY, TODAY, WEEKLY, _strikes


def _index(token, symbol, name):
    return {"token": token, "symbol": symbol, "name": name, "expiry": "", "strike": "0.000000", "lotsize": "1",
            "instrumenttype": "AMXIDX", "exch_seg": "NSE", "tick_size": "0.000000"}


def _fut(token, expiry: date, name="NIFTY", lot="65"):
    return {"token": token, "symbol": f"{name}{expiry:%d%b%y}FUT".upper(), "name": name,
            "expiry": f"{expiry:%d%b%Y}".upper(), "strike": "-1.000000", "lotsize": lot,
            "instrumenttype": "FUTIDX", "exch_seg": "NFO", "tick_size": "10.000000"}


def _opt(token, expiry: date, strike: int, right: str):
    return {"token": token, "symbol": f"NIFTY{expiry:%d%b%y}{strike}{right}".upper(), "name": "NIFTY",
            "expiry": f"{expiry:%d%b%Y}".upper(), "strike": f"{strike * 100:.6f}", "lotsize": "65",
            "instrumenttype": "OPTIDX", "exch_seg": "NFO", "tick_size": "5.000000"}


def master() -> list[dict]:
    rows = [_index("99926000", "Nifty 50", "NIFTY"), _index("99926017", "India VIX", "INDIA VIX"),
            {"token": "2885", "symbol": "RELIANCE-EQ", "name": "RELIANCE", "expiry": "", "strike": "-1.000000",
             "lotsize": "1", "instrumenttype": "", "exch_seg": "NSE", "tick_size": "10.000000"},
            {"token": "9999", "symbol": "RELIANCE-BE", "name": "RELIANCE", "expiry": "", "strike": "-1.000000",
             "lotsize": "1", "instrumenttype": "", "exch_seg": "NSE", "tick_size": "10.000000"},
            _fut("48704", MONTHLY), _fut("61471", date(2026, 11, 24)), _fut("48700", MONTHLY, "BANKNIFTY", "30"),
            _opt("40000", EXPIRED, 25300, "CE")]
    token = 50000
    for exp in (WEEKLY, MONTHLY):
        for k in _strikes():
            for right in ("CE", "PE"):
                token += 1
                rows.append(_opt(str(token), exp, k, right))
    return rows


# ── Instruments ──────────────────────────────────────────────────────────────

def test_nse_rows_use_kite_names_and_strip_the_series():
    nse = to_kite_rows(master(), "NSE")
    by_symbol = {r["tradingsymbol"]: r for r in nse}
    assert by_symbol["NIFTY 50"]["segment"] == "INDICES" and by_symbol["NIFTY 50"]["instrument_token"] == 99926000
    assert find_token(nse, VIX_SYMBOL) == 99926017
    assert by_symbol["RELIANCE"]["segment"] == "NSE" and by_symbol["RELIANCE"]["instrument_token"] == 2885
    assert "RELIANCE-BE" not in by_symbol and len([r for r in nse if r["tradingsymbol"] == "RELIANCE"]) == 1


def test_nfo_rows_are_in_rupees_dated_and_offset():
    nfo = to_kite_rows(master(), "NFO")
    opt = next(r for r in nfo if r["tradingsymbol"] == "NIFTY19OCT2625000CE")
    assert {k: v for k, v in opt.items() if k != "instrument_token"} == {
        "tradingsymbol": "NIFTY19OCT2625000CE", "name": "NIFTY", "segment": "NFO-OPT", "instrument_type": "CE",
        "exchange": "NFO", "expiry": WEEKLY, "strike": 25000.0, "lot_size": 65, "tick_size": 0.05}
    assert opt["instrument_token"] > NFO_OFFSET
    fut = next(r for r in nfo if r["tradingsymbol"] == "NIFTY27OCT26FUT")
    assert fut["segment"] == "NFO-FUT" and fut["instrument_type"] == "FUT" and fut["expiry"] == MONTHLY
    assert fut["instrument_token"] == NFO_OFFSET + 48704


def test_the_contract_reference_builds_from_angel_rows():
    rows = master()
    ref = build_reference("NIFTY", to_kite_rows(rows, "NSE"), to_kite_rows(rows, "NFO"), TODAY, 25262)
    assert ref.spot_token == 99926000
    assert ref.future_token == NFO_OFFSET + 48704 and ref.future_expiry == MONTHLY
    assert ref.expiries[:2] == [WEEKLY, MONTHLY] and EXPIRED not in ref.expiries
    assert ref.lot_size == 65 and ref.strike_step == 50
    atm = ref.options[(WEEKLY, 25250.0, "CE")]
    assert to_angel(atm.token)[0] == "NFO"


def test_token_round_trip():
    assert to_angel(99926000) == ("NSE", "99926000")
    assert to_angel(2885) == ("NSE", "2885")
    assert to_angel(NFO_OFFSET + 48704) == ("NFO", "48704")


# ── Ticks and candles ────────────────────────────────────────────────────────

def snap_quote(**over):
    msg = {"subscription_mode": 3, "exchange_type": 2, "token": "50123", "exchange_timestamp": 1792133100000,
           "last_traded_price": 14550, "volume_trade_for_the_day": 123450, "open_interest": 987650,
           "best_5_buy_data": [{"flag": 1, "quantity": 650, "price": 14545, "no of orders": 3}],
           "best_5_sell_data": [{"flag": 0, "quantity": 325, "price": 14560, "no of orders": 2}]}
    return {**msg, **over}


def test_a_snap_quote_becomes_a_kite_tick():
    tick = tick_to_kite(snap_quote())
    assert tick["instrument_token"] == NFO_OFFSET + 50123
    assert tick["last_price"] == 145.5 and tick["volume_traded"] == 123450 and tick["oi"] == 987650
    assert tick["exchange_timestamp"] == datetime.fromtimestamp(1792133100, tz=IST)
    assert tick["depth"]["buy"][0] == {"price": 145.45, "quantity": 650, "orders": 3}
    assert tick["depth"]["sell"][0]["price"] == 145.6


def test_swapped_book_sides_are_put_right():
    swapped = snap_quote(best_5_buy_data=snap_quote()["best_5_sell_data"],
                         best_5_sell_data=snap_quote()["best_5_buy_data"])
    tick = tick_to_kite(swapped)
    assert tick["depth"]["buy"][0]["price"] < tick["depth"]["sell"][0]["price"]


def test_an_index_ltp_packet_and_junk():
    tick = tick_to_kite({"subscription_mode": 1, "exchange_type": 1, "token": "99926000",
                         "exchange_timestamp": 1792133100000, "last_traded_price": 2526240})
    assert tick == {"instrument_token": 99926000, "last_price": 25262.4,
                    "exchange_timestamp": datetime.fromtimestamp(1792133100, tz=IST)}
    assert tick_to_kite({"token": "99926000", "last_traded_price": 0}) is None


def test_candles_and_open_interest():
    candles = candles_to_kite([["2026-10-15T09:15:00+05:30", 25200, 25210.5, 25190, 25205, 0],
                               ["2026-10-15T09:16:00+05:30", 25205, 25220, 25200, 25215, 1200]])
    assert candles[0] == {"date": datetime(2026, 10, 15, 9, 15, tzinfo=IST), "open": 25200.0,
                          "high": 25210.5, "low": 25190.0, "close": 25205.0, "volume": 0}
    merged = merge_oi(candles, [{"time": "2026-10-15T09:16:00+05:30", "oi": 15000000}])
    assert [c["oi"] for c in merged] == [0, 15000000]


def test_subscription_modes_by_kind():
    groups = subscription_groups([99926000, 2885, NFO_OFFSET + 50123])
    assert groups[1] == [{"exchangeType": 1, "tokens": ["99926000"]}]
    assert groups[2] == [{"exchangeType": 1, "tokens": ["2885"]}]
    assert groups[3] == [{"exchangeType": 2, "tokens": ["50123"]}]


# ── The broker over a fake SDK client ────────────────────────────────────────

class FakeApi:
    def __init__(self, login_ok=True):
        self.login_ok = login_ok
        self.candle_calls: list[dict] = []

    def generateSession(self, client_code, pin, totp):
        assert len(totp) == 6 and totp.isdigit()
        if not self.login_ok:
            return {"status": False, "message": "Invalid totp", "errorcode": "AB1050", "data": None}
        return {"status": True, "data": {"clientcode": client_code, "jwtToken": "Bearer jwt", "feedToken": "feed"}}

    def getfeedToken(self):
        return "feed"

    def getMarketData(self, mode, tokens):
        assert mode == "LTP" and tokens == {"NSE": ["99926000"]}
        return {"status": True, "data": {"fetched": [{"symbolToken": "99926000", "ltp": 25262.4}], "unfetched": []}}

    def getCandleData(self, params):
        self.candle_calls.append(params)
        return {"status": True, "data": [[f"{params['fromdate'][:10]}T09:15:00+05:30", 1, 2, 0.5, 1.5, 10]]}

    def getOIData(self, params):
        return {"status": True, "data": [{"time": f"{params['fromdate'][:10]}T09:15:00+05:30", "oi": 77}]}


def broker(api=None):
    return AngelBroker("key", "A123", "1234", "JBSWY3DPEHPK3PXP", master_fn=master, pause=lambda s: None,
                       api=api or FakeApi())


def test_login_and_the_stream_needs_it():
    b = broker()
    with pytest.raises(AngelError):
        b.ticker()
    assert b.login() == "A123"
    assert isinstance(b.ticker(), AngelTickerAdapter)


def test_a_refused_login_says_why():
    with pytest.raises(AngelError, match="AB1050.*Invalid totp"):
        broker(FakeApi(login_ok=False)).login()


def test_index_prices_by_kite_name():
    assert broker().index_prices(["NIFTY 50"]) == {"NIFTY 50": 25262.4}


def test_history_is_split_into_allowed_spans_with_oi():
    api = FakeApi()
    b = broker(api)
    start, end = datetime(2026, 8, 1, 9, 15, tzinfo=IST), datetime(2026, 10, 15, 15, 30, tzinfo=IST)
    candles = b.historical(NFO_OFFSET + 48704, start, end, "minute", oi=True)
    assert len(api.candle_calls) == 3                       # 75 days in 30-day spans
    assert all(c["exchange"] == "NFO" and c["symboltoken"] == "48704" and c["interval"] == "ONE_MINUTE"
               for c in api.candle_calls)
    assert len(candles) == 3 and all(c["oi"] == 77 for c in candles)


def test_a_separate_historical_key_logs_in_and_serves_history():
    main, history = FakeApi(), FakeApi()
    b = AngelBroker("key", "A123", "1234", "JBSWY3DPEHPK3PXP", master_fn=master, pause=lambda s: None,
                    api=main, historical_api=history)
    b.login()
    b.historical(99926000, datetime(2026, 10, 14, 9, 15, tzinfo=IST), datetime(2026, 10, 15, 15, 30, tzinfo=IST))
    assert history.candle_calls and not main.candle_calls


def test_a_refused_historical_login_fails_the_login():
    b = AngelBroker("key", "A123", "1234", "JBSWY3DPEHPK3PXP", master_fn=master, pause=lambda s: None,
                    api=FakeApi(), historical_api=FakeApi(login_ok=False))
    with pytest.raises(AngelError, match="historical-data key refused"):
        b.login()


# ── The stream loop ──────────────────────────────────────────────────────────

class FakeSocket:
    def __init__(self, packets):
        self.packets = packets
        self.subscribed: list[tuple[int, list[dict]]] = []
        self.closed = False

    def connect(self):                  # opens, delivers its packets, then the server hangs up
        self.on_open(None)
        for p in self.packets:
            self.on_data(None, p)

    def subscribe(self, correlation_id, mode, token_list):
        self.subscribed.append((mode, token_list))

    def close_connection(self):
        self.closed = True


def test_the_stream_delivers_ticks_resubscribes_and_reconnects():
    sockets = [FakeSocket([snap_quote()]), FakeSocket([snap_quote(last_traded_price=14600)])]
    made = iter(sockets)
    ticker = AngelTickerAdapter("key", "A123", "Bearer jwt", "feed", socket_factory=lambda: next(made),
                                sleep=lambda s: None)
    ticks, events, connects = [], [], []
    done = threading.Event()

    def on_connect():
        connects.append(1)
        ticker.subscribe([99926000, NFO_OFFSET + 50123])
        if len(connects) == 2:
            ticker.stop()
            done.set()

    ticker.start(on_ticks=ticks.extend, on_connect=on_connect, on_event=lambda k, d: events.append(k))
    assert done.wait(5)
    ticker._thread.join(5)
    assert [t["last_price"] for t in ticks] == [145.5, 146.0]
    assert events == ["close", "reconnect"]                  # one hang-up, one reconnect, then a clean stop
    assert {mode for mode, _ in sockets[0].subscribed} == {1, 3}
    assert sockets[1].subscribed, "the new socket is subscribed again"


def test_the_stream_gives_up_after_too_many_failed_connects():
    class Dead:
        def connect(self):
            raise OSError("refused")

        def close_connection(self):
            pass

    ticker = AngelTickerAdapter("key", "A123", "Bearer jwt", "feed", max_reconnects=2,
                                socket_factory=Dead, sleep=lambda s: None)
    events = []
    ticker.start(on_ticks=lambda t: None, on_connect=lambda: None, on_event=lambda k, d: events.append(k))
    ticker._thread.join(5)
    assert events[-1] == "noreconnect"
    assert events.count("reconnect") == 2

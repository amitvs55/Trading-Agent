from datetime import datetime, timedelta

from options.core.calendar import IST
from options.market_data.bars import BarAggregator, tick_time
from tests.options.fixtures import ist

TOKEN = 1019253001


def tick(price, ts, **extra):
    return {"instrument_token": TOKEN, "last_price": price, "exchange_timestamp": ts, **extra}


def depth(bid, ask, bid_qty=650, ask_qty=1300):
    return {"buy": [{"price": bid, "quantity": bid_qty, "orders": 3}],
            "sell": [{"price": ask, "quantity": ask_qty, "orders": 5}]}


def test_ticks_in_one_minute_build_one_bar():
    agg = BarAggregator()
    t0 = ist(2026, 10, 16, 10, 0, 5)
    agg.add(tick(140.0, t0, volume_traded=1000, oi=50000, depth=depth(139.9, 140.1)), t0)
    agg.add(tick(146.5, t0 + timedelta(seconds=20), volume_traded=1600, oi=50650), t0)
    agg.add(tick(138.0, t0 + timedelta(seconds=40), volume_traded=2100, oi=51300,
                 depth=depth(137.95, 138.05, 1950, 2600)), t0)

    [bar] = agg.pop_all()
    assert bar.ts == ist(2026, 10, 16, 10, 0)
    assert (bar.open, bar.high, bar.low, bar.close) == (140.0, 146.5, 138.0, 138.0)
    assert bar.volume_day == 2100 and bar.oi == 51300
    assert (bar.bid, bar.ask, bar.bid_qty, bar.ask_qty) == (137.95, 138.05, 1950, 2600)
    assert bar.ticks == 3


def test_pop_closed_waits_for_the_grace_period_and_drops_late_ticks():
    agg = BarAggregator()
    t0 = ist(2026, 10, 16, 10, 0, 30)
    agg.add(tick(140.0, t0), t0)
    agg.add(tick(141.0, ist(2026, 10, 16, 10, 1, 1)), t0)

    assert agg.pop_closed(ist(2026, 10, 16, 10, 1, 2)) == []           # still inside grace
    [closed] = agg.pop_closed(ist(2026, 10, 16, 10, 1, 4))
    assert closed.ts == ist(2026, 10, 16, 10, 0)

    agg.add(tick(139.0, ist(2026, 10, 16, 10, 0, 59)), t0)              # arrives after flush
    assert agg.late_ticks == 1
    [open_bar] = agg.pop_all()
    assert open_bar.ts == ist(2026, 10, 16, 10, 1)


def test_invalid_ticks_are_ignored():
    agg = BarAggregator()
    t0 = ist(2026, 10, 16, 10, 0)
    agg.add({"instrument_token": TOKEN, "last_price": 0, "exchange_timestamp": t0}, t0)
    agg.add({"last_price": 140.0, "exchange_timestamp": t0}, t0)
    assert agg.pop_all() == [] and agg.tick_count == 0


def test_tick_time_handles_naive_server_local_timestamps():
    epoch = ist(2026, 10, 16, 10, 0, 7).timestamp()
    naive_local = datetime.fromtimestamp(epoch)           # how kiteconnect builds it
    received = ist(2026, 10, 16, 10, 0, 8)
    assert tick_time({"exchange_timestamp": naive_local}, received) == ist(2026, 10, 16, 10, 0, 7)


def test_tick_time_falls_back_to_receipt_time():
    received = ist(2026, 10, 16, 10, 0, 8)
    assert tick_time({}, received) == received
    skewed = received - timedelta(hours=5, minutes=30)    # e.g. a UTC time mislabelled as IST
    assert tick_time({"exchange_timestamp": skewed.replace(tzinfo=IST)}, received) == received

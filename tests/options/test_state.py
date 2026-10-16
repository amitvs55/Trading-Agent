from datetime import date, datetime, timedelta

from options.core.calendar import IST
from options.engine.state import MarketState
from tests.options.fixtures import ist

TOKEN = 9001
DAY = date(2026, 10, 16)


def live_bar(ts, close, volume_day, oi=None):
    return {"instrument_token": TOKEN, "ts": ts, "open": close, "high": close + 2, "low": close - 2,
            "close": close, "volume_day": volume_day, "oi": oi, "bid": close - 0.5, "ask": close + 0.5,
            "bid_qty": 65, "ask_qty": 65, "ticks": 5}


def test_live_bars_resample_to_5m_buckets_from_0915():
    s = MarketState(DAY)
    start = ist(2026, 10, 16, 9, 15)
    s.add_bars([live_bar(start + timedelta(minutes=i), 25300 + i, 1000 * (i + 1)) for i in range(12)])
    five = s.frame(TOKEN, "5min")
    # 09:15–09:24 complete; the 09:25 bucket has only 2 of 5 minutes so it is dropped
    assert list(five.index) == [ist(2026, 10, 16, 9, 15), ist(2026, 10, 16, 9, 20)]
    first = five.iloc[0]
    assert (first["open"], first["close"], first["high"], first["low"]) == (25300, 25304, 25306, 25298)
    assert first["volume"] == 5000                        # per-bar volume from cumulative volume_day
    assert len(s.frame(TOKEN, "5min", closed_only=False)) == 3


def test_history_and_live_volume_join_without_double_counting():
    s = MarketState(DAY)
    s.load_history(TOKEN, [{"date": ist(2026, 10, 16, 9, 15), "open": 1, "high": 2, "low": 1, "close": 2,
                            "volume": 4000, "oi": 100}])
    s.add_bars([live_bar(ist(2026, 10, 16, 9, 16), 2, volume_day=6500)])
    one = s.frame(TOKEN, "1min")
    assert list(one["volume"]) == [4000, 2500]


def test_live_bar_overwrites_the_same_history_minute():
    s = MarketState(DAY)
    t = ist(2026, 10, 16, 9, 15)
    s.load_history(TOKEN, [{"date": t, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}])
    s.add_bars([live_bar(t, 3, volume_day=100)])
    assert len(s.frame(TOKEN, "1min")) == 1 and s.last_price(TOKEN) == 3


def test_prev_day_from_daily_candles_or_history():
    s = MarketState(DAY)
    s.load_daily(TOKEN, [{"date": datetime(2026, 10, 14, tzinfo=IST), "open": 1, "high": 5, "low": 0.5, "close": 4, "volume": 9},
                         {"date": datetime(2026, 10, 15, tzinfo=IST), "open": 4, "high": 8, "low": 3, "close": 7, "volume": 9},
                         {"date": datetime(2026, 10, 16, tzinfo=IST), "open": 7, "high": 9, "low": 6, "close": 8, "volume": 9}])
    assert s.prev_day(TOKEN) == {"date": date(2026, 10, 15), "open": 4.0, "high": 8.0, "low": 3.0, "close": 7.0}

    h = MarketState(DAY)
    h.load_history(TOKEN, [{"date": ist(2026, 10, 15, 9, 15 + i), "open": 10 + i, "high": 12 + i, "low": 9 + i,
                            "close": 11 + i, "volume": 1} for i in range(3)])
    assert h.prev_day(TOKEN) == {"date": date(2026, 10, 15), "open": 10.0, "high": 14.0, "low": 9.0, "close": 13.0}
    assert MarketState(DAY).prev_day(TOKEN) is None


def test_daily_includes_todays_running_candle():
    s = MarketState(DAY)
    s.load_daily(TOKEN, [{"date": datetime(2026, 10, 15, tzinfo=IST), "open": 4, "high": 8, "low": 3, "close": 7, "volume": 9}])
    s.add_bars([live_bar(ist(2026, 10, 16, 9, 15), 25300, 100), live_bar(ist(2026, 10, 16, 9, 16), 25310, 300)])
    d = s.daily(TOKEN)
    assert list(d.index) == [date(2026, 10, 15), DAY]
    assert d.loc[DAY, "close"] == 25310 and d.loc[DAY, "high"] == 25312 and d.loc[DAY, "volume"] == 300


def test_cache_is_invalidated_by_new_bars():
    s = MarketState(DAY)
    s.add_bars([live_bar(ist(2026, 10, 16, 9, 15) + timedelta(minutes=i), 100, i) for i in range(5)])
    assert len(s.frame(TOKEN, "5min")) == 1
    s.add_bars([live_bar(ist(2026, 10, 16, 9, 20) + timedelta(minutes=i), 101, 10 + i) for i in range(5)])
    assert len(s.frame(TOKEN, "5min")) == 2
    assert s.as_of() == ist(2026, 10, 16, 9, 24)


def test_unknown_token_is_empty():
    s = MarketState(DAY)
    assert s.frame(1).empty and s.last(1) is None and s.last_price(1) is None

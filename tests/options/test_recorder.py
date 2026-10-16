import pytest

from options.market_data.recorder import Recorder
from options.reference import build_reference
from options.storage import Store, make_engine
from tests.options.fixtures import (FUT_TOKEN, NIFTY_SPOT_TOKEN, NSE_ROWS, TODAY, VIX_TOKEN, Clock,
                                    FakeTicker, RecordingNotifier, ist, nfo_rows, option_token, WEEKLY)


@pytest.fixture
def setup(tmp_path):
    clock = Clock(ist(2026, 10, 16, 10, 0, 0))
    ticker, notifier = FakeTicker(), RecordingNotifier()
    store = Store(make_engine(f"sqlite:///{tmp_path}/options.db"))
    ref = build_reference("NIFTY", NSE_ROWS, nfo_rows(), TODAY, 25262.0)
    rec = Recorder(ticker, [ref], store, notifier, vix_token=VIX_TOKEN, window=15, n_expiries=2,
                   stale_after_s=60, now_fn=clock)
    rec.start({"NIFTY": 25262.0})
    return rec, ticker, notifier, store, clock


def spot(price, ts):
    return {"instrument_token": NIFTY_SPOT_TOKEN, "last_price": price, "exchange_timestamp": ts}


def test_start_subscribes_spot_future_vix_and_option_window(setup):
    rec, ticker, *_ = setup
    assert {NIFTY_SPOT_TOKEN, FUT_TOKEN, VIX_TOKEN} <= rec.subscribed
    assert len(rec.subscribed) == 3 + 31 * 2 * 2
    ticker.callbacks["connect"]()
    assert sorted(ticker.subscriptions[-1]) == sorted(rec.subscribed)


def test_closed_minutes_are_written(setup):
    rec, ticker, _, store, clock = setup
    ticker.callbacks["ticks"]([spot(25262.0, ist(2026, 10, 16, 10, 0, 10)),
                               {"instrument_token": option_token(WEEKLY, 25250, "CE"), "last_price": 141.0,
                                "exchange_timestamp": ist(2026, 10, 16, 10, 0, 20), "oi": 120000}])
    clock.now = ist(2026, 10, 16, 10, 1, 5)
    rec.flush(clock())
    assert rec.bars_written == 2
    assert store.count_bars_since(ist(2026, 10, 16, 10, 0)) == 2


def test_window_follows_the_index(setup):
    rec, ticker, *_ = setup
    ticker.callbacks["ticks"]([spot(25700.0, ist(2026, 10, 16, 10, 0, 10))])
    # 25700 + 15 strikes reaches 26900: 26100…26900 are new (9 strikes × CE/PE × 2 expiries)
    assert rec.recentre() == 36
    assert len(ticker.subscriptions[-1]) == 36
    assert rec.recentre() == 0


def test_stale_feed_alerts_once_and_reports_recovery(setup):
    rec, ticker, notifier, _, clock = setup
    ticker.callbacks["ticks"]([spot(25262.0, ist(2026, 10, 16, 10, 0, 40))])
    clock.now = ist(2026, 10, 16, 10, 2, 0)
    rec.check_stale(clock())
    rec.check_stale(clock())
    assert sum("No market data" in t for t in notifier.texts()) == 1
    ticker.callbacks["ticks"]([spot(25270.0, ist(2026, 10, 16, 10, 2, 0))])
    rec.check_stale(clock())
    assert "recovered" in notifier.texts()[-1]
    assert rec.stale_alerts == 1


def test_no_stale_alert_outside_market_hours(setup):
    rec, _, notifier, _, clock = setup
    clock.now = ist(2026, 10, 16, 16, 0)
    rec.check_stale(clock())
    assert notifier.messages == []


def test_websocket_events_are_counted_logged_and_escalated(setup):
    rec, ticker, notifier, *_ = setup
    ticker.callbacks["event"]("close", "1006 connection lost")
    ticker.callbacks["event"]("noreconnect", "gave up reconnecting")
    rec.flush(ist(2026, 10, 16, 10, 0, 30))
    assert rec.disconnects == 1
    assert any("could not reconnect" in t for t in notifier.texts())


def test_bars_are_kept_and_retried_when_the_database_fails(setup):
    rec, ticker, _, store, clock = setup
    real_write = store.write_bars
    calls = {"n": 0}

    def flaky(rows):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        return real_write(rows)

    store.write_bars = flaky
    ticker.callbacks["ticks"]([spot(25262.0, ist(2026, 10, 16, 10, 0, 10))])
    rec.flush(ist(2026, 10, 16, 10, 1, 5))
    assert rec.bars_written == 0 and rec.summary()["bars_unsaved"] == 1
    rec.flush(ist(2026, 10, 16, 10, 1, 6))
    assert rec.bars_written == 1 and rec.summary()["bars_unsaved"] == 0


def test_run_until_flushes_everything_and_stops_the_ticker(setup):
    rec, ticker, _, store, clock = setup
    ticker.callbacks["ticks"]([spot(25262.0, ist(2026, 10, 16, 10, 0, 1))])
    rec.run_until(ist(2026, 10, 16, 10, 0, 5), sleep=clock.sleep)
    assert ticker.stopped
    assert rec.bars_written == 1

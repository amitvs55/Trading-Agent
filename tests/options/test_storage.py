from datetime import date

import pytest

from options.storage import Store, make_engine, normalize_db_url
from tests.options.fixtures import NSE_ROWS, TODAY, ist, nfo_rows


@pytest.fixture
def store(tmp_path):
    return Store(make_engine(f"sqlite:///{tmp_path}/options.db"))


def bar(token, ts, close=100.0):
    return {"instrument_token": token, "ts": ts, "open": 100.0, "high": 101.0, "low": 99.0,
            "close": close, "volume_day": 1000, "oi": 5000, "bid": close - 0.05, "ask": close + 0.05,
            "bid_qty": 65, "ask_qty": 130, "ticks": 4}


def test_normalize_db_url():
    assert normalize_db_url("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_db_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url("sqlite:///data/options.db") == "sqlite:///data/options.db"


def test_latest_access_token_for_the_day_wins(store):
    store.save_access_token(TODAY, "first", "AB1234", ist(2026, 10, 16, 8, 40))
    store.save_access_token(TODAY, "second", "AB1234", ist(2026, 10, 16, 8, 41))
    assert store.load_access_token(TODAY) == "second"
    assert store.load_access_token(date(2026, 10, 19)) is None


def test_bars_upsert_on_token_and_minute(store):
    t = ist(2026, 10, 16, 10, 0)
    assert store.write_bars([bar(1, t), bar(2, t)]) == 2
    store.write_bars([bar(1, t, close=105.0)])                       # same key: update, not duplicate
    assert store.count_bars_since(ist(2026, 10, 16, 0, 0)) == 2
    assert store.count_bars_since(ist(2026, 10, 16, 10, 1)) == 0
    assert store.last_bar_ts().replace(tzinfo=None) == t.replace(tzinfo=None)


def test_large_batches_are_chunked(store):
    rows = [bar(token, ist(2026, 10, 16, 10, 0)) for token in range(1, 501)]
    assert store.write_bars(rows) == 500
    assert store.count_bars_since(ist(2026, 10, 16, 0, 0)) == 500


def test_instrument_snapshot_and_events(store):
    rows = [r for r in NSE_ROWS if r["segment"] == "INDICES"] + nfo_rows()[:10]
    assert store.save_instruments(TODAY, rows) == len(rows)
    assert store.save_instruments(TODAY, rows) == len(rows)           # idempotent per day
    store.log_event("ws_close", "1006 connection lost", ist(2026, 10, 16, 11, 0))

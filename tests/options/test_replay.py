from collections import defaultdict

import pytest

from options.backtest.replay import main, replay, replay_day
from options.config import OptionsSettings
from options.core.calendar import NseCalendar
from options.core.constituents import NIFTY_HEAVYWEIGHTS
from options.storage import Store, make_engine
from tests.options.fixtures import NSE_ROWS, TODAY, nfo_rows
from tests.options.market import build_market
from tests.options.test_setups_engine import AlwaysBull


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    """A recorded session in the database, built from the synthetic market."""
    path = tmp_path_factory.mktemp("rec") / "rec.db"
    store = Store(make_engine(f"sqlite:///{path}"))
    ctx = build_market(trend=1)
    equities = [{"instrument_token": 500_000 + j, "tradingsymbol": sym, "name": sym, "segment": "NSE",
                 "instrument_type": "EQ", "expiry": "", "strike": 0.0, "lot_size": 1, "tick_size": 0.05}
                for j, (sym, _) in enumerate(NIFTY_HEAVYWEIGHTS)]
    store.save_instruments(TODAY, NSE_ROWS + equities + nfo_rows())
    rows = []
    for token, by_ts in ctx.state._rows.items():
        cum = defaultdict(int)
        for ts in sorted(by_ts):
            r = by_ts[ts]
            cum[ts.date()] += int(r["volume"] or 0)
            rows.append({"instrument_token": token, "ts": ts.to_pydatetime(), "open": r["open"], "high": r["high"],
                         "low": r["low"], "close": r["close"], "volume_day": cum[ts.date()], "oi": r["oi"],
                         "bid": r["bid"], "ask": r["ask"], "bid_qty": r["bid_qty"], "ask_qty": r["ask_qty"], "ticks": 1})
    store.write_bars(rows)
    return store, path


def test_replay_produces_signals_and_is_deterministic(source, tmp_path):
    src, _ = source
    cfg = OptionsSettings(OPTIONS_INDICES=["NIFTY"])
    a = replay_day(src, Store(make_engine(f"sqlite:///{tmp_path}/a.db")), TODAY, cfg, NseCalendar(), setups=[AlwaysBull()])
    b = replay_day(src, Store(make_engine(f"sqlite:///{tmp_path}/b.db")), TODAY, cfg, NseCalendar(), setups=[AlwaysBull()])
    assert a, "the always-firing setup should produce at least one signal"
    key = lambda s: (s.signal_id, s.contract.tradingsymbol, s.entry_high, s.stop_loss, s.state, s.exit_reason, s.pnl_rupees)
    assert [key(s) for s in a] == [key(s) for s in b]
    assert all(s.created_at.time().hour >= 9 for s in a)


def test_replay_report_and_cli_guard(source, tmp_path):
    src, path = source
    report = replay(src, Store(make_engine(f"sqlite:///{tmp_path}/c.db")), TODAY, TODAY,
                    OptionsSettings(OPTIONS_INDICES=["NIFTY"]), setups=[AlwaysBull()])
    assert report["days"] == [TODAY.isoformat()] and report["signals"] >= 1
    assert main(["--from", "2026-10-16", "--to", "2026-10-16", "--source", f"sqlite:///{path}",
                 "--out", f"sqlite:///{path}"]) == 2


def test_the_replay_job_reports_signals_decisions_and_progress(source, tmp_path):
    from options.backtest.replay_job import REPORT_KEY, run
    src, _ = source
    steps = []
    real = src.set_meta_json
    src.set_meta_json = lambda k, v, now: (steps.append(dict(v)), real(k, v, now))
    req = {"from": TODAY.isoformat(), "to": TODAY.isoformat(), "requested_at": "x", "by": "admin"}
    report = run(src, req, cfg=OptionsSettings(OPTIONS_INDICES=["NIFTY"]), calendar=NseCalendar(),
                 workdir=str(tmp_path))
    src.set_meta_json = real
    assert report["status"] == "done" and report["days"] == [TODAY.isoformat()]
    assert report["decisions"]["candidates"] >= len(report["signals"])
    assert all(r["symbol"].startswith("NIFTY") for r in report["signals"])
    assert any(s.get("total") == 1 and s.get("done") == 0 for s in steps)      # progress before the day
    assert src.get_meta_json(REPORT_KEY)["status"] == "done"
    assert not (tmp_path / "replay.db").samefile(src.engine.url.database)      # never the live database


def test_day_candles_come_from_saved_minutes(source):
    from datetime import datetime, time, timedelta
    from options.core.calendar import IST
    src, _ = source
    token = NSE_ROWS[0]["instrument_token"]
    days = src.daily_bars(token, datetime.combine(TODAY - timedelta(days=60), time(0), IST),
                          datetime.combine(TODAY + timedelta(days=1), time(0), IST))
    assert days and all(d["low"] <= d["close"] <= d["high"] for d in days)
    assert [d["date"] for d in days] == sorted(d["date"] for d in days)

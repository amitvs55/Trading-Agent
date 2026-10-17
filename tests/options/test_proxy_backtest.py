"""Proxy historical backtest: expiry rules, a priced option chain, and a full run through the engine."""

from datetime import date, datetime, timedelta

import numpy as np
import pytest

from options.backtest import proxy
from options.backtest.proxy import SPOT_TOKEN, VIX_TOKEN, ProxyMarket, decode_option, fut_token, opt_token
from options.core.calendar import NseCalendar, at_ist
from options.session import history_rows
from options.storage import Store, make_engine
from tests.options.test_setups_engine import AlwaysBull

CAL = NseCalendar()


def trading_days(start: date, n: int, skip: set[date] = frozenset()) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5 and d not in skip:
            out.append(d)
        d += timedelta(days=1)
    return out


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    """25 sessions of synthetic NIFTY spot and VIX minutes, the way `proxy fetch` stores them."""
    store = Store(make_engine(f"sqlite:///{tmp_path_factory.mktemp('h')}/hist.db"))
    rng = np.random.default_rng(3)
    days = trading_days(date(2026, 9, 21), 25, skip={date(2026, 10, 2)})        # Gandhi Jayanti
    level = 25000.0
    for d in days:
        path = level * np.exp(np.cumsum(rng.normal(0.00003, 0.0008, 375)))
        candles = [{"date": at_ist(d, datetime.min.time()).replace(hour=9, minute=15) + timedelta(minutes=i),
                    "open": px, "high": px * 1.0003, "low": px * 0.9997, "close": px, "volume": 0}
                   for i, px in enumerate(path)]
        store.insert_bars_if_missing(history_rows(SPOT_TOKEN, candles))
        store.insert_bars_if_missing(history_rows(VIX_TOKEN, [{**c, "open": 13, "high": 13, "low": 13, "close": 13.0}
                                                               for c in candles]))
        level = float(path[-1])
    return store, days


def test_expiry_rules_follow_nse(history):
    store, days = history
    m = ProxyMarket(store)
    assert m.weekly_expiries(date(2026, 9, 28)) == [date(2026, 9, 29), date(2026, 10, 6)]       # Tuesdays
    assert m.monthly_expiry(2026, 9) == date(2026, 9, 29)
    assert not m.calendar.is_trading_day(date(2026, 10, 2))                                   # no data that weekday
    old = ProxyMarket.__new__(ProxyMarket)
    old.calendar = CAL
    assert old.weekly_expiries(date(2025, 8, 18))[0] == date(2025, 8, 21)                       # Thursday then
    assert old.monthly_expiry(2025, 8) == date(2025, 8, 28)
    assert decode_option(opt_token(date(2026, 10, 6), 25150.0, "PE")) == (date(2026, 10, 6), 25150.0, "PE")
    assert fut_token(date(2026, 10, 27)) == 900_261027


def test_the_proxy_prices_a_consistent_chain(history):
    store, days = history
    m = ProxyMarket(store)
    day = days[-1]
    rows = m.instruments_on(day)
    assert {r["segment"] for r in rows} == {"INDICES", "NFO-FUT", "NFO-OPT"}
    bars = m.bars_between(at_ist(day, datetime.min.time()), at_ist(day, datetime.max.time()))
    first = min(b["ts"] for b in bars)
    snap = {b["instrument_token"]: b for b in bars if b["ts"] == first}
    spot = snap[SPOT_TOKEN]["close"]
    exp = m.weekly_expiries(day)[0]
    atm = round(spot / 50) * 50
    ce, pe = snap[opt_token(exp, atm, "CE")], snap[opt_token(exp, atm, "PE")]
    assert ce["bid"] < ce["close"] < ce["ask"] and ce["oi"] == proxy.SYNTH_OI
    assert abs((ce["close"] - pe["close"]) - (spot - atm)) < 0.02 * spot                        # rough put-call parity
    fut = snap[fut_token(m.futures(day)[0])]
    assert fut["close"] > spot and fut["volume_day"] == proxy.FUT_VOLUME_PER_MIN


def test_a_proxy_run_goes_through_the_live_engine(history, tmp_path):
    store, days = history
    day = days[-1]
    rep = proxy.run(store, Store(make_engine(f"sqlite:///{tmp_path}/a.db")), day, day, setups=[AlwaysBull()])
    assert rep["kind"] == "proxy" and rep["days"] == 1 and rep["signals"] >= 1
    assert set(rep) >= {"evidence", "evidence_by_setup", "monthly", "stability", "benchmark", "notes"}
    assert any("not a record of trades" in n for n in rep["notes"])
    # The market it replays is a pure function of the history: the same bars every time
    span = (at_ist(day, datetime.min.time()), at_ist(day, datetime.max.time()))
    assert ProxyMarket(store).bars_between(*span) == ProxyMarket(store).bars_between(*span)


def test_cli_refuses_to_mix_with_the_live_database(tmp_path, monkeypatch):
    live = f"sqlite:///{tmp_path}/live.db"
    monkeypatch.setattr(proxy.default_settings, "DATABASE_URL", live)
    assert proxy.main(["run", "--from", "2026-10-01", "--to", "2026-10-02", "--history", live,
                       "--out", f"sqlite:///{tmp_path}/o.db"]) == 2
    assert proxy.main(["run", "--from", "2026-10-01", "--to", "2026-10-02", "--history", f"sqlite:///{tmp_path}/h.db",
                       "--out", live]) == 2


def test_fetch_stores_both_series(tmp_path):
    class Broker:
        def instruments(self, ex):
            return [{"instrument_token": 99926000, "tradingsymbol": "NIFTY 50", "segment": "INDICES"},
                    {"instrument_token": 99926017, "tradingsymbol": "INDIA VIX", "segment": "INDICES"}]

        def historical(self, token, start, end, interval="minute", oi=False):
            t0 = at_ist(date(2026, 10, 16), datetime.min.time()).replace(hour=9, minute=15)
            return [{"date": t0 + timedelta(minutes=i), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}
                    for i in range(3)]

    store = Store(make_engine(f"sqlite:///{tmp_path}/f.db"))
    assert proxy.fetch(store, date(2026, 10, 16), date(2026, 10, 16), broker=Broker()) == {"NIFTY 50": 3, "India VIX": 3}
    assert store.bar_counts_between(at_ist(date(2026, 10, 16), datetime.min.time()),
                                    at_ist(date(2026, 10, 17), datetime.min.time())) == {SPOT_TOKEN: 3, VIX_TOKEN: 3}


def test_ablation_rescales_weights_and_restores_them(tmp_path):
    from options.backtest import ablation
    from options.engine import grading

    original = dict(grading.PILLAR_WEIGHTS)
    seen = []

    def fake_run(history, target, start, end):
        w = dict(grading.PILLAR_WEIGHTS)
        seen.append(w)
        r = 0.3 if w["trend"] else 0.1                     # pretend trend helps
        return {"evidence": {"trades": 40, "mean_r": r, "ci_r": [r - 0.2, r + 0.2]},
                "overall": {"win_rate": 0.5, "total_rupees": 1000.0}}

    out = ablation.ablate(None, date(2026, 1, 1), date(2026, 6, 30), tmp_path, run=fake_run, pillars=["trend", "macro"])
    assert grading.PILLAR_WEIGHTS == original                       # restored
    no_trend = seen[1]
    assert no_trend["trend"] == 0 and sum(no_trend.values()) == pytest.approx(100)
    assert out["results"]["trend"]["delta_r"] == pytest.approx(-0.2)
    assert out["results"]["macro"]["delta_r"] == pytest.approx(0.0)

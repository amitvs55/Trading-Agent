"""Track-record statistics: intervals, trades needed, Sharpe/Sortino, PSR/DSR and calibration."""

from datetime import date, timedelta
from statistics import NormalDist

import pytest

from options.core.schemas import PillarCheck, SignalState
from options.engine import statistics as st
from tests.options.fixtures import ist


def test_t_quantiles_match_tables():
    # Student's t table values
    assert st.t_quantile(0.975, 5) == pytest.approx(2.5706, abs=0.002)
    assert st.t_quantile(0.975, 10) == pytest.approx(2.2281, abs=0.001)
    assert st.t_quantile(0.975, 30) == pytest.approx(2.0423, abs=0.001)
    assert st.t_quantile(0.95, 20) == pytest.approx(1.7247, abs=0.001)
    assert st.t_quantile(0.975, 5000) == pytest.approx(1.95996, abs=1e-4)


def test_interval_and_trades_needed():
    assert st.mean_interval([1.0]) is None
    lo, hi = st.mean_interval([1.0, 2.0, 3.0, 4.0, 5.0])
    half = 2.7764 * (2.5 ** 0.5) / 5 ** 0.5                    # t(0.975, 4) · s / √n
    assert lo == pytest.approx(3 - half, abs=0.01) and hi == pytest.approx(3 + half, abs=0.01)
    # The review's rule of thumb (§6.4): σ ≈ 1.2 R and μ = 0.2 R need about 100 trades
    rs = [0.2 + 1.2 * x for x in (-1, 1)] * 10                 # mean 0.2, sd ≈ 1.23 over 20 trades
    more = st.trades_needed(rs)
    assert 80 <= 20 + more <= 110
    assert st.trades_needed([-0.5, 0.1, -0.2]) is None          # no edge: no number of trades proves one


def test_psr_and_dsr_discount_luck():
    good = [0.4, -0.3, 0.9, 0.2, -0.5, 1.1, 0.3, -0.2, 0.8, 0.1] * 5
    psr = st.probabilistic_sharpe(good)
    assert 0.5 < psr <= 1.0
    lonely = st.deflated_sharpe(good, [0.25])                   # one setup tried: DSR equals PSR
    assert lonely == pytest.approx(psr)
    crowded = st.deflated_sharpe(good, [0.25, -0.1, 0.05, 0.3, -0.2, 0.15, 0.0, 0.1])
    assert crowded < psr                                       # best of many tries is worth less


def sig(base, i, r, pnl, score=80, statuses=None, day=None):
    checks = [PillarCheck(pillar=p, status=s, detail="") for p, s in (statuses or {"trend": "pass"}).items()]
    closed = ist(2026, 11, 2, 11, 0) + timedelta(days=day if day is not None else i)
    return base.model_copy(update={"signal_id": f"NF-x-{i:03d}", "state": SignalState.CLOSED, "r_multiple": r,
                                   "pnl_rupees": pnl, "score": score, "checks": checks, "closed_at": closed,
                                   "created_at": closed - timedelta(hours=1)})


@pytest.fixture
def base_signal(tmp_path):
    from options.config import OptionsSettings
    from options.engine.engine import SignalEngine
    from options.storage import Store, make_engine
    from tests.options.fixtures import RecordingNotifier
    from tests.options.market import build_market
    from tests.options.test_setups_engine import AlwaysBull

    ctx = build_market(trend=1)
    store = Store(make_engine(f"sqlite:///{tmp_path}/s.db"))
    eng = SignalEngine({"NIFTY": ctx.ref}, ctx.state, store, RecordingNotifier(), OptionsSettings(), ctx.calendar,
                       vix_token=ctx.vix_token, constituents={"NIFTY": ctx.constituents}, vix_history=ctx.vix_history,
                       events=[], now_fn=lambda: ctx.now, setups=[AlwaysBull()])
    eng.evaluate(ctx.now)
    return eng.open[0]


def test_record_and_account_stats(base_signal):
    sigs = [sig(base_signal, i, r, r * 1000) for i, r in enumerate([1.5, -1, 2, -1, 0.5, -1, 1.8, -0.4] * 3)]
    rec = st.record_stats(sigs)
    assert rec["trades"] == 24 and rec["enough"] and rec["ci_r"][0] < rec["mean_r"] < rec["ci_r"][1]
    assert rec["t_stat"] == pytest.approx(rec["mean_r"] / (rec["sd_r"] / 24 ** 0.5))
    days = [date(2026, 11, 2) + timedelta(days=i) for i in range(30)]
    acct = st.account_stats(sigs, 100_000, days)
    assert acct["days"] == 30 and acct["sharpe"] is not None and acct["sortino"] is not None
    assert acct["return_pct"] == pytest.approx(sum(s.pnl_rupees for s in sigs) / 1000)


def test_calibration_by_score_and_pillar(base_signal):
    sigs = ([sig(base_signal, i, 1.0, 1000, score=92, statuses={"trend": "pass"}) for i in range(6)]
            + [sig(base_signal, 10 + i, -1.0, -1000, score=65, statuses={"trend": "warn"}) for i in range(6)])
    cal = st.calibration(sigs)
    bands = {b["band"]: b for b in cal["by_score"]}
    assert bands["90–100"]["win_rate"] == 1.0 and bands["60–70"]["avg_r"] == -1.0
    assert cal["score_monotonic"] is True
    assert cal["by_pillar"]["trend"]["lift_r"] == pytest.approx(2.0)


def test_performance_endpoint_includes_statistics(tmp_path, base_signal):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import options as routes
    from options.config import OptionsSettings
    from options.core.calendar import NseCalendar
    from options.storage import Store, make_engine

    store = Store(make_engine(f"sqlite:///{tmp_path}/p.db"))
    for i, r in enumerate([1.2, -1, 0.8, -0.6, 2.0]):
        store.save_signal(sig(base_signal, i, r, r * 900), ist(2026, 11, 10, 15, 0))
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_store] = lambda: store
    app.dependency_overrides[routes.get_cfg] = lambda: OptionsSettings(_env_file=None)
    app.dependency_overrides[routes.get_calendar] = NseCalendar
    app.dependency_overrides[routes.current_user] = lambda: {"id": 1, "username": "a", "role": "admin", "token": "t"}
    routes._stats_cache.clear()
    body = TestClient(app).get("/api/options/performance").json()["statistics"]
    assert body["overall"]["trades"] == 5 and not body["overall"]["enough"]
    assert set(body["by_setup"]) == {"S1_TREND_PULLBACK"} and body["account"]["days"] > 0
    assert body["benchmark"] is None                           # no recorded NIFTY bars in this database

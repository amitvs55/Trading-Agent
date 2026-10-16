"""Live clock data, agent health, confidence and the paper account."""

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deps
from api.routes import agents as agents_routes, options as options_routes, paper as paper_routes
from options.admin.repo import AdminRepo
from options.agents import breadth, health, selftest, technical
from options.config import OptionsSettings
from options.core.schemas import Grade, PillarCheck, SignalState
from options.engine import confidence
from options.engine.engine import SignalEngine
from options.engine.snapshot import SnapshotError, take
from options.paper.ledger import PaperSettings, build
from options.storage import Store, make_engine
from tests.options.fixtures import RecordingNotifier, ist
from tests.options.market import build_market
from tests.options.test_engine_parts import make_signal
from tests.options.test_setups_engine import AlwaysBull, engine  # noqa: F401  (pytest fixture)
from utils import agent_health


def _boom(*a, **k):
    raise RuntimeError("feed parser broke")


# ── Agent health ─────────────────────────────────────────────────────────────

def test_a_failing_agent_degrades_its_pillar_instead_of_stopping_the_snapshot(monkeypatch):
    monkeypatch.setattr(breadth, "analyse", _boom)
    snap = take(build_market())
    assert snap.failed == ["breadth"] and snap.breadth.status == "na" and "feed parser broke" in snap.breadth.detail
    by_agent = {r.agent: r for r in snap.runs}
    assert set(by_agent) == set(health.AGENTS) and by_agent["technical"].status == "ok"
    assert all(r.ms >= 0 for r in snap.runs)


def test_without_the_technical_agent_there_is_nothing_to_evaluate(monkeypatch):
    monkeypatch.setattr(technical, "analyse", _boom)
    with pytest.raises(SnapshotError) as e:
        take(build_market())
    assert e.value.runs[0].agent == "technical" and e.value.runs[0].status == "error"


def test_tracker_alerts_after_two_failures_and_on_recovery():
    tr, t = health.AgentTracker(), ist(2026, 10, 19, 9, 20)
    bad, good = [health.AgentRun("macro", "error", 1, error="timeout")], [health.AgentRun("macro", "ok", 1, "fine")]
    assert tr.update(bad, t) == []
    [alert] = tr.update(bad, t)
    assert "Global markets agent failing" in alert and "No new signals" in alert
    assert tr.update(bad, t) == []                                       # told once, not every 5 minutes
    [back] = tr.update(good, t)
    assert "recovered" in back and tr.agents["macro"].failing_in_row == 0


def test_engine_pauses_new_signals_while_an_agent_fails(engine, monkeypatch):
    eng, ctx, store, notifier, _ = engine
    monkeypatch.setattr(breadth, "analyse", _boom)
    eng.evaluate(ctx.now)
    eng.evaluate(ctx.now + timedelta(minutes=5))
    assert store.signals_since(ctx.now - timedelta(hours=1)) == []         # AlwaysBull would have fired
    status = store.load_agent_status("NIFTY")
    assert status["signals_paused"] and status["failed"] == ["breadth"]
    assert status["agents"]["breadth"]["errors"] == 2 and status["agents"]["technical"]["status"] == "ok"
    assert any("Breadth agent failing" in m for m in notifier.texts())
    monkeypatch.undo()
    eng.evaluate(ctx.now)                                                  # fresh data, agent fixed
    assert len(store.signals_since(ctx.now - timedelta(hours=1))) == 1     # recovered: trading resumes
    assert not store.load_agent_status("NIFTY")["signals_paused"]


def test_selftest_runs_every_agent_on_synthetic_data_before_anything_is_recorded(tmp_path):
    store = Store(make_engine(f"sqlite:///{tmp_path}/s.db"))
    result = selftest.run(store, OptionsSettings(_env_file=None), ist(2026, 10, 17, 11, 0))
    assert result["source"] == "synthetic" and result["passed"] and result["errors"] == 0
    assert set(result["agents"]) == set(health.AGENTS)
    assert store.load_agent_status("selftest")["ran_at"].startswith("2026-10-17T11:00")


def test_research_agents_are_recorded_once_per_run_and_errors_kept():
    seen = []
    agent_health.set_sink(seen.append)
    try:
        inner = agent_health.tracked("trader", lambda: "ok")
        outer = agent_health.tracked("trader", lambda: inner())
        assert outer() == "ok"
        assert agent_health.snapshot()["trader"]["status"] == "ok" and len(seen) == 1   # nested call not counted twice
        with pytest.raises(ValueError):
            agent_health.tracked("news_analyst", lambda: (_ for _ in ()).throw(ValueError("bad JSON")))()
        st = agent_health.snapshot()["news_analyst"]
        assert st["status"] == "error" and "bad JSON" in st["error"] and st["errors"] >= 1
    finally:
        agent_health.set_sink(None)


def test_every_research_agent_class_is_tracked():
    import agents.bear_researcher, agents.execution, agents.fundamentals, agents.market_data  # noqa: E401
    for cls in (agents.bear_researcher.BearResearcherAgent, agents.execution.ExecutionEngine,
                agents.fundamentals.FundamentalsAgent, agents.market_data.MarketDataAgent):
        assert getattr(cls.run, "__agent_tracked__", False), cls


# ── Confidence ───────────────────────────────────────────────────────────────

def _checks(**status):
    names = ["trend", "futures_flow", "option_chain", "trigger", "levels", "volatility", "breadth", "momentum",
             "macro", "timing", "events"]
    return [PillarCheck(pillar=n, status=status.get(n, "pass"), detail=f"{n} detail") for n in names]


def test_confidence_breakdown_adds_up_to_the_score():
    sig = make_signal(checks=_checks(breadth="fail", option_chain="warn"), score=82.5)
    conf = confidence.breakdown(sig)
    assert sum(p["points"] for p in conf["parts"]) == pytest.approx(82.5)
    assert conf["level"] == "High" and conf["strengths"][:2] == ["Trend", "Futures flow"]
    assert [w["label"] for w in conf["weaknesses"][:2]] == ["Breadth", "Option chain"]
    assert conf["weaknesses"][0]["lost"] == 10


def test_band_is_only_trusted_with_enough_trades():
    closed = [make_signal(signal_id=f"NF-{i}", state=SignalState.CLOSED, pnl_rupees=500 if i % 2 else -300,
                          r_multiple=0.5, fill_price=143, closed_at=ist(2026, 10, 16, 11, 0)) for i in range(25)]
    bands = confidence.band_stats(closed)
    assert bands["A"]["trades"] == 25 and bands["A"]["enough"] and bands["A"]["win_rate"] == pytest.approx(12 / 25)
    few = confidence.band_stats(closed[:5])
    assert not few["A"]["enough"]
    line = confidence.telegram_line(make_signal(checks=_checks(), score=100), bands["A"])
    assert "Confidence 100/100" in line and "48% won over 25" in line


# ── Paper account ────────────────────────────────────────────────────────────

START = ist(2026, 10, 19, 9, 0)


def closed_signal(i, fill, exit_price, minute, grade=Grade.A, **kw):
    s = make_signal(signal_id=f"NF-261019-{i:03d}", created_at=START + timedelta(minutes=minute), grade=grade, **kw)
    s.state, s.fill_price, s.filled_at, s.initial_stop = SignalState.CLOSED, fill, START + timedelta(minutes=minute + 1), 104
    s.exit_price, s.closed_at, s.exit_reason = exit_price, START + timedelta(minutes=minute + 30), "T2_HIT"
    from options.engine.lifecycle import close
    s.state = SignalState.ACTIVE
    close(s, exit_price, s.closed_at, "T2_HIT")                          # the engine's own P&L for comparison
    return s


def test_paper_account_follows_signals_and_matches_their_pnl():
    win, loss = closed_signal(1, 143, 200, 30), closed_signal(2, 140, 110, 90)
    before = closed_signal(3, 140, 200, -120)                            # before the account started
    acct = build([win, loss, before], PaperSettings(100_000, START), 3, 10, {}, START + timedelta(hours=5))
    assert acct["stats"]["trades"] == 2 and acct["stats"]["wins"] == 1
    assert acct["realised"] == pytest.approx(win.pnl_rupees + loss.pnl_rupees, abs=0.01)
    assert acct["balance"] == pytest.approx(100_000 + win.pnl_rupees + loss.pnl_rupees, abs=0.01)
    assert [p["balance"] for p in acct["curve"]][0] == 100_000 and len(acct["curve"]) == 3


def test_paper_account_respects_its_daily_stop_and_cash():
    loss = closed_signal(1, 143, 104, 30)                                # about ₹2.6k lost
    later = closed_signal(2, 140, 200, 120)
    acct = build([loss, later], PaperSettings(100_000, START), 3, 2, {}, START + timedelta(hours=5))   # 2% stop
    assert acct["stats"]["trades"] == 1 and "daily loss stop" in acct["skipped"][0]["reason"]
    poor = build([later], PaperSettings(5_000, START), 3, 10, {}, START + timedelta(hours=5))
    assert poor["stats"]["trades"] == 0 and "not enough paper cash" in poor["skipped"][0]["reason"]


def test_paper_open_position_is_marked_to_the_live_bid_and_grade_filter_applies():
    s = make_signal(signal_id="NF-261019-009", created_at=START + timedelta(minutes=20))
    s.state, s.fill_price, s.filled_at, s.initial_stop = SignalState.ACTIVE, 143, START + timedelta(minutes=21), 104
    b = make_signal(signal_id="NF-261019-010", created_at=START + timedelta(minutes=25), grade=Grade.B)
    b.state, b.fill_price, b.filled_at, b.initial_stop = SignalState.ACTIVE, 150, START + timedelta(minutes=26), 120
    acct = build([s, b], PaperSettings(100_000, START, "A"), 3, 10, {s.signal_id: 160.0, b.signal_id: 151.0},
                 START + timedelta(hours=1))
    [pos] = acct["open"]
    assert pos["signal_id"] == s.signal_id and pos["unrealised"] == pytest.approx((160 - 143) * 65)
    assert acct["equity"] == pytest.approx(100_000 + (160 - 143) * 65)
    assert acct["cash"] == pytest.approx(100_000 - 143 * 65)


# ── API ──────────────────────────────────────────────────────────────────────

ADMIN = {"id": 1, "username": "admin", "role": "admin", "token": "t"}


@pytest.fixture
def api(tmp_path):
    engine_ = make_engine(f"sqlite:///{tmp_path}/a.db")
    store, repo = Store(engine_), AdminRepo(engine_, secret_key="k")
    app = FastAPI()
    for r in (options_routes.router, agents_routes.router, paper_routes.router):
        app.include_router(r)
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_repo] = lambda: repo
    app.dependency_overrides[deps.get_cfg] = lambda: OptionsSettings(_env_file=None)
    app.dependency_overrides[deps.current_user] = lambda: ADMIN
    app.dependency_overrides[deps.require_admin] = lambda: ADMIN
    return TestClient(app), store, repo


def test_time_status_and_signal_confidence_endpoints(api):
    client, store, _ = api
    t = client.get("/api/time").json()
    assert t["epoch_ms"] > 1_700_000_000_000 and "+05:30" in t["ist"]
    status = client.get("/api/options/status").json()
    assert status["market_opens_at"].endswith("09:15:00+05:30") and status["market_closes_at"].endswith("15:30:00+05:30")
    sig = make_signal(checks=_checks(), score=100, created_at=options_routes.now_ist())
    store.save_signal(sig, sig.created_at)
    [row] = client.get("/api/options/signals").json()["signals"]
    assert row["confidence"]["score"] == 100 and row["confidence"]["band"]["enough"] is False
    detail = client.get(f"/api/options/signals/{sig.signal_id}").json()
    assert len(detail["signal"]["confidence"]["parts"]) == 10


def test_agents_endpoint_and_selftest(api):
    client, store, _ = api
    body = client.get("/api/agents").json()
    assert {a["id"] for a in body["catalog"]} == set(health.AGENTS) and body["signal"] == {}
    assert len(body["research"]) == 13 and body["selftest"] is None
    run = client.post("/api/admin/agents/selftest").json()
    assert run["passed"] and run["source"] == "synthetic"
    assert client.get("/api/agents").json()["selftest"]["passed"]


def test_paper_endpoint_creates_the_account_and_resets_it(api):
    client, store, repo = api
    first = client.get("/api/paper").json()
    assert first["balance"] == 100_000 and first["settings"]["follow"] == "all" and first["stats"]["trades"] == 0
    assert client.put("/api/admin/paper", json={"follow": "B+"}).status_code == 422
    done = client.put("/api/admin/paper", json={"reset": True, "starting_balance": 200_000, "follow": "A"}).json()
    assert done["settings"]["starting_balance"] == 200_000
    again = client.get("/api/paper").json()
    assert again["balance"] == 200_000 and again["settings"]["follow_label"] == "Grade A only"

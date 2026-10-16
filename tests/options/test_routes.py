import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import options as routes
from options.core.calendar import now_ist
from options.storage import Store, make_engine
from tests.options.fixtures import FakeBroker, RecordingNotifier


@pytest.fixture
def ctx(tmp_path):
    app = FastAPI()
    app.include_router(routes.router)
    store, notifier, broker = Store(make_engine(f"sqlite:///{tmp_path}/o.db")), RecordingNotifier(), FakeBroker()
    app.dependency_overrides[routes.get_store] = lambda: store
    app.dependency_overrides[routes.get_notifier] = lambda: notifier
    app.dependency_overrides[routes.get_broker] = lambda: broker
    app.dependency_overrides[routes.get_allowed_user] = lambda: "AB1234"
    app.dependency_overrides[routes.get_dashboard_token] = lambda: ""       # auth off unless a test sets it
    return TestClient(app), store, notifier, app


def test_login_redirects_to_zerodha(ctx):
    client, *_ = ctx
    r = client.get("/kite/login", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == FakeBroker.LOGIN_URL


def test_callback_saves_todays_token_and_notifies(ctx):
    client, store, notifier, _ = ctx
    r = client.get("/kite/callback", params={"request_token": "rt", "status": "success", "action": "login"})
    assert r.status_code == 200 and "Kite connected" in r.text
    assert store.load_access_token(now_ist().date()) == "tok-123"
    assert "tok-123" not in r.text                                       # never echo the token
    assert "Kite connected" in notifier.texts()[0]


@pytest.mark.parametrize("params,code", [
    ({"status": "cancelled"}, 400),
    ({"request_token": "bad", "status": "success"}, 502),
])
def test_failed_logins_store_nothing(ctx, params, code):
    client, store, notifier, _ = ctx
    assert client.get("/kite/callback", params=params).status_code == code
    assert store.load_access_token(now_ist().date()) is None and notifier.messages == []


def test_callback_rejects_other_zerodha_accounts(ctx):
    client, store, _, app = ctx
    app.dependency_overrides[routes.get_allowed_user] = lambda: "ZZ9999"
    r = client.get("/kite/callback", params={"request_token": "rt", "status": "success"})
    assert r.status_code == 403 and store.load_access_token(now_ist().date()) is None


def test_unconfigured_kite_returns_503(ctx, monkeypatch):
    client, _, _, app = ctx
    del app.dependency_overrides[routes.get_broker]
    monkeypatch.setattr(routes.settings, "KITE_API_KEY", "")
    assert client.get("/kite/login", follow_redirects=False).status_code == 503


def test_status(ctx):
    client, *_ = ctx
    body = client.get("/api/options/status").json()
    assert {"trading_day", "session_phase", "kite_connected_today", "bars_today", "risk"} <= body.keys()
    assert body["data_provider"] in ("angel", "kite") and body["data_provider_name"] in ("Angel One", "Kite")
    assert {"data_configured", "data_connected_today", "data_needs_manual_login"} <= body.keys()
    assert body["risk"]["risk_per_trade_pct"] == 3.0 and body["risk"]["daily_loss_stop_pct"] == 10.0


def test_dashboard_endpoints_require_the_token_when_set(ctx):
    client, _, _, app = ctx
    app.dependency_overrides[routes.get_dashboard_token] = lambda: "s3cret"
    assert client.get("/api/options/board").status_code == 401
    assert client.get("/api/options/board", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/api/options/board", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200 and ok.json()["boards"] == {}
    assert client.get("/kite/login", follow_redirects=False).status_code == 307     # login flow stays public


def test_signals_detail_performance_and_evaluations(ctx):
    from tests.options.test_engine_parts import make_signal
    from options.core.schemas import SignalState

    client, store, _, app = ctx
    app.dependency_overrides[routes.get_dashboard_token] = lambda: ""
    now = now_ist()
    sig = make_signal(created_at=now)
    sig.state, sig.pnl_rupees, sig.r_multiple, sig.closed_at = SignalState.CLOSED, 1500.0, 0.8, now
    store.save_signal(sig, now)
    store.signal_event(sig.signal_id, "CREATED", 144, "BUY_CE grade A", now)
    store.log_evaluation(now, "NIFTY", "S2_ORB", 1, None, 55.0, "NO_TRADE", ["outside the entry window"])

    listed = client.get("/api/options/signals").json()
    assert [s["signal_id"] for s in listed["signals"]] == [sig.signal_id]
    assert listed["setup_labels"]["S1_TREND_PULLBACK"] == "S1 Trend pullback"
    detail = client.get(f"/api/options/signals/{sig.signal_id}").json()
    assert detail["signal"]["pnl_rupees"] == 1500.0 and detail["events"][0]["kind"] == "CREATED"
    assert client.get("/api/options/signals/NF-000000-999").status_code == 404
    perf = client.get("/api/options/performance").json()
    assert perf["overall"]["trades"] == 1 and perf["equity"][0]["equity"] == 1500.0
    assert perf["by_setup"]["S1_TREND_PULLBACK"]["wins"] == 1
    evs = client.get("/api/options/evaluations").json()["evaluations"]
    assert evs[0]["outcome"] == "NO_TRADE" and "entry window" in evs[0]["reasons"]

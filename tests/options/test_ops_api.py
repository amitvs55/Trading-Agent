"""Admin operations API (controls, alerts, audit, calendar, recorder events) and the watchdog."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api import deps
from api.main import app
from options.admin import security, watchdog
from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.core.calendar import NseCalendar
from options.engine import controls
from options.storage import Store, make_engine
from tests.options.fixtures import Clock, ist

PW = "correct horse battery"


@pytest.fixture
def ops(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "PBKDF2_ITERATIONS", 1_000)
    engine = make_engine(f"sqlite:///{tmp_path}/ops.db")
    repo, store = AdminRepo(engine, secret_key="k"), Store(engine)
    app.dependency_overrides[deps.get_repo] = lambda: repo
    app.dependency_overrides[deps.get_store] = lambda: store
    app.dependency_overrides[deps.get_cfg] = lambda: OptionsSettings(_env_file=None)
    app.dependency_overrides[deps.get_calendar] = NseCalendar
    monkeypatch.setattr(deps, "base_settings", lambda: OptionsSettings(_env_file=None))
    token = repo.create_session(repo.create_user("amit", PW, role="admin", full_name="Amit Shinde"))
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, repo, store
    app.dependency_overrides.clear()


def test_pause_resume_and_exit_all_are_recorded(ops, monkeypatch):
    api, h, repo, store = ops
    sent = []
    monkeypatch.setattr("api.routes.admin._alert", lambda cfg, text: sent.append(text))
    r = api.put("/api/admin/controls/pause", headers=h, json={"paused": True, "reason": "RBI surprise"})
    assert r.status_code == 200 and r.json()["paused"] is True and r.json()["paused_by"] == "amit"
    assert "New signals paused" in sent[-1] and "RBI surprise" in sent[-1]
    status = api.get("/api/options/status", headers=h).json()
    assert status["signals_paused"]["by"] == "amit" and status["signals_paused"]["reason"] == "RBI surprise"

    api.put("/api/admin/controls/pause", headers=h, json={"paused": True})       # no change: no second alert
    assert len(sent) == 1
    api.put("/api/admin/controls/pause", headers=h, json={"paused": False})
    assert "resumed" in sent[-1] and api.get("/api/options/status", headers=h).json()["signals_paused"] is None

    r = api.post("/api/admin/controls/exit-all", headers=h)
    assert r.json()["exit_all_pending"] and controls.pending_exit_all(store)
    actions = [e["action"] for e in api.get("/api/admin/audit", headers=h).json()["entries"]]
    assert actions[:3] == ["exit_all", "signals_resumed", "signals_paused"]


def test_trading_rule_changes_are_audited(ops):
    api, h, _, _ = ops
    r = api.put("/api/admin/trading", headers=h, json={"risk_per_trade_pct": 2.0, "bars_retention_days": 365})
    assert r.status_code == 200 and r.json()["trading"]["bars_retention_days"] == 365
    [entry] = [e for e in api.get("/api/admin/audit", headers=h).json()["entries"] if e["action"] == "trading_rules"]
    assert "risk_per_trade_pct: 3.0 -> 2.0" in entry["detail"] and "bars_retention_days: 730 -> 365" in entry["detail"]
    assert api.put("/api/admin/trading", headers=h, json={"bars_retention_days": 10}).status_code == 422


def test_alerts_log_shows_delivery_status(ops):
    api, h, _, store = ops
    now = ist(2026, 10, 19, 10, 0)
    a = store.outbox_add("d1", "card", None, now)
    store.outbox_update(a, status="sent", channel="telegram", sent_at=now)
    b = store.outbox_add("d2", "lost", None, now)
    store.outbox_update(b, status="expired", last_error="not delivered within 15 min")
    body = api.get("/api/admin/alerts", headers=h).json()
    assert [x["status"] for x in body["alerts"]] == ["expired", "sent"] and "digest" not in body["alerts"][0]


def test_calendar_endpoints(ops):
    api, h, _, _ = ops
    r = api.post("/api/admin/calendar/holidays", headers=h, json={"date": "2027-01-26", "name": "Republic Day"})
    assert r.status_code == 200 and any(x["date"] == "2027-01-26" and x["source"] == "added" for x in r.json()["holidays"])
    assert api.post("/api/admin/calendar/holidays", headers=h,
                    json={"date": "2027-01-30", "name": "Sat"}).status_code == 422
    assert api.put("/api/admin/calendar/years/2027", headers=h, json={"complete": True}).json()["years"][-1]["complete"]
    ev = api.post("/api/admin/calendar/events", headers=h,
                  json={"name": "RBI MPC decision", "at": "2027-04-07T10:00:00+05:30", "impact": "high"}).json()
    added = [e for e in ev["events"] if e["source"] == "added"][0]
    assert api.delete(f"/api/admin/calendar/events/{added['id']}", headers=h).status_code == 200
    assert api.delete("/api/admin/calendar/events/nope", headers=h).status_code == 404
    assert api.delete("/api/admin/calendar/holidays/2026-10-20", headers=h).status_code == 404   # built-in
    assert api.delete("/api/admin/calendar/holidays/2027-01-26", headers=h).status_code == 200


def test_recorder_events_endpoint(ops):
    api, h, _, store = ops
    from options.core.calendar import now_ist
    store.log_event("ws_close", "1006 abnormal closure", now_ist() - timedelta(hours=1))
    [e] = api.get("/api/admin/recorder/events", headers=h).json()["events"]
    assert e["kind"] == "ws_close" and e["ts"].endswith("+05:30")


# ── Watchdog ─────────────────────────────────────────────────────────────────

@pytest.fixture
def dog(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/w.db")
    repo, store = AdminRepo(engine, secret_key="k"), Store(engine)
    clock, sent = Clock(ist(2026, 10, 19, 10, 0)), []
    wd = watchdog.Watchdog(repo, store, sent.append, NseCalendar, now_fn=clock)
    return wd, repo, store, clock, sent


def beat(repo, clock, state="running"):
    repo.set_meta_json("recorder_status", {"ts": clock().isoformat(), "state": state})


def test_watchdog_alerts_once_when_the_recorder_goes_quiet_and_on_recovery(dog):
    wd, repo, store, clock, sent = dog
    beat(repo, clock)
    store.write_bars([{"instrument_token": 1, "ts": clock() - timedelta(minutes=1), "open": 1, "high": 1, "low": 1,
                       "close": 1, "ticks": 1}])
    assert wd.check() == []
    clock.sleep(240)                                   # no heartbeat for 4 minutes
    [msg] = wd.check()
    assert "Recorder service not responding" in msg
    clock.sleep(60)
    assert wd.check() == []                            # not repeated
    beat(repo, clock)
    store.write_bars([{"instrument_token": 1, "ts": clock() - timedelta(seconds=30), "open": 1, "high": 1, "low": 1,
                       "close": 1, "ticks": 1}])
    assert wd.check() == ["✅ Recorder service is responding again."]


def test_watchdog_session_not_running_needs_a_grace_period(dog):
    wd, repo, _, clock, sent = dog
    beat(repo, clock, "restarting")
    assert wd.check() == []                            # a crash restart is under way
    clock.sleep(400)
    beat(repo, clock, "restarting")
    [msg] = wd.check()
    assert "Today's session isn't running" in msg


def test_watchdog_flags_a_hung_session_and_is_quiet_on_holidays(dog):
    wd, repo, store, clock, sent = dog
    beat(repo, clock)
    store.write_bars([{"instrument_token": 1, "ts": clock() - timedelta(minutes=10), "open": 1, "high": 1, "low": 1,
                       "close": 1, "ticks": 1}])
    [msg] = wd.check()
    assert "No market data saved" in msg and "09:50" in msg
    code, body = watchdog.status(repo, store, clock(), NseCalendar())
    assert code == 503 and body["problems"] == ["data"]
    holiday = ist(2026, 10, 20, 11, 0)                 # Dussehra
    assert watchdog.status(repo, store, holiday, NseCalendar())[0] == 200


def test_public_recorder_health_endpoint(ops):
    api, _, repo, _ = ops
    r = api.get("/health/recorder")
    assert r.status_code in (200, 503) and set(r.json()) == {"status", "problems", "recorder_state", "checked_at"}

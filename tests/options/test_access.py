"""What a viewer may call: the signal pages only. Everything that costs money (the research
pipeline) or changes settings needs an admin, whatever the UI shows."""

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-used")      # config.settings needs one to import

import pytest
from fastapi.testclient import TestClient

from api import deps
from api.main import app
from options.admin import security
from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.core.calendar import NseCalendar
from options.storage import Store, make_engine

PW = "correct horse battery"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "PBKDF2_ITERATIONS", 1_000)
    engine = make_engine(f"sqlite:///{tmp_path}/acl.db")
    repo = AdminRepo(engine, secret_key="k")
    app.dependency_overrides[deps.get_repo] = lambda: repo
    app.dependency_overrides[deps.get_store] = lambda: Store(engine)
    app.dependency_overrides[deps.get_cfg] = lambda: OptionsSettings(_env_file=None)
    app.dependency_overrides[deps.get_calendar] = NseCalendar
    admin = repo.create_session(repo.create_user("admin", PW, role="admin"))
    viewer = repo.create_session(repo.create_user("guest", PW, role="viewer", full_name="Guest"))
    yield TestClient(app), {"Authorization": f"Bearer {admin}"}, {"Authorization": f"Bearer {viewer}"}
    app.dependency_overrides.clear()


ADMIN_ONLY = [
    ("POST", "/api/analyze", {"ticker": "TCS", "exchange": "NSE"}),
    ("GET", "/api/history", None),
    ("GET", "/api/pricehistory/TCS.NS", None),
    ("GET", "/api/usage", None),
    ("GET", "/api/agents", None),
    ("POST", "/api/admin/agents/selftest", None),
    ("GET", "/api/admin/connectors", None),
    ("GET", "/api/admin/users", None),
    ("PUT", "/api/admin/paper", {"reset": True}),
    ("GET", "/api/admin/controls", None),
    ("PUT", "/api/admin/controls/pause", {"paused": True}),
    ("POST", "/api/admin/controls/exit-all", None),
    ("GET", "/api/admin/alerts", None),
    ("GET", "/api/admin/audit", None),
    ("GET", "/api/admin/recorder/events", None),
    ("GET", "/api/admin/metrics", None),
    ("GET", "/api/admin/calendar", None),
    ("POST", "/api/admin/calendar/holidays", {"date": "2027-01-26", "name": "Republic Day"}),
    ("POST", "/api/admin/calendar/events", {"name": "RBI", "at": "2027-04-07T10:00:00+05:30"}),
]
VIEWER_OK = ["/api/options/status", "/api/options/signals", "/api/options/performance", "/api/paper", "/api/auth/me"]


@pytest.mark.parametrize("method,path,body", ADMIN_ONLY)
def test_viewers_are_refused_everything_admin_only(client, method, path, body):
    api, _, viewer = client
    r = api.request(method, path, headers=viewer, json=body)
    assert r.status_code == 403, f"{method} {path} gave {r.status_code}"


@pytest.mark.parametrize("path", VIEWER_OK)
def test_viewers_and_admins_both_see_the_signal_pages(client, path):
    api, admin, viewer = client
    assert api.get(path, headers=viewer).status_code == 200
    assert api.get(path, headers=admin).status_code == 200


def test_admins_still_reach_the_admin_pages(client):
    api, admin, _ = client
    assert api.get("/api/agents", headers=admin).status_code == 200
    assert api.get("/api/admin/users", headers=admin).status_code == 200


def test_cors_trusts_only_the_ui_and_responses_carry_security_headers(client):
    api, admin, _ = client
    pre = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
    evil = api.options("/api/options/status", headers={"Origin": "https://someone-else.up.railway.app", **pre})
    assert "access-control-allow-origin" not in evil.headers          # *.railway.app is no longer trusted
    ours = api.options("/api/options/status", headers={"Origin": "http://localhost:3001", **pre})
    assert ours.headers["access-control-allow-origin"] == "http://localhost:3001"
    assert "access-control-allow-credentials" not in ours.headers
    r = api.get("/api/options/status", headers=admin)
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"

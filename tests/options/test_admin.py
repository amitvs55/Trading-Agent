from datetime import timedelta
from types import SimpleNamespace

import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from api import deps
from api.routes import admin as admin_routes
from options.admin import connectors, health, security
from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.storage import Store, app_settings, make_engine
from tests.options.fixtures import ist


@pytest.fixture(autouse=True)
def fast_hashing(monkeypatch):
    monkeypatch.setattr(security, "PBKDF2_ITERATIONS", 1_000)


@pytest.fixture
def repo(tmp_path):
    return AdminRepo(make_engine(f"sqlite:///{tmp_path}/a.db"), secret_key="test-key")


# ── Security primitives ──────────────────────────────────────────────────────

def test_password_hashing_and_rules():
    h = security.hash_password("correct horse battery")
    assert h.startswith("pbkdf2_sha256$") and "correct" not in h
    assert security.verify_password("correct horse battery", h)
    assert not security.verify_password("wrong", h) and not security.verify_password("x", "garbage")
    assert security.password_problem("short") and security.password_problem("adminadmin1", "adminadmin1")
    assert security.password_problem("a long enough one") is None


def test_cipher_round_trip_and_wrong_key():
    c = security.Cipher("k1")
    token = c.encrypt("s3cret")
    assert token != "s3cret" and c.decrypt(token) == "s3cret"
    with pytest.raises(ValueError):
        security.Cipher("k2").decrypt(token)
    assert security.normalize_code("abcde-fghij") == "ABCDEFGHIJ"


# ── Repository ───────────────────────────────────────────────────────────────

def test_users_sessions_and_setup_code(repo):
    code = repo.ensure_setup_code()
    assert code and repo.check_setup_code(code.lower()) and not repo.check_setup_code("WRONG-CODE0")
    uid = repo.create_user("Amit", "correct horse battery")
    assert repo.has_admin() and repo.ensure_setup_code() is None
    assert repo.authenticate("amit", "correct horse battery")["username"] == "amit"
    assert repo.authenticate("amit", "nope") is None and repo.authenticate("ghost", "x") is None

    token = repo.create_session(uid)
    assert repo.resolve_session(token)["id"] == uid and repo.resolve_session("forged") is None
    other = repo.create_session(uid)
    repo.revoke_user_sessions(uid, keep_token=token)
    assert repo.resolve_session(other) is None and repo.resolve_session(token)
    repo.revoke_session(token)
    assert repo.resolve_session(token) is None


def test_sessions_expire(tmp_path):
    clock = {"now": ist(2026, 10, 16, 10, 0)}
    r = AdminRepo(make_engine(f"sqlite:///{tmp_path}/e.db"), secret_key="k", now_fn=lambda: clock["now"])
    token = r.create_session(r.create_user("amit", "correct horse battery"))
    clock["now"] += timedelta(days=15)
    assert r.resolve_session(token) is None


def test_secrets_are_encrypted_at_rest(repo):
    repo.set_setting("ANGEL_PIN", "4321", secret=True, by="amit")
    repo.set_setting("ANGEL_CLIENT_CODE", "A123", secret=False, by="amit")
    with repo.engine.connect() as conn:
        raw = dict(conn.execute(select(app_settings.c.key, app_settings.c.value)).all())
    assert "4321" not in raw["ANGEL_PIN"] and raw["ANGEL_CLIENT_CODE"] == '"A123"'
    assert repo.setting_values() == {"ANGEL_PIN": "4321", "ANGEL_CLIENT_CODE": "A123"}


def test_generated_key_is_reused_across_instances(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/g.db")
    AdminRepo(engine, secret_key="").set_setting("TELEGRAM_BOT_TOKEN", "123:abc", secret=True, by=None)
    assert AdminRepo(engine, secret_key="").setting_values()["TELEGRAM_BOT_TOKEN"] == "123:abc"


def test_setting_secret_key_later_re_encrypts_saved_secrets(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/m.db")
    AdminRepo(engine, secret_key="").set_setting("ANGEL_PIN", "4321", secret=True, by=None)
    moved = AdminRepo(engine, secret_key="now-from-env")
    assert moved.setting_values()["ANGEL_PIN"] == "4321" and moved.get_meta("settings_key") is None
    assert AdminRepo(engine, secret_key="now-from-env").setting_values()["ANGEL_PIN"] == "4321"
    assert AdminRepo(engine, secret_key="a-different-key").setting_values() == {}       # unreadable: skipped, not a crash


# ── Connectors and effective settings ────────────────────────────────────────

def test_ui_values_override_the_environment(repo):
    base = OptionsSettings(_env_file=None, ANGEL_API_KEY="from-env", OPTIONS_CAPITAL=50_000)
    connectors.save_connector(repo, "angel", {"ANGEL_API_KEY": "from-ui-key-123456", "ANGEL_PIN": "4321"}, by="amit")
    connectors.save_trading(repo, {"capital": 200_000, "live_setups": ["S1_TREND_PULLBACK"]}, by="amit")
    cfg = connectors.effective_settings(repo, base)
    assert cfg.ANGEL_API_KEY == "from-ui-key-123456" and cfg.ANGEL_PIN == "4321"
    assert cfg.OPTIONS_CAPITAL == 200_000 and cfg.OPTIONS_LIVE_SETUPS == ["S1_TREND_PULLBACK"]

    view = connectors.connectors_payload(repo, base)
    angel = next(c for c in view["connectors"] if c["id"] == "angel")
    fields = {f["key"]: f for f in angel["fields"]}
    assert fields["ANGEL_API_KEY"]["source"] == "app" and fields["ANGEL_API_KEY"]["display"] == "••••3456"
    assert "4321" not in str(view)                                          # secrets never leave the server
    assert fields["ANGEL_CLIENT_CODE"]["source"] == "unset" and "Client code" in angel["missing"]


def test_save_connector_keeps_blank_and_clears_none(repo):
    connectors.save_connector(repo, "telegram", {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "42"}, by="a")
    connectors.save_connector(repo, "telegram", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": None}, by="a")
    assert repo.setting_values() == {"TELEGRAM_BOT_TOKEN": "123:abc"}
    with pytest.raises(ValueError):
        connectors.save_connector(repo, "telegram", {"ANGEL_PIN": "1"}, by="a")
    with pytest.raises(KeyError):
        connectors.save_connector(repo, "nope", {}, by="a")


def test_provider_and_trading_validation(repo):
    connectors.set_data_provider(repo, "KITE", by="a")
    assert connectors.effective_settings(repo, OptionsSettings(_env_file=None)).provider == "kite"
    with pytest.raises(ValueError):
        connectors.set_data_provider(repo, "upstox", by="a")
    with pytest.raises(ValueError):
        connectors.save_trading(repo, {"risk_per_trade_pct": 25}, by="a")
    with pytest.raises(ValueError):
        connectors.save_trading(repo, {"risk_per_trade_pct": 3, "daily_loss_stop_pct": 2}, by="a")
    with pytest.raises(ValueError):
        connectors.save_trading(repo, {"live_setups": ["MADE_UP"]}, by="a")


def test_research_overrides_reach_the_pipeline_settings(repo, monkeypatch):
    from config import settings as research_module
    monkeypatch.setattr(research_module.settings, "OPENAI_API_KEY", "env-key")
    connectors.save_connector(repo, "openai", {"OPENAI_API_KEY": "sk-ui-1234567890", "MODEL_NAME": "gpt-4o-mini"}, by="a")
    connectors.apply_research_overrides(repo)
    assert research_module.settings.OPENAI_API_KEY == "sk-ui-1234567890"


# ── Health checks ────────────────────────────────────────────────────────────

class FakeHttp:
    def __init__(self, ok=True):
        self.ok = ok
        self.posts = []

    def get(self, url, timeout):
        return SimpleNamespace(status_code=200 if self.ok else 401, headers={"content-type": "application/json"},
                               json=lambda: {"ok": self.ok, "result": {"username": "nifty_bot"}})

    def post(self, url, json, timeout):
        self.posts.append(json)
        return SimpleNamespace(status_code=200, json=lambda: {"ok": True}, text="")


def hctx(repo, tmp_path, now=ist(2026, 10, 16, 16, 0), **kw):
    store = Store(repo.engine)
    cfg = kw.pop("cfg", OptionsSettings(_env_file=None))
    research = kw.pop("research", SimpleNamespace(OPENAI_API_KEY="", MODEL_NAME="gpt-4o-mini"))
    return health.HealthContext(repo=repo, store=store, cfg=cfg, research=research, now=now, **kw)


def test_system_checks(repo, tmp_path):
    ctx = hctx(repo, tmp_path)
    assert health.check_database(ctx)[0] == "ok"
    assert health.check_recorder(ctx)[0] == "fail"
    repo.set_meta_json("recorder_status", {"ts": ctx.now.isoformat(), "state": "waiting",
                                           "next_start": ist(2026, 10, 19, 8, 30).isoformat()})
    status, msg, _ = health.check_recorder(ctx)
    assert status == "ok" and "Mon 19 Oct 08:30" in msg
    stale = hctx(repo, tmp_path, now=ctx.now + timedelta(minutes=10))
    assert health.check_recorder(stale)[0] == "fail"
    assert health.check_market_data(ctx)[0] == "warn"                      # closed, nothing recorded yet
    assert health.check_market_data(hctx(repo, tmp_path, now=ist(2026, 10, 16, 11, 0)))[0] == "fail"


def test_angel_check(repo, tmp_path):
    cfg = OptionsSettings(_env_file=None, DATA_PROVIDER="angel", ANGEL_API_KEY="k", ANGEL_CLIENT_CODE="A1",
                          ANGEL_PIN="1", ANGEL_TOTP_SECRET="S")
    broker = SimpleNamespace(login=lambda: "A1", index_prices=lambda s: {"NIFTY 50": 25262.4})
    status, msg, _ = health.check_angel(hctx(repo, tmp_path, cfg=cfg, angel_factory=lambda c: broker))
    assert status == "ok" and "A1" in msg and "25,262.40" in msg
    assert health.check_angel(hctx(repo, tmp_path, cfg=OptionsSettings(_env_file=None, DATA_PROVIDER="angel")))[0] == "fail"
    repo.set_meta_json("recorder_status", {"ts": ist(2026, 10, 16, 11, 0).isoformat(), "state": "running"})
    busy = hctx(repo, tmp_path, now=ist(2026, 10, 16, 11, 0), cfg=cfg, angel_factory=lambda c: broker)
    assert health.check_angel(busy)[0] == "skip"                          # don't disturb the live session


def test_telegram_check(repo, tmp_path):
    cfg = OptionsSettings(_env_file=None, TELEGRAM_BOT_TOKEN="123:abc", TELEGRAM_CHAT_ID="42")
    http = FakeHttp()
    status, msg, _ = health.check_telegram(hctx(repo, tmp_path, cfg=cfg, http=http, send_telegram_test=True))
    assert status == "ok" and "@nifty_bot" in msg and http.posts[0]["chat_id"] == "42"
    assert health.check_telegram(hctx(repo, tmp_path, cfg=cfg, http=FakeHttp(ok=False)))[0] == "fail"
    assert health.check_telegram(hctx(repo, tmp_path))[0] == "fail"


def _openai_error(cls, status, message):
    """The SDK's own constructor needs its HTTP client's response type; the check only uses except + str()."""
    err = cls.__new__(cls)
    Exception.__init__(err, message)
    err.status_code = status
    return err


@pytest.mark.parametrize("error,expected,text", [
    (None, "ok", "answered"),
    (lambda: _openai_error(openai.AuthenticationError, 401, "bad key"), "fail", "rejected"),
    (lambda: _openai_error(openai.RateLimitError, 429, "insufficient_quota"), "fail", "no credits"),
])
def test_openai_check(repo, tmp_path, error, expected, text):
    def create(**kw):
        if error:
            raise error()
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    research = SimpleNamespace(OPENAI_API_KEY="sk-x", MODEL_NAME="gpt-4o-mini")
    status, msg, _ = health.check_openai(hctx(repo, tmp_path, research=research, openai_factory=lambda k: client))
    assert status == expected and text in msg


def test_run_checks_stores_results_and_captures_errors(repo, tmp_path):
    def boom():
        raise RuntimeError("yahoo down")
    results = health.run_checks(hctx(repo, tmp_path, macro_probe=boom), ["database", "macro"])
    by_id = {r["id"]: r for r in results}
    assert by_id["database"]["status"] == "ok" and by_id["macro"]["status"] == "fail"
    assert "yahoo down" in repo.health_results()["macro"]["message"]
    with pytest.raises(KeyError):
        health.run_checks(hctx(repo, tmp_path), ["nope"])


# ── API end to end ───────────────────────────────────────────────────────────

@pytest.fixture
def api(repo, monkeypatch):
    app = FastAPI()
    app.include_router(admin_routes.router)
    app.dependency_overrides[deps.get_repo] = lambda: repo
    app.dependency_overrides[deps.get_store] = lambda: Store(repo.engine)
    app.dependency_overrides[deps.get_cfg] = lambda: connectors.effective_settings(repo, OptionsSettings(_env_file=None))
    monkeypatch.setattr(deps, "base_settings", lambda: OptionsSettings(_env_file=None))
    admin_routes._failures.clear()
    return TestClient(app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_first_run_setup_and_login(api, repo):
    assert api.get("/api/auth/state").json() == {"has_admin": False}
    code = repo.ensure_setup_code()
    bad = api.post("/api/auth/setup", json={"setup_code": "WRONG-WRONG", "username": "amit", "password": "correct horse battery"})
    assert bad.status_code == 403 and bad.json()["detail"]["code"] == "bad_setup_code"
    weak = api.post("/api/auth/setup", json={"setup_code": code, "username": "amit", "password": "short"})
    assert weak.status_code == 422
    ok = api.post("/api/auth/setup", json={"setup_code": code, "username": "Amit", "password": "correct horse battery"})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "admin"
    token = ok.json()["token"]
    assert api.get("/api/auth/me", headers=auth(token)).json()["username"] == "amit"
    again = api.post("/api/auth/setup", json={"setup_code": code, "username": "eve", "password": "correct horse battery"})
    assert again.status_code == 409

    assert api.post("/api/auth/login", json={"username": "amit", "password": "nope"}).status_code == 401
    login = api.post("/api/auth/login", json={"username": "AMIT", "password": "correct horse battery"})
    assert login.status_code == 200
    assert api.post("/api/auth/logout", headers=auth(login.json()["token"])).json() == {"ok": True}
    assert api.get("/api/auth/me", headers=auth(login.json()["token"])).status_code == 401


def test_login_is_throttled(api, repo):
    repo.create_user("amit", "correct horse battery")
    for _ in range(5):
        api.post("/api/auth/login", json={"username": "amit", "password": "wrong"})
    r = api.post("/api/auth/login", json={"username": "amit", "password": "correct horse battery"})
    assert r.status_code == 429


def test_connectors_health_and_recorder_api(api, repo, monkeypatch):
    token = repo.create_session(repo.create_user("amit", "correct horse battery"))
    assert api.get("/api/admin/connectors").status_code == 401
    view = api.get("/api/admin/connectors", headers=auth(token)).json()
    assert {c["id"] for c in view["connectors"]} == {"angel", "kite", "telegram", "openai"}

    saved = api.put("/api/admin/connectors/angel", headers=auth(token),
                    json={"values": {"ANGEL_API_KEY": "angel-key-0987654321", "ANGEL_CLIENT_CODE": "A123"}}).json()
    angel = next(c for c in saved["connectors"] if c["id"] == "angel")
    assert "angel-key-0987654321" not in str(saved) and angel["fields"][1]["display"] == "A123"
    assert api.put("/api/admin/connectors/angel", headers=auth(token),
                   json={"values": {"KITE_API_KEY": "x"}}).status_code == 422
    assert api.put("/api/admin/data-provider", headers=auth(token), json={"provider": "kite"}).json()["data_provider"] == "kite"
    assert api.put("/api/admin/trading", headers=auth(token), json={"risk_per_trade_pct": 40}).status_code == 422
    t = api.put("/api/admin/trading", headers=auth(token), json={"capital": 150000, "live_setups": ["S2_ORB"]}).json()
    assert t["trading"]["capital"] == 150000 and t["trading"]["live_setups"] == ["S2_ORB"]

    run = api.post("/api/admin/health/run", headers=auth(token), json={"ids": ["database"]}).json()
    assert run["results"]["database"]["status"] == "ok"
    assert api.get("/api/admin/health", headers=auth(token)).json()["results"]["database"]["status"] == "ok"

    monkeypatch.setattr(admin_routes, "now_ist", lambda: ist(2026, 10, 16, 11, 0))
    assert api.post("/api/admin/recorder/restart", headers=auth(token)).json()["ok"]
    assert repo.get_meta_json("recorder_command")["by"] == "amit"
    monkeypatch.setattr(admin_routes, "now_ist", lambda: ist(2026, 10, 17, 11, 0))      # Saturday
    assert api.post("/api/admin/recorder/restart", headers=auth(token)).status_code == 409


def test_password_change_signs_out_other_devices(api, repo):
    uid = repo.create_user("amit", "correct horse battery")
    mine, other = repo.create_session(uid), repo.create_session(uid)
    assert api.post("/api/auth/password", headers=auth(mine),
                    json={"current_password": "wrong", "new_password": "a brand new secret"}).status_code == 403
    assert api.post("/api/auth/password", headers=auth(mine),
                    json={"current_password": "correct horse battery", "new_password": "a brand new secret"}).json()["ok"]
    assert repo.resolve_session(other) is None and repo.resolve_session(mine)
    assert repo.authenticate("amit", "a brand new secret")

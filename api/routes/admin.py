"""Accounts (first-run setup, login, password) and the admin Connectors API."""

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.deps import base_settings, current_user, get_cfg, get_repo, get_store, invalidate_cfg, require_admin
from options.admin import connectors, health, security
from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.core.calendar import NseCalendar, now_ist
from options.daemon import COMMAND_KEY, can_start_now
from options.storage import Store
from utils.logger import setup_logger

logger = setup_logger("options.auth")
router = APIRouter(tags=["admin"])

# ── Brute-force throttle (per process; enough for a single-admin tool) ────────

MAX_FAILURES, WINDOW_S = 5, 15 * 60
_failures: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _throttle_key(kind: str, request: Request, who: str = "") -> str:
    return f"{kind}:{request.client.host if request.client else '?'}:{who.lower()}"


def _check_throttle(key: str) -> None:
    with _lock:
        q = _failures[key]
        while q and time.monotonic() - q[0] > WINDOW_S:
            q.popleft()
        if len(q) >= MAX_FAILURES:
            raise HTTPException(429, {"code": "too_many_attempts",
                                      "message": "Too many failed attempts. Try again in 15 minutes."})


def _record_failure(key: str) -> None:
    with _lock:
        _failures[key].append(time.monotonic())


def _clear_failures(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


# ── Accounts ─────────────────────────────────────────────────────────────────

class SetupBody(BaseModel):
    setup_code: str = Field(min_length=4, max_length=40)
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=200)


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class PasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


def _session_payload(repo: AdminRepo, user: dict) -> dict:
    return {"token": repo.create_session(user["id"]), "user": user}


@router.get("/api/auth/state")
def auth_state(repo: AdminRepo = Depends(get_repo)) -> dict:
    return {"has_admin": repo.has_admin()}


@router.post("/api/auth/setup")
def auth_setup(body: SetupBody, request: Request, repo: AdminRepo = Depends(get_repo)) -> dict:
    key = _throttle_key("setup", request)
    _check_throttle(key)
    if repo.has_admin():
        raise HTTPException(409, {"code": "already_set_up", "message": "An admin account already exists. Log in instead."})
    if not repo.check_setup_code(body.setup_code):
        _record_failure(key)
        raise HTTPException(403, {"code": "bad_setup_code",
                                  "message": "That setup code is wrong. It's printed in the API service's logs."})
    if problem := security.password_problem(body.password, body.username):
        raise HTTPException(422, {"code": "weak_password", "message": problem})
    user_id = repo.create_user(body.username, body.password, role="admin")
    repo.set_meta("setup_code_digest", "used")
    _clear_failures(key)
    logger.info("Admin account %s created", body.username.lower())
    return _session_payload(repo, repo.get_user(user_id))


@router.post("/api/auth/login")
def auth_login(body: LoginBody, request: Request, repo: AdminRepo = Depends(get_repo)) -> dict:
    key = _throttle_key("login", request, body.username)
    _check_throttle(key)
    user = repo.authenticate(body.username, body.password)
    if user is None:
        _record_failure(key)
        raise HTTPException(401, {"code": "bad_credentials", "message": "Wrong username or password."})
    _clear_failures(key)
    return _session_payload(repo, user)


@router.post("/api/auth/logout")
def auth_logout(user: dict = Depends(current_user), repo: AdminRepo = Depends(get_repo)) -> dict:
    repo.revoke_session(user["token"])
    return {"ok": True}


@router.get("/api/auth/me")
def auth_me(user: dict = Depends(current_user)) -> dict:
    return {k: v for k, v in user.items() if k != "token"}


@router.post("/api/auth/password")
def auth_password(body: PasswordBody, user: dict = Depends(current_user), repo: AdminRepo = Depends(get_repo)) -> dict:
    if not user["id"] or repo.authenticate(user["username"], body.current_password) is None:
        raise HTTPException(403, {"code": "bad_credentials", "message": "Your current password is wrong."})
    if problem := security.password_problem(body.new_password, user["username"]):
        raise HTTPException(422, {"code": "weak_password", "message": problem})
    repo.set_password(user["id"], body.new_password)
    repo.revoke_user_sessions(user["id"], keep_token=user["token"])     # sign out every other device
    return {"ok": True}


# ── Connectors and settings ──────────────────────────────────────────────────

class ConnectorBody(BaseModel):
    values: dict[str, str | None]


class ProviderBody(BaseModel):
    provider: str


class TradingBody(BaseModel):
    capital: float | None = None
    risk_per_trade_pct: float | None = None
    daily_loss_stop_pct: float | None = None
    live_setups: list[str] | None = None


class HealthBody(BaseModel):
    ids: list[str] | None = None
    send_telegram_test: bool = False


def _payload(repo: AdminRepo) -> dict:
    return {**connectors.connectors_payload(repo, base_settings()), "recorder": health.recorder_status(repo),
            "secret_key_from_env": bool(os.getenv("SECRET_KEY"))}


def _saved(repo: AdminRepo, research_changed: bool = False) -> dict:
    invalidate_cfg()
    if research_changed:
        connectors.apply_research_overrides(repo)
    return _payload(repo)


@router.get("/api/admin/connectors")
def admin_connectors(_: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo)) -> dict:
    return _payload(repo)


@router.put("/api/admin/connectors/{connector_id}")
def admin_save_connector(connector_id: str, body: ConnectorBody, user: dict = Depends(require_admin),
                         repo: AdminRepo = Depends(get_repo)) -> dict:
    try:
        changed = connectors.save_connector(repo, connector_id, body.values, user["username"])
    except KeyError:
        raise HTTPException(404, {"code": "unknown_connector", "message": f"No connector {connector_id}"})
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})
    logger.info("%s updated %s: %s", user["username"], connector_id, ", ".join(changed) or "nothing")
    return _saved(repo, research_changed=connector_id == "openai")


@router.put("/api/admin/data-provider")
def admin_data_provider(body: ProviderBody, user: dict = Depends(require_admin),
                        repo: AdminRepo = Depends(get_repo)) -> dict:
    try:
        connectors.set_data_provider(repo, body.provider, user["username"])
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})
    return _saved(repo)


@router.put("/api/admin/trading")
def admin_trading(body: TradingBody, user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo)) -> dict:
    try:
        connectors.save_trading(repo, body.model_dump(exclude_none=True), user["username"])
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})
    return _saved(repo)


def _health_ctx(repo: AdminRepo, store: Store, cfg: OptionsSettings, send_test: bool = False) -> health.HealthContext:
    from config.settings import settings as research
    return health.HealthContext(repo=repo, store=store, cfg=cfg, research=research, now=now_ist(),
                                send_telegram_test=send_test)


@router.get("/api/admin/health")
def admin_health(_: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo)) -> dict:
    names = {k: v[0] for k, v in health.CHECKS.items()}
    return {"results": repo.health_results(), "checks": names, "recorder": health.recorder_status(repo)}


@router.post("/api/admin/health/run")
def admin_health_run(body: HealthBody, _: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                     store: Store = Depends(get_store), cfg: OptionsSettings = Depends(get_cfg)) -> dict:
    try:
        results = health.run_checks(_health_ctx(repo, store, cfg, body.send_telegram_test), body.ids)
    except KeyError as e:
        raise HTTPException(404, {"code": "unknown_check", "message": f"Unknown check {e}"})
    return {"results": {r["id"]: r for r in results}}


@router.post("/api/admin/recorder/restart")
def admin_recorder_restart(user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo)) -> dict:
    now = now_ist()
    if not can_start_now(now, NseCalendar()):
        raise HTTPException(409, {"code": "market_closed",
                                  "message": "There's no session to run now. The next one starts at 08:30 on the "
                                             "next trading day."})
    repo.set_meta_json(COMMAND_KEY, {"action": "restart", "requested_at": now.isoformat(), "by": user["username"]})
    return {"ok": True, "requested_at": now.isoformat()}

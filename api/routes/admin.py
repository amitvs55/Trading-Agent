"""Accounts (first-run setup, login, password) and the admin Connectors API."""

import os
import threading
import time
from collections import defaultdict, deque

from datetime import date, datetime, timedelta
from html import escape

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.deps import (base_settings, current_user, get_calendar, get_cfg, get_repo, get_store, invalidate_cfg,
                      require_admin)
from options.admin import connectors, health, security
from options.admin.repo import ROLES, AdminRepo, LastAdmin, UserExists
from options.config import OptionsSettings
from options.core import calendar_store
from options.core.calendar import IST, NseCalendar, now_ist
from options.daemon import COMMAND_KEY, can_start_now
from options.engine import controls
from options.notify import make_notifier
from options.storage import Store
from utils.logger import setup_logger

logger = setup_logger("options.auth")
router = APIRouter(tags=["admin"])


def _audit(store: Store, user: dict, action: str, detail: str) -> None:
    try:
        store.audit(user["username"], action, detail, now_ist())
    except Exception:
        logger.exception("Couldn't write the audit log")


def _alert(cfg: OptionsSettings, text: str) -> None:
    """Background task: tell the alert channel about an admin action."""
    try:
        make_notifier(cfg).send(text)
    except Exception:
        logger.exception("Admin alert failed")

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


class ProfileBody(BaseModel):
    full_name: str = Field(max_length=80)


@router.patch("/api/auth/profile")
def auth_profile(body: ProfileBody, user: dict = Depends(current_user), repo: AdminRepo = Depends(get_repo)) -> dict:
    if not user["id"]:
        raise HTTPException(400, {"code": "no_profile", "message": "The API token has no profile to edit."})
    return repo.update_user(user["id"], full_name=body.full_name)


# ── Users (admin) ────────────────────────────────────────────────────────────

class NewUserBody(BaseModel):
    full_name: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=200)
    role: str = "viewer"


class UserPatchBody(BaseModel):
    full_name: str | None = Field(None, max_length=80)
    role: str | None = None
    disabled: bool | None = None


class ResetPasswordBody(BaseModel):
    new_password: str = Field(min_length=1, max_length=200)


def _user_or_404(repo: AdminRepo, user_id: int) -> dict:
    target = repo.get_user(user_id)
    if target is None:
        raise HTTPException(404, {"code": "unknown_user", "message": "No such user."})
    return target


@router.get("/api/admin/users")
def admin_users(_: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo)) -> dict:
    return {"users": repo.list_users(), "roles": list(ROLES)}


@router.post("/api/admin/users")
def admin_create_user(body: NewUserBody, user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                      store: Store = Depends(get_store)) -> dict:
    if body.role not in ROLES:
        raise HTTPException(422, {"code": "invalid", "message": f"Role must be one of {', '.join(ROLES)}."})
    if problem := security.password_problem(body.password, body.username):
        raise HTTPException(422, {"code": "weak_password", "message": problem})
    try:
        new_id = repo.create_user(body.username, body.password, role=body.role, full_name=body.full_name)
    except UserExists as e:
        raise HTTPException(409, {"code": "username_taken", "message": str(e)})
    logger.info("%s created %s user %s", user["username"], body.role, body.username.lower())
    _audit(store, user, "user_created", f"{body.username.lower()} ({body.role})")
    return repo.get_user(new_id)


@router.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, body: UserPatchBody, user: dict = Depends(require_admin),
                      repo: AdminRepo = Depends(get_repo), store: Store = Depends(get_store)) -> dict:
    _user_or_404(repo, user_id)
    if user_id == user["id"] and (body.disabled or (body.role is not None and body.role != user["role"])):
        raise HTTPException(422, {"code": "self_change", "message": "You can't disable your own account or change "
                                  "your own role. Ask another admin to do it."})
    try:
        updated = repo.update_user(user_id, full_name=body.full_name, role=body.role, disabled=body.disabled)
    except LastAdmin as e:
        raise HTTPException(409, {"code": "last_admin", "message": str(e)})
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})
    logger.info("%s updated user %s", user["username"], updated["username"])
    _audit(store, user, "user_updated", f"{updated['username']}: " + ", ".join(
        f"{k}={v}" for k, v in body.model_dump(exclude_none=True).items()))
    return updated


@router.post("/api/admin/users/{user_id}/password")
def admin_reset_password(user_id: int, body: ResetPasswordBody, user: dict = Depends(require_admin),
                         repo: AdminRepo = Depends(get_repo), store: Store = Depends(get_store)) -> dict:
    target = _user_or_404(repo, user_id)
    if problem := security.password_problem(body.new_password, target["username"]):
        raise HTTPException(422, {"code": "weak_password", "message": problem})
    repo.set_password(user_id, body.new_password)
    repo.revoke_user_sessions(user_id, keep_token=user["token"] if user_id == user["id"] else None)
    logger.info("%s reset the password of %s", user["username"], target["username"])
    _audit(store, user, "password_reset", target["username"])
    return {"ok": True}


@router.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                      store: Store = Depends(get_store)) -> dict:
    target = _user_or_404(repo, user_id)
    if user_id == user["id"]:
        raise HTTPException(422, {"code": "self_change", "message": "You can't delete the account you're signed in with."})
    try:
        repo.delete_user(user_id)
    except LastAdmin as e:
        raise HTTPException(409, {"code": "last_admin", "message": str(e)})
    logger.info("%s deleted user %s", user["username"], target["username"])
    _audit(store, user, "user_deleted", target["username"])
    return {"ok": True}


# ── Connectors and settings ──────────────────────────────────────────────────

class ConnectorBody(BaseModel):
    values: dict[str, str | None]
    test: bool = True             # test the new values first and store nothing if the test fails


class ProviderBody(BaseModel):
    provider: str


class TradingBody(BaseModel):
    capital: float | None = None
    risk_per_trade_pct: float | None = None
    daily_loss_stop_pct: float | None = None
    live_setups: list[str] | None = None
    bars_retention_days: int | None = None


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
                         repo: AdminRepo = Depends(get_repo), store: Store = Depends(get_store)) -> dict:
    """Store a connector's edits only once they're well-formed and (unless test=false) pass a live test."""
    try:
        clean = connectors.clean_values(connector_id, body.values)
    except KeyError:
        raise HTTPException(404, {"code": "unknown_connector", "message": f"No connector {connector_id}"})
    except connectors.InvalidFields as e:
        raise HTTPException(422, {"code": "invalid", "message": "Fix the highlighted fields. Nothing was saved.",
                                  "fields": e.problems})
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})

    missing = connectors.missing_after(repo, connector_id, clean, base_settings())
    result = None
    if body.test and clean and not missing and connector_id in health.CHECKS:
        cfg, research = connectors.preview_settings(repo, clean, base_settings())
        result = health.run_checks(_health_ctx(repo, store, cfg, research=research), [connector_id],
                                   store_results=False)[0]
        if result["status"] == "fail":
            logger.info("%s's %s edits failed their test; nothing saved", user["username"], connector_id)
            reason = result["message"].rstrip()
            reason += "" if reason.endswith((".", "!", "?")) else "."
            raise HTTPException(422, {"code": "test_failed", "message": f"{reason} Nothing was saved.",
                                      "health": result})

    changed = connectors.save_connector(repo, connector_id, clean, user["username"])
    if result:
        health.save_result(repo, result)
    logger.info("%s updated %s: %s%s", user["username"], connector_id, ", ".join(changed) or "nothing",
                f" (test {result['status']})" if result else " (not tested)")
    _audit(store, user, "connector_saved", f"{connector_id}: {', '.join(changed) or 'nothing'}"
           + (f" (test {result['status']})" if result else " (not tested)"))
    return {**_saved(repo, research_changed=connector_id == "openai"), "test": result, "missing": missing}


@router.put("/api/admin/data-provider")
def admin_data_provider(body: ProviderBody, user: dict = Depends(require_admin),
                        repo: AdminRepo = Depends(get_repo), store: Store = Depends(get_store)) -> dict:
    try:
        connectors.set_data_provider(repo, body.provider, user["username"])
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})
    _audit(store, user, "data_provider", body.provider)
    return _saved(repo)


@router.put("/api/admin/trading")
def admin_trading(body: TradingBody, user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                  store: Store = Depends(get_store)) -> dict:
    before = connectors.trading_view(connectors.effective_settings(repo, base_settings()))
    try:
        connectors.save_trading(repo, body.model_dump(exclude_none=True), user["username"])
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})
    after = connectors.trading_view(connectors.effective_settings(repo, base_settings()))
    changes = [f"{k}: {before[k]} -> {after[k]}" for k in connectors.AUDITED_TRADING_FIELDS if before[k] != after[k]]
    if changes:
        _audit(store, user, "trading_rules", "; ".join(changes))
    return _saved(repo)


def _health_ctx(repo: AdminRepo, store: Store, cfg: OptionsSettings, send_test: bool = False,
                research: object | None = None) -> health.HealthContext:
    if research is None:
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
def admin_recorder_restart(user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                           store: Store = Depends(get_store), cal: NseCalendar = Depends(get_calendar)) -> dict:
    now = now_ist()
    if not can_start_now(now, cal):
        raise HTTPException(409, {"code": "market_closed",
                                  "message": "There's no session to run now. The next one starts at 08:30 on the "
                                             "next trading day."})
    repo.set_meta_json(COMMAND_KEY, {"action": "restart", "requested_at": now.isoformat(), "by": user["username"]})
    _audit(store, user, "recorder_restart", "start today's session")
    return {"ok": True, "requested_at": now.isoformat()}


# ── Emergency controls ───────────────────────────────────────────────────────

class PauseBody(BaseModel):
    paused: bool
    reason: str = Field("", max_length=200)


def _controls_view(store: Store) -> dict:
    return {**controls.read(store), "exit_all_pending": controls.pending_exit_all(store)}


@router.get("/api/admin/controls")
def admin_controls(_: dict = Depends(require_admin), store: Store = Depends(get_store)) -> dict:
    return _controls_view(store)


@router.put("/api/admin/controls/pause")
def admin_pause(body: PauseBody, tasks: BackgroundTasks, user: dict = Depends(require_admin),
                store: Store = Depends(get_store), cfg: OptionsSettings = Depends(get_cfg)) -> dict:
    """Pause or resume new signals. Open signals keep being managed either way."""
    was = bool(controls.read(store).get("paused"))
    controls.set_paused(store, body.paused, user["username"], body.reason, now_ist())
    if was != body.paused:
        _audit(store, user, "signals_paused" if body.paused else "signals_resumed", body.reason or "")
        who = escape(user.get("full_name") or user["username"])
        why = f": {escape(body.reason)}" if body.reason else ""
        tasks.add_task(_alert, cfg, f"⏸ <b>New signals paused</b> by {who}{why}. Open signals are still managed."
                       if body.paused else f"▶️ <b>New signals resumed</b> by {who}.")
    return _controls_view(store)


@router.post("/api/admin/controls/exit-all")
def admin_exit_all(user: dict = Depends(require_admin), store: Store = Depends(get_store)) -> dict:
    """Ask the engine to close every open signal at the live bid (cancel unfilled ones)."""
    controls.request_exit_all(store, user["username"], now_ist())
    _audit(store, user, "exit_all", f"{len(store.open_signals())} open signal(s)")
    return _controls_view(store)


# ── Alerts, audit log, recorder events ───────────────────────────────────────

def _iso(row: dict, *keys: str) -> dict:
    out = dict(row)
    for k in keys:
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = (v.replace(tzinfo=IST) if v.tzinfo is None else v).isoformat()
    return out


@router.get("/api/admin/alerts")
def admin_alerts(limit: int = Query(50, ge=1, le=500), _: dict = Depends(require_admin),
                 store: Store = Depends(get_store)) -> dict:
    rows = [_iso({k: v for k, v in r.items() if k not in ("digest", "buttons")}, "created_at", "sent_at")
            for r in store.outbox_recent(limit)]
    return {"alerts": rows, "last_24h": store.outbox_counts_since(now_ist() - timedelta(hours=24))}


@router.get("/api/admin/audit")
def admin_audit(limit: int = Query(100, ge=1, le=1000), _: dict = Depends(require_admin),
                store: Store = Depends(get_store)) -> dict:
    return {"entries": [_iso(r, "ts") for r in store.audit_recent(limit)]}


@router.get("/api/admin/recorder/events")
def admin_recorder_events(days: int = Query(3, ge=1, le=30), _: dict = Depends(require_admin),
                          store: Store = Depends(get_store)) -> dict:
    """Disconnects, reconnects and daily summaries the session logged (the session_events table)."""
    return {"events": [_iso(r, "ts") for r in store.session_events_since(now_ist() - timedelta(days=days))]}


# ── Trading calendar ─────────────────────────────────────────────────────────

class HolidayBody(BaseModel):
    date: date
    name: str = Field(min_length=1, max_length=80)


class YearBody(BaseModel):
    complete: bool


class EventBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    at: datetime
    impact: str = "high"


def _calendar_payload(repo: AdminRepo) -> dict:
    invalidate_cfg()                                   # drops the cached calendar too
    return calendar_store.calendar_view(repo, now_ist().date())


@router.get("/api/admin/calendar")
def admin_calendar(_: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo)) -> dict:
    return calendar_store.calendar_view(repo, now_ist().date())


@router.post("/api/admin/calendar/holidays")
def admin_add_holiday(body: HolidayBody, user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                      store: Store = Depends(get_store)) -> dict:
    try:
        calendar_store.add_holiday(repo, body.date, body.name)
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})
    _audit(store, user, "holiday_added", f"{body.date.isoformat()} {body.name}")
    return _calendar_payload(repo)


@router.delete("/api/admin/calendar/holidays/{day}")
def admin_remove_holiday(day: date, user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                         store: Store = Depends(get_store)) -> dict:
    try:
        calendar_store.remove_holiday(repo, day)
    except KeyError:
        raise HTTPException(404, {"code": "unknown_holiday", "message": "Only holidays added here can be removed."})
    _audit(store, user, "holiday_removed", day.isoformat())
    return _calendar_payload(repo)


@router.put("/api/admin/calendar/years/{year}")
def admin_year_complete(year: int, body: YearBody, user: dict = Depends(require_admin),
                        repo: AdminRepo = Depends(get_repo), store: Store = Depends(get_store)) -> dict:
    if not 2020 <= year <= 2100:
        raise HTTPException(422, {"code": "invalid", "message": "Year out of range."})
    calendar_store.set_year_complete(repo, year, body.complete)
    _audit(store, user, "holiday_year", f"{year} complete={body.complete}")
    return _calendar_payload(repo)


@router.post("/api/admin/calendar/events")
def admin_add_event(body: EventBody, user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                    store: Store = Depends(get_store)) -> dict:
    try:
        ev = calendar_store.add_event(repo, body.name, body.at, body.impact)
    except ValueError as e:
        raise HTTPException(422, {"code": "invalid", "message": str(e)})
    _audit(store, user, "event_added", f"{ev['name']} at {ev['at']} ({ev['impact']})")
    return _calendar_payload(repo)


@router.delete("/api/admin/calendar/events/{event_id}")
def admin_remove_event(event_id: str, user: dict = Depends(require_admin), repo: AdminRepo = Depends(get_repo),
                       store: Store = Depends(get_store)) -> dict:
    try:
        calendar_store.remove_event(repo, event_id)
    except KeyError:
        raise HTTPException(404, {"code": "unknown_event", "message": "Only events added here can be removed."})
    _audit(store, user, "event_removed", event_id)
    return _calendar_payload(repo)

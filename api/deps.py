"""Shared API dependencies: database, effective settings, and the signed-in user."""

import secrets
import time
from functools import lru_cache

from fastapi import Depends, Header, HTTPException

from options.admin.connectors import effective_settings
from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.storage import Store, make_engine

CFG_TTL_S = 5.0          # UI edits reach every request within this long (and at once on this worker)


@lru_cache(maxsize=1)
def base_settings() -> OptionsSettings:
    """Environment only: DATABASE_URL, SECRET_KEY and anything not set from the UI."""
    return OptionsSettings()


@lru_cache(maxsize=1)
def _engine():
    return make_engine(base_settings().DATABASE_URL)


def get_store() -> Store:
    return Store(_engine())


@lru_cache(maxsize=1)
def get_repo() -> AdminRepo:
    return AdminRepo(_engine())


_cfg_cache: dict[int, tuple[float, OptionsSettings]] = {}


def get_cfg(repo: AdminRepo = Depends(get_repo)) -> OptionsSettings:
    hit = _cfg_cache.get(id(repo))
    if hit and time.monotonic() - hit[0] < CFG_TTL_S:
        return hit[1]
    cfg = effective_settings(repo, base_settings())
    _cfg_cache[id(repo)] = (time.monotonic(), cfg)
    return cfg


def invalidate_cfg() -> None:
    _cfg_cache.clear()


def _bearer(authorization: str | None) -> str:
    return (authorization or "").removeprefix("Bearer ").strip()


def current_user(authorization: str | None = Header(None), repo: AdminRepo = Depends(get_repo)) -> dict:
    token = _bearer(authorization)
    if token:
        user = repo.resolve_session(token)
        if user:
            return {**user, "token": token}
        legacy = base_settings().DASHBOARD_TOKEN          # optional static token for scripts
        if legacy and secrets.compare_digest(token.encode(), legacy.encode()):
            return {"id": 0, "username": "api-token", "role": "admin", "token": token}
    if not repo.has_admin():
        raise HTTPException(401, {"code": "setup_required", "message": "Create the admin account first."})
    raise HTTPException(401, {"code": "login_required", "message": "Please log in."})


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, {"code": "forbidden", "message": "Admins only."})
    return user

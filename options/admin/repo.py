"""Database access for accounts, sessions, UI-managed settings and health results."""

import json
import os
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine

from options.admin import security
from options.core.calendar import IST, now_ist
from options.storage import app_meta, app_settings, auth_failures, health_checks, user_sessions, users
from utils.logger import setup_logger

logger = setup_logger("options.admin")

SESSION_TTL = timedelta(days=14)
ROLES = ("admin", "viewer")          # viewers see every page but cannot change settings or accounts


class UserExists(ValueError):
    pass


class LastAdmin(ValueError):
    pass

_DUMMY_HASH: str | None = None
TOUCH_EVERY = timedelta(minutes=5)          # don't write last_seen_at on every request


class AdminRepo:
    def __init__(self, engine: Engine, secret_key: str | None = None, now_fn=now_ist):
        self.engine = engine
        self.now = now_fn
        self._secret_key = secret_key if secret_key is not None else os.getenv("SECRET_KEY", "")
        self._cipher: security.Cipher | None = None

    # ── Meta (small key/value facts) ─────────────────────────────────────────

    def get_meta(self, key: str) -> str | None:
        with self.engine.connect() as conn:
            return conn.execute(select(app_meta.c.value).where(app_meta.c.key == key)).scalar()

    def set_meta(self, key: str, value: str) -> None:
        with self.engine.begin() as conn:
            done = conn.execute(update(app_meta).where(app_meta.c.key == key)
                                .values(value=value, updated_at=self.now())).rowcount
            if not done:
                conn.execute(app_meta.insert().values(key=key, value=value, updated_at=self.now()))

    def get_meta_json(self, key: str) -> dict | None:
        raw = self.get_meta(key)
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    def set_meta_json(self, key: str, value: dict) -> None:
        self.set_meta(key, json.dumps(value, default=str))

    def delete_meta(self, key: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(app_meta).where(app_meta.c.key == key))

    @property
    def cipher(self) -> security.Cipher:
        """Keyed from SECRET_KEY when set; otherwise from a key generated once and kept in app_meta,
        so secrets are never stored in plain text even before anyone sets SECRET_KEY. Setting
        SECRET_KEY later re-encrypts the saved secrets with it and drops the stored key."""
        if self._cipher is None:
            stored = self.get_meta("settings_key")
            if self._secret_key:
                self._cipher = security.Cipher(self._secret_key)
                if stored:
                    self._rekey(security.Cipher(stored), self._cipher)
                    self.delete_meta("settings_key")
            else:
                if not stored:
                    stored = security.new_secret_key()
                    self.set_meta("settings_key", stored)
                self._cipher = security.Cipher(stored)
        return self._cipher

    def _rekey(self, old: security.Cipher, new: security.Cipher) -> None:
        with self.engine.begin() as conn:
            for r in conn.execute(select(app_settings.c.key, app_settings.c.value).where(app_settings.c.secret == 1)).all():
                try:
                    plain = old.decrypt(r.value)
                except ValueError:
                    continue                                   # already under the new key
                conn.execute(update(app_settings).where(app_settings.c.key == r.key).values(value=new.encrypt(plain)))

    # ── Users ────────────────────────────────────────────────────────────────

    def has_admin(self) -> bool:
        with self.engine.connect() as conn:
            return bool(conn.execute(select(func.count()).select_from(users).where(users.c.role == "admin")).scalar())

    def _active_admins(self, conn) -> int:
        return int(conn.execute(select(func.count()).select_from(users)
                                .where(users.c.role == "admin", users.c.disabled == 0)).scalar())

    def create_user(self, username: str, password: str, role: str = "admin", full_name: str | None = None) -> int:
        if role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}")
        name = username.strip().lower()
        with self.engine.begin() as conn:
            if conn.execute(select(users.c.id).where(users.c.username == name)).first():
                raise UserExists(f"The username {name} is already taken.")
            res = conn.execute(users.insert().values(username=name, password_hash=security.hash_password(password),
                                                     role=role, created_at=self.now(), disabled=0,
                                                     full_name=(full_name or "").strip() or None))
            return int(res.inserted_primary_key[0])

    def list_users(self) -> list[dict]:
        with self.engine.connect() as conn:
            return [_public(r) for r in conn.execute(select(users).order_by(users.c.created_at))]

    def update_user(self, user_id: int, *, full_name: str | None = None, role: str | None = None,
                    disabled: bool | None = None) -> dict:
        """Change a user's name, role or access. The last active admin can never be demoted or disabled."""
        values: dict = {}
        if full_name is not None:
            values["full_name"] = full_name.strip() or None
        if role is not None:
            if role not in ROLES:
                raise ValueError(f"role must be one of {', '.join(ROLES)}")
            values["role"] = role
        if disabled is not None:
            values["disabled"] = 1 if disabled else 0
        with self.engine.begin() as conn:
            row = conn.execute(select(users).where(users.c.id == user_id)).first()
            if row is None:
                raise KeyError(user_id)
            loses_admin = row.role == "admin" and not row.disabled and (
                (role is not None and role != "admin") or disabled is True)
            if loses_admin and self._active_admins(conn) <= 1:
                raise LastAdmin("There must always be at least one active admin.")
            if values:
                conn.execute(update(users).where(users.c.id == user_id).values(**values))
        if disabled:
            self.revoke_user_sessions(user_id)
        return self.get_user(user_id)

    def delete_user(self, user_id: int) -> None:
        with self.engine.begin() as conn:
            row = conn.execute(select(users).where(users.c.id == user_id)).first()
            if row is None:
                raise KeyError(user_id)
            if row.role == "admin" and not row.disabled and self._active_admins(conn) <= 1:
                raise LastAdmin("There must always be at least one active admin.")
            conn.execute(delete(user_sessions).where(user_sessions.c.user_id == user_id))
            conn.execute(delete(users).where(users.c.id == user_id))

    def get_user(self, user_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.id == user_id)).first()
        return _public(row) if row else None

    def authenticate(self, username: str, password: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.username == username.strip().lower())).first()
        if row is None:
            security.verify_password(password, _dummy_hash())     # same cost as a real check: no username probing
            return None
        if not security.verify_password(password, row.password_hash) or row.disabled:
            return None
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == row.id).values(last_login_at=self.now()))
        return _public(row)

    def set_password(self, user_id: int, password: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id)
                         .values(password_hash=security.hash_password(password)))

    # ── Sessions ─────────────────────────────────────────────────────────────

    def create_session(self, user_id: int) -> str:
        token, now = security.new_token(), self.now()
        with self.engine.begin() as conn:
            conn.execute(user_sessions.insert().values(token_digest=security.token_digest(token), user_id=user_id,
                                                       created_at=now, expires_at=now + SESSION_TTL,
                                                       last_seen_at=now))
        return token

    def resolve_session(self, token: str) -> dict | None:
        digest, now = security.token_digest(token), self.now()
        with self.engine.connect() as conn:
            row = conn.execute(select(user_sessions).where(user_sessions.c.token_digest == digest)).first()
        if row is None or _aware(row.expires_at) <= now:
            return None
        user = self.get_user(row.user_id)
        if user is None or user["disabled"]:
            return None
        if now - _aware(row.last_seen_at) > TOUCH_EVERY:
            with self.engine.begin() as conn:
                conn.execute(update(user_sessions).where(user_sessions.c.token_digest == digest)
                             .values(last_seen_at=now, expires_at=now + SESSION_TTL))
        return user

    def revoke_session(self, token: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(user_sessions).where(user_sessions.c.token_digest == security.token_digest(token)))

    def revoke_user_sessions(self, user_id: int, keep_token: str | None = None) -> None:
        q = delete(user_sessions).where(user_sessions.c.user_id == user_id)
        if keep_token:
            q = q.where(user_sessions.c.token_digest != security.token_digest(keep_token))
        with self.engine.begin() as conn:
            conn.execute(q)

    # ── Brute-force throttle (shared by every API worker, kept across restarts) ──

    def failures_since(self, key: str, since: datetime) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(auth_failures)
                                    .where(auth_failures.c.key == key, auth_failures.c.ts >= since)).scalar() or 0)

    def record_failure(self, key: str, keep: timedelta = timedelta(days=1)) -> None:
        now = self.now()
        with self.engine.begin() as conn:
            conn.execute(auth_failures.insert().values(key=key[:200], ts=now))
            conn.execute(delete(auth_failures).where(auth_failures.c.ts < now - keep))

    def clear_failures(self, key: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(auth_failures).where(auth_failures.c.key == key))

    # ── First-run setup code ─────────────────────────────────────────────────

    def ensure_setup_code(self) -> str | None:
        """A fresh one-time code while no admin exists (logged at API start-up); None afterwards."""
        if self.has_admin():
            return None
        code = os.getenv("ADMIN_SETUP_CODE") or security.new_setup_code()
        self.set_meta("setup_code_digest", security.token_digest(security.normalize_code(code)))
        return code

    def check_setup_code(self, code: str) -> bool:
        expected = self.get_meta("setup_code_digest")
        return bool(expected) and security.token_digest(security.normalize_code(code)) == expected

    # ── Settings saved from the UI ───────────────────────────────────────────

    def setting_values(self) -> dict[str, object]:
        """Decoded values of every saved setting (secrets decrypted)."""
        out = {}
        cipher = self.cipher                     # first: may re-encrypt rows under a new SECRET_KEY
        with self.engine.connect() as conn:
            rows = conn.execute(select(app_settings)).all()
        for r in rows:
            try:
                raw = cipher.decrypt(r.value) if r.secret else r.value
            except ValueError:
                logger.warning("Saved secret %s can't be decrypted (SECRET_KEY changed?); re-enter it", r.key)
                continue
            out[r.key] = json.loads(raw)
        return out

    def setting_meta(self) -> dict[str, dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(app_settings.c.key, app_settings.c.updated_at, app_settings.c.updated_by)).all()
        return {r.key: {"updated_at": r.updated_at, "updated_by": r.updated_by} for r in rows}

    def set_setting(self, key: str, value: object, secret: bool, by: str | None) -> None:
        raw = json.dumps(value)
        stored = self.cipher.encrypt(raw) if secret else raw
        with self.engine.begin() as conn:
            done = conn.execute(update(app_settings).where(app_settings.c.key == key)
                                .values(value=stored, secret=int(secret), updated_at=self.now(), updated_by=by)).rowcount
            if not done:
                conn.execute(app_settings.insert().values(key=key, value=stored, secret=int(secret),
                                                          updated_at=self.now(), updated_by=by))

    def delete_setting(self, key: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(app_settings).where(app_settings.c.key == key))

    # ── Health results ───────────────────────────────────────────────────────

    def save_health(self, check_id: str, status: str, message: str, details: dict | None,
                    latency_ms: int | None, checked_at: datetime) -> None:
        values = dict(status=status, message=message[:1000], details=json.dumps(details or {}, default=str),
                      latency_ms=latency_ms, checked_at=checked_at)
        with self.engine.begin() as conn:
            done = conn.execute(update(health_checks).where(health_checks.c.check_id == check_id)
                                .values(**values)).rowcount
            if not done:
                conn.execute(health_checks.insert().values(check_id=check_id, **values))

    def health_results(self) -> dict[str, dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(health_checks)).all()
        return {r.check_id: {"status": r.status, "message": r.message, "details": json.loads(r.details or "{}"),
                             "latency_ms": r.latency_ms, "checked_at": _aware(r.checked_at).isoformat()}
                for r in rows}


def _aware(ts: datetime) -> datetime:
    """SQLite hands datetimes back naive; they were written in IST."""
    return ts.replace(tzinfo=IST) if ts.tzinfo is None else ts


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = security.hash_password(security.new_token())
    return _DUMMY_HASH


def _public(row) -> dict:
    return {"id": row.id, "username": row.username, "role": row.role, "full_name": row.full_name,
            "disabled": bool(row.disabled),
            "created_at": _aware(row.created_at).isoformat(),
            "last_login_at": _aware(row.last_login_at).isoformat() if row.last_login_at else None}

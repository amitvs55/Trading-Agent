"""The admin's emergency controls, shared by the API (writes) and the engine (reads).

- **Pause new signals:** the engine keeps managing open signals but sends no new ones.
- **Exit all:** every open signal is closed at the live bid (or cancelled if not yet filled),
  with a follow-up for each, once. The engine acknowledges the request so a restart never
  repeats it.

Both live in app_meta, so they work across the API and recorder processes and survive restarts.
"""

from datetime import datetime

CONTROL_KEY = "signals_control"        # {"paused", "paused_by", "paused_at", "reason", "exit_all_at", "exit_all_by"}
ACK_KEY = "signals_control_ack"        # {"exit_all_at": <the request handled last>}


def read(store) -> dict:
    return store.get_meta_json(CONTROL_KEY) or {"paused": False}


def set_paused(store, paused: bool, by: str, reason: str, now: datetime) -> dict:
    state = read(store)
    state.update(paused=paused, paused_by=by, paused_at=now.isoformat(), reason=(reason or "").strip()[:200])
    store.set_meta_json(CONTROL_KEY, state, now)
    return state


def request_exit_all(store, by: str, now: datetime) -> dict:
    state = read(store)
    state.update(exit_all_at=now.isoformat(), exit_all_by=by)
    store.set_meta_json(CONTROL_KEY, state, now)
    return state


def pending_exit_all(store) -> str | None:
    """The exit-all request not yet carried out, if any."""
    state = read(store)
    asked = state.get("exit_all_at")
    done = (store.get_meta_json(ACK_KEY) or {}).get("exit_all_at")
    return asked if asked and asked != done else None


def ack_exit_all(store, asked_at: str, now: datetime) -> None:
    store.set_meta_json(ACK_KEY, {"exit_all_at": asked_at, "done_at": now.isoformat()}, now)

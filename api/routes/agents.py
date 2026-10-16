"""Agents page: health of every signal agent (per index) and research agent, plus the self-test."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_cfg, get_repo, get_store, require_admin
from options.admin.health import recorder_status
from options.admin.repo import AdminRepo
from options.agents import health, selftest
from options.config import OptionsSettings
from options.core.calendar import now_ist
from options.storage import Store
from utils import agent_health

router = APIRouter(tags=["agents"])
RESEARCH_KEY = "research"


def _research(store: Store) -> list[dict]:
    saved = store.load_agent_status(RESEARCH_KEY) or {}
    live = agent_health.snapshot()                        # this process's runs, newer than what's saved
    rows = []
    for agent, label, stage in agent_health.RESEARCH_AGENTS:
        st = live.get(agent) or saved.get(agent) or {}
        rows.append({"id": agent, "label": label, "stage": stage, "status": st.get("status", "idle"),
                     "last_run_at": st.get("last_run_at"), "last_ok_at": st.get("last_ok_at"),
                     "seconds": st.get("seconds"), "error": st.get("error"), "runs": st.get("runs", 0),
                     "errors": st.get("errors", 0)})
    return rows


@router.get("/api/agents", dependencies=[Depends(require_admin)])
def agents(store: Store = Depends(get_store), repo: AdminRepo = Depends(get_repo),
           cfg: OptionsSettings = Depends(get_cfg)) -> dict:
    return {
        "now": now_ist().isoformat(timespec="seconds"),
        "catalog": health.describe(),
        "signal": {i: st for i in cfg.OPTIONS_INDICES if (st := store.load_agent_status(i))},
        "selftest": store.load_agent_status(selftest.SELFTEST_KEY),
        "research": _research(store),
        "recorder": recorder_status(repo),
        "openai_configured": bool(getattr(__import__("config.settings", fromlist=["settings"]).settings,
                                          "OPENAI_API_KEY", "")),
    }


@router.post("/api/admin/agents/selftest", dependencies=[Depends(require_admin)])
def run_selftest(store: Store = Depends(get_store), cfg: OptionsSettings = Depends(get_cfg)) -> dict:
    try:
        return selftest.run(store, cfg, now_ist())
    except Exception as e:
        raise HTTPException(500, {"code": "selftest_failed", "message": f"Self-test crashed: {type(e).__name__}: {e}"})


def install_research_sink(store: Store) -> None:
    """Persist research-agent outcomes so the Agents page survives redeploys (called at API start-up)."""
    agent_health.set_sink(lambda state: store.save_agent_status(RESEARCH_KEY, state, now_ist()),
                          initial=store.load_agent_status(RESEARCH_KEY))

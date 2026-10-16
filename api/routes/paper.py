"""Paper trading account (options/paper/ledger.py): read it, or reset it from the Paper page."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import current_user, get_cfg, get_repo, get_store, require_admin
from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.core.calendar import now_ist
from options.core.schemas import OPEN_STATES
from options.paper.ledger import DEFAULT_BALANCE, FOLLOW, PAPER_KEY, PaperSettings, build
from options.storage import Store

router = APIRouter(tags=["paper"])
MIN_BALANCE, MAX_BALANCE = 10_000, 100_000_000


def ensure_account(repo: AdminRepo, balance: float = DEFAULT_BALANCE) -> PaperSettings:
    """The account the Paper page shows; created (starting now) the first time it's needed."""
    raw = repo.get_meta_json(PAPER_KEY)
    if raw:
        return PaperSettings.from_meta(raw)
    st = PaperSettings(balance, now_ist(), "all")
    repo.set_meta_json(PAPER_KEY, st.to_meta())
    return st


class PaperBody(BaseModel):
    reset: bool = False
    starting_balance: float | None = Field(None, ge=MIN_BALANCE, le=MAX_BALANCE)
    follow: str | None = None


@router.get("/api/paper", dependencies=[Depends(current_user)])
def paper(store: Store = Depends(get_store), repo: AdminRepo = Depends(get_repo),
          cfg: OptionsSettings = Depends(get_cfg)) -> dict:
    st = ensure_account(repo)
    now = now_ist()
    signals = store.signals_since(st.started_at - timedelta(days=1))
    for s in store.open_signals():                 # positional signals opened earlier and still running
        if all(x.signal_id != s.signal_id for x in signals):
            signals.append(s)
    bids = {}
    for s in signals:
        if s.state in OPEN_STATES and s.fill_price and (bar := store.latest_bar(s.contract.token)):
            bids[s.signal_id] = bar.get("bid") or bar.get("close")
    return build(signals, st, cfg.OPTIONS_RISK_PER_TRADE_PCT, cfg.OPTIONS_DAILY_LOSS_STOP_PCT, bids, now)


@router.put("/api/admin/paper", dependencies=[Depends(require_admin)])
def update_paper(body: PaperBody, repo: AdminRepo = Depends(get_repo)) -> dict:
    st = ensure_account(repo)
    if body.follow is not None and body.follow not in FOLLOW:
        raise HTTPException(422, {"code": "invalid", "message": f"follow must be one of {', '.join(FOLLOW)}"})
    st = PaperSettings(body.starting_balance if body.starting_balance is not None else st.starting_balance,
                       now_ist() if body.reset else st.started_at, body.follow or st.follow)
    repo.set_meta_json(PAPER_KEY, st.to_meta())
    return {"ok": True, "settings": st.to_meta()}

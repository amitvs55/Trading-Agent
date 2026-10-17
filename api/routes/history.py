"""GET /api/history — research runs and their (simulated) trade decisions, newest first.

Read from the `research_runs` table. Records written to logs/trades.jsonl by older versions (or
by the command-line tool) are imported once at start-up by `import_legacy_log`.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query

from api.deps import get_store
from options.core.calendar import IST
from options.storage import Store
from utils.logger import setup_logger

logger = setup_logger("api.history")
router = APIRouter()

TRADE_LOG = Path(__file__).resolve().parents[2] / "logs" / "trades.jsonl"


def _iso(ts) -> str | None:
    if ts is None:
        return None
    return (ts.replace(tzinfo=IST) if ts.tzinfo is None else ts).isoformat()


def record(r: dict) -> dict:
    """One History row. The exchange comes from the run (the Yahoo suffix used to be stripped first,
    so every row said NSE), and the entry is the decision's entry price (it used to read a field that
    never existed, so every row showed a dash)."""
    usage = json.loads(r["usage"]) if r.get("usage") else None
    return {
        "run_id": r["run_id"], "order_id": r.get("order_id"), "ticker": r["ticker"], "exchange": r["exchange"],
        "status": r.get("order_status") or r["status"], "run_status": r["status"], "action": r.get("action"),
        "entry_price": r.get("entry"), "stop_loss": r.get("stop_loss"), "take_profit": r.get("take_profit"),
        "size_pct": r.get("size_pct"), "details": r.get("details") or r.get("error") or "",
        "logged_at": _iso(r.get("finished_at") or r["started_at"]), "started_at": _iso(r["started_at"]),
        "requested_by": r.get("requested_by"), "model": r.get("model"), "cost_usd": r.get("cost_usd"),
        "usage": usage,
    }


@router.get("/history")
def get_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ticker: str = Query("", max_length=24, description="Filter by ticker symbol"),
    status: str = Query("", max_length=24, description="Filter by status"),
    store: Store = Depends(get_store),
) -> dict:
    total, rows = store.research_runs(ticker=ticker, status=status, limit=limit, offset=offset)
    return {"total": total, "offset": offset, "limit": limit, "records": [record(r) for r in rows]}


def import_legacy_log(store: Store, path: Path = TRADE_LOG) -> int:
    """Copy records from the old JSONL ledger into research_runs (once per order id)."""
    if not path.exists() or os.environ.get("RESEARCH_IMPORT_LEGACY", "on") == "off":
        return 0
    added = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        order_id = str(rec.get("order_id") or "")[:16]
        if not order_id or store.research_has_order(order_id):
            continue
        ticker = str(rec.get("ticker") or "?")[:32]
        try:
            ts = datetime.fromisoformat(str(rec.get("logged_at")).replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.now(timezone.utc)
        usage = rec.get("usage") if isinstance(rec.get("usage"), dict) else None
        run_id = f"legacy{order_id}"[:16]
        store.research_start(run_id, ticker, "BSE" if ticker.upper().endswith(".BO") else "NSE", None,
                             (usage or {}).get("model") or "unknown", ts)
        store.research_finish(run_id, ts, status="done", order_status=rec.get("status"), order_id=order_id,
                              details=rec.get("details"), usage=json.dumps(usage) if usage else None,
                              cost_usd=(usage or {}).get("cost_usd"), total_tokens=(usage or {}).get("total_tokens"))
        added += 1
    if added:
        logger.info("Imported %d research record(s) from %s", added, path)
    return added

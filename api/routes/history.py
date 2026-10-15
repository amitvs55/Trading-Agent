"""GET /api/history — reads logs/trades.jsonl and returns trade records."""

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter()

TRADE_LOG = Path(__file__).resolve().parents[2] / "logs" / "trades.jsonl"


@router.get("/history")
async def get_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ticker: str = Query("", description="Filter by ticker symbol"),
    status: str = Query("", description="Filter by status"),
) -> dict:
    records: list[dict[str, Any]] = []

    if TRADE_LOG.exists():
        with open(TRADE_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Apply filters
    if ticker:
        records = [r for r in records if ticker.upper() in r.get("ticker", "").upper()]
    if status:
        records = [r for r in records if r.get("status", "").lower() == status.lower()]

    # Sort newest first by logged_at
    records.sort(key=lambda r: r.get("logged_at", ""), reverse=True)

    total = len(records)
    page = records[offset: offset + limit]

    return {"total": total, "offset": offset, "limit": limit, "records": page}

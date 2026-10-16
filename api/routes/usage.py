"""GET /api/usage — aggregates OpenAI token usage and USD cost from logs/trades.jsonl."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from config.settings import settings

router = APIRouter()

TRADE_LOG = Path(__file__).resolve().parents[2] / "logs" / "trades.jsonl"


def _empty() -> dict[str, Any]:
    return {"runs": 0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "cached_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}


def _add(bucket: dict[str, Any], usage: dict[str, Any]) -> None:
    bucket["runs"] += 1
    for key in ("calls", "prompt_tokens", "completion_tokens", "cached_tokens", "total_tokens"):
        bucket[key] += int(usage.get(key) or 0)
    bucket["cost_usd"] += float(usage.get("cost_usd") or 0.0)


def _finish(bucket: dict[str, Any]) -> dict[str, Any]:
    runs = bucket["runs"]
    return {
        **bucket,
        "cost_usd": round(bucket["cost_usd"], 6),
        "avg_cost_per_run": round(bucket["cost_usd"] / runs, 6) if runs else 0.0,
    }


def _parse_day(value: Any) -> date | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _read_records() -> list[dict[str, Any]]:
    if not TRADE_LOG.exists():
        return []
    records = []
    with open(TRADE_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


@router.get("/usage")
async def get_usage() -> dict:
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=6)
    month_start = today - timedelta(days=29)

    all_time, today_b, week_b = _empty(), _empty(), _empty()
    daily = {month_start + timedelta(days=i): _empty() for i in range(30)}
    by_agent: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    untracked_runs = 0

    for rec in _read_records():
        usage = rec.get("usage")
        if not isinstance(usage, dict):
            untracked_runs += 1
            continue

        _add(all_time, usage)
        day = _parse_day(rec.get("logged_at") or rec.get("timestamp"))
        if day is not None:
            if day == today:
                _add(today_b, usage)
            if day >= week_start:
                _add(week_b, usage)
            if day in daily:
                _add(daily[day], usage)

        model = str(usage.get("model") or "unknown")
        _add(by_model.setdefault(model, _empty()), usage)

        for agent, stats in (usage.get("by_agent") or {}).items():
            if not isinstance(stats, dict):
                continue
            bucket = by_agent.setdefault(agent, {"calls": 0, "total_tokens": 0, "cost_usd": 0.0})
            bucket["calls"] += int(stats.get("calls") or 0)
            bucket["total_tokens"] += int(stats.get("total_tokens") or 0)
            bucket["cost_usd"] += float(stats.get("cost_usd") or 0.0)

    agents = sorted(
        ({"agent": k, **v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_agent.items()),
        key=lambda a: a["cost_usd"],
        reverse=True,
    )

    return {
        "model": settings.MODEL_NAME,
        "all_time": _finish(all_time),
        "today": _finish(today_b),
        "last_7_days": _finish(week_b),
        "daily": [
            {"date": d.isoformat(), "cost_usd": round(b["cost_usd"], 6),
             "total_tokens": b["total_tokens"], "runs": b["runs"]}
            for d, b in sorted(daily.items())
        ],
        "by_agent": agents,
        "by_model": {k: _finish(v) for k, v in by_model.items()},
        "most_expensive_agent": agents[0] if agents else None,
        "untracked_runs": untracked_runs,
    }

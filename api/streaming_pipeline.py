"""StreamingPipeline — wraps TradingPipeline to emit SSE events at each stage."""

import asyncio
import json
from typing import Any

from orchestrator.pipeline import TradingPipeline


def _serialize(obj: Any) -> Any:
    """Recursively convert Pydantic models / enums to JSON-safe dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


class StreamingPipeline(TradingPipeline):
    """
    Subclass of TradingPipeline that pushes SSE events onto an asyncio.Queue
    as each stage starts and completes.  The pipeline methods run in a thread
    (via run_in_executor) so we use call_soon_threadsafe to post to the queue.
    """

    def __init__(self, ticker: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        super().__init__(ticker)
        self._q = queue
        self._loop = loop

    # ── internal helpers ──────────────────────────────────────────────────────

    def _emit(self, event: dict) -> None:
        self._loop.call_soon_threadsafe(self._q.put_nowait, event)

    # ── stage overrides ───────────────────────────────────────────────────────

    def _stage_data_collection(self) -> dict:
        self._emit({
            "stage": 1,
            "status": "running",
            "agents": ["market_data", "sentiment", "news", "fundamentals"],
        })
        result = super()._stage_data_collection()
        self._emit({
            "stage": 1,
            "status": "complete",
            "payload": {
                "market":       _serialize(result["market"]),
                "sentiment":    _serialize(result["sentiment"]),
                "news":         _serialize(result["news"]),
                "fundamentals": _serialize(result["fundamentals"]),
            },
        })
        return result

    def _stage_research(self, analyst_outputs: dict) -> tuple:
        self._emit({"stage": 2, "status": "running", "agents": ["bull_researcher", "bear_researcher", "moderator"]})
        bull, bear, verdict = super()._stage_research(analyst_outputs)
        self._emit({
            "stage": 2,
            "status": "complete",
            "payload": {
                "bull_case":      _serialize(bull),
                "bear_case":      _serialize(bear),
                "debate_verdict": _serialize(verdict),
            },
        })
        return bull, bear, verdict

    def _stage_trading(self, verdict, market_data) -> Any:
        self._emit({"stage": 3, "status": "running", "agents": ["trader"]})
        proposal = super()._stage_trading(verdict, market_data)
        self._emit({
            "stage": 3,
            "status": "complete",
            "payload": {"trade_proposal": _serialize(proposal)},
        })
        return proposal

    def _stage_risk(self, proposal) -> list:
        self._emit({"stage": 4, "status": "running", "agents": ["risk_aggressive", "risk_neutral", "risk_conservative"]})
        assessments = super()._stage_risk(proposal)
        self._emit({
            "stage": 4,
            "status": "complete",
            "payload": {"risk_assessments": _serialize(assessments)},
        })
        return assessments

    def _stage_decision(self, proposal, risk_assessments) -> Any:
        self._emit({"stage": 5, "status": "running", "agents": ["portfolio_manager"]})
        decision = super()._stage_decision(proposal, risk_assessments)
        self._emit({
            "stage": 5,
            "status": "complete",
            "payload": {"final_decision": _serialize(decision)},
        })
        return decision

    def _stage_execution(self, decision) -> Any:
        self._emit({"stage": 6, "status": "running", "agents": ["execution_engine"]})
        execution = super()._stage_execution(decision)
        self._emit({
            "stage": 6,
            "status": "complete",
            "payload": {"execution": _serialize(execution)},
        })
        return execution

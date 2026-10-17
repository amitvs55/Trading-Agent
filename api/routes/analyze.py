"""POST /api/analyze — runs the research pipeline and streams SSE events per stage.

Guard rails (review finding F-19):
- the ticker and exchange are validated before anything runs;
- at most RESEARCH_MAX_CONCURRENT runs at once, and none once today's spend reaches
  RESEARCH_DAILY_BUDGET_USD (both on the Connectors page, OpenAI card);
- when the browser goes away the run stops before its next stage instead of finishing unseen;
- every run is recorded in `research_runs` (History, Usage) with each LLM call's prompt and
  answer in `research_llm_calls`, so nothing is lost on a redeploy and any result can be audited.
"""

import asyncio
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import time
from typing import AsyncGenerator, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_store, require_admin
from api.streaming_pipeline import PipelineCancelled, StreamingPipeline, _serialize
from config.settings import settings
from options.core.calendar import at_ist, now_ist
from options.storage import Store
from utils.logger import setup_logger

logger = setup_logger("api.analyze")
router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)
_running = threading.Lock()
_active = 0


class AnalyzeRequest(BaseModel):
    # NSE/BSE symbols: letters, digits, & and -, optionally with the Yahoo suffix already on
    ticker: str = Field(min_length=1, max_length=24, pattern=r"^[A-Za-z0-9&\-]{1,20}(\.(NS|BO|ns|bo))?$")
    exchange: Literal["NSE", "BSE"] = "NSE"


def yahoo_symbol(ticker: str, exchange: str) -> str:
    t = ticker.upper()
    return t if "." in t else t + (".NS" if exchange == "NSE" else ".BO")


def _claim_slot() -> bool:
    global _active
    with _running:
        if _active >= max(1, settings.RESEARCH_MAX_CONCURRENT):
            return False
        _active += 1
        return True


def _release_slot() -> None:
    global _active
    with _running:
        _active = max(0, _active - 1)


def _record_result(store: Store, run_id: str, result) -> None:
    d, ex = result.final_decision, result.execution
    usage = result.usage.model_dump(mode="json") if result.usage else None
    store.research_finish(
        run_id, now_ist(), status="done", action=d.action, order_status=ex.status, order_id=ex.order_id,
        entry=d.final_entry, stop_loss=d.final_stop_loss, take_profit=d.final_take_profit,
        size_pct=d.final_position_size_pct, details=ex.details,
        model=(usage or {}).get("model") or settings.MODEL_NAME,
        total_tokens=(usage or {}).get("total_tokens"), cost_usd=(usage or {}).get("cost_usd"),
        usage=json.dumps(usage) if usage else None, decision=d.model_dump_json())


def _record_calls(store: Store, run_id: str, calls: list[dict]) -> None:
    try:
        store.research_log_calls([{**c, "run_id": run_id} for c in calls])
    except Exception:
        logger.exception("Couldn't save the LLM calls of run %s", run_id)


async def _event_stream(pipeline: StreamingPipeline, queue: asyncio.Queue, store: Store,
                        run_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE `data:` lines as the pipeline progresses."""
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(_executor, pipeline.run)
    finished = False
    try:
        yield f"data: {json.dumps({'run_id': run_id})}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.2)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                if future.done() and queue.empty():
                    break
        try:
            result = future.result()
        except Exception as exc:
            store.research_finish(run_id, now_ist(), status="failed", error=f"{type(exc).__name__}: {str(exc)[:500]}",
                                  cost_usd=pipeline.usage.summary().get("cost_usd"))
            finished = True
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return
        _record_result(store, run_id, result)
        finished = True
        yield f"data: {json.dumps({'done': True, 'run_id': run_id, 'full_result': _serialize(result)})}\n\n"
    finally:
        if not finished:
            # The browser went away (or the server is stopping): don't spend more on a run nobody sees
            pipeline.cancelled.set()
            try:
                await asyncio.wait_for(asyncio.shield(future), timeout=120)
            except PipelineCancelled:
                pass
            except Exception:
                logger.exception("Research run %s ended with an error after the client left", run_id)
            store.research_finish(run_id, now_ist(), status="cancelled", error="browser disconnected",
                                  cost_usd=pipeline.usage.summary().get("cost_usd"))
        _record_calls(store, run_id, pipeline.call_log)
        _release_slot()


@router.post("/analyze")
async def analyze(req: AnalyzeRequest, user: dict = Depends(require_admin),
                  store: Store = Depends(get_store)) -> StreamingResponse:
    now = now_ist()
    spent = store.research_cost_since(at_ist(now.date(), time(0)))
    budget = settings.RESEARCH_DAILY_BUDGET_USD
    if budget > 0 and spent >= budget:
        raise HTTPException(429, {"code": "daily_budget", "message":
                                  f"Today's research budget (${budget:.2f}) is used up (${spent:.2f} spent). "
                                  "It resets at midnight IST, or raise it on the Connectors page."})
    if not _claim_slot():
        raise HTTPException(429, {"code": "busy", "message": "Research runs are already in progress. "
                                  "Wait for one to finish, then try again."})
    run_id = uuid.uuid4().hex[:12]
    symbol = yahoo_symbol(req.ticker, req.exchange)
    try:
        store.research_start(run_id, symbol, req.exchange, user.get("username"), settings.MODEL_NAME, now)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        pipeline = StreamingPipeline(ticker=symbol, queue=queue, loop=loop)
    except Exception:
        _release_slot()
        raise
    return StreamingResponse(
        _event_stream(pipeline, queue, store, run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )

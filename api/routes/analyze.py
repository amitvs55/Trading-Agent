"""POST /api/analyze — runs the pipeline and streams SSE events per stage."""

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.streaming_pipeline import StreamingPipeline, _serialize

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)


class AnalyzeRequest(BaseModel):
    ticker: str
    exchange: str = "NSE"


async def _event_stream(ticker: str, exchange: str) -> AsyncGenerator[str, None]:
    """Yield SSE `data:` lines as the pipeline progresses."""
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    # Append .NS / .BO suffix for yfinance if not already present
    yf_ticker = ticker.upper()
    if "." not in yf_ticker:
        suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
        yf_ticker = yf_ticker + suffix

    pipeline = StreamingPipeline(ticker=yf_ticker, queue=queue, loop=loop)

    # Kick off blocking pipeline in thread pool
    future = loop.run_in_executor(_executor, pipeline.run)

    done = False
    while not done:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.2)
            yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            # Check if pipeline finished (future done) and queue drained
            if future.done() and queue.empty():
                done = True

    # Retrieve final result (or propagate exception)
    try:
        result = future.result()
        yield f"data: {json.dumps({'done': True, 'full_result': _serialize(result)})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"


@router.post("/analyze")
async def analyze(req: AnalyzeRequest) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(req.ticker, req.exchange),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

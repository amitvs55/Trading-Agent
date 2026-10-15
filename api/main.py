"""FastAPI application entry-point for the TradingAgents India dashboard."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.analyze import router as analyze_router
from api.routes.history import router as history_router
from api.routes.pricehistory import router as pricehistory_router

app = FastAPI(
    title="TradingAgents India API",
    description="Multi-agent LLM trading analysis pipeline — NSE/BSE",
    version="1.0.0",
)

import os

_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
_origins = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(pricehistory_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "TradingAgents India API"}

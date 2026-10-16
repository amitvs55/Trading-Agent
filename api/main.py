"""FastAPI application entry-point for the TradingAgents India dashboard."""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.deps import current_user, get_repo, get_store
from api.routes.admin import router as admin_router
from api.routes.agents import install_research_sink, router as agents_router
from api.routes.analyze import router as analyze_router
from api.routes.history import router as history_router
from api.routes.options import router as options_router
from api.routes.paper import ensure_account, router as paper_router
from api.routes.pricehistory import router as pricehistory_router
from api.routes.usage import router as usage_router
from options.admin.connectors import apply_research_overrides
from utils.logger import setup_logger

logger = setup_logger("api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        repo = get_repo()
        apply_research_overrides(repo)              # OpenAI key/model saved on the Connectors page
        if code := repo.ensure_setup_code():
            # Shown only while no admin exists: whoever reads the server logs can claim the account
            logger.warning("No admin account yet. Open the dashboard and create it with setup code: %s", code)
            print(f"ADMIN SETUP CODE: {code}", flush=True)
    except Exception:
        logger.exception("Admin start-up checks failed")
    try:
        repo = get_repo()
        ensure_account(repo)                        # the paper account counts from the first start-up
        install_research_sink(get_store())          # research agents' outcomes survive redeploys
    except Exception:
        logger.exception("Paper account / agent health start-up failed")
    yield


app = FastAPI(
    title="TradingAgents India API",
    description="Multi-agent LLM trading analysis pipeline — NSE/BSE",
    version="1.0.0",
    lifespan=lifespan,
)

_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
_origins = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=7200,           # browsers reuse a preflight for 2 h (Chrome's cap) instead of one per poll URL every 10 min
)
# JSON shrinks 5-10x; the research pipeline's event stream is excluded by Starlette (it must flush per event)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Everything except /health, the auth endpoints and the Kite login redirect needs a signed-in user
signed_in = [Depends(current_user)]
app.include_router(analyze_router, prefix="/api", dependencies=signed_in)
app.include_router(history_router, prefix="/api", dependencies=signed_in)
app.include_router(pricehistory_router, prefix="/api", dependencies=signed_in)
app.include_router(usage_router, prefix="/api", dependencies=signed_in)
app.include_router(options_router)  # /kite/* login flow + /api/options/* (signed-in)
app.include_router(admin_router)    # /api/auth/* + /api/admin/* (admin)
app.include_router(agents_router)   # /api/agents (signed-in) + /api/admin/agents/selftest
app.include_router(paper_router)    # /api/paper (signed-in) + /api/admin/paper


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "TradingAgents India API"}

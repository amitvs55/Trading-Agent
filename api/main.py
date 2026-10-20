"""FastAPI application entry-point for the TradingAgents India dashboard."""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from api.deps import base_settings, current_user, get_calendar, get_repo, get_store, require_admin
from api.routes.admin import router as admin_router
from api.routes.agents import install_research_sink, router as agents_router
from api.routes.analyze import router as analyze_router
from api.routes.check import router as check_router, start_warmer
from api.routes.desk import router as desk_router
from api.routes.history import import_legacy_log, router as history_router
from api.routes.options import router as options_router, stop_live_hub
from api.routes.paper import ensure_account, router as paper_router
from api.routes.pricehistory import router as pricehistory_router
from api.routes.usage import router as usage_router
from options.admin import watchdog
from options.admin.connectors import apply_research_overrides, effective_settings
from options.core.calendar import now_ist
from options.notify import make_notifier
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
        import_legacy_log(get_store())              # research runs from the old JSONL ledger, once
    except Exception:
        logger.exception("Paper account / agent health start-up failed")
    dog = None
    if os.getenv("WATCHDOG", "on").lower() not in ("0", "off", "false"):
        try:
            repo = get_repo()
            dog = watchdog.Watchdog(repo, get_store(),
                                    lambda text: make_notifier(effective_settings(repo, base_settings())).send(text),
                                    get_calendar)
            dog.start()                             # alerts if the recorder goes quiet in market hours
        except Exception:
            logger.exception("Recorder watchdog didn't start")
    warmer = None
    try:
        warmer = start_warmer(get_store, lambda: effective_settings(get_repo(), base_settings()))
    except Exception:
        logger.exception("Option Check warm-up didn't start")
    yield
    if dog:
        dog.stop()
    if warmer:
        warmer.set()
    stop_live_hub()


app = FastAPI(
    title="TradingAgents India API",
    description="Multi-agent LLM trading analysis pipeline — NSE/BSE",
    version="1.0.0",
    lifespan=lifespan,
)

_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
_origins = [o.strip() for o in _raw.split(",") if o.strip()]
if _ui := os.getenv("RAILWAY_SERVICE_UI_URL"):           # Railway provides the UI service's public domain
    _origins.append(f"https://{_ui}")

# Only this app's own UI may call the API from a browser (it used to trust every *.railway.app site,
# anyone's app included). The session travels in the Authorization header, never a cookie, so no
# credentials mode is needed either.
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(set(_origins)),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=7200,           # browsers reuse a preflight for 2 h (Chrome's cap) instead of one per poll URL every 10 min
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")     # signals and settings are never cached
    return response
# JSON shrinks 5-10x; the research pipeline's event stream is excluded by Starlette (it must flush per event)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Everything except /health, the auth endpoints and the Kite login redirect needs a signed-in user
# The research pipeline (it spends OpenAI credit), its history and its usage are for admins only;
# viewers get the signal pages: /api/options/*, /api/paper and their own /api/auth/* profile.
admins_only = [Depends(require_admin)]
app.include_router(analyze_router, prefix="/api", dependencies=admins_only)
app.include_router(history_router, prefix="/api", dependencies=admins_only)
app.include_router(pricehistory_router, prefix="/api", dependencies=admins_only)
app.include_router(usage_router, prefix="/api", dependencies=admins_only)
app.include_router(options_router)  # /kite/* login flow + /api/options/* (signed-in)
app.include_router(check_router)    # /api/options/check* (signed-in: admins and viewers)
app.include_router(admin_router)    # /api/auth/* + /api/admin/* (admin)
app.include_router(agents_router)   # /api/agents + /api/admin/agents/selftest (admin)
app.include_router(paper_router)    # /api/paper (signed-in) + /api/admin/paper
app.include_router(desk_router)     # /api/desk* (signed-in: each user's own paper trading desk)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "TradingAgents India API"}


@app.get("/health/recorder")
def health_recorder(repo=Depends(get_repo), store=Depends(get_store), cal=Depends(get_calendar)) -> JSONResponse:
    """Public, for an external uptime monitor: 503 while the recorder is down, hung or not running in
    market hours; 200 otherwise (including outside trading hours). Reveals no data or settings."""
    code, body = watchdog.status(repo, store, now_ist(), cal)
    return JSONResponse(body, status_code=code)

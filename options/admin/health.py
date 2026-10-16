"""Health checks for the system and every connector, run from the Connectors page.

Each check returns (status, message, details) with status ok | warn | fail | skip, is timed,
and its latest result is stored so the page shows it without re-running anything.
"""

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Callable

import requests
from sqlalchemy import text

from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.core.calendar import IST, NseCalendar, at_ist
from options.storage import Store

CHECK_TIMEOUT_S = 25
RECORDER_STALE_S = 120
DATA_STALE_S = 180

Result = tuple[str, str, dict]


@dataclass
class HealthContext:
    repo: AdminRepo
    store: Store
    cfg: OptionsSettings
    research: object                                  # config.settings.Settings (OpenAI key, model)
    now: datetime
    calendar: NseCalendar = field(default_factory=NseCalendar)
    angel_factory: Callable | None = None             # cfg → broker with login() / index_prices()
    kite_factory: Callable | None = None              # (cfg, access_token|None) → broker
    http: requests.Session = field(default_factory=requests.Session)
    openai_factory: Callable | None = None            # api_key → OpenAI-like client
    macro_probe: Callable[[], float] | None = None    # returns one global quote
    send_telegram_test: bool = False


def _market_open(ctx: HealthContext) -> bool:
    return ctx.calendar.is_market_open(ctx.now)


def recorder_status(repo: AdminRepo) -> dict | None:
    return repo.get_meta_json("recorder_status")


# ── System ───────────────────────────────────────────────────────────────────

def check_database(ctx: HealthContext) -> Result:
    with ctx.store.engine.connect() as conn:
        conn.execute(text("select 1"))
    bars = ctx.store.count_bars_since(at_ist(ctx.now.date(), dtime(0)))
    return "ok", f"Connected ({ctx.store.engine.dialect.name})", {"bars_today": bars}


def check_recorder(ctx: HealthContext) -> Result:
    st = recorder_status(ctx.repo)
    if not st:
        return "fail", "No heartbeat yet. Is the recorder service deployed and running?", {}
    seen = datetime.fromisoformat(st["ts"])
    age = (ctx.now - seen).total_seconds()
    details = {k: st.get(k) for k in ("state", "next_start", "session_started_at", "last_exit_code", "last_command")}
    if age > RECORDER_STALE_S:
        return "fail", f"Last heartbeat {age / 60:.0f} min ago. The recorder service looks down.", details
    if st.get("state") == "running":
        return "ok", "Running today's session", details
    nxt = st.get("next_start")
    when = datetime.fromisoformat(nxt).astimezone(IST).strftime("%a %d %b %H:%M") if nxt else "—"
    return "ok", f"Waiting · next session {when}", details


def check_market_data(ctx: HealthContext) -> Result:
    last = ctx.store.last_bar_ts()
    if last is None:
        return ("fail" if _market_open(ctx) else "warn"), "No market data recorded yet", {}
    last = last.replace(tzinfo=IST) if last.tzinfo is None else last
    age = (ctx.now - last).total_seconds()
    stamp = last.astimezone(IST).strftime("%d %b %H:%M")
    if _market_open(ctx):
        if age <= DATA_STALE_S:
            return "ok", f"Live · last bar {age:.0f}s ago", {"last_bar_at": last.isoformat()}
        return "fail", f"Market is open but the last bar is {age / 60:.0f} min old ({stamp})", {"last_bar_at": last.isoformat()}
    return "ok", f"Market closed · last data {stamp}", {"last_bar_at": last.isoformat()}


# ── Connectors ───────────────────────────────────────────────────────────────

def check_angel(ctx: HealthContext) -> Result:
    cfg = ctx.cfg
    in_use = cfg.provider == "angel"
    missing = [k for k in ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET") if not getattr(cfg, k)]
    if missing:
        return ("fail" if in_use else "skip"), (f"Missing {', '.join(missing)}" if in_use else "Not configured"), {}
    st = recorder_status(ctx.repo) or {}
    if in_use and _market_open(ctx) and st.get("state") == "running":
        return "skip", "The recorder is logged in and recording; the test is skipped during market hours so it " \
                       "doesn't open a second session", {}
    from options.brokers.angel import AngelBroker
    factory = ctx.angel_factory or (lambda c: AngelBroker(c.ANGEL_API_KEY, c.ANGEL_CLIENT_CODE, c.ANGEL_PIN,
                                                          c.ANGEL_TOTP_SECRET,
                                                          historical_api_key=c.ANGEL_HISTORICAL_API_KEY))
    broker = factory(cfg)
    client = broker.login()
    nifty = broker.index_prices(["NIFTY 50"])["NIFTY 50"]
    note = "" if in_use else " · not the active data provider"
    return "ok", f"Logged in as {client} · NIFTY 50 at {nifty:,.2f}{note}", {"client_code": client, "nifty": nifty}


def check_kite(ctx: HealthContext) -> Result:
    cfg = ctx.cfg
    in_use = cfg.provider == "kite"
    if not (cfg.KITE_API_KEY and cfg.KITE_API_SECRET):
        return ("fail" if in_use else "skip"), ("Missing KITE_API_KEY / KITE_API_SECRET" if in_use else "Not configured"), {}
    from options.brokers.kite import KiteBroker
    factory = ctx.kite_factory or (lambda c, token: KiteBroker(c.KITE_API_KEY, c.KITE_API_SECRET, token))
    token = ctx.store.load_access_token(ctx.now.date()) if in_use else None
    if not token or token == "auto-login":
        broker = factory(cfg, None)
        return ("warn" if in_use else "skip"), "Not logged in today", {"login_url": broker.login_url()}
    profile = factory(cfg, token).profile()
    return "ok", f"Logged in as {profile.get('user_name') or profile.get('user_id')}", {}


def check_telegram(ctx: HealthContext) -> Result:
    token, chat = ctx.cfg.TELEGRAM_BOT_TOKEN, ctx.cfg.TELEGRAM_CHAT_ID
    if not token or not chat:
        return "fail", "Missing bot token or chat ID: no alerts will be sent", {}
    try:
        resp = ctx.http.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
    except requests.RequestException as e:
        return "fail", f"Couldn't reach Telegram ({type(e).__name__})", {}       # never log the URL: it holds the token
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200 or not body.get("ok"):
        return "fail", f"Telegram rejected the bot token ({resp.status_code})", {}
    bot = body["result"].get("username", "bot")
    if ctx.send_telegram_test:
        from options.notify.telegram import TelegramNotifier
        sent = TelegramNotifier(token, chat, session=ctx.http).send(
            "✅ <b>Test message</b> from your TradingAgents Connectors page.")
        if not sent:
            return "fail", f"@{bot} is valid, but the message to chat {chat} failed. Has the chat started the bot?", {}
        return "ok", f"@{bot} · test message sent", {"bot": bot}
    return "ok", f"@{bot} is reachable", {"bot": bot}


def check_openai(ctx: HealthContext) -> Result:
    key = getattr(ctx.research, "OPENAI_API_KEY", "")
    model = getattr(ctx.research, "MODEL_NAME", "") or "gpt-4o-mini"
    if not key:
        return "warn", "No API key: the research pages won't run (options signals don't need it)", {}
    import openai

    client = (ctx.openai_factory or (lambda k: openai.OpenAI(api_key=k, timeout=15, max_retries=0)))(key)
    try:
        client.chat.completions.create(model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=1)
    except openai.AuthenticationError:
        return "fail", "The API key was rejected", {}
    except openai.RateLimitError as e:
        if "insufficient_quota" in str(e):
            return "fail", "The key works but the account has no credits (insufficient_quota)", {}
        return "warn", "Rate-limited right now; the key itself works", {}
    except openai.NotFoundError:
        return "fail", f"Model {model} isn't available to this key", {}
    return "ok", f"Key valid · {model} answered", {"model": model}


def check_macro(ctx: HealthContext) -> Result:
    def probe() -> float:
        import yfinance as yf
        return float(yf.Ticker("^N225").history(period="5d")["Close"].dropna().iloc[-1])

    value = (ctx.macro_probe or probe)()
    return "ok", f"Global quotes available (Nikkei {value:,.0f})", {}


CHECKS: dict[str, tuple[str, Callable[[HealthContext], Result]]] = {
    "database": ("Database", check_database),
    "recorder": ("Recorder service", check_recorder),
    "market_data": ("Market data feed", check_market_data),
    "angel": ("Angel One SmartAPI", check_angel),
    "kite": ("Zerodha Kite Connect", check_kite),
    "telegram": ("Telegram", check_telegram),
    "openai": ("OpenAI", check_openai),
    "macro": ("Global markets (Yahoo)", check_macro),
}


def _timed(ctx: HealthContext, check_id: str) -> dict:
    name, fn = CHECKS[check_id]
    started = time.perf_counter()
    try:
        status, message, details = fn(ctx)
    except Exception as e:
        status, message, details = "fail", f"{type(e).__name__}: {str(e)[:200]}", {}
    latency = int((time.perf_counter() - started) * 1000)
    return {"id": check_id, "name": name, "status": status, "message": message, "details": details,
            "latency_ms": latency, "checked_at": ctx.now.isoformat()}


def run_checks(ctx: HealthContext, ids: list[str] | None = None) -> list[dict]:
    ids = ids or list(CHECKS)
    unknown = [i for i in ids if i not in CHECKS]
    if unknown:
        raise KeyError(", ".join(unknown))
    pool = ThreadPoolExecutor(max_workers=len(ids))
    futures = {i: pool.submit(_timed, ctx, i) for i in ids}
    deadline = time.monotonic() + CHECK_TIMEOUT_S
    results = []
    for i, fut in futures.items():
        try:
            results.append(fut.result(timeout=max(0.0, deadline - time.monotonic())))
        except FuturesTimeout:
            results.append({"id": i, "name": CHECKS[i][0], "status": "fail",
                            "message": f"No answer within {CHECK_TIMEOUT_S}s", "details": {},
                            "latency_ms": CHECK_TIMEOUT_S * 1000, "checked_at": ctx.now.isoformat()})
    pool.shutdown(wait=False, cancel_futures=True)       # a hung check must not hold the response
    for r in results:
        ctx.repo.save_health(r["id"], r["status"], r["message"], r["details"], r["latency_ms"], ctx.now)
    return results

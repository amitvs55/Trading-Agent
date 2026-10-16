# Build progress — live NIFTY options signal tool

**Resume instruction for a new session:** read this file and `docs/index-options-plan.md`, then continue with the first unchecked item. Each item lists its files.

**Decisions locked in (16 Oct 2026):**
- **Broker:** Zerodha Kite Connect, data only, no orders.
- **Alerts:** Telegram. WhatsApp can be added later behind `options/notify`.
- **How to set up and deploy:** `docs/options-runbook.md`.
- **Scope:** NIFTY first. Intraday + positional, **buy-only** (BUY CE / BUY PE / EXIT).
- **Money:** capital ₹1 lakh, **risk 3% per trade, 10% daily loss stop**, always 1 lot.
- **Hosting:** Railway. `api` service (FastAPI), `ui` (Next.js), Postgres, and an always-on `recorder` (`SERVICE_ROLE=recorder` → `options/daemon.py`, which starts the session at 08:30 IST on trading days).
- **Frontend:** existing Next.js app in `ui/`. The user wants it polished ("perfect as heaven").
- **Testing:** Python 3.12 installed (user scope); run `.venv\Scripts\python -m pytest tests/options` (venv at repo root; already in .gitignore). Options tests: 120 passed (157 with the old app's tests). Synthetic market for tests: `tests/options/market.py`.

## Status legend
`[x]` written and tested · `[~]` written, tests written but not yet run · `[ ]` not started

## Phase A — Data foundation (plan weeks 1–2)
- [x] Settings — `options/config.py`
- [x] NSE calendar + 2026 holidays — `options/core/calendar.py`, `options/core/holidays.py`
- [x] Contract reference from the instrument dump — `options/reference.py`
- [x] Storage: sessions, instruments, 1m bars, events — `options/storage.py`
- [x] Tick → 1m bars — `options/market_data/bars.py`
- [x] Recorder (WebSocket, strike window, stale alerts) — `options/market_data/recorder.py`
- [x] Kite adapter — `options/brokers/kite.py`
- [x] Telegram notifier — `options/notify/`
- [x] Daily session runner — `options/session.py`
- [x] API: `/kite/login`, `/kite/callback`, `/api/options/status` — `api/routes/options.py`
- [x] Tests — `tests/options/test_{calendar,reference,bars,storage,telegram,recorder,session,routes}.py`
- [x] Black-76 IV and Greeks — `options/quant/black76.py`
- [x] Indicators (EMA, RSI, MACD, ATR, ADX, Supertrend, VWAP, CPR, swings) — `options/quant/indicators.py`
- [x] In-memory market state + resampling 1m → 5m/15m/60m; previous-day OHLC from Kite historical — `options/engine/state.py`

## Phase B — Analysis agents (12 pillars)
- [x] Technical: trend, levels, momentum — `options/agents/technical.py`
- [x] Futures & OI flow — `options/agents/futures_flow.py`
- [x] Option chain — `options/agents/option_chain.py`
- [x] Volatility & Greeks, option quality — `options/agents/volatility.py`
- [x] Constituents & breadth — `options/agents/breadth.py`
- [x] Global & macro (yfinance context; FII/DII optional) — `options/agents/macro.py`
- [x] Events calendar (+ optional news) — `options/agents/events.py`, dates in `options/core/events.py`
- [x] Regime & session gate — `options/agents/regime.py`

## Phase C — Signals
- [x] Setups S1 trend pullback, S2 ORB, S3 OI-wall break, P1 positional — `options/setups/`
- [x] Grading (12 pillars, gates, A/B/C) — `options/engine/grading.py`
- [x] Strike/expiry selection, levels, sizing (3%, over-budget flag), daily stop — `options/engine/selection.py`, `levels.py`, `risk.py`
- [x] Signal lifecycle + outcome tracking with full costs — `options/engine/lifecycle.py`, `costs.py`
- [x] Signal tables in storage; Telegram cards and updates; morning brief and EOD report — `options/delivery/`
- [x] Engine wired into the session (5m evaluation, tick-level exits)

**Phase C notes:** the engine is `options/engine/engine.py` (`SignalEngine`, hooked into the recorder through `on_bars` and `on_tick`). The session (`options/session.py`) loads 10 sessions of 1m history and ~1 year of daily data, then sends the morning brief and the end-of-day report. Every evaluation is logged to the `evaluations` table (the "why no trade" log). The latest pillars per index go to `board_state`.

## Phase D — Dashboard (Next.js, `ui/`)
- [x] API: board, signals, performance (+ SSE)
- [x] Pages: Live board, Signal detail, Performance, Status
- [x] Login protection for the dashboard (live NSE data must not be public)

**Phase D notes:**
- **Pages:** `ui/src/app/signals` (live board, open signals, decision log), `signals/[id]` (detail), `performance` (track record).
- **Shared code:** components in `ui/src/components/options/`, API client in `ui/src/lib/optionsApi.ts`.
- **Navbar:** now shows live board values; the old fake index prices are removed.
- **Login:** set `DASHBOARD_TOKEN` on the API; the UI asks for it once per browser.
- **Verified:** in the browser on desktop and a 375px phone; `npm run build` passes.

## Phase E — Validation and deploy
- [x] Replay harness over recorded bars through the live engine — `options/backtest/replay.py` (deterministic; separate output DB)
- [ ] Railway: Postgres, recorder cron service, environment variables (needs user approval)
- [ ] Shadow mode for 4–6 weeks, then LIVE per setup

## User setup still pending
- **Kite Connect:** create the app (Appendix A of the plan) and set `KITE_API_KEY`, `KITE_API_SECRET` and `KITE_USER_ID` on Railway.
- **Telegram:** create the bot (Appendix C of the plan) and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

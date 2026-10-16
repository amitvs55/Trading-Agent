# Build progress — live NIFTY options signal tool

**Resume instruction for a new session:** read this file and `docs/index-options-plan.md`, then continue with the first unchecked item. Each item lists its files.

**Decisions locked in (16 Oct 2026):**
- **Broker:** **Angel One SmartAPI** (free), data only, no orders. Switched from Kite on 16 Oct 2026 because Kite's data plan costs ₹500/month. `DATA_PROVIDER=angel` (default) or `kite`; both adapters hand data over in Kite's shapes, so nothing downstream knows which is in use.
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
- [x] Railway (16 Oct 2026): Postgres added; `recorder` service (always-on daemon, `SERVICE_ROLE=recorder`); `DATABASE_URL` wired to api and recorder; api, ui and recorder deployed and verified. **Secrets still to be set by the user** (see below).
- [x] Angel One adapter (16 Oct 2026) — `options/brokers/angel.py`, chosen by `options/brokers/make_broker`; automatic login (MPIN + TOTP, retries until 15:00) in `options/session.py`; status fields `data_provider*` in the API and the dashboard's connection chip. Tests: `tests/options/test_angel.py` and the auto-login cases in `test_session.py` (180 passing). Checked against Angel's live scrip master: NIFTY lot 65, step 50, weekly 19 Oct; BANKNIFTY lot 30, step 100; all 13 heavyweights found. **Not yet run against a live Angel login** (needs the user's credentials).
- [x] Deployed 16 Oct 2026 (16:15 IST): Angel adapter + admin/Connectors on api, recorder and ui. Verified: protected endpoints return 401 setup_required; the setup code is in the API logs; the recorder logs "database connected, next session Mon 19 Oct 08:30".
- [x] Admin account + Connectors page (16 Oct 2026). `options/admin/` holds security (PBKDF2 passwords, session tokens, Fernet encryption), the repo (users, sessions, settings, meta, health) and connectors (registry, effective settings = env + UI, trading rules). It also holds `health.py` with 8 checks. API: `api/deps.py` (current_user/require_admin; every page needs a session) and `api/routes/admin.py` (setup with a one-time code printed in the API logs, login with throttling, password, connectors, data provider, trading rules, health, recorder restart). The recorder daemon became a supervisor with a heartbeat and a restart command. UI: `components/auth/AuthGate.tsx` (setup and login screens), `app/connectors`, `components/connectors/*`, and a user menu in the navbar. The old DASHBOARD_TOKEN gate is gone; that variable still works as a static API token. Tests: `tests/options/test_admin.py` and `test_daemon.py` (206 passing). Verified in the browser: setup, health run, saving a connector, trading rules, sign-out and sign-in, phone width.
- [x] Only correct values reach the database (16 Oct 2026). `options/admin/validation.py` tidies and checks every connector value (MPIN 4 digits, TOTP secret base32 with spaces removed, numeric Telegram chat ID, bot token shape, sk- keys, and so on), with plain-language reasons. A save is checked first, then tested live with the new values (`connectors.preview_settings`); a failed test stores nothing unless the admin presses **Save anyway**. Bad values saved earlier are flagged under their field. The health checks run the same format checks before calling a service, and the Telegram check now looks the chat up (getChat). Tests: 222 passing.
- [x] Smooth UI, no flicker (17 Oct 2026). Measured on a production build first. Fonts self-hosted via next/font (metric-matched fallbacks, no Google CSS import). The server sends the real layout instead of a "Loading…" splash: AuthGate renders pages at once with a saved session, and an inline script hides the shell before paint when there is none. Page data loads in parallel with /api/auth/me instead of after it, and other pages' data is prefetched when the browser is idle, so navigation renders in ~35 ms. One SWRConfig (keepPreviousData; deep compare means an unchanged poll renders nothing). Skeletons match the real layout (CLS 0). Inline error banners are replaced by one floating "Reconnecting…" notice (`lib/connection.ts`). Memoised board and signal cards, with the level row moved to module level: polling went from 24 DOM nodes rebuilt per 16 s to 0. Fixed a sign-in bug where a cached rejection signed out the next session. API: gzip and a 2 h CORS preflight cache. Deployed 17 Oct 2026.
- [x] Moved all Railway services to Singapore (17 Oct 2026). api, ui, Postgres and recorder went from us-east4 (Virginia) to `asia-southeast1-eqsg3a`, using `railway scale --service <svc> asia-southeast1-eqsg3a=1 us-east4-eqdc4a=0` (Railway CLI 5.69; 4.33's `scale` crashes). Postgres's 192 MB volume migrated with a few minutes of downtime; the admin account and settings survived. Measured from the user's network, an API call on a reused connection went from ~0.45 s to ~0.1 s, and the first byte of a UI page from 0.8–1.6 s to 0.3–0.5 s. The recorder is now next door to Angel One's servers in India.
- [x] **Phase F (17 Oct 2026: "build all four and deploy")**. Defaults: the paper account follows ALL signals, starts at ₹1,00,000, and the Agents page includes the research agents.
  - [x] F1 Live IST clock in the navbar on every page (`lib/clock.ts`, `LiveClock.tsx`). One shared second-aligned ticker, server-synced via public `/api/time`, with an NSE open/close countdown from `market_opens_at`/`market_closes_at` on /api/options/status. "x ago" labels tick live (`components/common/LiveAge.tsx`). Only the clock's DOM changes each second (verified).
  - [x] F2 Agent health. `options/agents/health.py`: each agent in `snapshot.take` runs in `guard`; a failure degrades its pillar to n/a, and the engine sends no new signal while any agent fails (open trades still managed). A technical failure raises `SnapshotError`. `AgentTracker` alerts on Telegram after 2 consecutive failures, and again on recovery. Status per index is in the `agent_status` table. `options/agents/selftest.py` replays the first 45 min of the last recorded day (`replay_day(until=)`) or runs on `options/backtest/synthetic.py` (moved from the tests). Research agents are tracked by wrapping every `run` (`utils/agent_health.py`, persisted by the API sink). `/api/agents`, `POST /api/admin/agents/selftest`, `/agents` page.
  - [x] F3 Confidence: `options/engine/confidence.py` (per-pillar points that add up to the score, level, strengths and weaknesses, grade-band track record, shown only once 20+ trades exist). Added to every signal in the API (`confidence`), as a meter and "Why" breakdown on the signal card, a full section on the detail page, and one line on the Telegram card.
  - [x] F4 Paper account: `options/paper/ledger.py` rebuilds it from signals on every request (engine sizing at paper balance, daily stop, cash check, per-trade rounding identical to the track record). Settings in app_meta `paper_account`, created at API start-up. `/api/paper`, `PUT /api/admin/paper` (reset, balance, follow all/A). `/paper` page.
  - [x] F5 237 tests passing. Browser-checked on a production build: 0 extra DOM changes while the clock ticks, no horizontal overflow at 375 px, all 8 nav links fit at 1280 px. Deployed 17 Oct 2026.
- [x] User accounts (17 Oct 2026, asked: "create a user account, like my account as Amit Shinde"). `users` gained `full_name` and `disabled` (added in place to the existing Postgres table by `storage._add_missing_columns`). Roles: admin and viewer (viewers see every page but every /api/admin/* call is refused). Repo: list/create/update/delete, with guards so the last active admin can't be demoted, disabled or deleted; disabled users can't sign in and lose their sessions. API: `GET/POST /api/admin/users`, `PATCH/DELETE /api/admin/users/{id}`, `POST /api/admin/users/{id}/password`, `PATCH /api/auth/profile`. UI: `/account` (profile name, password, users list with add/edit/disable/reset/delete); the navbar shows initials and full name. Tests: `tests/options/test_users.py` (240 passing). The user creates their own account in the UI (passwords are never chosen by the assistant).
- [x] Viewer access + mobile-first UI (17 Oct 2026). Asked: "for viewers why all pages are showing" and "not mobile responsive, I want enterprise level". Viewers get Signals, Paper, Performance and their account. Research (it spends OpenAI credit), History, Usage, Agents and Connectors are admin-only in the API (`api/main.py` routers use `require_admin`; `/api/agents` too) and in the UI (`components/layout/nav.ts` role-aware nav, `RouteGuard` sends viewers from / to /signals and shows an admins-only screen elsewhere; setup links are hidden). Tests: `tests/options/test_access.py`. Mobile: below lg a native-style bottom tab bar plus a "More" sheet (`MobileNav.tsx`), with safe-area insets and viewport-fit=cover. Every wide table has a card layout on phones (Performance, Paper, decision log, research agents, trade history; the 9-column ones until lg). Inputs are 16px below lg (no iOS zoom), touch controls are at least 40px, and the research form, progress strip and stage grids are fixed for phones. Installable app: `app/manifest.ts` plus icons drawn by `ui/scripts/make_icons.py` into ui/public (the Dockerfile now copies public/). Audited on a production build: all 9 pages at 320 and 375 px have no horizontal overflow, no sideways table scroll, no control under 40px and no zooming inputs; 768 and 1440 checked too. 256 tests passing.
- [ ] Shadow mode for 4–6 weeks, then LIVE per setup

## User setup still pending
- Done 16 Oct 2026: admin account created; Angel One connected on the Connectors page (health check logs in).
- **Telegram:** bot token saved; the Chat ID must be the user's numeric Telegram ID (from @userinfobot), not the bot's username. Then press **Send test message**.
- **Before 1 Dec 2026:** set Builder = Dockerfile (and Healthcheck = /health on `api`) in the dashboard for `api` and `ui`, because railway.json stops working then (runbook §8).
- **Rotate the OpenAI API key:** a Railway config dump printed it into the 16 Oct session log.
- **Kite Connect (optional, later):** only if switching back with `DATA_PROVIDER=kite`.
- **Telegram:** create the bot (Appendix C of the plan) and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

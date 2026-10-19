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
- [x] Viewer access + mobile-first UI (17 Oct 2026). Asked: "for viewers why all pages are showing" and "not mobile responsive, I want enterprise level". Viewers get Signals, Paper, Performance and their account. Research (it spends OpenAI credit), History, Usage, Agents and Connectors are admin-only in the API (`api/main.py` routers use `require_admin`; `/api/agents` too) and in the UI (`components/layout/nav.ts` role-aware nav, `RouteGuard` sends viewers from / to /signals and shows an admins-only screen elsewhere; setup links are hidden). Tests: `tests/options/test_access.py`. Mobile: below lg a native-style bottom tab bar plus a "More" sheet (`MobileNav.tsx`), with safe-area insets and viewport-fit=cover. Every wide table has a card layout on phones (Performance, Paper, decision log, research agents, trade history; the 9-column ones until lg). Inputs are 16px below lg (no iOS zoom), touch controls are at least 40px, and the research form, progress strip and stage grids are fixed for phones. Installable app: `app/manifest.ts` plus icons drawn by `ui/scripts/make_icons.py` into ui/public (the Dockerfile now copies public/). Audited on a production build: all 9 pages at 320 and 375 px have no horizontal overflow, no sideways table scroll, no control under 40px and no zooming inputs; 768 and 1440 checked too. 255 tests passing.
- [ ] Shadow mode for 4–6 weeks, then LIVE per setup

## Phase G — Production hardening (from docs/review/, started 17 Oct 2026)

The user asked: "use that report and build what is missing, production grade". The work follows the roadmap in `docs/review/PLATFORM_REVIEW.md` §9 and `docs/review/backlog.csv` (R-01…R-32). R-25 (setups S4–S7) and R-26 (BANKNIFTY/FINNIFTY) are deliberately not built: the report gates them on S1–S3 passing the evidence bar first. R-07's operational half (setting SECRET_KEY on Railway and rotating the OpenAI key) is the user's to do.

**Stage 1: Stabilize (done, 290 tests passing):**
- [x] R-01 Auto-restart a crashed session. `options/daemon.py`: restarts after 30 s, 2 min, then 5 min (at most 3 a day, until 15:20) and alerts on each restart and on giving up. A container started after 15:00 still runs a short session while intraday signals are open. Session exit codes: 0 ok, 1 crash, 2 keys missing, 3 login failed.
- [x] R-02 Durable, non-blocking alerts. `options/notify/outbox.py` (`alerts_outbox` table, in-order sender thread, backoff for up to 15 min, duplicate guard, recovery after a restart) and `options/notify/email.py` (SMTP fallback, new "E-mail (SMTP)" connector). The session drains the outbox before it exits.
- [x] R-03 Watchdog. `options/admin/watchdog.py` runs in the API, once a minute in trading hours. It alerts once when the heartbeat is lost, the session isn't running, or no bar was saved for 3 minutes, and again on recovery. Public `/health/recorder` (200/503) is there for an external uptime monitor. `WATCHDOG=off` disables it (local demo, tests).
- [x] R-04 Warm-up history. Each request is tried 3 times; a `HistoryReport` goes into the morning brief, with a Telegram warning on failure. History is 20 sessions, and the indicator guards are 100 bars (above convergence). Warm-up candles are now saved to `bars_1m` (insert-if-missing), so replays warm up like the live engine.
- [x] R-05 The duplicate-signal keys are rebuilt from today's `evaluations` when the engine starts.
- [x] R-06 Kill switch. `options/engine/controls.py` gives "pause new signals" (everyone sees a chip on Signals) and "exit all" (carried out once, acknowledged). It is on the new admin **Operations** page.
- [x] R-08 Calendars editable from the UI. `options/core/calendar_store.py` handles holidays and events, with a warning when next year's holiday list is missing. API is under `/api/admin/calendar/*`.
- [x] R-10 Auto-demote: a LIVE setup whose last 30 trades average ≤ ₹0 after costs goes back to SHADOW. It is alerted and written to the audit log.
- [x] R-19 (part): a `bars_1m(ts)` index (created on existing tables too), retention (`OPTIONS_BARS_RETENTION_DAYS`, default 730, editable in Trading rules), a minutes-recorded line in the EOD summary, and `session_events` shown on Operations.
- [x] R-32 LIVE cards carry broker-stop guidance: an SL-limit order with trigger and limit (NSE doesn't accept SL-M on options), or a GTT for positional trades. Follow-ups say to move the stop up after T1 and to exit and cancel after an exit.
- [x] Audit log (`audit_log`): trading rules, pauses, exit-all, connectors, users, calendar edits, restarts and auto-demotions. Shown as the change log on Operations.
- [x] Health checks added: e-mail, alert delivery (last 24 h), trading calendar. The recorder check reports restarts and giving up.
- [x] R-20 (most): muted text moved to #8391a7, which passes 4.5:1 on every surface. Selects are labelled, charts have `role="img"`, inline links are underlined, Signal detail has an h1, focus rings are on form controls, and icon buttons are 28 px. axe goes from 1,274 nodes to 0 serious or critical on all 11 pages at 375 and 1440 px. The navbar shows only what fits and puts the rest under "More", so there is no overflow at 1024 px.
- Tests: `tests/options/test_hardening.py` and `tests/options/test_ops_api.py`. `tests/conftest.py` now points the default DATABASE_URL at a temp file, so no test can touch `data/`.

**Stage 2: Complete (done):**
- [x] R-11 Research runs in Postgres. `research_runs` replaces `logs/trades.jsonl` (the old file is imported once at start-up). History has real Entry and Exchange values, stop/target, server-side search and filter, and a CSV export guarded against formula injection; Usage counts IST days.
- [x] R-12 News pillar. `options/agents/news_feed.py` polls the RBI press-release RSS every 2 min. Rule-based classification: a high-impact release (policy rate, CRR/SLR, Governor's statement) blocks entries for 15 min through the `no_fresh_news` gate; medium is a warning; routine items are ignored. Headlines never reach an LLM.
- [x] R-13 Branded `not-found.tsx`, `error.tsx` and `global-error.tsx`. RouteGuard waits for the role on admin pages (no 403, no flash).
- [x] R-14 `/api/analyze` validates ticker and exchange, caps concurrent runs (2), enforces a daily USD budget (editable on the OpenAI card) and stops between stages when the browser disconnects. Every run and every LLM call (prompt, response, model snapshot, seed) is stored. `/api/pricehistory` is a sync def with validated input.
- [x] Production bug fixed (17 Oct 2026, reported from the phone): "cannot access local variable 'e'". The agent retry path (`agents/base.py`) used the exception variable after its block; it now retries only malformed output (ValueError/TypeError), not API errors.

**Stage 3: Strengthen (done):**
- [x] R-15 Proxy historical backtest, `options/backtest/proxy.py`. NIFTY spot and VIX minutes, future at fair value, options repriced by Black-76 at VIX IV, constant OI (OI pillars neutral, S3 can't fire), NSE expiry rules (Thursday→Tuesday on 1 Sep 2025). It is fed through the live engine via replay. `fetch` (needs the Angel credentials and the user's go-ahead) and `run --save` (report on Performance, `/api/options/backtest`). It found a live bug: a signal could "fill" after the premium had already fallen through the stop. Fixed in `lifecycle.on_quote` (cancelled instead).
- [x] R-16 `options/engine/statistics.py`: 95% CI of avg R, t-stat, trades still needed, Sharpe/Sortino on daily P&L, PSR/DSR across setups, NIFTY benchmark. Shown on Performance as "Is the edge real?", with "too few trades" honesty below 20.
- [x] R-17 Calibration (score bands, pillar lift) on Performance. `options/backtest/ablation.py` re-runs the backtest without each pillar.
- [x] R-18 LLM: one retry layer (transient errors only), timeout 60 s, temperature 0, seed 7, model default `gpt-4o-mini-2024-07-18`, full call log (`research_llm_calls`, 90-day retention). Sentiment uses only the given headlines. Headlines are cleaned and fenced as `<untrusted_data>`. Research RSI is Wilder's. Not done: a with/without-debate ablation (needs paid LLM runs).
- [x] R-19 Bad-tick guard: index/futures ticks more than 5% from the last (VIX 25%) are dropped unless 3 agree. `rejected_ticks` is in the EOD summary.
- [x] R-20/R-21 Accessibility and layout shift. axe shows 0 serious/critical on all pages, and CLS ≤ 0.1 on every page at 375/768/1440 (content area at least one screen tall; a pre-paint role marker `role-admin` on `<html>` for role-only placeholders; real tiles as skeletons).

**Stage 4: Scale (started):**
- [x] R-23 (UI half): Next 16.4.2 + React 19.3.1 (clears every open Next advisory, including two RCEs), exact pins, `npm ci` in `ui/Dockerfile`, ESLint 9 flat config (`npm run lint`, 0 problems), type errors fail the build. The Signal detail page uses `useParams` (params is a Promise in Next 16).
- [x] R-27 (half): e-mail fallback channel.
- [x] R-32 Broker-stop guidance.

**Deployed 17 Oct 2026 (commit 1943072)** to api, recorder and ui. Checked: /health 200, /health/recorder ok (waiting for Mon 19 Oct 08:30), the new endpoints answer 401 (they need a login), every UI page returns 200 and an unknown URL gets the branded 404, a research run completed in production, and the start-up logs are clean. 322 tests passing.

**Second batch (17 Oct 2026, after "continue"): the remaining list is built:**
- [x] R-09 OI units: `selection.oi_unit()` reads shares vs contracts from the chain (multiples of the lot, size) and converts contracts before the MIN_OI check. The board stores `oi_unit`, and the market-data health check shows it during market hours.
- [x] R-22 CI: `.github/workflows/ci.yml` runs backend pytest with coverage ≥ 85% (currently 89%), UI lint, build and typecheck, then Playwright E2E. pip-audit and npm audit report but don't block.
- [x] R-23 (Python half): `requirements.lock` holds exact versions from the tested venv (Windows-only packages removed, uvloop added for Linux), and the Dockerfile installs from it. `requirements-dev.txt` adds pytest-cov and pip-audit. kiteconnect stays, so its old autobahn/twisted pins remain (reported by pip-audit).
- [x] R-24: CSP (connect-src limited to the site and the API), HSTS, X-Frame-Options, nosniff, Referrer- and Permissions-Policy on the UI (production only). The API trusts only `ALLOWED_ORIGINS` plus `RAILWAY_SERVICE_UI_URL`, without credentials mode, and sends nosniff, DENY, no-referrer and no-store. The login and setup throttle lives in Postgres (`auth_failures`): 5 failures per IP+user (right-most X-Forwarded-For) and 20 per user per 15 min. Not done: cookie sessions (they would need a same-origin proxy).
- [x] R-27 Shock detector: `options/agents/shock.py` makes the `no_market_shock` gate fire on a ≥ 5σ one-minute move in the future (same session) or VIX up ≥ 10% in 15 min, then blocks entries for 15 min.
- [x] R-28 Metrics: `session_metrics` stores one row a minute (ticks, bars, bad ticks, slowest evaluation, slowest alert delivery, open signals) via `options/market_data/metrics.py`. An alert fires on an evaluation over 2 s (once an hour). The Operations page has a metrics panel and `/api/admin/metrics`.
- [x] R-29 Root `README.md`. R-31: a viewer account needs a personal-use confirmation (API 422 without it, recorded in the audit log).
- [x] R-30 Playwright E2E (`ui/e2e`, `npm run e2e`): seeds a throwaway SQLite database and runs the real API plus a production UI build. Flows: sign-in, the signal record, pause and resume, viewer limits, the 404, and an axe gate, on desktop and phone (8 tests). Locally it runs on Edge. It found and fixed: the red "paused" title contrast, the account-menu and logo label-in-name mismatches, and a non-focusable scroll area.
- [x] Review docs updated: `docs/review/PLATFORM_REVIEW.md` §0 lists what is resolved and what is open; the SL-M wording is corrected (SL-limit or GTT).
- **Deployed 17 Oct 2026 (commit 6f5d8ee).** Checked: health 200; the recorder is waiting for Mon 19 Oct 08:30; CORS lets the UI in and refuses another railway.app origin (400); CSP connect-src includes the API; HSTS and nosniff/DENY are present; clean start-ups on Next 16.4.2 and the lockfile build.
- Not built: a with/without-debate LLM ablation (needs paid runs), and R-25/R-26 (held back until S1–S3 show an edge).

**Needs the user:** set `SECRET_KEY` on Railway api AND recorder at the same moment (outside market hours; secrets are re-encrypted automatically). Rotate the OpenAI key. Say yes or no to downloading 2 years of NIFTY/VIX history from Angel for the backtest. Optional: set up the E-mail (SMTP) connector, and point an uptime monitor at `/health/recorder`.

## Live incidents
- **19 Oct 2026, history refused (commits 5b75f43, d45ed4e).** 08:30: the futures OI-history call failed and took the futures candles with it. After the 09:33 restart, every Angel history request failed with SmartAPI `DataException`. Its body: `b'Access denied because of exceeding access rate'`, i.e. Angel's history rate limit. The live feed was unaffected. No separate historical key is configured; history uses the main login. Fixes:
  - OI history is optional, with a 7-day chunk fallback.
  - 1-minute warm-up comes from our own `bars_1m` first, so a restart makes no minute requests.
  - Refused futures get a spot+basis stand-in, held in memory only.
  - The main login takes over if a separate history key fails.
  - Previous closes fall back to the last session's saved bars. On 19 Oct there were none for the heavyweights, so breadth waits.
  - Failed series are retried every 10 minutes.
  - Angel's reply is now logged.
  - Deployed 10:02 IST: "History: 4/5 loaded", missing only India VIX daily; the 10:05 check ran clean.
  - Follow-ups done the same day:
    - Previous closes also come from the quote API in market hours (`CloseKeeper`, d0b731f).
    - Every Angel history request goes through one gate, `HISTORY_GAP_S` = 1 s after the previous one ends (570c8b9).
    - The previous-close requests run after recording starts.
    - The branch is pushed, so CI runs on every push.

## Live NIFTY 50 + SENSEX ticker (19 Oct 2026)
Requirement: smooth, no lag, no time mismatch.

**Path from tick to screen, with no polling:**
- **Recorder:** `options/market_data/live.py` `LiveIndexFeed` takes every accepted index tick on the WebSocket thread. SENSEX comes over the BSE channel (`BSE_OFFSET` = 3e9, exchange type 3, token from the scrip master with fallback 99919000). The NIFTY future is included so the Signals card's spot, future and basis come from the same moment. A publisher thread sends on the leading edge, at most 4 a second, coalescing bursts. `Store.publish_live` saves `app_meta.live_indices` (once a second) and runs `pg_notify('live_indices')` on Postgres.
- **API:** `api/live.py` `LiveHub` uses one LISTEN thread per process. Each stream has a one-slot mailbox, so the newest update wins and nothing backs up. On SQLite, or while the listener reconnects, it reads the saved copy every 250 ms.
  - `GET /api/options/live/indices` returns the snapshot.
  - `GET /api/options/live/indices/stream` is SSE: `levels`, `ping` every 15 s, and `bye` after 10 min, so no proxy cuts it mid-update.
- **UI:**
  - `ui/src/lib/liveIndices.ts` keeps one shared fetch stream (authenticated) and repaints on animation frames.
  - A level never goes backwards (exchange timestamps).
  - Reconnect backoff is 0.5–5 s; after 3 failures it polls every second. A hidden tab closes the stream.
  - The last levels are cached in localStorage for an instant first paint, shown dimmed until live.
  - `components/layout/LiveTicker.tsx`: a fixed-height strip under the navbar at every width. It was briefly inline in the bar at 2xl, where it covered the logo and Signals for admins; that was fixed in a330246, guarded by E2E `nav.spec.ts`. Against an API without the feed (404), the strip stays hidden from the first paint (`html.live-off`) and checks again each minute. Digits are tabular with fixed widths, and changes flash with CSS only.

**Time:** the "as of" time is the exchange's. Live, delayed (> 5 s) and stale (> 60 s) are judged with the server-synced clock (`lib/clock.ts`). Open and closed flip at 09:15:00 and 15:30:00 from `market_window` times.

**Previous close (fixed per session):** `CloseKeeper` takes it from the quote API in market hours, checked against ltp − net change. Otherwise it comes from the previous session's last saved bar. The same keeper fills the breadth heavyweights' missing previous closes. At 15:36 the session publishes the official closing levels.

**Other fixes:**
- "Market data 78s ago" counted from the bar's start. It now counts from the last tick, or the bar's end, and reads "live".
- `session_metrics.live_lag_ms` holds the p95 delay from exchange tick to push, and the Operations panel shows it.

**Tests:** `tests/options/test_live.py`, plus E2E `ui/e2e/live.spec.ts`, which checks updates in place with zero layout shift and runs axe.

## User setup still pending
- Done 16 Oct 2026: admin account created; Angel One connected on the Connectors page (health check logs in).
- **Telegram:** bot token saved; the Chat ID must be the user's numeric Telegram ID (from @userinfobot), not the bot's username. Then press **Send test message**.
- **Before 1 Dec 2026:** set Builder = Dockerfile (and Healthcheck = /health on `api`) in the dashboard for `api` and `ui`, because railway.json stops working then (runbook §8).
- **Rotate the OpenAI API key:** a Railway config dump printed it into the 16 Oct session log.
- **Kite Connect (optional, later):** only if switching back with `DATA_PROVIDER=kite`.
- **Telegram:** create the bot (Appendix C of the plan) and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

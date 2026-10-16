# Options signal tool — runbook

How to set up, deploy, run and validate the live NIFTY options signal tool. The design is in [index-options-plan.md](index-options-plan.md); build status is in [build-progress.md](build-progress.md).

> Personal research tool, not investment advice. Keep the signals to yourself: sharing them with others needs SEBI Research Analyst registration.

## 1. What runs where

```
 Railway project "trading-agent"
 ┌──────────────────────────┐   writes bars, signals, board   ┌────────────┐
 │ recorder (always on)     │ ───────────────────────────────▶│  Postgres  │
 │ python -m options.daemon │                                 └─────┬──────┘
 │ session 08:30–15:31 IST  │◀── Kite WebSocket + REST              │ reads
 │ sends Telegram messages  │                                       ▼
 └──────────────────────────┘                          ┌──────────────────────────┐
                                                       │ api (FastAPI)            │
   You ── Telegram ── tap "Login to Kite" ───────────▶ │ /kite/login, /kite/callback│
   You ── browser ──▶ ui (Next.js) ── /api/options/* ▶ │ /api/options/* (password)  │
                                                       └──────────────────────────┘
```

- **recorder:** a small always-on service (`SERVICE_ROLE=recorder`, same Docker image as the API) running `options.daemon`. On each trading day at 08:30 IST it starts the session in a fresh process. The session waits for your Kite login, records the market, runs the signal engine, sends the morning brief, signals and end-of-day report to Telegram, and exits after the close. If the service restarts during market hours, it starts that day's session immediately. A cron service isn't used because Railway's config-as-code is deprecated for new services.
- **api:** your existing FastAPI service. It now also handles the Kite login redirect and serves the dashboard data.
- **ui:** your existing Next.js service. The new pages are **Signals** and **Performance**.

## 2. One-time setup

### 2.1 Accounts (only you can do these)
1. **Kite Connect app:** follow Appendix A of the plan. Set the redirect URL to `https://api-production-fea2.up.railway.app/kite/callback`.
2. **Telegram bot:** follow Appendix C of the plan.
3. **Dashboard password:** choose a long random string. This becomes `DASHBOARD_TOKEN`.

### 2.2 Railway
1. **Postgres:** add a **PostgreSQL** database to the `trading-agent` project.
2. **Recorder service:** a service named `recorder`, deployed from the repo root with `railway up --service recorder`. It needs the variable `SERVICE_ROLE=recorder`; the Dockerfile then runs the scheduler instead of the API. No other settings are needed.
3. **Variables:**

| Variable | api | recorder | Notes |
|---|---|---|---|
| `DATABASE_URL` | ✅ | ✅ | `${{Postgres.DATABASE_URL}}` (a reference variable) |
| `SERVICE_ROLE` | | ✅ | `recorder` |
| `KITE_API_KEY`, `KITE_API_SECRET` | ✅ | ✅ | From the Kite developer console. Keep the secret secret. |
| `KITE_USER_ID` | ✅ | | Your Zerodha client ID; logins from other accounts are rejected |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | ✅ | ✅ | Appendix C |
| `DASHBOARD_TOKEN` | ✅ | | Protects `/api/options/*`. **Required** on a public URL. |
| `OPTIONS_LIVE_SETUPS` | | ✅ | JSON list of setups promoted to LIVE, e.g. `["S1_TREND_PULLBACK"]`. Default `[]` (all SHADOW). |
| `OPTIONS_CAPITAL`, `OPTIONS_RISK_PER_TRADE_PCT`, `OPTIONS_DAILY_LOSS_STOP_PCT` | ✅ | ✅ | Defaults 100000 / 3 / 10 |

4. **Deploy:** deploy `api` and `recorder`. `ui` needs a redeploy for the new pages.

## 3. Daily use
| Time (IST) | What happens | What you do |
|---|---|---|
| 08:30 | Telegram: "Good morning! Log in to Kite…" with a button | Tap **Login to Kite** and sign in. The bot replies "Kite connected". |
| ~08:35 | Recorder loads contracts and 10 days of history; Telegram: "Recording started" plus the **morning brief** | Read the brief |
| 09:30–15:00 | Signals on 5-minute closes, with follow-ups (filled, T1, stop, exit) on the same ID | Decide whether to take each signal; you place any order yourself |
| 15:10 | Positional (P1) evaluation | — |
| 15:15 | Intraday square-off messages | — |
| 15:31 | End-of-day report and recording summary | — |

**On the dashboard:**
- **Signals** shows the live board, open signals with a live premium marker, and the decision log ("why no trade").
- **Performance** shows the full track record.

## 4. Shadow → Live
Every setup starts in **SHADOW**: signals are sent and tracked, but marked "not for trading yet".

Promote a setup only when its shadow record meets the plan's §11 bar:
- 50 or more completed trades.
- Positive expectancy after costs.
- A drawdown you can live with.
- Results consistent with replay.

To promote it, add the setup to `OPTIONS_LIVE_SETUPS` on the recorder. If a setup's results turn negative, remove it again.

## 5. Validating on your own recorded days
Recorded sessions build up in Postgres from day 1. Replay them through the exact live engine, writing into a separate database so the live record is never touched:

```bash
python -m options.backtest.replay --from 2026-10-19 --to 2026-12-31 --source "$DATABASE_URL" --out sqlite:///data/replay.db
```

Bars are replayed minute by minute with the engine clock 4 seconds after each close, so a replay sees exactly what the live system saw, with no look-ahead.

## 6. Running locally
```bash
.venv\Scripts\python -m pytest tests/options
```
- API: `.venv\Scripts\python -m uvicorn api.main:app --port 8000` (uses `sqlite:///data/options.db` unless `DATABASE_URL` is set).
- UI: `npm --prefix ui run dev`, then open http://localhost:3000/signals.
- A full session needs Kite credentials: `python -m options.session` (it exits immediately on holidays and weekends).

## 7. Yearly and monthly upkeep
- **December:** add next year's NSE holidays to `options/core/holidays.py`. Until then, every weekday counts as a trading day and a warning is logged.
- **As announced:** add RBI policy, Budget and Fed dates to `options/core/events.py`.
- **Monthly:** refresh the approximate NIFTY heavyweight weights in `options/core/constituents.py` from NSE's factsheet. Also update them after the semi-annual rebalance.
- **Nothing to do:** lot sizes, expiries and strike steps update automatically from Kite's instrument list every morning.

## 8. Railway config-as-code deprecation (before 1 Dec 2026)
Railway stops honouring `railway.json` on **1 Dec 2026**. The `api` and `ui` services currently get their Dockerfile builder (and the API's `/health` check) from those files. Before that date:
- Open each service in the Railway dashboard.
- Set **Builder = Dockerfile**, and **Healthcheck path = /health** for `api`.
- Delete the `railway.json` files.

The recorder already doesn't depend on them.

## 9. Troubleshooting
| Symptom | Likely cause |
|---|---|
| "KITE_API_KEY / KITE_API_SECRET are not set" on Telegram | Variables missing on the recorder service |
| Login page says "Wrong account" | `KITE_USER_ID` doesn't match the Zerodha account you logged in with |
| "No market data for …s" alert | WebSocket dropped; it reconnects automatically, and signals pause meanwhile |
| Dashboard asks for a password | That's `DASHBOARD_TOKEN`; it's stored only in that browser |
| Board says "No analysis yet" | Before the first 5-minute close (09:20), not logged in to Kite, or the recorder isn't running |
| "Signal engine error" alert | Recording continues; check the recorder logs on Railway |

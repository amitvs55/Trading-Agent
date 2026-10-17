# Trading Platform Review: Use Cases, Indicators, Safety, UI & Roadmap

You are a principal engineer, quant developer, and applied-AI architect. Review this trading platform end to end: backend, market data, indicators and strategy logic, AI agents, order execution, and every UI screen. Back every finding with evidence from the code.

## 1. Project context (fill in what you know; leave the rest blank)
- Platform and purpose:
- Users (only me, or other traders/subscribers too):
- Markets and instruments (e.g., NSE equities, F&O, indices, crypto):
- Trading style and timeframes (intraday / swing / positional; candle intervals):
- Mode (analysis only / alerts / paper trading / live trading):
- Brokers and data sources:
- Targets, with numbers (e.g., max drawdown ≤ 15%, Sharpe ≥ 1.2 after costs, signal-to-order latency < 2 s):
- Intended use cases or PRD location (optional):
- Design system / brand rules (optional):
- Out of scope:

If a field is blank, infer it from the code, README, docs, configs, DB schema, and UI text, and label every inferred item INFERRED.

## 2. Objective
Answer four questions with evidence:
1. Coverage: which use cases does the platform actually implement, and how completely? Give exact counts.
2. Adequacy: for each use case, are the technology, logic, and indicators enough to reach its target? If not, what exactly is missing?
3. Safety: can a bug, bad data, or a missing control cause wrong orders or unbounded losses?
4. Roadmap: what must be fixed, built, or changed, and in what order, so every use case reaches its target?

## 3. Ground rules
- First, save this prompt verbatim to `docs/review/REVIEW_PROMPT.md`. Re-read it whenever you resume or lose track.
- Read-only. Don't modify, refactor, or fix source files. You may run tests, coverage, type-checks, linters, builds, and dependency audits if they don't change tracked files.
- Put verification scripts (e.g., recomputing indicators with a reference library) in `docs/review/scripts/` and run them in a separate virtual environment. Never add dependencies to the project.
- Never touch live systems:
  - no orders and no broker API calls, live or sandbox
  - no LLM APIs, paid data feeds, social-media APIs, payment gateways, or messaging providers
  - no production databases
  - use only data already in the repo, fixtures, or synthetic data; if you need to download historical data, ask at the Phase 2 checkpoint
- If you find secrets (broker keys, TOTP secrets, API tokens), report the location and redact the value.
- Every finding cites evidence as `path/to/file.ext:L10-L42`. If you can't verify something, mark it UNVERIFIED and say what would verify it.
- Trace, don't guess. A use case counts as implemented only if you followed it end to end: UI → API → logic/agent → data or broker → back to the UI. Never assume functionality from names or comments.
- Be direct and use numbers. Mention strengths briefly; spend the report on gaps and fixes.
- Keep running notes in `docs/review/_notes.md` and resume from them. If you can use sub-agents, explore modules in parallel, but make the final judgments yourself.

## 4. Definitions
- **Use case:** an end-to-end goal that an actor accomplishes. The actor can be a user, an admin, or the system itself (schedulers, data jobs, agent pipelines, webhooks).
  - Examples: "User backtests an RSI strategy on Nifty 50 stocks and sees performance stats"; "At 9:20 IST the system generates signals and places orders with stop-losses"; "User sets a price alert and gets notified."
  - A single function or endpoint is not a use case.
  - Group use cases by actor and mark each one Core or Supporting.
- **Status:**
  - COMPLETE
  - PARTIAL: missing steps, or only the happy path works.
  - STUB: mock, hardcoded, placeholder, or TODO.
  - BROKEN: wired but would fail; say why.
  - PLANNED: only in docs, TODOs, or UI text.
  - ORPHANED: code that nothing reaches.
- **Indicators.** Assess all three layers:
  - Market inputs: the technical (trend, momentum, volatility, volume), fundamental, sentiment, news, and macro data the platform uses.
  - Decision logic: how inputs become signals and trades (rules, weights, thresholds, LLM reasoning, votes).
  - Success metrics: how performance is measured (backtest stats, paper/live P&L, signal hit rate, latency, uptime).
- **Verdict:** SUFFICIENT, PARTIALLY SUFFICIENT, or INSUFFICIENT, with a confidence level (High/Medium/Low) and the single biggest reason.
- **Effort:** S ≤ 1 day, M ≤ 1 week, L > 1 week.
- **Severity:** Critical, High, Medium, or Low. Anything that can place unintended orders or allow unbounded losses is Critical.

## 5. Process

### Phase 1 — Reconnaissance
Map the following:
- structure, frameworks and versions, entry points
- configs and env vars, DB schema
- market-data pipeline: sources, storage, candle building
- schedulers and jobs
- broker integration
- LLM agents
- frontend stack: UI and chart libraries, state, real-time transport
- tests (run them with coverage if configured)
- CI/CD, deployment, docs

Draw the architecture and the data → signal → order flow as Mermaid diagrams.

### Phase 2 — Inventories (CHECKPOINT)
Build these five inventories:
1. Use cases: Use case | Actor | Core/Supporting | UI screen | API endpoint(s) | Logic/agent | Data/tables | External services | Tests | Status
2. Screens: Screen | Route | Roles | Use cases served | Status
   - Build the list from the router or page definitions. For Next.js, that's every page file under app/ or pages/, including route groups, dynamic segments, and the not-found/error/loading files; other frameworks have an equivalent route or page list.
   - Add modals and drawers.
   - A screen is STUB if it shows mock data, placeholder text, or dead buttons.
3. Indicators: Indicator | Where computed | Parameters | Timeframe | Used by | Also computed in UI? | Checked against reference?
4. Data sources: Source | Official or unofficial | Delay | Rate limits | Used for
5. LLM agents (if any): Agent | Inputs | Model | Output schema | Consumed by

Also list:
- orphaned endpoints
- UI calls to endpoints that don't exist
- unused tables
- dead code
- indicators that are computed but never used

If intended use cases were given, compute coverage (implemented ÷ intended).

→ STOP here. Show me the inventories with counts, and tell me what you need from me (test logins, sample data, permission to download historical data). Wait for my corrections before continuing.

### Phase 3 — Use-case adequacy (Core first)
For each use case, assess:
1. Target: the stated or INFERRED target, written as a measurable criterion.
2. Technology fit: is the approach right for the job and the timeframe? For example, an LLM pipeline that takes minutes can't drive intraday entries.
3. Logic: correctness, edge cases, validation, error handling, retries and timeouts, idempotency, concurrency, state transitions.
4. Indicators: are the market inputs and decision logic enough to reach the target? What's missing or redundant? (Phase 4A has the detailed checks.)
5. Success metrics: can we tell today whether it hits its target? If not, what metric, log, or test is needed?
6. Data: is the required data present, correct, and fresh?
7. Security and privacy.
8. Performance and cost: latency, query efficiency, LLM tokens and cost per decision.
9. Tests: what covers it, and which critical paths are untested.
10. UX flow: steps and clicks to finish, dead ends, whether the UI shows what the user needs in order to act (e.g., why a signal fired), and loading/success/error feedback.

End each use case with: verdict and confidence, gaps, recommended fix, and effort. A use case that is SUFFICIENT with High confidence only needs a short summary; go deep on the rest.

### Phase 4 — Trading-critical audits

**A. Indicators and signals**
- Correctness:
  - Recompute key indicators on sample data with a reference implementation (e.g., TA-Lib) and report mismatches.
  - Check warm-up periods, NaN handling, adjusted vs unadjusted prices, and timezone and candle alignment.
  - Check whether UI and backend values agree.
- Look-ahead and repainting: does any signal use data that isn't available at decision time? Examples: trading at the close of the same candle used to compute the signal, using revised data, using news published after the decision.
- Coverage: which dimensions are covered (trend, momentum, volatility, volume, regime/breadth, sentiment, fundamentals, macro), and which missing ones matter for the target?
- Redundancy: correlated indicators that add no new information (e.g., several momentum oscillators).
- Parameters: defaults vs tuned, how they were chosen, overfitting risk, fit to the timeframe, multi-timeframe confirmation.
- Regime awareness: does the logic adapt to trending, ranging, and high-volatility markets?
- Evidence: is there any backtest or forward test showing the signals reach the target? If not, design the minimum test that would.

**B. Backtest validity** (if a backtester or any performance claim exists)
- look-ahead bias, survivorship bias (index constituents change), corporate actions
- realistic fills, slippage, and liquidity limits
- full costs: brokerage, STT, exchange charges, GST, SEBI fees, stamp duty
- in-sample vs out-of-sample and walk-forward testing; enough trades to be meaningful
- a benchmark (e.g., buy-and-hold Nifty) and standard metrics: CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor, expectancy
- whether backtesting and live trading share the same signal code

**C. Risk and execution safety** (if it places orders, paper or live)
- Paper and live modes are cleanly separated, and it is impossible to trade live by accident.
- Pre-trade checks are enforced in deterministic code. An LLM must never be the only risk control. Check:
  - position size, risk per trade, daily loss limit, max open positions
  - exposure and concentration, margin
  - price bands and circuit limits
  - fat-finger checks
- A kill switch exists, and behavior on crash and restart is defined.
- Order lifecycle: idempotency, no duplicate orders on retry, partial fills, rejections, cancellations, reconciliation with broker positions.
- Stop-losses: are they held at the broker (e.g., SL or GTT orders), or only monitored by our process (and lost if it crashes)?
- Broker API: token expiry and refresh, rate limits, websocket reconnects, error handling.
- Market calendar: IST, holidays, pre-open, expiry days, special sessions.
- Money math: Decimal, not float, for prices and P&L; tick-size and lot-size rounding.
- Audit trail: every signal, decision, and order is logged with timestamps and rationale.
- Regulation: SEBI rules on API/algo trading and on giving buy/sell recommendations to others. Verify the current rules, and flag anything that may need registration or disclaimers.

**D. Market data quality**
- official vs unofficial sources, delays, terms and rate limits, retries
- missing, duplicate, or outlier candles
- split and bonus adjustments
- stale-data detection: does trading stop when data is stale?
- storage schema, indexes, retention
- correct tick-to-candle aggregation

**E. LLM agents** (if present, e.g., a TradingAgents-style pipeline: analysts → bull/bear debate → trader → risk team → portfolio manager → execution)
- Are agents fed computed numbers, or asked to "analyze" from memory (hallucination risk)?
- Are outputs validated against a schema, and what happens on malformed output?
- Does each stage change outcomes? Propose an ablation (e.g., decisions with vs without the debate).
- Reproducibility: temperature, pinned model versions, every prompt and response logged per decision.
- Leakage: backtests on dates the model already "knows" from training are contaminated. News and sentiment must be time-aligned to the decision.
- Prompt injection through scraped news or social posts.
- Cost and latency per decision, compared with the trading timeframe.

### Phase 5 — Cross-cutting engineering
Review these areas across the whole codebase:
- architecture and modularity
- code quality and duplication
- security: authentication, authorization, secrets, OWASP Top 10
- reliability
- observability: logs, traces, alerts during market hours
- testing strategy, CI/CD, dependency health, docs

Stack checks (apply whichever exist):
- Next.js (App Router): server/client boundaries, secrets in NEXT_PUBLIC_ variables, auth in server actions, route handlers, and middleware, caching bugs.
- FastAPI: auth on every protected route, Pydantic validation, blocking I/O or heavy pandas work on the event loop, CORS, rate limiting.
- Supabase/Postgres: RLS on every table, the service-role key never in the client, indexes for time-series queries, migrations in sync with code.
- Python data code: timezone-aware datetimes, vectorized pandas, float precision, NaN handling.
- Redis, websockets, schedulers: stale cache, reconnects, overlapping or missed jobs, jobs aligned to market hours.
- Payments and alert channels (if present): signature and webhook verification, idempotency, opt-in, retries.

### Phase 6 — Screen-by-screen UI review
If you can run the app locally against mock or dev data without breaking the live-systems rule, walk through every screen in a headless browser. Save screenshots at 375, 768, and 1440 px wide to `docs/review/screenshots/`. Otherwise, review from code and mark visual findings UNVERIFIED.

Check every screen for:
1. Functional completeness: every button, link, form, and menu works. No mock data, placeholder text, or console errors.
2. States: loading, empty, error, logged out, permission denied, slow network, websocket disconnected, market closed.
3. Charts: correct candles, timezone, and holiday/session gaps; overlays match backend indicator values; no memory leaks on live updates.
4. Freshness: every live number has a last-updated time and a visible stale/disconnected state.
5. Orders:
   - a clear paper-vs-live indicator
   - confirmation before live orders
   - double-submit prevention and fat-finger guards
   - quantity and price validated against lot size and tick size
   - clear rejection messages
6. Numbers: ₹ with Indian digit grouping (1,00,000), consistent decimals, signed % changes, P&L split into realized/unrealized and before/after charges.
7. Responsive layout at 375, 768, and 1440 px: no horizontal scroll, touch targets of about 44 px.
8. Accessibility (WCAG 2.2 AA): keyboard use, visible focus, labels, contrast, ARIA, screen-reader announcements. Gains and losses must not be shown by red/green color alone. Run axe or Lighthouse if you can, and check the code as well.
9. Design consistency: one set of design tokens and shared components; flag deviations from the brand rules, if given.
10. Navigation: menus, deep links, 404/500 pages, auth redirects. Flag permissions that are enforced only in the UI.
11. Frontend performance: bundle size, client components that don't need to be client components, re-renders on every tick, Core Web Vitals (LCP, INP, CLS).
12. Frontend security: dangerouslySetInnerHTML, unsanitized LLM or user content, tokens in localStorage, secrets in client bundles.
13. AI in the UI: progress indicators for slow agent runs, the reasoning and confidence behind each signal, clear not-financial-advice disclaimers, graceful failure.
14. Frontend tests: component tests, end-to-end coverage of Core flows, visual regression.

### Phase 7 — Research and benchmarking
Research every Core use case, and every use case or indicator set rated below SUFFICIENT:
- Find how production trading systems and current literature handle it: proven indicator combinations, regime filters, validation methods, risk frameworks, and realistic targets for this market and timeframe.
- Prefer primary sources (official docs, exchange and regulator sites, papers). Cite links with dates.
- Tag each claim [CODE] or [RESEARCH].
- Recommend what fits this stack and a small team, not the theoretical ideal.
- If you can't browse, list the research questions with your best current knowledge, marked UNVERIFIED.

## 6. Deliverables

### docs/review/PLATFORM_REVIEW.md
1. Executive summary (max 1 page):
   - overall verdict
   - use-case counts by status
   - "Safe to run live today?" yes/no, with reasons
   - top 5 risks, top 5 opportunities, 3 strengths to keep
2. Scorecard: a 1–5 score with a one-line justification for each of architecture, code quality, security, reliability, data quality, indicators and signals, backtest validity, risk controls, execution safety, AI agents, testing, observability, UI/UX, accessibility, frontend performance, compliance, and docs.
3. Diagrams: architecture, data → signal → order flow, and sequence diagrams for the top 3 Core use cases.
4. Inventories and traceability matrix.
5. Use-case deep dives.
6. Indicator and signal audit, including reference-check results.
7. Findings from Phases 4 and 5: ID, severity, evidence, impact, recommendation.
8. Research notes with sources.
9. Roadmap in four stages:
   - Stabilize: safety, security, critical bugs.
   - Complete: partial, stub, and broken use cases.
   - Strengthen: indicators, validation, metrics.
   - Scale/Expand.
   Each item has: ID, title, linked use cases and findings, problem, solution, effort, impact, dependencies, and measurable acceptance criteria.
10. Quick wins: high impact, effort S.
11. Open questions and assumptions for me.

### docs/review/UI_REVIEW.md
- screen inventory
- Mermaid navigation map
- per-screen table: status, responsive, accessibility, states covered, issue count
- findings for every screen that has issues
- top 10 UI fixes

### docs/review/backlog.csv
One row per roadmap item, with columns: ID, title, use case, type (bug/security/risk/data/indicator/feature/ui/ux/a11y/tech-debt/metric), priority, effort, impact, dependencies, acceptance criteria.

Before finishing, check that:
- every use case has a deep dive
- every route appears in the screen inventory
- every Critical or High finding has evidence and a roadmap item
- the counts in the executive summary match the inventories
- no secret values appear anywhere in the output

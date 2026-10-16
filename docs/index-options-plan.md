# Live Index Options Signal Tool — Plan v2

**Product:** live BUY/SELL signals for options on **NIFTY 50, BANK NIFTY and FIN NIFTY**, delivered during market hours to Telegram and a web dashboard. Every signal is backed by the full analysis and tracked automatically to its result.
**Not in scope:** automatic order placement. You place trades yourself. Auto-execution can be added later, but only after the signals have a proven track record.
**Status:** plan v2, 16 Oct 2026. Replaces v0.1.

---

## 0. Your choices (16 Oct 2026) and what they change

| Choice | Decision | Effect on the build |
|---|---|---|
| Broker / data | **Zerodha Kite Connect** | Needs the **paid Connect plan (₹500/mo)**, or Zerodha's active-trader waiver if you qualify. The free *Personal* plan has **no market data**. See §10. |
| Signal style | **Intraday buy-only + positional buy-only** | Signals are BUY CE / BUY PE / EXIT only. Intraday setups S1–S5; positional setups P1–P2 (§5), generated at 15:10 for 1–3 day holds. S6 and S7 are deferred. |
| Indices | **NIFTY first** | MVP is NIFTY only. BANK NIFTY and then FIN NIFTY are added once NIFTY setups pass shadow testing. |
| Capital | **Up to ₹1 lakh** | Always **1 lot** (65 units). Strike band narrowed to delta **0.40–0.55**. A signal whose stop is too wide for your risk budget is marked **"over budget"** rather than given an artificially tight stop. |

**Capital arithmetic for ₹1 lakh (1 NIFTY lot = 65 units):**

| Risk per trade you choose | ₹ at risk | Largest stop the tool can accept |
|---|---|---|
| 1% | ₹1,000 | ₹15 premium points |
| 2% | ₹2,000 | ₹31 premium points |
| **3% (your choice)** | **₹3,000** | **₹46 premium points intraday; about ₹30 for positional (1.5× gap buffer)** |

- **Typical stop size:** structure-based stops on near-ATM NIFTY options are roughly 15–40 premium points, depending on VIX and days to expiry. The shadow test will measure the real figure.
- **Positional trades can gap overnight** past their stop. The tool therefore sizes them as if the stop were 1.5× wider, and marks them over budget when that doesn't fit.
- **Risk per trade is set to 3%** (your choice, 16 Oct 2026). For scale: 5 full losses in a row means about a 14% drawdown, and 10 in a row about 26%. Streaks like that are normal for systems that win less than half the time, so the daily stop below matters.
- **Daily loss stop: 10%** (your choice, 16 Oct 2026). After three full losses (9%), the next signal would risk breaching 10%, so it is blocked and signals pause until the next day.
- **Max open signals:** 1 intraday + 1 positional at a time, because ₹1 lakh covers premium for about 2 lots.

| More choices | Decision | Effect |
|---|---|---|
| Kite Connect | **Set up from scratch** | You follow the step-by-step setup in Appendix A. Static IP **not needed**, because Zerodha requires it only for order placement and this tool only reads market data. |
| Alerts | **Telegram** for now (your choice: it's free) | Telegram Bot API (Appendix C). WhatsApp can be added later behind the same notifier; its setup is kept in Appendix B. |

---

## 1. What "genuine" means for this tool

No tool can predict the market perfectly, and any tool claiming 90% accuracy is lying. A *genuine* tool is one whose signals are **meaningful, explained and honestly measured**. These rules are built in and can't be switched off:

| # | Rule | What it prevents |
|---|---|---|
| 1 | **Signals fire only on a closed 5-minute candle.** A sent signal can never change or disappear. | "Repainting" signals that look perfect in hindsight |
| 2 | **Every signal is saved with a timestamp *before* its outcome is known.** It can't be edited or deleted afterwards. | Cherry-picked track records |
| 3 | **Results are measured automatically on real live bid/ask prices,** after brokerage, STT and charges. | Paper profits that don't exist in real trading |
| 4 | **Losses appear as prominently as wins.** The performance page shows every signal. | Survivorship bias |
| 5 | **No made-up "85% confidence" numbers.** A signal shows a **grade** (A/B) plus the *actual* historical stats of that setup once it has 30+ results. | Fake precision |
| 6 | **"NO TRADE" is a valid output.** On choppy or event days, the tool says so and explains why. | Forcing trades to look busy |
| 7 | **Every signal shows all 12 analysis pillars** (§4), including the ones that disagree. | Black-box calls you can't judge |
| 8 | **New setups run in SHADOW mode first.** Signals are tracked but marked "not for trading" until proven. | Trusting untested logic with money |

**Realistic expectations once it's working:** 0–3 signals per index per day, many days with none, and a win rate that may be **below 50%**. A system can still make money that way, if winners are bigger than losers. The tool measures this rather than promising it.

---

## 2. Verified market facts (checked 15–16 Oct 2026)

| | NIFTY 50 | BANK NIFTY | FIN NIFTY |
|---|---|---|---|
| Expiries listed | **Weekly + monthly** | **Monthly only** | **Monthly only** |
| Expiry day | Every **Tuesday** (monthly = last Tuesday) | **Last Tuesday** | **Last Tuesday** |
| Lot size (since Jan 2026 series) | 65 | 30 | 60 |
| Strike step near ATM* | 50 | 100 | 50 |

\* Strike steps are from memory, not re-verified. The tool reads them from the broker's instrument list.

- **BANK NIFTY and FIN NIFTY weeklies ended in Nov 2024.** SEBI now allows one weekly benchmark index per exchange.
- **Expiries moved from Thursday to Tuesday on 1 Sep 2025.**
- **A holiday on expiry day moves the expiry to the previous trading day.** Next case: Dussehra on Tue 20 Oct 2026, so the NIFTY weekly expires Mon 19 Oct. The BANK NIFTY and FIN NIFTY monthly expires Tue 27 Oct.
- **The last Tuesday of each month is a triple expiry** (all three indices). The highest-gamma day of the month gets special rules.
- **STT has risen since 1 Apr 2026:** 0.15% of premium on option sales and 0.15% of intrinsic value on exercise. The result tracker uses these rates.
- **The tool never hard-codes expiries, lot sizes or strike steps.** It loads them from the broker's instrument master at 08:30 every trading day.

---

## 3. What you get each trading day

| Time (IST) | Output | Content |
|---|---|---|
| 08:30 | Telegram: **login link** | Tap "Login to Kite", sign in, and the bot confirms "Kite connected". Reminders at 09:05 and 09:20 if you haven't. |
| 08:50 | **Morning Brief** (Telegram + dashboard) | Per index: expected gap from GIFT Nifty, global cues, FII/DII flows, today's events, key levels (previous high/low/close, CPR, OI walls), IV percentile, and a **day bias** with reasons. It flags expiry day and the triple expiry. |
| 09:15–09:30 | Observe | Opening range builds. No signals, except gap setups after 09:30. |
| 09:30–15:00 | **Live signals** | Entry signals (grade A/B), then **management updates** for each one: entry filled, T1 hit / stop-loss moved to cost, tighten stop, exit |
| Continuous | **Live Analysis Board** (dashboard) | For each index, all 12 pillars updating live, plus active signals and why the tool is or isn't trading |
| 12:30 | Midday update | What changed since the morning: regime, OI walls, flows |
| 15:00 | No new intraday entries | Exit reminders |
| 15:15 | Intraday exit signals | Closes everything still open |
| 15:45 | **EOD Report** | Every signal and its outcome in ₹ and R, running performance, tomorrow's levels |

### Example signal card (illustrative numbers)
```
🟢 BUY CE · NIFTY · Grade A (81/100) · S1 Trend pullback
NIFTY 27-OCT-2026 25300 CE  (Δ 0.52, lot 65)          ID NF-261016-003
Entry   138–144 (limit)          valid till 10:35
SL      104   or NIFTY fut 5m close < 25,215
T1      190  (book 50%, SL → cost)   T2 238 (trail)
R:R     1 : 1.3 / 1 : 2.6         Time stop 14:45
Size    1 lot = ₹2,405 risk (2.4% of ₹1L; limit 3%)

Analysis 10✅ 1⚠️ 1➖
✅ Trend      15m & 60m up, Supertrend up
✅ Trigger    pullback to fut VWAP, bullish 5m close
✅ Levels     room to 25,400 call wall (1.6× ATR)
✅ Momentum   RSI 58 rising, MACD hist turning up
✅ Fut flow   long buildup, OI +2.1%
✅ Chain      put writers +18L @25200, call wall steady
✅ Volatility IV pct 38 (fair), VIX steady
✅ Option     spread 0.9%, theta 3.1/hr OK
✅ Breadth    HDFC, ICICI, RELIANCE up · A/D 38:12
⚠️ Macro      Asia mixed, US futures flat
✅ Events     none until 14:00
➖ News       no relevant headlines
Setup S1 history (A grade): 42 signals · 52% hit T1 · avg +0.31R
```
Follow-up messages use the same ID, for example `🔄 NF-261016-003 T1 hit @190 · booked 50% · SL → 141` or `🔴 EXIT NF-261016-003 @171 · reason: futures turned to long unwinding`.

---

## 4. The 12 analysis pillars

Every candidate signal is checked against all 12 pillars. Each one scores ✅ pass, ⚠️ warning, ❌ against or ➖ not applicable.

| # | Pillar | What is analysed | Source agent |
|---|---|---|---|
| 1 | **Trend** | 15m/60m EMA 20/50 alignment, Supertrend (10, 3), higher highs and higher lows | Technical |
| 2 | **Trigger** | Quality of the setup's entry candle and its location | Setup detector |
| 3 | **Levels and room** | Previous day's high/low/close, CPR/pivots, swing support/resistance, futures VWAP, OI walls. Is there room to T1 before the next barrier? | Technical + Chain |
| 4 | **Momentum** | RSI(14) and divergences, MACD histogram, ADX | Technical |
| 5 | **Futures flow** | Buildup type (long buildup, short buildup, short covering, long unwinding), basis vs fair value, futures volume surge | OI & Flow |
| 6 | **Option chain** | Change in OI at nearby strikes, shifting OI walls, PCR over ATM ± expected move, max pain (expiry week only) | Option Chain |
| 7 | **Volatility** | India VIX, ATM IV and IV percentile per index, IV vs realized vol, skew, expected move | Vol & Greeks |
| 8 | **Option quality** | Delta, theta burn per hour, gamma on expiry day, bid-ask spread, depth | Vol & Greeks |
| 9 | **Constituents and breadth** | Heavyweights' contribution in points, divergence, advance/decline, % of stocks above VWAP | Breadth |
| 10 | **Global and macro** | GIFT Nifty, Asia, US futures, USD-INR, crude, yields, FII/DII cash, FII index-futures long/short ratio | Macro |
| 11 | **Events** | RBI MPC, Budget, CPI/GDP, Fed, heavyweight results, expiry day | News & Events |
| 12 | **News and shock** | Relevant headlines and a sudden-move detector | News & Events |

**Mandatory gates.** Any failure means NO TRADE, with the reason shown:
- Data is fresh.
- The session window is open.
- No event window is active.
- Liquidity passes.
- R:R to T1 is at least 1.3.
- The daily risk budget is not used up.
- The setup is allowed in the current regime.

---

## 5. Signal setups (the actual trading logic)

Signals come from **named, rule-based setups**, not from a vague overall score. Every signal therefore has a clear reason, an invalidation point, and its own track record. All triggers use **futures prices**, because index spot has no volume and no VWAP.

| ID | Setup | Regime | Trigger (5m close) | Key confirmations | Signal |
|---|---|---|---|---|---|
| **S1** | Trend pullback | Trend | Pulls back to futures VWAP or EMA20, then closes back in the trend direction | Futures long buildup or short covering (bull case); breadth aligned | BUY CE / BUY PE |
| **S2** | Opening range breakout | Any except chop | After 09:30, closes beyond the 09:15–09:30 range with futures volume ≥ 1.5× average | OI wall shifts in the same direction; gap aligned; no wall within 0.5 ATR | BUY CE / BUY PE |
| **S3** | OI wall break (short covering) | Trend or expanding | Closes beyond the max-call-OI strike while call OI there **falls**. Mirror for the put wall. | Futures price ↑ with OI ↓; heavyweights leading | BUY CE / BUY PE |
| **S4** | Range rejection at OI wall | Range | Rejection candle at the call or put wall while OI there **rises** | RSI divergence; breadth not confirming the move | BUY PE / BUY CE, or a SELL spread when IV is rich |
| **S5** | Gap and go / gap fill | First 45 min | Gap > 0.5 ATR. Go: first 15m holds beyond the gap. Fill: price reclaims the prior close. | GIFT Nifty and global direction; breadth; first-15m futures flow | BUY CE / BUY PE |
| **S6** | Expiry-day momentum | NIFTY on Tuesdays; all three on the last Tuesday | After 11:00, breakout from consolidation with a sharp change in OI | ATM/ITM strikes only, half size, exit by 14:45. Tagged **high risk**. | BUY CE / BUY PE |
| **S7** | Rich-IV range sell (hedged) | Range, IV pct > 60 | Price mid-range between OI walls, no events for 24h | Short leg beyond the wall or 1 SD of expected move; hedge leg 2–4 strikes further | SELL CE / SELL PE (always as a **spread**) |

### Positional setups (buy-only, evaluated at 15:10, hold 1–3 trading days)

| ID | Setup | Trigger (daily candle forming at 15:10) | Key confirmations | Signal |
|---|---|---|---|---|
| **P1** | Daily trend continuation | Close above the previous day's high (bull) or below its low (bear), in the direction of the daily EMA 20/50 trend | EOD futures long or short buildup; FII index-futures long/short ratio rising (bull) or falling (bear); IV percentile < 60; no major event in the next 2 sessions | BUY CE / BUY PE, expiry with ≥ 4 trading days left |
| **P2** | Multi-day range breakout | Close beyond a 5–10 day range, with futures volume ≥ 1.5× its 10-day average | OI wall at the breakout strike being unwound; breadth aligned; GIFT Nifty and global direction checked at 08:50 the next day | Same |

**Positional rules:**
- Stop on a **daily close** beyond invalidation, or a 35% premium cap.
- Exit by day 3, or at the next morning's open if the gap goes against the trade.
- Never hold through RBI policy, the Budget or a Fed decision.

**Rollout:**
- **MVP:** NIFTY with S1, S2 and S3, the most common and easiest to validate, plus P1. Then add S4, S5 and P2.
- **S6 and S7** are added only after shadow testing, because they carry more risk.
- **Each setup has a kill rule:** after 30 results, if expectancy after costs is ≤ 0, it automatically drops back to SHADOW mode.

### Grading (0–100)
- **Pillar weights:**
  - Trend 15, Futures flow 15, Option chain 15
  - Trigger 10, Levels/room 10, Volatility 10, Breadth 10
  - Momentum 5, Macro 5, Timing/expiry fit 5
  - News 0 (it only ever adds a ⚠️ or blocks)
- **Points per pillar:** ✅ = full weight, ⚠️ = half, ➖ = half (neutral), ❌ = zero.
- **Grade A ≥ 75 · Grade B 60–74 · Grade C < 60.** C is logged, never sent.
- **Hard conflict:** ❌ on **Trend** or **Futures flow** caps the signal at C. A buy against the trend or against the flow is never sent.

---

## 6. Strike, expiry, entry, stop-loss and targets

### Expiry
Expiries come from the instrument master, so they are already holiday-adjusted.

| Index | Intraday signals | Positional (1–5 day) signals, phase 2 |
|---|---|---|
| NIFTY | Nearest weekly with ≥ 1 trading day left. On expiry day, only S6 is allowed. | Expiry with ≥ 4 trading days left |
| BANK NIFTY | Current monthly. In the last week, expiry-day rules apply. | Current monthly if ≥ 6 days remain, else next month |
| FIN NIFTY | Same as BANK NIFTY, **plus a strict liquidity check**. If it fails, NO TRADE. | Same; skip if next month's chain is thin |

### Strike
- **ATM** comes from the **synthetic forward** (strike + call − put), not spot.
- **Delta bands:**
  - Buy signals: delta **0.45–0.60** (ATM to 1 strike ITM). **For your ₹1 lakh account: 0.40–0.55**, so that a 1-lot stop fits the risk budget more often.
  - Grade A momentum setups with cheap IV may use 0.35–0.50.
  - **Never** delta < 0.25.
  - Spreads: short leg 0.15–0.30, hedge leg 0.05–0.12.
- **Liquidity filter:** spread ≤ 3% of premium, OI above a floor, and depth ≥ 3× one lot. If the strike fails, move one strike toward ATM. If that fails too, NO TRADE.

### Levels
1. **Start from the underlying.** Invalidation is the far side of the trigger level, or 1–1.5 × ATR. T1 is the next level or about 1.5R. T2 is the next OI wall or the expected-move boundary.
2. **Convert to premium** with Black-76 using live IV. Approximation: `ΔP ≈ Δ·ΔS + ½Γ·ΔS² + Θ·Δt`.
3. **The SL is the tighter of** the premium at invalidation and a hard 30% cap. For spreads, exit at 2× the credit, or on a breach of the short strike.
4. **Validity window:** about 15 minutes. If the entry price isn't reached in that time, the signal is marked EXPIRED. It's logged, but doesn't count as a win or a loss.
5. **Suggested size** comes from your capital and risk per trade: `lots = floor(capital × risk% ÷ ((entry − SL) × lot_size))`.

---

## 7. Signal lifecycle (what "live" means)

```
          detect on 5m close
 FORMING ───────────────────► TRIGGERED ──(ask ≤ entry high, within validity)──► ACTIVE
 (dashboard only)              │  sent to Telegram                              │
                               ├──(validity passes)──► EXPIRED                  ├──(bid ≥ T1)──► T1_HIT ──(bid ≥ T2 / trail / exit rule)──► CLOSED
                               └──(invalidated first)─► CANCELLED               │                 SL → cost
                                                                                └──(SL / invalidation / time stop / 15:15 / exit rule)──► CLOSED
```

**Exit and management rules,** checked on every tick and on each 5m close:
- Stop-loss on premium, or a 5m futures close beyond invalidation.
- T1 hit: book 50% and move the SL to cost.
- Trail the rest on the 5m swing or Supertrend.
- **Flow flip** (futures turn to unwinding or opposite buildup): "tighten SL" alert. If the trend pillar also flips: EXIT.
- An opposite grade-A signal on the same index: EXIT.
- An event window approaching: EXIT.
- IV crush after an event (buy signals): review alert.
- Time stop. 15:15 square-off. Expiry-day cut-off at 14:45.

**Result measurement:**
- Entry is assumed filled at the **ask** when the ask comes inside the entry band.
- Exits are filled at the **bid**.
- Brokerage, STT, exchange charges, SEBI fee, stamp duty and GST are all deducted.
- Results are reported per lot in **₹** and in **R** (multiples of risk).

---

## 8. Architecture

```
 ┌────────────── LIVE SOURCES ───────────────┐   ┌──────── REFERENCE / SLOW SOURCES ────────┐
 │ Broker WebSocket: index, futures, VIX,    │   │ Instrument master · NSE holidays & events │
 │ heavyweights, ATM±N options · REST chain  │   │ NSE EOD (FII/DII, participant OI) · RSS   │
 └──────────────┬────────────────────────────┘   │ GIFT Nifty · global markets               │
                │                                └───────────────┬───────────────────────────┘
        ┌───────▼────────┐                               ┌───────▼────────┐
        │ 1 MARKET DATA  │  ticks→bars, chain snapshots  │ 2 REFERENCE &  │ expiries, lots, steps,
        │   (live)       │  health/staleness             │   CALENDAR     │ holidays, event windows
        └───────┬────────┘                               └───────┬────────┘
                │                Redis Streams bus               │
   ┌──────────┬─┴────────┬──────────┬──────────┬─────────┬───────┴──┬───────────┐
   ▼          ▼          ▼          ▼          ▼         ▼          ▼           ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌───────┐ ┌────────┐ ┌──────────┐
│3 TECH│ │4 FUT & │ │5 OPTION│ │6 VOL & │ │7 CONST.│ │8 MACRO│ │9 NEWS &│ │10 REGIME │
│      │ │  OI    │ │  CHAIN │ │  GREEKS│ │ BREADTH│ │       │ │ EVENTS │ │ & SESSION│
└──┬───┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬───┘ └───┬────┘ └────┬─────┘
   └─────────┴──────────┴──────────┴────┬─────┴──────────┴─────────┴───────────┘
                                        ▼   MarketSnapshot per index (every 5m close)
                          ┌──────────────────────────────┐
                          │ 11 SETUP DETECTORS  S1…S7    │
                          └──────────────┬───────────────┘
                                         ▼ candidates
                          ┌──────────────────────────────┐
                          │ 12 CONFLUENCE & GRADING      │ 12 pillars → score → A/B/C, gates
                          │    + strike/expiry selector  │
                          │    + levels & sizing         │
                          └──────────────┬───────────────┘
                                         ▼ Signal (immutable, saved first)
                          ┌──────────────────────────────┐
                          │ 13 SIGNAL LIFECYCLE MANAGER  │ entry / T1 / trail / exit updates
                          └───────┬──────────────┬───────┘
                                  ▼              ▼
                 ┌──────────────────────┐  ┌────────────────────────┐
                 │ 14 DELIVERY          │  │ 15 OUTCOME TRACKER &   │
                 │ Telegram · Dashboard │  │    PERFORMANCE         │
                 │ Brief · EOD report   │  │ bid/ask fills, costs,  │
                 └──────────────────────┘  │ per-setup stats, kill  │
                                           └────────────────────────┘
        16 BACKTEST & SHADOW (offline): replays the same agents 3–15 on stored data
```

### Agent summary

| # | Agent | Inputs and cadence | Core logic | Output |
|---|---|---|---|---|
| 1 | Market Data | Broker WebSocket ticks; chain REST every 30–60 s | Bars at 1/3/5/15m; re-centres strike window; heartbeat and `STALE` flag; gap fill; **records everything from day 1** | `md.*` streams |
| 2 | Reference & Calendar | Instrument master 08:30; holidays; event calendar | Expiries, lots, steps, freeze quantity; trading-day maths; event windows | Lookup service + `gate.events` |
| 3 | Technical | Futures and spot bars, 1m to daily | EMA, Supertrend, VWAP (futures), ORB, previous high/low/close, CPR, swing S/R, RSI, MACD, ADX, ATR | Pillars 1, 3, 4 + levels |
| 4 | Futures & OI Flow | Futures ticks + OI; EOD participant OI | Buildup type, basis, volume surge, FII long/short ratio | Pillar 5 |
| 5 | Option Chain | Chain snapshots | ΔOI by strike, OI walls and their shifts, PCR over ATM ± expected move, max pain | Pillars 3, 6 |
| 6 | Volatility & Greeks | VIX, chain, futures, T-bill rate | Black-76 IV and Greeks, IV percentile, realized vol, skew, expected move, theta per hour | Pillars 7, 8 + strike data |
| 7 | Constituents & Breadth | Heavyweight ticks, NSE weights, constituent list | Point contribution, divergence, A/D, % above VWAP, concentration flag | Pillar 9 |
| 8 | Global & Macro | GIFT Nifty, globals every 15 min; EOD flows | Gap estimate, risk-on/off z-score, FII flow trend | Pillar 10 + morning bias |
| 9 | News & Events | Calendar; RSS every 1–2 min | Calendar windows (deterministic); optional cheap LLM headline tagging; shock detector | Pillars 11, 12 |
| 10 | Regime & Session | Agents 3, 6, 9 + clock | Trend, range or chop; session phase; expiry-day rules | Allowed setups + gates |
| 11 | Setup Detectors | MarketSnapshot at 5m close | S1–S7 rules | Candidates |
| 12 | Confluence & Grading | Candidates + all pillars | Gates, scoring, strike/expiry, levels, size | `Signal` |
| 13 | Lifecycle Manager | Signals + live ticks | State machine, exit rules, update messages | Signal updates |
| 14 | Delivery | Signals, updates, briefs | Telegram Bot API, dashboard (refreshes every 5–30 s) | Messages and UI |
| 15 | Outcome & Performance | Lifecycle events + bid/ask | Fill model, costs, R and ₹, per-setup stats, auto-demotion | Performance data |
| 16 | Backtest & Shadow | Stored history | Same code path; walk-forward tuning | Validation reports |

**Design choices:**
- **No AI model in the signal logic.** All signal maths is plain Python: fast, the same every time, and testable on history.
- **The AI model is optional,** used only for tagging headlines and the morning-brief summary. Signals keep working when the AI model is down or out of credits.

---

## 9. Code skeletons (Python 3.12)

### Signal schema — `options/core/schemas.py`
```python
from datetime import date, datetime, time
from enum import Enum
from typing import Literal

from pydantic import BaseModel

Index = Literal["NIFTY", "BANKNIFTY", "FINNIFTY"]


class Action(str, Enum):
    BUY_CE = "BUY_CE"
    BUY_PE = "BUY_PE"
    SELL_CE = "SELL_CE"      # bear call spread
    SELL_PE = "SELL_PE"      # bull put spread
    EXIT = "EXIT"
    NO_TRADE = "NO_TRADE"


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class SignalState(str, Enum):
    TRIGGERED = "TRIGGERED"
    ACTIVE = "ACTIVE"
    T1_HIT = "T1_HIT"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PillarCheck(BaseModel):
    pillar: str                                    # "trend", "futures_flow", ...
    status: Literal["pass", "warn", "fail", "na"]
    detail: str                                    # "15m & 60m up, Supertrend up"


class OptionContract(BaseModel):
    index: Index
    expiry: date
    strike: float
    right: Literal["CE", "PE"]
    token: str
    lot_size: int


class Signal(BaseModel):
    signal_id: str                                 # NF-261016-003
    created_at: datetime                           # stored before any outcome; never edited
    index: Index
    setup: str                                     # "S1_TREND_PULLBACK"
    action: Action
    grade: Grade
    score: float
    legs: list[OptionContract]
    entry_low: float
    entry_high: float
    stop_loss: float
    fut_invalidation: float                        # 5m futures close beyond this → exit
    t1: float
    t2: float
    valid_until: datetime
    time_stop: time
    lots_suggested: int
    checks: list[PillarCheck]
    mode: Literal["SHADOW", "LIVE"]
    state: SignalState = SignalState.TRIGGERED
    fill_price: float | None = None                # assumed fill at ask once entry is reached
```

### A setup detector — `options/setups/s1_trend_pullback.py`
```python
from dataclasses import dataclass


@dataclass
class Candidate:
    setup: str
    side: str            # "bull" | "bear"
    trigger: float       # futures price at signal
    invalidation: float  # futures price


class TrendPullback:
    id = "S1_TREND_PULLBACK"
    regimes = {"trend"}

    def detect(self, s) -> Candidate | None:   # s: MarketSnapshot (futures-based technicals)
        t = s.tech
        touched_vwap_from_above = t.fut_low_5m <= t.fut_vwap * 1.0005
        touched_vwap_from_below = t.fut_high_5m >= t.fut_vwap * 0.9995
        if t.htf_trend == "up" and touched_vwap_from_above and t.fut_close_5m > max(t.fut_vwap, t.fut_open_5m):
            return Candidate(self.id, "bull", t.fut_close_5m,
                             min(t.fut_low_5m, t.fut_vwap) - 0.25 * t.atr_5m)
        if t.htf_trend == "down" and touched_vwap_from_below and t.fut_close_5m < min(t.fut_vwap, t.fut_open_5m):
            return Candidate(self.id, "bear", t.fut_close_5m,
                             max(t.fut_high_5m, t.fut_vwap) + 0.25 * t.atr_5m)
        return None
```

### Grading — `options/engine/grading.py`
```python
from options.core.schemas import Grade, PillarCheck

PILLAR_WEIGHTS = {"trend": 15, "futures_flow": 15, "option_chain": 15, "trigger": 10,
                  "levels": 10, "volatility": 10, "breadth": 10, "momentum": 5,
                  "macro": 5, "timing": 5}
STATUS_POINTS = {"pass": 1.0, "warn": 0.5, "na": 0.5, "fail": 0.0}
GATES = ("data_fresh", "session_open", "no_event_window", "liquidity", "min_rr", "risk_budget",
         "regime_allows_setup")


def grade(checks: dict[str, PillarCheck], gates: dict[str, bool]) -> tuple[Grade | None, float, list[str]]:
    failed = [g for g in GATES if not gates.get(g, False)]
    if failed:
        return None, 0.0, failed                                  # NO TRADE, reasons shown on dashboard
    score = sum(w * STATUS_POINTS[checks[p].status] for p, w in PILLAR_WEIGHTS.items())
    if checks["trend"].status == "fail" or checks["futures_flow"].status == "fail" or score < 60:
        return Grade.C, score, []                                 # logged only, never sent
    return (Grade.A if score >= 75 else Grade.B), score, []
```

### Lifecycle and outcome tracking for long options — `options/engine/lifecycle.py`
```python
from datetime import datetime

from options.core.schemas import Signal, SignalState


def on_quote(sig: Signal, bid: float, ask: float, now: datetime) -> str | None:
    """Advance a BUY_CE/BUY_PE signal on each option quote. Returns an event name to broadcast."""
    if sig.state is SignalState.TRIGGERED:
        if now > sig.valid_until:
            sig.state = SignalState.EXPIRED
            return "EXPIRED"
        if ask <= sig.entry_high:
            sig.fill_price = ask
            sig.state = SignalState.ACTIVE
            return "ENTRY_FILLED"
    elif sig.state in (SignalState.ACTIVE, SignalState.T1_HIT):
        if bid <= sig.stop_loss:
            event = "SL_HIT" if sig.state is SignalState.ACTIVE else "STOPPED_AT_COST"
            sig.state = SignalState.CLOSED
            return event
        if sig.state is SignalState.ACTIVE and bid >= sig.t1:
            sig.state = SignalState.T1_HIT
            sig.stop_loss = sig.fill_price                         # move SL to cost
            return "T1_HIT"
        if sig.state is SignalState.T1_HIT and bid >= sig.t2:
            sig.state = SignalState.CLOSED
            return "T2_HIT"
        if now.time() >= sig.time_stop:
            sig.state = SignalState.CLOSED
            return "TIME_STOP"
    return None
# Futures invalidation, flow flips and opposite signals are checked separately on each 5m close.
```

### Proposed layout
The new package sits beside the existing equity tool and leaves it untouched.

```
options/
  core/       schemas.py  bus.py  config.py  calendar.py
  brokers/    base.py  <your_broker>.py  replay.py (backtest feed)
  agents/     market_data.py  reference.py  technical.py  futures_flow.py  option_chain.py
              volatility.py  breadth.py  macro.py  news_events.py  regime.py
  setups/     s1_trend_pullback.py  s2_orb.py  s3_oi_wall_break.py  s4_range_rejection.py ...
  engine/     snapshot.py  grading.py  selection.py  levels.py  lifecycle.py  outcomes.py  costs.py
  quant/      black76.py  indicators.py
  delivery/   whatsapp.py  briefs.py
  backtest/   replay.py  walkforward.py  reports.py
  runner.py
api/routes/   signals.py  board.py  performance.py      # added to the existing FastAPI app
ui/src/app/   signals/  board/  performance/            # added to the existing Next.js dashboard
```

---

## 10. Tech stack and data

| Layer | Choice |
|---|---|
| Language | Python 3.12 (same as the repo) |
| Runtime | asyncio services + **Redis Streams** bus; **APScheduler** (IST, holiday-aware) for the daily timeline |
| Storage | **PostgreSQL + TimescaleDB**: ticks, bars, chain snapshots, signals, outcomes. Signals are append-only. |
| Quant | numpy/pandas, TA-Lib or pandas-ta, own vectorized Black-76 |
| Delivery | **Telegram Bot API** (free; WhatsApp can be added behind the same interface); existing **FastAPI** and **Next.js** dashboard, behind a login (`DASHBOARD_TOKEN`) |
| AI model (optional) | Existing `utils/llm.py` + `utils/usage.py`, with a daily cost cap |
| Hosting | **Railway** is fine: one worker service plus Redis and Postgres, running about 08:30–16:00 IST. It places no orders, so no static IP is needed (confirm with your broker). |
| Tests | pytest. 100% coverage on setups, grading, lifecycle and cost maths. Replay tests on recorded market days. |

**Live data: Zerodha Kite Connect (your choice)**
- **Plan:** the paid Connect plan (₹500/month per app) includes WebSocket and historical data. Zerodha's forum says the fee is waived for active traders from Oct 2026, so check whether you qualify. The free Personal plan **won't work**, because it has no market data.
- **Login:** one manual login per day. The access token stays valid until early the next morning. The tool sends a Telegram message with a Login button at 08:30, and the Kite app's redirect URL points at the tool's API (`/kite/callback` on Railway). Zerodha discourages scripted logins, so keep this step manual.
- **Option chain:** Kite has **no option-chain endpoint**. The tool builds the chain itself:
  1. Read the NFO instrument dump (all NIFTY option contracts).
  2. Subscribe to ATM ± 15 strikes for the nearest two expiries on the **KiteTicker WebSocket in full mode**, which includes OI and market depth.
  3. Re-centre the window as NIFTY moves.

  This gives a **live** chain without polling.
- **Historical data:** candles with OI exist for current contracts only. **Expired options aren't available**, so start recording on day 1.
- **Rate limits:** quote and historical calls are rate-limited. Use the WebSocket for live data and REST only for backfill.
- **Static IP:** not required. Zerodha's rule (from 1 Apr 2026) covers order placement, modification and cancellation only; WebSocket and read-only APIs work from any IP, including Railway.
- Confirm the plan price and token rules on Zerodha's official pages.

**WhatsApp notifications (optional, for later; Meta WhatsApp Cloud API, official)**
- **Why official:** unofficial WhatsApp-Web libraries (Baileys, whatsapp-web.js) and free relay services break WhatsApp's terms and can get the number banned. That is not acceptable for trade alerts.
- **Sender number:** a **separate number** that is **not** registered on WhatsApp, such as a new prepaid SIM, becomes the bot. Your personal WhatsApp receives the alerts.
- **The 24-hour window:**
  - WhatsApp lets a business send free-form messages only within 24 hours of the user's last message. Outside that window it can only send pre-approved **templates**.
  - **The daily design uses this:** at 08:30 the bot sends one *utility template* ("Good morning, tap Login to start today's session") with a **Login** quick-reply button.
  - Your tap opens the 24-hour window, the bot replies with the Kite login link, and every brief, signal and update that day is a normal message inside the window.
  - The login callback and the alerts therefore share one tap.
- **Cost (Meta's pricing from 1 Oct 2026, per third-party rate cards):**
  - Service messages inside the window: **first 1,000 per month free** per number. This tool sends about 15–25 per trading day, so roughly 350–550 a month.
  - Utility template: about **₹0.115 + GST** each, for one a day. Expected total: **roughly ₹3–5 per month**.
  - Confirm on Meta's official rate card.
- **Formatting:** WhatsApp supports *bold*, _italic_ and ```monospace```, so the signal card (§3) renders as a monospace block. Reply buttons can be added (for example "Full analysis" opens the dashboard).
- **Webhook:** incoming taps arrive at `POST /whatsapp/webhook` on the Railway API. It is verified with Meta's verify token and the `X-Hub-Signature-256` HMAC.
- **Fallbacks:** the dashboard always shows everything. If the WhatsApp API is down or the window wasn't opened, signals still appear there, and you get the template prompt again at 09:20.

**Free reference data:**
- NSE downloads: holidays, bhavcopy, participant-wise OI, FII/DII, India VIX history, index weights.
- RSS feeds: RBI, PIB, NSE/BSE announcements.
- yfinance for global context only.

**History for backtests:**
- Broker APIs give years of index and futures 1-minute bars.
- Intraday data for **expired options** generally needs a paid vendor. Until you have it, backtests reprice options from IV, and the report says so.
- The tool records its own live chain from day 1, which becomes the best dataset over time.

---

## 11. Validation before you trust it

| Step | What | Pass criteria |
|---|---|---|
| 1. Replay tests | Replay recorded days tick-by-tick through the live code | The same input always produces the same signals; no look-ahead |
| 2. Historical backtest | 2+ years of futures 1m data (comparable regime only); options repriced via IV; full costs | Positive expectancy after costs per setup; acceptable drawdown; results stable across walk-forward windows |
| 3. **Shadow forward test** | **4–6 weeks live**, all signals marked SHADOW and tracked automatically | ≥ 50 signals; live expectancy after costs > 0; results within tolerance of the backtest |
| 4. Live signals | Setups that passed switch to LIVE. Others stay in SHADOW. | Ongoing: auto-demote a setup if its rolling 30-signal expectancy ≤ 0 |

---

## 12. Build plan (part-time)

| Week | Build | Done when |
|---|---|---|
| 1 | Kite Connect adapter (login flow, instrument dump, KiteTicker), Reference & Calendar agent, Postgres/Redis, **start recording NIFTY** | Ticks and chain stored all session, no gaps |
| 2 | Bars, chain snapshots, Black-76 IV and Greeks, data-health monitor | IV and Greeks match the broker's figures within tolerance |
| 3 | Technical + Regime & Session agents | Pillars 1, 3, 4 and the regime visible live on a basic page |
| 4 | Futures & OI Flow + Option Chain + Volatility agents | Pillars 5–8 live |
| 5 | Breadth + Macro + News & Events (calendar first; AI model optional) | All 12 pillars live; **Morning Brief** sent at 08:50 |
| 6 | Setups S1–S3, grading, strike/expiry selection, levels, sizing | Graded candidates appear on the dashboard |
| 7 | Lifecycle manager, outcome tracker with costs, Telegram signals and updates | Full signal cards and follow-ups on Telegram (SHADOW) |
| 8 | Dashboard: Live Analysis Board, signal detail, performance page, EOD report | Everything visible on phone and desktop |
| 9 | Backtest and replay harness, walk-forward tuning | Backtest report per setup |
| 10 | Hardening: reconnects, token-refresh flow, alerts, tests, Railway deploy | Runs 5 full days unattended without incidents |
| 11–16 | **Shadow forward test;** add S4 and S5 | Setups that meet §11 go LIVE |

---

## 13. Compliance (personal use)

- **Keep it personal.** Sending these signals to other people, free or paid, counts as research or advice and needs **SEBI Research Analyst registration**.
- **No orders through the API means the retail-algo rules don't apply.** Those rules (static IP, Algo ID, effective 1 Apr 2026) cover API order placement, so a signals-only tool avoids them. If auto-execution is added later, they apply in full.
- **Keep live NSE data private.** Broker data is licensed for personal use, so the dashboard must sit **behind a login**, not on a public URL.
- **This is not legal or tax advice.** F&O income is taxed as business income; consult a CA.

---

## 14. Main risks

| Risk | Mitigation |
|---|---|
| Overfitting | Few parameters, walk-forward, shadow test, auto-demotion |
| Regime breaks in history (BANK NIFTY and FIN NIFTY weeklies ended, Thursday → Tuesday, lot sizes, STT) | Backtest only comparable periods; contract specs loaded from the instrument master |
| Bad or stale data | Heartbeats, `STALE` gate leading to NO TRADE, gap fill, Telegram alert |
| Illiquid strikes (especially FIN NIFTY) | Spread and depth filters; NO TRADE when they fail |
| Expiry-day gamma | Only S6 runs on expiry day, at half size, with a 14:45 cut-off |
| Event shocks | Calendar windows plus the shock detector |
| Broker token expiry | 08:30 one-tap login link; alert if not refreshed by 08:50 |
| Treating signals as certainties | Grades plus real stats, visible losses, and "NO TRADE" days |

---

## 15. Decisions (all answered, 16 Oct 2026)
- **Broker:** Kite Connect, set up from scratch.
- **Alerts:** Telegram.
- **Signals:** intraday + positional, buy-only.
- **Index:** NIFTY first.
- **Money:** capital ₹1 lakh, 3% risk per trade, 10% daily loss stop.

**Still to do (account steps only you can do):** Appendix A (Kite) and Appendix C (Telegram). The build status is in `docs/build-progress.md`; how to run and deploy it is in `docs/options-runbook.md`.

---

## Appendix A — Kite Connect setup (you do this; about 30 minutes plus approval time)
1. **Zerodha account:** make sure the **F&O (NFO) segment is active** and **TOTP 2FA** is enabled in the Kite app.
2. **Developer account:** sign up at **developers.kite.trade**. This is a separate login from your trading account.
3. **Plan:** add credits for the **Connect** plan (₹500/month), or check Zerodha's active-trader waiver. Do **not** pick the free *Personal* plan, which has no market data.
4. **Create the app:**
   - **Type:** Connect.
   - **App name:** for example "NIFTY Signals".
   - **Zerodha Client ID:** yours.
   - **Redirect URL:** `https://api-production-fea2.up.railway.app/kite/callback`.
   - **Postback URL:** leave empty.
5. **Keys:** copy the **API key** and **API secret** into the Railway service variables `KITE_API_KEY` and `KITE_API_SECRET`. **Never paste the secret into chat or commit it to git.**
6. **Static IP:** skip. It isn't needed for data-only use.
7. **Daily use after the build:** tap Login on Telegram, sign in on Kite, and you're done. The token lasts until early the next morning.

## Appendix B — WhatsApp Cloud API setup (optional, for later; about 1 hour plus Meta review)
1. **Sender number:** get a **new SIM or number that has never been on WhatsApp**, or delete WhatsApp from a spare number first. Your personal number stays as the receiver.
2. **Meta Business:** create a **Meta Business portfolio** at business.facebook.com. Business verification is optional at this tiny volume.
3. **Developer app:** go to **developers.facebook.com**, create an app of type *Business*, and add the **WhatsApp** product.
   - Meta gives you a **free test number** first. It can message up to 5 allowlisted numbers, so add your personal number and **we can build and test with it immediately**.
4. **Real sender:** add the new SIM as the sender in WhatsApp Manager, verify it by SMS, and set a display name such as "NIFTY Signals". Add a payment method for the few-rupees-a-month template fee.
5. **Permanent token:** create a **System User** in Business Settings, give it the WhatsApp app, and generate a **permanent access token**. Put it in Railway as `WHATSAPP_TOKEN`, along with:
   - `WHATSAPP_PHONE_NUMBER_ID` (from the WhatsApp → API Setup page)
   - `WHATSAPP_APP_SECRET` (from App settings)
   - `WHATSAPP_VERIFY_TOKEN` (any random string you choose)
   - `WHATSAPP_TO` (your personal number with country code)
6. **Webhook:** in the app's WhatsApp → Configuration, set the callback to `https://api-production-fea2.up.railway.app/whatsapp/webhook` with your verify token, and subscribe to **messages**. This works once the Week 1 code is deployed.
7. **Template:** create a **Utility** template named `daily_login` (for example "Good morning! Tap Login to start today's NIFTY signal session.") with one quick-reply button, **Login**. Meta usually approves templates within minutes to hours.

## Appendix C — Telegram bot setup (you do this; about 5 minutes, free)
1. **Create the bot:** in Telegram, open **@BotFather**, send `/newbot`, and pick a name (for example "NIFTY Signals") and a username ending in `bot`. Copy the **token** it gives you.
2. **Start it:** open your new bot and press **Start**, or send it any message. A bot can only message you after you've messaged it once.
3. **Find your chat ID:** open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser, with your token in place of `<TOKEN>`. Find `"chat":{"id":123456789` in the reply; that number is your chat ID.
4. **Set the variables:** on Railway, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` on **both** the `api` and `recorder` services.
5. **Keep it private:** don't add the bot to groups or share it, because sending signals to other people needs SEBI RA registration (§13).

## Sources
- Expiry schedule:
  - [HDFC Sky — Bank Nifty expiry](https://hdfcsky.com/blogs/share-market/bank-nifty-expiry)
  - [niftywise.org — expiry calendar](https://niftywise.org/expiry-calendar.php)
  - [strota.in — India expiry schedule](https://strota.in/india-expiry-schedule)
  - [AlgoTest — all index expiry day](https://algotest.in/blog/all-index-expiry-day/)
- Lot sizes:
  - [HDFC Sky — Jan 2026 lot sizes](https://hdfcsky.com/news/nse-revises-market-lot-sizes-for-major-index-derivatives-effective-january-2026)
  - [Kotak Neo — lot size revision](https://www.kotakneo.com/news/market-news/index-derivative-lot-size-revision-2026/)
- SEBI F&O measures:
  - [Groww — fixed expiry days](https://groww.in/blog/sebi-mandates-fixed-expiry-days-for-f-and-o-nse-and-bse-to-file-choices)
  - [Pocketful — SEBI F&O rules](https://www.pocketful.in/blog/trading/sebi-fo-new-rules/)
- STT:
  - [5paisa — STT hike](https://www.5paisa.com/news/stt-hike-on-fo-to-take-effect-from-april-1-amid-rising-options-activity)
  - [Sansa Legal — new STT rates](https://www.sansalegal.com/post/stt-hike-on-futures-and-options-new-rates-effective-april-1-2026)
- Retail algo framework:
  - [Fyers — rules from April 1](https://fyers.in/community/blogs-gdppin8d/post/sebi-s-new-algo-trading-rules-kick-in-on-april-1-here-is-what-changes-Yew3vdG4CgoXk1q)
  - [AlgoBulls — SEBI algo rules](https://algobulls.com/blog/industry-insights-and-updates/sebi-new-algotrading-regulations-for-retail-investors-2026)
  - [QuantInsti — SEBI framework](https://blog.quantinsti.com/sebi-algo-trading-guidelines-retail-investors)
- Broker APIs:
  - [Zerodha forum — Kite Connect fees](https://kite.trade/forum/discussion/15015/revising-kite-connect-fees-from-2000-to-500-per-month)
  - [Zerodha forum — free API for active users](https://kite.trade/forum/discussion/16294/free-api-subscription-for-active-users)
  - [cernoquant — broker API charges](https://cernoquant.com/blog/broker-api-charges-comparison)
  - [Zerodha support — static IP](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/static-ip)
  - [Kite forum — static IP for order endpoints only](https://kite.trade/forum/discussion/comment/52114/)
- WhatsApp Cloud API:
  - [Meta — Cloud API get started](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)
  - [WhatsApp API pricing India 2026 — whautomate](https://whautomate.com/whatsapp-business-api-pricing-india)
  - [Oct 2026 pricing changes — leminai](https://leminai.com/whatsapp-api-new-pricing/)
  - [Oct 2026 pricing — greentick](https://greentick.ai/blogs/whatsapp-business-api-pricing/)
  - [Test number limitations — WANotifier](https://help.wanotifier.com/en/article/test-phone-number-limitations-kt0ly2/)

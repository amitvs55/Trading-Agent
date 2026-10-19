"""The Option Check report: what an amount in one contract can turn into, and why.

Built from market facts (facts.py) and the user's parameters only, so what-ifs are instant.

Two views of the future, side by side:
- Market view: NIFTY follows the distribution the option market itself prices (lognormal at the
  ATM implied volatility, no drift). Under it, a fairly priced option loses its spread and charges
  on average, so this view shows the ranges and the cost of being wrong, not an edge.
- History view: NIFTY's real paths over the same part of the session on past days (history.py),
  so drift, trends and fat tails are as they were.

For each view the contract is repriced along every path (Black-76, the contract's own IV, kept
fixed) and two ways of trading it are played out: holding to the horizon, and following the plan
exactly as live signals are managed (stop, T1: book half or lock half the gain, T2, trailing stop
20% under the best bid, time exit).
"""

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import numpy as np

from options.check.history import EXIT_INTRADAY, MIN_SESSIONS, MIN_SIMILAR, SESSION_MINUTES, HistoryModel, minute_of
from options.core.calendar import IST, MARKET_OPEN, NseCalendar, at_ist
from options.engine.costs import charges
from options.quant import vec
from options.quant.black76 import EXPIRY_TIME, year_fraction

N_PATHS = 4000
STEP_MIN = 5
OVERNIGHT_SHARE = 0.25          # of a day's variance that arrives between the close and the next open
TRAIL_FROM_PEAK = 0.80          # as in options/engine/lifecycle.py
LAST_BAR = time(15, 29)


@dataclass
class Params:
    amount: float = 25_000
    entry: float | None = None            # premium paid; default the ask
    horizon: str = "intraday"             # "intraday" (exit by 15:15) | "expiry" (hold to settlement)
    iv_shift: float = 0.0                 # volatility points added to the contract's IV (2 → +2%)
    slippage_pct: float = 0.0             # paid on entry and given up on exit, on top of the spread
    capital: float = 100_000
    risk_pct: float = 3.0


# ── Time ──────────────────────────────────────────────────────────────────────

def _schedule(start: datetime, end: datetime, calendar: NseCalendar) -> tuple[list[datetime], int, int, int]:
    """Simulation times every STEP_MIN trading minutes from start to end (both included), plus
    (start minute, sessions ahead, end minute) in session minutes for the history paths."""
    start, end = start.astimezone(IST), end.astimezone(IST)
    s_min = min(max(minute_of(start), 0), SESSION_MINUTES - 1)
    e_min = min(max(minute_of(end), 0), SESSION_MINUTES - 1)
    days = [start.date()]
    while days[-1] < end.date():
        days.append(calendar.next_trading_day(days[-1]))
    ahead = len(days) - 1
    minutes: list[tuple[date, int]] = []
    for i, d in enumerate(days):
        lo = s_min if i == 0 else 0
        hi = e_min if i == ahead else SESSION_MINUTES - 1
        minutes += [(d, m) for m in range(lo, hi + 1)]
    picks = sorted(set(range(0, len(minutes), STEP_MIN)) | {len(minutes) - 1})
    times = [at_ist(minutes[p][0], MARKET_OPEN) + timedelta(minutes=minutes[p][1]) for p in picks]
    if end.time() >= EXPIRY_TIME:
        times[-1] = end                                   # settlement at 15:30, not the 15:29 bar
    return times, s_min, ahead, e_min


def horizon_window(now: datetime, horizon: str, expiry: date, calendar: NseCalendar,
                   market_open: bool | None = None) -> tuple[datetime, datetime, str]:
    """(start, end, label). Outside market hours the trade starts at the next open."""
    local = now.astimezone(IST)
    if calendar.is_market_open(local) if market_open is None else market_open:
        start = local
    else:
        day = local.date() if calendar.is_trading_day(local.date()) and local.time() < MARKET_OPEN \
            else calendar.next_trading_day(local.date())
        start = at_ist(day, MARKET_OPEN)
    settle = at_ist(expiry, EXPIRY_TIME)
    if horizon == "expiry":
        return start, settle, f"expiry {expiry:%a %d %b} 15:30"
    end = at_ist(start.date(), EXIT_INTRADAY)
    if start >= end:
        end = at_ist(start.date(), LAST_BAR)
    end = min(end, settle)
    return start, end, (f"{end:%H:%M} today" if end.date() == local.date() else f"{end:%a %d %b %H:%M}")


# ── Simulation ────────────────────────────────────────────────────────────────

def _market_paths(f0: float, sigma: float, times: list[datetime], rng: np.random.Generator) -> np.ndarray:
    """Forward paths (N_PATHS × steps) with the market's variance spread over trading time and
    overnight gaps, no drift (the forward is a martingale)."""
    n = len(times)
    if n < 2:
        return np.full((N_PATHS, 1), f0)
    weights = np.empty(n - 1)
    for i in range(1, n):
        gap = (times[i] - times[i - 1]).total_seconds() / 60
        weights[i - 1] = OVERNIGHT_SHARE if times[i].date() != times[i - 1].date() else (1 - OVERNIGHT_SHARE) * gap / SESSION_MINUTES
    total_years = max((times[-1] - times[0]).total_seconds() / (365 * 24 * 3600), 1e-9)
    var = sigma ** 2 * total_years * weights / weights.sum()
    half = rng.standard_normal((N_PATHS // 2, n - 1))
    z = np.vstack([half, -half])                          # antithetic pairs: half the noise for the same work
    steps = np.sqrt(var) * z - 0.5 * var
    paths = f0 * np.exp(np.concatenate([np.zeros((len(z), 1)), np.cumsum(steps, axis=1)], axis=1))
    return paths * (f0 / paths[:, -1].mean())             # the forward is the market's mean: match it exactly


def _values(paths: np.ndarray, times: list[datetime], expiry: date, k: float, r: float, iv: float, right: str) -> np.ndarray:
    ts = np.array([year_fraction(t, expiry) for t in times])
    vals = vec.price(paths, k, ts[None, :], r, iv, right)
    if times[-1] >= at_ist(expiry, EXPIRY_TIME):
        vals[:, -1] = vec.payoff(paths[:, -1], k, right)
    return vals


def _play(vals: np.ndarray, entry: float, exit_haircut: float, plan: dict | None, lots: int, lot: int,
          settles: bool) -> dict:
    """Hold vs follow-the-plan outcomes per path, in ₹ before charges, plus how each plan path ended."""
    units = lots * lot
    bid = vals * (1 - exit_haircut)
    last = vals[:, -1] if settles else bid[:, -1]
    hold = (last - entry) * units
    if plan is None:
        return {"hold": hold, "plan": None, "outcome": None}
    n, steps = vals.shape
    stop = np.full(n, plan["stop"], dtype=float)
    t1, t2 = plan["t1"], plan["t2"]
    state = np.zeros(n, dtype=int)            # 0 active, 1 after T1, 2 done
    booked = np.zeros(n)                      # ₹ booked at T1 (2+ lots: half the units)
    did_book = np.zeros(n, dtype=bool)
    exit_px = np.full(n, np.nan)
    outcome = np.full(n, "time", dtype=object)
    half = (lots // 2) * lot
    peak = np.zeros(n)
    for j in range(1, steps):
        b = bid[:, j]
        live = state < 2
        hit_stop = live & (b <= stop)
        exit_px[hit_stop] = np.minimum(b[hit_stop], stop[hit_stop])
        outcome[hit_stop & (state == 0)] = "stop"
        outcome[hit_stop & (state == 1)] = "t1_then_stop"
        state[hit_stop] = 2
        first = (state == 0) & (b >= t1)
        if first.any():
            if half:
                booked[first] = half * (b[first] - entry)
                did_book[first] = True
                stop[first] = entry
            else:
                stop[first] = entry + 0.5 * (b[first] - entry)
            peak[first] = b[first]
            state[first] = 1
        run = state == 1
        if run.any():
            peak[run] = np.maximum(peak[run], b[run])
            t2_hit = run & (b >= t2)
            exit_px[t2_hit] = b[t2_hit]
            outcome[t2_hit] = "t2"
            state[t2_hit] = 2
            still = run & ~t2_hit
            stop[still] = np.maximum(stop[still], peak[still] * TRAIL_FROM_PEAK)
    open_ = state < 2
    exit_px[open_] = last[open_]
    outcome[open_ & (state == 1)] = "t1_then_time"
    rest = units - np.where(did_book, half, 0)
    pnl = booked + rest * (exit_px - entry)
    return {"hold": hold, "plan": pnl, "outcome": outcome}


def _exact_exit_value(f0: float, k: float, right: str, r: float, sigma_u: float, iv: float,
                      start: datetime, end: datetime, expiry: date, settles: bool) -> float:
    """E[option value at the exit] under the market view, in closed form: NIFTY's variance up to the
    exit (σ_u) plus the option's own variance from there to expiry (its IV) make one lognormal."""
    dt = max((end - start).total_seconds() / (365 * 24 * 3600), 1e-9)
    tau = 0.0 if settles else year_fraction(end, expiry)
    total_var = sigma_u ** 2 * dt + iv ** 2 * tau
    t_all = dt + tau
    from options.quant.black76 import price as b76_price
    undiscounted = b76_price(f0, k, t_all, 0.0, math.sqrt(total_var / t_all), right)
    return undiscounted * math.exp(-r * tau)


def _control(sim: dict, exact_hold_gross: float) -> dict:
    """Control variate: the hold P&L's mean is known exactly, so shift it there, and correct the plan's
    P&L by its measured co-movement with holding (β). Removes most of the sampling noise."""
    hold = sim["hold"]
    shift = exact_hold_gross - hold.mean()
    out = {**sim, "hold": hold + shift}
    if sim["plan"] is not None and hold.var() > 0:
        beta = float(np.cov(sim["plan"], hold)[0, 1] / hold.var())
        out["plan"] = sim["plan"] + beta * shift
    return out


def _summary(pnl: np.ndarray, capital_used: float, cost: float) -> dict:
    net = pnl - cost
    return {"p_profit": float((net > 0).mean()), "expected": float(net.mean()),
            "p10": float(np.percentile(net, 10)), "p50": float(np.percentile(net, 50)), "p90": float(np.percentile(net, 90)),
            "expected_pct": float(net.mean() / capital_used * 100) if capital_used else None,
            "worst": float(net.min()), "best": float(net.max())}


def _plan_summary(sim: dict, capital_used: float, cost: float) -> dict | None:
    if sim["plan"] is None:
        return None
    out = _summary(sim["plan"], capital_used, cost)
    oc = sim["outcome"]
    out["outcomes"] = {k: float((oc == k).mean()) for k in ("stop", "t1_then_stop", "t1_then_time", "t2", "time")}
    out["p_t1"] = float(np.isin(oc, ["t1_then_stop", "t1_then_time", "t2"]).mean())
    return out


# ── The report ────────────────────────────────────────────────────────────────

def _round_trip(entry: float, exit_: float, units: int) -> float:
    return charges(entry * units, max(exit_, 0) * units, 2).total


def _seed(facts: dict, params: Params) -> int:
    key = f"{facts['contract']['symbol']}|{facts['as_of']}|{facts.get('checked_at')}|{params.horizon}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def build(facts: dict, params: Params, history: HistoryModel | None, calendar: NseCalendar) -> dict:
    c = facts["contract"]
    now = datetime.fromisoformat(facts.get("checked_at") or facts["as_of"])
    expiry = date.fromisoformat(c["expiry"])
    side, right, k, lot = facts["side"], c["right"], c["strike"], c["lot_size"]
    base = {"facts": facts, "params": params.__dict__, "contract": c}

    ask, mid = c.get("ask"), c.get("mid")
    quoted = params.entry or ask or mid
    iv0 = c.get("iv")
    if not quoted or not iv0 or not facts.get("forward"):
        return {**base, "priced": False, "verdict": _verdict_unpriced(facts),
                "evidence": evidence(facts, None, params, None)}

    slip = params.slippage_pct / 100
    entry = round(quoted * (1 + slip), 2)
    spread_half = (c["spread_pct"] or 0) / 200
    exit_haircut = min(spread_half + slip, 0.5)
    iv = max(iv0 + params.iv_shift / 100, 0.01)

    lot_cost = entry * lot
    lots = int(params.amount // lot_cost) if lot_cost > 0 else 0
    shown_lots = max(lots, 1)
    units = shown_lots * lot
    used = entry * units
    buy_costs = charges(used, 0, 1).total
    max_loss = used + buy_costs
    be_unit = entry + _round_trip(entry, entry, units) / units
    breakeven = k + be_unit if right == "CE" else k - be_unit
    plan = facts.get("plan")
    if plan and params.entry:                                 # the user's own price moves the plan with it
        shift = entry - plan["entry_high"]
        plan = {**plan, "stop": max(plan["stop"] + shift, 0.05), "t1": plan["t1"] + shift, "t2": plan["t2"] + shift}
    stop_risk = (entry - plan["stop"]) * units + _round_trip(entry, plan["stop"], units) if plan else None
    budget = params.capital * params.risk_pct / 100

    start, end, end_label = horizon_window(now, params.horizon, expiry, calendar, facts.get("market_open"))
    settles = end >= at_ist(expiry, EXPIRY_TIME)
    times, s_min, ahead, e_min = _schedule(start, end, calendar)
    f0, s0, r = facts["forward"], facts["spot"] or facts["forward"], facts["r"]
    sigma_u = facts.get("atm_iv") or iv0
    rng = np.random.default_rng(_seed(facts, params))

    # Market view
    m_paths = _market_paths(f0, sigma_u, times, rng)
    m_vals = _values(m_paths, times, expiry, k, r, iv, right)
    m_sim = _play(m_vals, entry, exit_haircut, plan, shown_lots, lot, settles)
    exit_mean = _exact_exit_value(f0, k, right, r, sigma_u, iv, times[0], times[-1], expiry, settles)
    m_sim = _control(m_sim, units * ((exit_mean if settles else exit_mean * (1 - exit_haircut)) - entry))
    cost_mid = _round_trip(entry, entry, units)
    market = {"hold": _summary(m_sim["hold"], used, cost_mid), "plan": _plan_summary(m_sim, used, cost_mid),
              "paths": N_PATHS, "sigma": sigma_u}

    # History view
    hist = None
    if history is not None and history.sessions >= MIN_SESSIONS:
        rel, starts = history.paths(s_min, ahead, e_min, STEP_MIN)
        if rel.size and rel.shape[1] == len(times):
            h_vals = _values(f0 * rel, times, expiry, k, r, iv, right)
            h_sim = _play(h_vals, entry, exit_haircut, plan, shown_lots, lot, settles)
            hist = {"hold": _summary(h_sim["hold"], used, cost_mid), "plan": _plan_summary(h_sim, used, cost_mid),
                    "sessions": len(starts), "from": history.days[0].isoformat(), "to": history.days[-1].isoformat()}
            keep = history.similar(starts, s_min, facts.get("prior_move_60m"), facts.get("vix"))
            if len(keep) >= MIN_SIMILAR:
                sub = {"hold": h_sim["hold"][keep],
                       "plan": h_sim["plan"][keep] if h_sim["plan"] is not None else None,
                       "outcome": h_sim["outcome"][keep] if h_sim["outcome"] is not None else None}
                hist["similar"] = {"hold": _summary(sub["hold"], used, cost_mid), "plan": _plan_summary(sub, used, cost_mid),
                                   "sessions": len(keep),
                                   "rule": "same direction over the previous hour" + (", India VIX within ±20%" if facts.get("vix") else "")}
            else:
                hist["similar"] = {"sessions": len(keep), "rule": "too few similar sessions (need 30)"}
        else:
            hist = {"sessions": 0, "note": "not enough complete sessions for this horizon"}
    elif history is not None:
        hist = {"sessions": history.sessions, "note": f"needs at least {MIN_SESSIONS} saved sessions"}

    report = {
        **base, "priced": True,
        "position": {"entry": entry, "lots": lots, "shown_lots": shown_lots, "units": units, "lot_cost": lot_cost,
                     "capital_used": used, "leftover": max(params.amount - used, 0) if lots else 0,
                     "min_amount": lot_cost + buy_costs if lots == 0 else None,
                     "buy_charges": buy_costs, "round_trip_charges": cost_mid, "max_loss": max_loss,
                     "breakeven": breakeven, "stop_risk": stop_risk, "budget": budget,
                     "over_budget": (stop_risk or max_loss) > budget, "iv_used": iv},
        "plan": plan,
        "horizon": {"start": start.isoformat(), "end": end.isoformat(), "label": end_label, "settles": settles,
                    "starts_at_open": start > now},
        "market": market, "history": hist,
        "scenarios": scenarios(facts, entry, exit_haircut, iv, units, times, expiry, sigma_u, settles),
        "curve": curve(facts, entry, iv, units, times, expiry, sigma_u, settles),
    }
    report["verdict"] = verdict(facts, report)
    report["evidence"] = evidence(facts, report, params, history)
    return report


def scenarios(facts, entry, haircut, iv, units, times, expiry, sigma_u, settles) -> dict:
    """₹ P&L (after charges) if NIFTY is at each level at a few moments."""
    c = facts["contract"]
    f0, s0, r = facts["forward"], facts["spot"] or facts["forward"], facts["r"]
    ratio = f0 / s0
    horizon_years = max((times[-1] - times[0]).total_seconds() / (365 * 24 * 3600), 1e-6)
    sd = s0 * sigma_u * math.sqrt(horizon_years)
    basis = (facts.get("fut") or s0) - s0
    rows: dict[float, str] = {round(s0, 0): "now"}
    for mult, name in ((-2, "−2σ"), (-1, "−1σ"), (1, "+1σ"), (2, "+2σ")):
        rows.setdefault(round(s0 + mult * sd, 0), name)
    for name, lvl in (facts.get("levels") or {}).items():
        spot_lvl = lvl - basis                                  # levels are in futures points
        if abs(spot_lvl - s0) <= 2.5 * sd:
            rows.setdefault(round(spot_lvl, 0), name)
    for name in ("put", "call"):
        w = (facts.get("oi_walls") or {}).get(name)
        if w and abs(w - s0) <= 2.5 * sd:
            rows.setdefault(round(float(w), 0), f"{name} wall")
    be = (c["strike"] + entry) if c["right"] == "CE" else (c["strike"] - entry)
    if abs(be - s0) <= 3 * sd:
        rows.setdefault(round(be, 0), "breakeven (premium)")
    moments = []
    t0 = times[0]
    for label, when in (("in 30 min", t0 + timedelta(minutes=30)), ("at the exit", times[-1])):
        if when <= times[-1] and (not moments or when > moments[-1][1]):
            moments.append((label, when))
    out_rows = []
    for spot_lvl in sorted(rows, reverse=True):
        cells = []
        for label, when in moments:
            f = spot_lvl * ratio
            if settles and when >= times[-1]:
                val = float(vec.payoff(f, c["strike"], c["right"]))
                exit_ = val
            else:
                val = float(vec.price(f, c["strike"], year_fraction(when, expiry), r, iv, c["right"]))
                exit_ = val * (1 - haircut)
            pnl = (exit_ - entry) * units - _round_trip(entry, exit_, units)
            cells.append({"value": round(exit_, 2), "pnl": round(pnl, 0)})
        out_rows.append({"spot": spot_lvl, "label": rows[spot_lvl], "move_pct": (spot_lvl / s0 - 1) * 100, "cells": cells})
    return {"moments": [{"label": lbl, "at": w.isoformat()} for lbl, w in moments], "rows": out_rows, "sd": sd}


def curve(facts, entry, iv, units, times, expiry, sigma_u, settles) -> dict:
    """P&L across NIFTY levels at the exit and at expiry, with the market's 1σ/2σ ranges."""
    c = facts["contract"]
    f0, s0, r = facts["forward"], facts["spot"] or facts["forward"], facts["r"]
    ratio = f0 / s0
    horizon_years = max((times[-1] - times[0]).total_seconds() / (365 * 24 * 3600), 1e-6)
    sd = s0 * sigma_u * math.sqrt(horizon_years)
    xs = np.linspace(s0 - 3 * sd, s0 + 3 * sd, 61)
    exit_vals = vec.payoff(xs * ratio, c["strike"], c["right"]) if settles else \
        vec.price(xs * ratio, c["strike"], year_fraction(times[-1], expiry), r, iv, c["right"])
    expiry_vals = vec.payoff(xs * ratio, c["strike"], c["right"])
    cost = _round_trip(entry, entry, units)
    return {"spot": s0, "sd": sd,
            "points": [{"x": round(float(x), 1), "exit": round(float((v - entry) * units - cost), 0),
                        "expiry": round(float((e - entry) * units - cost), 0)}
                       for x, v, e in zip(xs, exit_vals, expiry_vals)]}


# ── Verdict ───────────────────────────────────────────────────────────────────

BLOCKING_GATES = {"data_fresh", "no_market_shock", "no_fresh_news", "liquidity"}


def _verdict_unpriced(facts: dict) -> dict:
    return {"call": "Can't price", "tone": "neutral", "score": facts.get("score"),
            "summary": "No usable quote or volatility for this contract, so the money side can't be worked out.",
            "for": [], "against": [f"Quote: {facts['contract'].get('quote_source', 'none')}"]}


def verdict(facts: dict, rep: dict) -> dict:
    pill = {p["pillar"]: p for p in facts.get("pillars", [])}
    score = facts.get("score") or 0
    gates = {g["name"]: g for g in facts.get("gates", [])}
    c, pos = facts["contract"], rep["position"]
    hist = rep.get("history") or {}
    view = (hist.get("similar") if (hist.get("similar") or {}).get("hold") else None) or (hist if hist.get("hold") else None)
    view_name = "similar past sessions" if view is not None and view is hist.get("similar") else "past sessions"
    market = rep["market"]
    use_plan = bool(rep.get("plan"))
    key = "plan" if use_plan else "hold"
    h_ev = (view or {}).get(key, {}) or {}
    m_ev = market.get(key) or {}

    fors, againsts, blocks = [], [], []
    for name in ("trend", "futures_flow", "option_chain", "momentum", "breadth", "levels"):
        p = pill.get(name)
        if not p:
            continue
        label = name.replace("_", " ").capitalize()
        if p["status"] == "pass":
            fors.append((PRIORITY[name], f"{label}: {p['detail']}"))
        elif p["status"] == "fail":
            againsts.append((PRIORITY[name], f"{label} against: {p['detail']}"))
    if facts["candidate"]["setups_fired"]:
        fors.append((9, facts["candidate"]["note"]))
    for name, g in gates.items():
        if not g["ok"] and (name in BLOCKING_GATES or (name == "session_open" and facts["market_open"])):
            (blocks if name in BLOCKING_GATES else againsts).append((10, g["reason"]))
    if c.get("spread_pct") is not None and c["spread_pct"] <= 1.0:
        fors.append((4, f"Tight spread ({c['spread_pct']:.1f}%)"))
    greeks = c.get("greeks") or {}
    if greeks.get("theta_day") and c.get("mid"):
        per_hour = abs(greeks["theta_day"]) / 24                           # decay runs on the clock
        decay_pct = per_hour / c["mid"] * 100
        if decay_pct >= 1:
            againsts.append((7, f"Time decay ≈ ₹{per_hour * pos['units']:,.0f} an hour on this position "
                                f"({decay_pct:.1f}% of the premium) if NIFTY stands still"))
    if facts.get("expiry_day"):
        againsts.append((6, "Expires today: the premium melts fast and small moves swing it hard"))
    if h_ev.get("expected") is not None:
        line = (f"{view_name.capitalize()}: averaged ₹{h_ev['expected']:+,.0f} after charges "
                f"({h_ev['p_profit'] * 100:.0f}% made money, n={view.get('sessions')})")
        (fors if h_ev["expected"] > 0 else againsts).append((8, line))
    if pos["over_budget"]:
        againsts.append((5, f"Risk ₹{(pos['stop_risk'] or pos['max_loss']):,.0f} is over your "
                            f"{rep['params']['risk_pct']:g}% rule (₹{pos['budget']:,.0f})"))
    rr = (rep.get("plan") or {}).get("rr1")
    if rr is not None:
        (fors if rr >= 1.3 else againsts).append((5, f"Reward:risk to T1 {rr:.2f}"))

    trend_fail = pill.get("trend", {}).get("status") == "fail"
    flow_fail = pill.get("futures_flow", {}).get("status") == "fail"
    h_expected = h_ev.get("expected")
    weak_money = (h_expected is not None and h_expected < -0.10 * pos["capital_used"]
                  and (m_ev.get("expected") or 0) < -0.10 * pos["capital_used"])
    if blocks or (trend_fail and flow_fail) or score < 45 or weak_money:
        call, tone = "Avoid", "bad"
    elif score >= 60 and not trend_fail and (h_expected is None or h_expected >= 0):
        call, tone = "Worth taking", "good"
    else:
        call, tone = "Marginal", "warn"
    summary = {
        "Avoid": "The evidence is against this trade right now.",
        "Worth taking": "Direction and history both lean your way; size it within your rules.",
        "Marginal": "Some of the evidence agrees, some doesn't: there's no clear edge.",
    }[call]
    if not facts["market_open"]:
        summary += " Market closed: prices are from the last session and will differ at the open."
    return {"call": call, "tone": tone, "score": round(score, 1), "summary": summary,
            "basis": f"{view_name} ({key})" if h_ev else f"market view ({key})",
            "blocks": [b for _, b in blocks],
            "for": [t for _, t in sorted(fors, key=lambda x: -x[0])[:3]],
            "against": [t for _, t in sorted(blocks + againsts, key=lambda x: -x[0])[:3]]}


PRIORITY = {"trend": 10, "futures_flow": 9, "option_chain": 8, "momentum": 6, "breadth": 5, "levels": 7}


# ── Evidence ──────────────────────────────────────────────────────────────────

def evidence(facts: dict, rep: dict | None, params: Params, history: HistoryModel | None) -> dict:
    c = facts["contract"]
    greeks = c.get("greeks") or {}
    numbers = [
        ("NIFTY spot", facts.get("spot")), ("NIFTY future", facts.get("fut")),
        (f"Forward for {c['expiry']}", facts.get("forward")), ("Forward from", facts.get("forward_source")),
        ("Contract bid / ask", f"{c.get('bid') or '—'} / {c.get('ask') or '—'} ({c.get('quote_source')})"),
        ("Spread", f"{c['spread_pct']:.2f}%" if c.get("spread_pct") is not None else None),
        ("Open interest", c.get("oi")),
        ("OI change today", f"{c['oi_change_pct']:+.1f}%" if c.get("oi_change_pct") is not None else None),
        ("Contract IV", f"{c['iv'] * 100:.1f}%" if c.get("iv") else None),
        ("ATM IV", f"{facts['atm_iv'] * 100:.1f}%" if facts.get("atm_iv") else None),
        ("Realised vol (20 days)", f"{facts['rv20'] * 100:.1f}%" if facts.get("rv20") else None),
        ("India VIX", f"{facts['vix']:.2f}" + (f" (1-yr percentile {facts['vix_pct']:.0f})" if facts.get("vix_pct") is not None else "")
         if facts.get("vix") else None),
        ("Delta", f"{greeks['delta']:.2f}" if greeks.get("delta") is not None else None),
        ("Theta per day", f"₹{greeks['theta_day']:.2f} per unit" if greeks.get("theta_day") is not None else None),
        ("Vega", f"₹{greeks['vega']:.2f} per vol point" if greeks.get("vega") is not None else None),
        ("Expected move today (1σ)", f"±{facts['expected_move_1d']:,.0f} pts" if facts.get("expected_move_1d") else None),
        ("Regime / phase", f"{facts.get('regime')} · {facts.get('phase')}"),
        ("Higher-timeframe trend", facts.get("htf_trend")),
        ("Put / call OI walls", f"{facts['oi_walls'].get('put') or '—'} / {facts['oi_walls'].get('call') or '—'}"),
        ("PCR", f"{facts['oi_walls']['pcr']:.2f}" if (facts.get("oi_walls") or {}).get("pcr") else None),
        ("The idea is wrong if", f"NIFTY future closes a 5-min bar {'below' if facts['side'] > 0 else 'above'} "
                                 f"{facts['candidate']['invalidation']:,.0f}"),
    ]
    assumptions = [
        "Pricing: Black-76 on the NIFTY forward for this expiry; time to the 15:30 expiry in calendar years.",
        f"The contract's implied volatility stays at {((rep or {}).get('position') or {}).get('iv_used', c.get('iv') or 0) * 100:.1f}% "
        "while you hold it (no volatility crush or spike unless you move the slider).",
        "You buy at the ask (or your price) and sell at the bid: half the current spread is lost on exit"
        + (f", plus {params.slippage_pct:g}% slippage each way." if params.slippage_pct else "."),
        "Charges: ₹20 per order, STT 0.15% on the sell side, exchange, SEBI, stamp duty and 18% GST "
        "(options/engine/costs.py). An option held to expiry is charged as a sale at its intrinsic value.",
        "Market view: NIFTY moves with the volatility the options market prices (ATM IV), no drift; a quarter "
        "of each day's variance arrives overnight. 4,000 simulated paths.",
        "History view: NIFTY's actual paths over the same session window on past days, scaled to today's level.",
        "Following the plan: stop, T1 (book half with 2+ lots, else lock half the gain), T2, trailing stop "
        "20% under the best bid, then exit at the horizon, exactly as live signals are managed.",
    ]
    if facts["forward_source"].startswith("spot carried"):
        assumptions.append("No chain is recorded for this expiry, so the forward is spot carried at the "
                           "risk-free rate; dividends are ignored.")
    if not facts["market_open"]:
        assumptions.append("Market closed: the trade is assumed to start at the next open at today's last "
                           "prices, which will differ.")
    return {
        "pillars": facts.get("pillars", []),
        "gates": facts.get("gates", []),
        "numbers": [{"label": k, "value": v} for k, v in numbers if v not in (None, "")],
        "assumptions": assumptions,
        "data_times": {"facts": facts["as_of"], "market_data": facts.get("data_as_of"), "source": facts["source"]},
        "history_span": ({"sessions": history.sessions, "from": history.days[0].isoformat(),
                          "to": history.days[-1].isoformat()} if history is not None and history.sessions else None),
        "why_market_view_loses": "Under the market's own pricing an option is worth what you pay, so on average "
                                 "it returns the price minus the spread and charges. An edge has to come from "
                                 "direction: that's what the pillars and the history view test.",
    }

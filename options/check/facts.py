"""Market facts for one contract: everything the check needs from the engine, as plain data.

Computed where the market state lives: inside the recorder during market hours (the same snapshot,
chain and live quotes the signals use), or by the API from saved bars when the market is closed.
The report (report.py) is built from these facts alone, so a what-if never asks the recorder again.

A hand-picked contract has no setup behind it, so the check builds the candidate a setup would:
the trigger is the future now, and the idea is wrong beyond the nearest technical level against
the trade (kept 0.5–1.5 five-minute ATRs away, like the setups do). Every pillar is then checked
for that direction exactly as for a signal.
"""

import math
from datetime import datetime

from options.agents.option_chain import ChainRow, build_chain
from options.agents.volatility import price_chain
from options.core.calendar import IST
from options.engine import grading
from options.engine.levels import plan
from options.engine.snapshot import Snapshot
from options.quant import black76 as b76
from options.reference import OptionInfo
from options.setups import ALL_SETUPS, SETUP_LABELS
from options.setups.base import Candidate, bounded_invalidation

HORIZONS = {"intraday": "intraday", "expiry": "positional"}     # the check's choice → the engine's horizon
QUOTE_MAX_AGE_S = 180


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def manual_candidate(snap: Snapshot, side: int, horizon: str) -> Candidate:
    tech, ctx = snap.tech, snap.ctx
    price = ctx.fut or ctx.spot
    atr = tech.atr_5m or price * 0.001
    against = [v for v in tech.levels.values() if (v - price) * side < 0]
    raw = (max(against) if side > 0 else min(against)) if against else price - side * atr
    fired = []
    for setup in ALL_SETUPS:
        try:
            cand = setup.detect(snap)
        except Exception:
            cand = None
        if cand is not None and cand.side == side:
            fired.append(setup.label)
    note = (f"{', '.join(fired)} fired for this direction" if fired
            else "No setup trigger right now: a hand-picked entry")
    return Candidate("MANUAL", side, HORIZONS[horizon], price, bounded_invalidation(price, raw, side, atr),
                     ctx.ref.future_token, "5min", "pass" if fired else "warn", note)


def contract_row(opt: OptionInfo, quote: dict | None, snap: Snapshot, now: datetime) -> tuple[ChainRow | None, str]:
    """The contract's quote as a chain row: the broker's quote if given, else the last recorded bar."""
    ctx = snap.ctx
    src = "live quote"
    bid = ask = ltp = oi = None
    if quote:
        bid, ask, ltp, oi = (_num(quote.get(k)) for k in ("bid", "ask", "ltp", "oi"))
    if not (bid or ask or ltp):
        last = ctx.state.last(opt.token)
        if last is None:
            return None, "no quote"
        as_of = last.get("ts")
        bid, ask, ltp, oi = _num(last.get("bid")), _num(last.get("ask")), _num(last.get("close")), _num(last.get("oi"))
        src = "last recorded minute"
        if as_of is not None and (now - as_of).total_seconds() > QUOTE_MAX_AGE_S:
            src = f"last recorded minute ({as_of.astimezone(IST):%d %b %H:%M})"
    row = ChainRow(opt.strike, opt.right, opt.token, opt.tradingsymbol, opt.lot_size, ltp=ltp, bid=bid, ask=ask, oi=oi,
                   oi_open=ctx.day_open_value(opt.token, "oi"), oi_15m=ctx.value_at(opt.token, "oi", 15),
                   oi_30m=ctx.value_at(opt.token, "oi", 30))
    return row, src


def forward_for(snap: Snapshot, opt: OptionInfo, now: datetime) -> tuple[float | None, float, dict | None, str]:
    """(forward, t, chain ATM IVs, how the forward was found) for the contract's expiry."""
    ctx = snap.ctx
    t = b76.year_fraction(now, opt.expiry)
    chain = build_chain(ctx, opt.expiry) if opt.expiry in ctx.ref.expiries else None
    if chain is not None:
        fwd, t = price_chain(ctx, chain)
        if fwd:
            ivs = [r.greeks["iv"] for r in (chain.get(chain.atm, "CE"), chain.get(chain.atm, "PE")) if r and r.greeks.get("iv")]
            return fwd, t, {"atm": chain.atm, "atm_iv": sum(ivs) / len(ivs) if ivs else None}, "put-call parity at the ATM strike"
    if ctx.ref.future_expiry == opt.expiry and ctx.fut:
        return ctx.fut, t, None, "the future of the same expiry"
    spot = ctx.spot or ctx.fut
    if not spot:
        return None, t, None, "no price"
    return spot * math.exp(ctx.r * t), t, None, "spot carried at the risk-free rate (no chain recorded for this expiry)"


def market_facts(snap: Snapshot, opt: OptionInfo, horizon: str, now: datetime, quote: dict | None = None,
                 open_signals: list | None = None, source: str = "live engine", checked_at: datetime | None = None,
                 market_open: bool | None = None) -> dict:
    """`now` is the moment of the data; `checked_at` the moment of the check (later when the data is
    saved, e.g. an evening check on the last session), which is when a trade could start."""
    ctx = snap.ctx
    side = 1 if opt.right == "CE" else -1
    cand = manual_candidate(snap, side, horizon)
    row, quote_src = contract_row(opt, quote, snap, now)
    fwd, t, chain_info, fwd_src = forward_for(snap, opt, now)

    contract = {"symbol": opt.tradingsymbol, "token": opt.token, "index": ctx.index, "expiry": opt.expiry.isoformat(),
                "strike": opt.strike, "right": opt.right, "lot_size": opt.lot_size, "quote_source": quote_src,
                "bid": None, "ask": None, "ltp": None, "mid": None, "spread_pct": None, "oi": None,
                "oi_change_pct": None, "volume": _num((quote or {}).get("volume")), "iv": None, "greeks": None}
    trade = None
    pillars, gates, score = [], [], None
    if row is not None:
        contract.update(bid=row.bid, ask=row.ask, ltp=row.ltp, mid=row.mid, spread_pct=row.spread_pct, oi=row.oi,
                        oi_change_pct=((row.oi / row.oi_open - 1) * 100) if row.oi and row.oi_open else None)
        if fwd and row.mid:
            iv = b76.implied_vol(row.mid, fwd, opt.strike, t, ctx.r, opt.right)
            if iv:
                g = b76.greeks(fwd, opt.strike, t, ctx.r, iv, opt.right)
                row.greeks = {"iv": iv, "delta": g.delta, "gamma": g.gamma, "vega": g.vega, "theta_day": g.theta_day}
                contract.update(iv=iv, greeks={"delta": g.delta, "gamma": g.gamma, "vega": g.vega, "theta_day": g.theta_day})
        room = snap.tech.room(side, cand.trigger)[0]
        trade = plan(row, side, cand.horizon, cand.trigger, cand.invalidation, fwd, t, ctx.r, room) if fwd else None
        checks = grading.checks(snap, cand, row)
        if trade is not None:
            gate_list = grading.gates(snap, cand, frozenset({snap.regime.regime}), checks, trade, None)
            gates = [{"name": g.name, "ok": g.ok, "reason": g.reason} for g in gate_list
                     if g.name not in ("risk_budget", "regime_allows_setup")]
        _, score, _ = grading.grade(checks, [])
        pillars = [{"pillar": c.pillar, "status": c.status, "detail": c.detail} for c in grading.ordered(checks)]

    vol = snap.vol
    spot_tok = ctx.ref.spot_token
    back = ctx.value_at(spot_tok, "close", 60) or ctx.day_open_value(spot_tok, "close")
    prior = (ctx.spot / back - 1) if ctx.spot and back else None
    levels = {k: round(v, 2) for k, v in sorted(snap.tech.levels.items(), key=lambda kv: -kv[1])}
    oi = snap.oi.features or {}
    on_contract = [s for s in (open_signals or []) if s.contract.token == opt.token]
    return {
        "v": 1,
        "source": source,
        "as_of": now.astimezone(IST).isoformat(timespec="seconds"),
        "checked_at": (checked_at or now).astimezone(IST).isoformat(timespec="seconds"),
        "data_as_of": ctx.state.as_of().astimezone(IST).isoformat(timespec="seconds") if ctx.state.as_of() else None,
        "market_open": ctx.calendar.is_market_open(now) if market_open is None else market_open,
        "phase": snap.regime.phase,
        "index": ctx.index, "side": side, "horizon": horizon,
        "spot": ctx.spot, "fut": ctx.fut, "prior_move_60m": prior, "forward": fwd, "forward_source": fwd_src, "t": t, "r": ctx.r,
        "contract": contract,
        "atm_iv": (chain_info or {}).get("atm_iv") or vol.atm_iv, "vix": vol.vix, "vix_pct": vol.vix_pct,
        "rv20": vol.rv20, "expected_move_1d": vol.expected_move_1d,
        "regime": snap.regime.regime, "htf_trend": snap.tech.htf_trend, "atr_5m": snap.tech.atr_5m,
        "expiry_day": opt.expiry == now.astimezone(IST).date(),
        "levels": levels,
        "oi_walls": {"put": oi.get("put_wall"), "call": oi.get("call_wall"), "max_pain": oi.get("max_pain"),
                     "pcr": oi.get("pcr")},
        "candidate": {"trigger": cand.trigger, "invalidation": round(cand.invalidation, 2), "note": cand.note,
                      "setups_fired": cand.trigger_quality == "pass"},
        "plan": None if trade is None else {
            "entry_low": trade.entry_low, "entry_high": trade.entry_high, "stop": trade.stop, "t1": trade.t1,
            "t2": trade.t2, "rr1": trade.rr1, "rr2": trade.rr2, "risk_points": trade.risk_points,
            "t1_points": trade.t1_points, "t2_points": trade.t2_points},
        "score": score, "pillars": pillars, "gates": gates,
        "events": {"window_active": snap.events.window_active, "detail": snap.events.pillar.detail,
                   "next": ({"name": snap.events.next_event.name, "at": snap.events.next_event.at.isoformat()}
                            if snap.events.next_event else None)},
        "engine_signals": [{"id": s.signal_id, "state": s.state.value, "grade": s.grade.value, "mode": s.mode,
                            "entry_high": s.entry_high, "stop": s.stop_loss, "t1": s.t1, "t2": s.t2}
                           for s in on_contract],
        "setup_labels": SETUP_LABELS,
    }

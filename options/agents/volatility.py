"""Volatility & Greeks agent (pillar 7) and per-contract option quality (pillar 8).

India VIX percentile over the last year stands in for IV percentile until the tool has
collected a year of its own ATM IV history.
"""

import math
from dataclasses import dataclass

import numpy as np

from options.agents.context import AgentContext
from options.agents.option_chain import Chain, ChainRow
from options.core.schemas import PillarCheck, PillarView
from options.quant import black76 as b76

BUY_IV_PASS_PCT = 50       # buyers want premium cheap or fair
BUY_IV_FAIL_PCT = 70       # above this, buying premium is a NO TRADE (plan §4)


@dataclass
class VolView:
    pillar: PillarView
    forward: float | None = None
    t: float | None = None
    atm_iv: float | None = None
    vix: float | None = None
    vix_change_pct: float | None = None
    vix_pct: float | None = None
    rv20: float | None = None
    expected_move_1d: float | None = None
    regime: str = "unknown"            # cheap | fair | rich | unknown


def percentile_rank(value: float, history: list[float]) -> float | None:
    if len(history) < 50:
        return None
    return float((np.asarray(history) < value).mean() * 100)


def realized_vol(closes: list[float], window: int = 20) -> float | None:
    if len(closes) <= window:
        return None
    r = np.diff(np.log(np.asarray(closes[-(window + 1):], dtype=float)))
    return float(r.std(ddof=1) * math.sqrt(252))


def price_chain(ctx: AgentContext, chain: Chain) -> tuple[float | None, float]:
    """Fill each row's IV and Greeks; return (forward, t)."""
    t = b76.year_fraction(ctx.now, chain.expiry)
    ce, pe = chain.get(chain.atm, "CE"), chain.get(chain.atm, "PE")
    fwd = None
    if ce and pe and ce.mid and pe.mid:
        fwd = b76.synthetic_forward(chain.atm, ce.mid, pe.mid, ctx.r, t)
    fwd = fwd or ctx.fut or ctx.spot
    if not fwd:
        return None, t
    for row in chain.rows.values():
        if not row.mid:
            continue
        iv = b76.implied_vol(row.mid, fwd, row.strike, t, ctx.r, row.right)
        if iv:
            g = b76.greeks(fwd, row.strike, t, ctx.r, iv, row.right)
            row.greeks = {"iv": iv, "delta": g.delta, "gamma": g.gamma, "vega": g.vega, "theta_day": g.theta_day}
    return fwd, t


def analyse(ctx: AgentContext, chain: Chain | None) -> VolView:
    vix = ctx.state.last_price(ctx.vix_token) if ctx.vix_token else None
    prev = ctx.state.prev_day(ctx.vix_token) if ctx.vix_token else None
    vix_chg = (vix / prev["close"] - 1) * 100 if vix and prev else None
    vix_pct = percentile_rank(vix, ctx.vix_history) if vix else None
    closes = ctx.state.daily(ctx.ref.spot_token, include_today=False)["close"].tolist()
    rv20 = realized_vol(closes)

    fwd, t, atm_iv = None, None, None
    if chain:
        fwd, t = price_chain(ctx, chain)
        ivs = [r.greeks["iv"] for r in (chain.get(chain.atm, "CE"), chain.get(chain.atm, "PE")) if r and r.greeks]
        atm_iv = sum(ivs) / len(ivs) if ivs else None
    move = fwd * atm_iv * math.sqrt(1 / 365) if fwd and atm_iv else None

    parts = []
    if vix:
        parts.append(f"VIX {vix:.1f}" + (f" ({vix_chg:+.1f}%)" if vix_chg is not None else ""))
    if atm_iv:
        parts.append(f"ATM IV {atm_iv * 100:.1f}%")
    if rv20:
        parts.append(f"RV20 {rv20 * 100:.1f}%")

    if vix_pct is not None:
        parts.append(f"VIX pct {vix_pct:.0f}")
        status = "pass" if vix_pct < BUY_IV_PASS_PCT else "warn" if vix_pct < BUY_IV_FAIL_PCT else "fail"
        regime = "cheap" if vix_pct < 40 else "fair" if vix_pct < BUY_IV_FAIL_PCT else "rich"
    elif atm_iv and rv20:
        ratio = atm_iv / rv20
        parts.append(f"IV/RV {ratio:.2f}")
        status = "pass" if ratio < 1.2 else "warn" if ratio < 1.5 else "fail"
        regime = "cheap" if ratio < 1.0 else "fair" if ratio < 1.5 else "rich"
    else:
        status, regime = "na", "unknown"
    if vix_chg is not None and vix_chg > 3 and status == "warn":
        parts.append("VIX rising helps buyers")
        status = "pass"

    return VolView(PillarView("volatility", " · ".join(parts) or "No volatility data yet", status=status,
                              features={"vix": vix, "vix_pct": vix_pct, "atm_iv": atm_iv, "rv20": rv20}),
                   forward=fwd, t=t, atm_iv=atm_iv, vix=vix, vix_change_pct=vix_chg, vix_pct=vix_pct,
                   rv20=rv20, expected_move_1d=move, regime=regime)


# Time decay judged over the expected hold: intraday ~2 hours, positional per day held
DECAY_RULES = {"intraday": (2 / 24, 2.0, 4.0, "2h"), "positional": (1.0, 8.0, 12.0, "day")}


def option_quality(row: ChainRow, horizon: str = "intraday") -> PillarCheck:
    """Pillar 8 for the chosen contract: bid-ask spread and time decay relative to premium."""
    spread, premium, theta = row.spread_pct, row.mid, row.greeks.get("theta_day")
    if spread is None or not premium:
        return PillarCheck(pillar="option_quality", status="na", detail="No live quote")
    days, warn_at, fail_at, label = DECAY_RULES[horizon]
    decay = abs(theta) * days / premium * 100 if theta else None
    detail = f"spread {spread:.1f}%" + (f", decay {decay:.1f}% of premium per {label}" if decay is not None else "")
    if spread > 3 or (decay is not None and decay >= fail_at):
        status = "fail"
    elif spread > 1.5 or (decay is not None and decay >= warn_at):
        status = "warn"
    else:
        status = "pass"
    return PillarCheck(pillar="option_quality", status=status, detail=detail)

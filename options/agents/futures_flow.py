"""Futures & OI flow agent (pillar 5): buildup type, basis and volume surge."""

import math

from options.agents.context import AgentContext
from options.core.schemas import PillarView
from options.quant.black76 import year_fraction

PRICE_MIN_PCT = 0.03       # smaller price moves over the window count as flat
OI_MIN_PCT = 0.10          # smaller OI changes count as flat

BUILDUPS = {
    (1, 1): ("long buildup", 1, 0.8),
    (1, -1): ("short covering", 1, 0.6),
    (-1, 1): ("short buildup", -1, 0.8),
    (-1, -1): ("long unwinding", -1, 0.6),
}


def classify(dp_pct: float, doi_pct: float) -> tuple[str, int, float]:
    p = 1 if dp_pct > PRICE_MIN_PCT else -1 if dp_pct < -PRICE_MIN_PCT else 0
    o = 1 if doi_pct > OI_MIN_PCT else -1 if doi_pct < -OI_MIN_PCT else 0
    if p == 0:
        return "no clear flow", 0, 0.0
    if o == 0:
        return ("price up, OI flat" if p > 0 else "price down, OI flat"), p, 0.4
    return BUILDUPS[(p, o)]


def analyse(ctx: AgentContext, window_min: int = 15) -> PillarView:
    token = ctx.ref.future_token
    price_now, price_then = ctx.fut, ctx.value_at(token, "close", window_min)
    oi_now, oi_then = ctx.value_at(token, "oi", 0), ctx.value_at(token, "oi", window_min)
    if not (price_now and price_then and oi_now and oi_then):
        return PillarView("futures_flow", "Waiting for 15 minutes of futures data")

    dp = (price_now / price_then - 1) * 100
    doi = (oi_now / oi_then - 1) * 100
    label, bias, strength = classify(dp, doi)

    f5 = ctx.state.frame(token, "5min")
    vol = f5["volume"] if not f5.empty else None
    vol_ratio = None
    if vol is not None and len(vol) > 21 and (vol.iloc[-21:-1] > 0).all():       # see technical.py
        vol_ratio = float(vol.iloc[-1] / vol.iloc[-21:-1].mean())
        if bias and vol_ratio >= 1.5:
            strength = min(1.0, strength + 0.2)

    features = {"price_chg_pct": dp, "oi_chg_pct": doi, "volume_ratio": vol_ratio}
    parts = [f"{label}: fut {dp:+.2f}%, OI {doi:+.1f}% ({window_min}m)"]
    if vol_ratio:
        parts.append(f"vol {vol_ratio:.1f}× avg")

    spot = ctx.spot
    if spot:
        t = year_fraction(ctx.now, ctx.ref.future_expiry)
        fair = spot * (math.exp(ctx.r * t) - 1)
        basis = price_now - spot
        features.update({"basis": basis, "basis_vs_fair": basis - fair})
        parts.append(f"basis {basis:+.0f} (fair {fair:+.0f})")

    return PillarView("futures_flow", " · ".join(parts), bias=bias, strength=strength, features=features)

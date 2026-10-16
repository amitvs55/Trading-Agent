"""Constituents & breadth agent (pillar 9): do the heavyweights confirm the index move?"""

from options.agents.context import AgentContext
from options.core.schemas import PillarView


def analyse(ctx: AgentContext) -> PillarView:
    rows = []
    for c in ctx.constituents:
        px = ctx.state.last_price(c.token)
        if px is None or not c.prev_close:
            continue
        then = ctx.value_at(c.token, "close", 15)
        rows.append((c, (px / c.prev_close - 1) * 100, (px / then - 1) * 100 if then else 0.0))
    if not ctx.constituents:
        return PillarView("breadth", "No constituent list configured", status="na")
    if len(rows) < len(ctx.constituents) / 2:
        return PillarView("breadth", "Waiting for constituent prices")

    wsum = sum(c.weight for c, _, _ in rows)
    w_day = sum(c.weight * d for c, d, _ in rows) / wsum
    w_15 = sum(c.weight * m for c, _, m in rows) / wsum
    adv, dec = sum(d > 0 for _, d, _ in rows), sum(d < 0 for _, d, _ in rows)

    votes = (1 if w_15 > 0.03 else -1 if w_15 < -0.03 else 0) + (1 if w_day > 0.15 else -1 if w_day < -0.15 else 0)
    bias = 1 if votes > 0 else -1 if votes < 0 else 0
    agreeing = sum((m > 0) if bias > 0 else (m < 0) for _, _, m in rows) / len(rows) if bias else 0
    strength = abs(votes) / 2 * (0.5 + 0.5 * agreeing)

    spot, spot_then = ctx.spot, ctx.value_at(ctx.ref.spot_token, "close", 15)
    index_15 = (spot / spot_then - 1) * 100 if spot and spot_then else 0.0
    divergence = abs(index_15) > 0.05 and index_15 * w_15 < 0
    if divergence:
        strength *= 0.5

    movers = sorted(rows, key=lambda r: abs(r[0].weight * r[1]), reverse=True)[:3]
    detail = ", ".join(f"{c.symbol} {d:+.1f}%" for c, d, _ in movers) + f" · A/D {adv}:{dec}"
    if divergence:
        detail += " · index diverging from heavyweights"
    return PillarView("breadth", detail, bias=bias, strength=strength,
                      features={"weighted_day_pct": w_day, "weighted_15m_pct": w_15, "adv": adv, "dec": dec,
                                "divergence": divergence})

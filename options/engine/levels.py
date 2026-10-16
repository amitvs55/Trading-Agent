"""Entry band, stop-loss and targets in option premium (plan §6).

Levels start on the underlying (the idea is wrong below the invalidation, the target is
the next barrier) and are converted to premium with Black-76 at the contract's live IV.
"""

from dataclasses import dataclass

from options.agents.option_chain import ChainRow
from options.quant import black76 as b76

TICK = 0.05
PREMIUM_STOP_CAP = {"intraday": 0.30, "positional": 0.35}   # never risk more than this share of premium
HOLD_YEARS = {"intraday": 0.5 / (365 * 24), "positional": 1 / 365}


def tick(x: float) -> float:
    return round(round(x / TICK) * TICK, 2)


@dataclass(frozen=True)
class TradePlan:
    entry_low: float
    entry_high: float
    stop: float
    t1: float
    t2: float
    rr1: float
    rr2: float
    risk_points: float          # underlying distance to invalidation
    t1_points: float
    t2_points: float


def plan(row: ChainRow, side: int, horizon: str, trigger: float, invalidation: float,
         forward: float, t: float, r: float, room: float | None) -> TradePlan | None:
    iv, ask, mid = row.greeks.get("iv"), row.ask, row.mid
    if not iv or not ask or not mid:
        return None
    risk_pts = abs(trigger - invalidation)
    t_hold = max(t - HOLD_YEARS[horizon], b76.MIN_T)

    def premium(points: float) -> float:
        return b76.premium_at(forward + side * points, row.strike, t_hold, r, iv, row.right)

    entry_high = tick(ask * 1.01)
    entry_low = tick(mid * 0.99)
    stop = tick(max(premium(-risk_pts), entry_high * (1 - PREMIUM_STOP_CAP[horizon])))
    t1_pts = room if room else 1.5 * risk_pts
    t2_pts = max(1.6 * t1_pts, 2.5 * risk_pts)
    t1, t2 = tick(premium(t1_pts)), tick(premium(t2_pts))
    risk = entry_high - stop
    if risk <= 0:
        return None
    return TradePlan(entry_low, entry_high, stop, t1, t2, (t1 - entry_high) / risk, (t2 - entry_high) / risk,
                     risk_pts, t1_pts, t2_pts)

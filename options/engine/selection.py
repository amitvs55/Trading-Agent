"""Expiry and strike selection for buy signals (plan §6)."""

from datetime import date

from options.agents.option_chain import Chain, ChainRow
from options.core.calendar import NseCalendar

MIN_DTE = {"intraday": 1, "positional": 4}     # trading days left at entry
DELTA_BAND = (0.40, 0.55)                      # ₹1 lakh account: near-ATM so 1 lot fits the budget
MAX_SPREAD_PCT = 3.0
MIN_OI = 100_000                               # units (Kite reports OI in shares)


def pick_expiry(expiries: list[date], today: date, horizon: str, calendar: NseCalendar) -> date | None:
    need = MIN_DTE[horizon]
    for exp in sorted(e for e in expiries if e >= today):
        if calendar.trading_days_between(today, exp) >= need:
            return exp
    return None


def pick_strike(chain: Chain, side: int, band: tuple[float, float] = DELTA_BAND,
                min_oi: float = MIN_OI) -> tuple[ChainRow | None, str]:
    """Liquid contract closest to the middle of the delta band, or (None, reason)."""
    right = "CE" if side > 0 else "PE"
    rows = [r for (k, rt), r in chain.rows.items() if rt == right and r.greeks.get("delta") is not None]
    if not rows:
        return None, "no priced contracts"
    lo, hi = band
    in_band = [r for r in rows if lo <= abs(r.greeks["delta"]) <= hi]
    if not in_band:
        return None, f"no strike with delta {lo:.2f}–{hi:.2f}"
    liquid = [r for r in in_band if r.bid and r.ask and r.spread_pct is not None and r.spread_pct <= MAX_SPREAD_PCT
              and (r.oi or 0) >= min_oi]
    if not liquid:
        return None, "strikes in the delta band are illiquid"
    mid = (lo + hi) / 2
    return min(liquid, key=lambda r: abs(abs(r.greeks["delta"]) - mid)), ""

"""Black-76 pricing, implied volatility and Greeks for index options.

Priced on the forward rather than spot (plan §3, agent 6): NIFTY weekly options have no
listed future of the same expiry, so the forward comes from put-call parity at the ATM
strike (`synthetic_forward`). Time is in calendar years to the 15:30 IST expiry.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, time

from options.core.calendar import IST, at_ist

EXPIRY_TIME = time(15, 30)
MIN_T = 1 / (365 * 24 * 60)          # one minute, so expiry-day maths never divides by zero
SQRT_2PI = math.sqrt(2 * math.pi)


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def year_fraction(now: datetime, expiry: date) -> float:
    seconds = (at_ist(expiry, EXPIRY_TIME) - now.astimezone(IST)).total_seconds()
    return max(seconds / (365 * 24 * 3600), MIN_T)


def _d1_d2(f: float, k: float, t: float, sigma: float) -> tuple[float, float]:
    vol_t = sigma * math.sqrt(t)
    d1 = (math.log(f / k) + 0.5 * vol_t * vol_t) / vol_t
    return d1, d1 - vol_t


def price(f: float, k: float, t: float, r: float, sigma: float, right: str) -> float:
    disc = math.exp(-r * t)
    d1, d2 = _d1_d2(f, k, t, sigma)
    if right == "CE":
        return disc * (f * norm_cdf(d1) - k * norm_cdf(d2))
    return disc * (k * norm_cdf(-d2) - f * norm_cdf(-d1))


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float          # per 1 point of the underlying
    vega: float           # per 1 vol point (1%)
    theta_day: float      # per calendar day
    iv: float


def greeks(f: float, k: float, t: float, r: float, sigma: float, right: str) -> Greeks:
    disc = math.exp(-r * t)
    d1, d2 = _d1_d2(f, k, t, sigma)
    p = price(f, k, t, r, sigma, right)
    pdf = norm_pdf(d1)
    delta = disc * norm_cdf(d1) if right == "CE" else -disc * norm_cdf(-d1)
    gamma = disc * pdf / (f * sigma * math.sqrt(t))
    vega = disc * f * pdf * math.sqrt(t) / 100
    theta_year = r * p - disc * f * pdf * sigma / (2 * math.sqrt(t))
    return Greeks(p, delta, gamma, vega, theta_year / 365, sigma)


def implied_vol(option_price: float, f: float, k: float, t: float, r: float, right: str,
                lo: float = 1e-4, hi: float = 5.0, tol: float = 1e-6, max_iter: int = 100) -> float | None:
    """Volatility that reproduces `option_price`, or None if the price is outside no-arbitrage
    bounds (below discounted intrinsic, or above the discounted forward/strike)."""
    disc = math.exp(-r * t)
    intrinsic = disc * max(f - k if right == "CE" else k - f, 0.0)
    upper = disc * (f if right == "CE" else k)
    if not (intrinsic < option_price < upper):
        return None

    sigma = 0.2
    for _ in range(max_iter):
        diff = price(f, k, t, r, sigma, right) - option_price
        if abs(diff) < tol:
            return sigma
        if diff > 0:
            hi = sigma
        else:
            lo = sigma
        vega = disc * f * norm_pdf(_d1_d2(f, k, t, sigma)[0]) * math.sqrt(t)
        step = sigma - diff / vega if vega > 1e-12 else None
        # Newton when it stays inside the bracket, bisection otherwise
        sigma = step if step is not None and lo < step < hi else (lo + hi) / 2
    return sigma if abs(price(f, k, t, r, sigma, right) - option_price) < 1e-3 else None


def synthetic_forward(strike: float, call_price: float, put_price: float, r: float, t: float) -> float:
    """Forward implied by put-call parity: C − P = e^{−rT}(F − K)."""
    return strike + math.exp(r * t) * (call_price - put_price)


def expected_move(f: float, sigma: float, t: float) -> float:
    """One standard deviation move of the underlying over time t."""
    return f * sigma * math.sqrt(t)


def premium_at(f_new: float, k: float, t_new: float, r: float, sigma: float, right: str) -> float:
    """Option value if the forward moves to f_new by time-to-expiry t_new at the same IV."""
    return price(f_new, k, max(t_new, MIN_T), r, sigma, right)

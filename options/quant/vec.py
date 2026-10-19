"""Black-76 on numpy arrays, for pricing thousands of simulated paths at once.

Same model and conventions as options/quant/black76.py (forward, calendar years to the 15:30
expiry); the normal CDF uses the Abramowitz–Stegun 7.1.26 erf (error < 1.5e-7), since numpy has
no erf and scipy isn't a dependency.
"""

import numpy as np

from options.quant.black76 import MIN_T

_P, _A = 0.3275911, (0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429)


def norm_cdf(x: np.ndarray) -> np.ndarray:
    z = np.abs(x) / np.sqrt(2.0)
    t = 1.0 / (1.0 + _P * z)
    poly = t * (_A[0] + t * (_A[1] + t * (_A[2] + t * (_A[3] + t * _A[4]))))
    erf = 1.0 - poly * np.exp(-z * z)
    return 0.5 * (1.0 + np.sign(x) * erf)


def price(f, k: float, t, r: float, sigma: float, right: str) -> np.ndarray:
    """Option value for forward(s) f at time(s)-to-expiry t (years); at t ≤ MIN_T it is the payoff."""
    f = np.asarray(f, dtype=float)
    t = np.maximum(np.asarray(t, dtype=float), MIN_T)
    disc = np.exp(-r * t)
    vol_t = sigma * np.sqrt(t)
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(f / k) + 0.5 * vol_t * vol_t) / vol_t
    d2 = d1 - vol_t
    if right == "CE":
        return disc * (f * norm_cdf(d1) - k * norm_cdf(d2))
    return disc * (k * norm_cdf(-d2) - f * norm_cdf(-d1))


def payoff(f, k: float, right: str) -> np.ndarray:
    f = np.asarray(f, dtype=float)
    return np.maximum(f - k, 0.0) if right == "CE" else np.maximum(k - f, 0.0)

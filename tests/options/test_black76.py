import math
from datetime import date

import pytest

from options.quant import black76 as b
from tests.options.fixtures import ist

F, K, T, R, SIG = 25300.0, 25300.0, 7 / 365, 0.06, 0.12


def test_atm_call_and_put_match_put_call_parity():
    c, p = b.price(F, K, T, R, SIG, "CE"), b.price(F, K, T, R, SIG, "PE")
    assert c - p == pytest.approx(math.exp(-R * T) * (F - K), abs=1e-9)
    # ATM ≈ 0.4 · F · σ√T for Black-76
    assert c == pytest.approx(0.4 * F * SIG * math.sqrt(T), rel=0.01)


@pytest.mark.parametrize("k,right", [(25000, "CE"), (25600, "CE"), (25000, "PE"), (25600, "PE"), (25300, "CE")])
def test_implied_vol_round_trips(k, right):
    p = b.price(F, k, T, R, 0.137, right)
    assert b.implied_vol(p, F, k, T, R, right) == pytest.approx(0.137, abs=1e-5)


def test_implied_vol_rejects_prices_outside_arbitrage_bounds():
    assert b.implied_vol(1.0, F, 25000, T, R, "CE") is None            # below intrinsic (≈300)
    assert b.implied_vol(30000.0, F, 25000, T, R, "CE") is None        # above the forward
    assert b.implied_vol(0.0, F, 26000, T, R, "CE") is None


def test_greeks_signs_and_finite_differences():
    g = b.greeks(F, K, T, R, SIG, "CE")
    h = 1.0
    up, dn = b.price(F + h, K, T, R, SIG, "CE"), b.price(F - h, K, T, R, SIG, "CE")
    assert g.delta == pytest.approx((up - dn) / (2 * h), rel=1e-4)
    assert g.gamma == pytest.approx((up - 2 * g.price + dn) / (h * h), rel=1e-3)
    vol_up = b.price(F, K, T, R, SIG + 0.01, "CE")
    assert g.vega == pytest.approx(vol_up - g.price, rel=0.02)
    tomorrow = b.price(F, K, T - 1 / 365, R, SIG, "CE")
    assert g.theta_day == pytest.approx(tomorrow - g.price, rel=0.05)
    assert 0.45 < g.delta < 0.55 and g.theta_day < 0

    p = b.greeks(F, K, T, R, SIG, "PE")
    assert -0.55 < p.delta < -0.45
    assert g.delta - p.delta == pytest.approx(math.exp(-R * T), abs=1e-9)


def test_synthetic_forward_recovers_the_forward():
    c, p = b.price(25340, 25300, T, R, SIG, "CE"), b.price(25340, 25300, T, R, SIG, "PE")
    assert b.synthetic_forward(25300, c, p, R, T) == pytest.approx(25340, abs=1e-6)


def test_year_fraction_counts_to_the_1530_expiry():
    t = b.year_fraction(ist(2026, 10, 16, 15, 30), date(2026, 10, 19))
    assert t == pytest.approx(3 / 365)
    assert b.year_fraction(ist(2026, 10, 19, 15, 45), date(2026, 10, 19)) == b.MIN_T


def test_expected_move_and_repricing():
    assert b.expected_move(25000, 0.16, 1 / 365) == pytest.approx(25000 * 0.16 / math.sqrt(365))
    assert b.premium_at(25400, K, T, R, SIG, "CE") > b.price(F, K, T, R, SIG, "CE")

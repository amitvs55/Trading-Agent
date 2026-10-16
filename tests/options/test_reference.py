from datetime import date, datetime

import pytest

from options.reference import as_date, build_reference, find_token, index_rows, infer_strike_step
from tests.options.fixtures import (EXPIRED, FUT_TOKEN, MONTHLY, NIFTY_SPOT_TOKEN, NSE_ROWS, TODAY,
                                    VIX_TOKEN, WEEKLY, nfo_rows)


@pytest.fixture
def ref():
    return build_reference("NIFTY", NSE_ROWS, nfo_rows(), TODAY, spot_price=25262.0)


def test_reference_comes_from_the_instrument_dump(ref):
    assert ref.spot_token == NIFTY_SPOT_TOKEN
    assert ref.future_token == FUT_TOKEN                 # nearest NIFTY future, not BANKNIFTY / Nov
    assert ref.future_expiry == MONTHLY
    assert ref.expiries == [WEEKLY, MONTHLY]             # expired 13 Oct contract dropped
    assert ref.lot_size == 65
    assert ref.strike_step == 50


def test_atm_is_the_nearest_listed_strike(ref):
    assert ref.atm_strike(25262) == 25250
    assert ref.atm_strike(25280) == 25300
    assert ref.atm_strike(25262, expiry=MONTHLY) == 25250


def test_window_covers_width_strikes_each_side_for_each_expiry(ref):
    opts = ref.window(25262, width=15, n_expiries=2)
    assert len(opts) == 31 * 2 * 2
    strikes = {o.strike for o in opts}
    assert min(strikes) == 24500 and max(strikes) == 26000
    assert {o.expiry for o in opts} == {WEEKLY, MONTHLY}
    assert {o.right for o in opts} == {"CE", "PE"}


def test_window_is_clipped_at_the_edge_of_the_chain(ref):
    opts = ref.window(23000, width=15, n_expiries=1)
    assert len(opts) == 16 * 2
    assert {o.expiry for o in opts} == {WEEKLY}


def test_strike_step_uses_the_common_gap_near_the_price():
    strikes = [s for exp, s, _ in build_reference("NIFTY", NSE_ROWS, nfo_rows(), TODAY).options if exp == WEEKLY]
    assert infer_strike_step(strikes, around=25250) == 50
    assert infer_strike_step(strikes, around=27000) == 100
    with pytest.raises(ValueError):
        infer_strike_step([25000.0], around=25000)


def test_missing_index_or_contracts_raise():
    with pytest.raises(LookupError):
        build_reference("BANKNIFTY", NSE_ROWS, nfo_rows(), TODAY)         # no NIFTY BANK spot row
    with pytest.raises(LookupError):
        build_reference("NIFTY", NSE_ROWS, [], TODAY)


def test_find_token_and_index_rows():
    assert find_token(NSE_ROWS, "INDIA VIX") == VIX_TOKEN
    with pytest.raises(LookupError):
        find_token(NSE_ROWS, "RELIANCE")                                  # not an index
    rows = index_rows(nfo_rows(), "NIFTY", TODAY)
    assert all(r["name"] == "NIFTY" for r in rows)
    assert all(as_date(r["expiry"]) >= TODAY for r in rows)
    assert not any(as_date(r["expiry"]) == EXPIRED for r in rows)


def test_as_date_accepts_kite_formats():
    assert as_date(date(2026, 10, 27)) == date(2026, 10, 27)
    assert as_date(datetime(2026, 10, 27, 15, 30)) == date(2026, 10, 27)
    assert as_date("2026-10-27") == date(2026, 10, 27)
    assert as_date("") is None and as_date(None) is None

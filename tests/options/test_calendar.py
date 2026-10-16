from datetime import date, datetime, timezone

from options.core.calendar import NseCalendar
from tests.options.fixtures import ist

cal = NseCalendar()


def test_holidays_and_weekends_are_not_trading_days():
    assert not cal.is_trading_day(date(2026, 10, 20))   # Dussehra (Tuesday)
    assert not cal.is_trading_day(date(2026, 10, 17))   # Saturday
    assert cal.is_trading_day(date(2026, 10, 19))       # Monday before Dussehra


def test_next_and_previous_trading_day_skip_holidays():
    assert cal.next_trading_day(date(2026, 10, 16)) == date(2026, 10, 19)
    assert cal.next_trading_day(date(2026, 10, 19)) == date(2026, 10, 21)
    assert cal.previous_trading_day(date(2026, 10, 21)) == date(2026, 10, 19)


def test_trading_days_between_counts_days_to_expiry():
    assert cal.trading_days_between(date(2026, 10, 16), date(2026, 10, 19)) == 1
    # 19, 21, 22, 23, 26, 27 Oct (20th is Dussehra)
    assert cal.trading_days_between(date(2026, 10, 16), date(2026, 10, 27)) == 6
    assert cal.trading_days_between(date(2026, 10, 27), date(2026, 10, 27)) == 0
    assert cal.trading_days_between(date(2026, 10, 27), date(2026, 10, 16)) == 0


def test_session_phases():
    assert cal.session_phase(ist(2026, 10, 16, 9, 0)) == "pre_market"
    assert cal.session_phase(ist(2026, 10, 16, 9, 20)) == "opening"
    assert cal.session_phase(ist(2026, 10, 16, 10, 0)) == "main"
    assert cal.session_phase(ist(2026, 10, 16, 14, 45)) == "late"
    assert cal.session_phase(ist(2026, 10, 16, 15, 10)) == "closing"
    assert cal.session_phase(ist(2026, 10, 16, 15, 30)) == "closed"
    assert cal.session_phase(ist(2026, 10, 20, 10, 0)) == "closed"      # holiday
    assert cal.is_market_open(ist(2026, 10, 16, 9, 15))
    assert not cal.is_market_open(ist(2026, 10, 16, 9, 14, 59))


def test_session_phase_converts_other_timezones_to_ist():
    utc = datetime(2026, 10, 16, 4, 30, tzinfo=timezone.utc)             # 10:00 IST
    assert cal.session_phase(utc) == "main"


def test_year_without_holiday_list_treats_weekdays_as_trading():
    assert not cal.has_year(2027)
    assert cal.is_trading_day(date(2027, 1, 4))                         # Monday
    assert not cal.is_trading_day(date(2027, 1, 2))                     # Saturday

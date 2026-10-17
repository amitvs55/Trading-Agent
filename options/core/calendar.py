"""NSE trading calendar: IST clock, trading days and intraday session phases."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from options.core.holidays import NSE_HOLIDAYS
from utils.logger import setup_logger

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Session phases used by the Regime & Session gate (plan §4, agent 10)
_PHASES = (
    (time(9, 15), "pre_market"),
    (time(9, 30), "opening"),
    (time(14, 30), "main"),
    (time(15, 0), "late"),
    (MARKET_CLOSE, "closing"),
)
OPEN_PHASES = frozenset({"opening", "main", "late", "closing"})

logger = setup_logger("options.calendar")


def now_ist() -> datetime:
    return datetime.now(IST)


def at_ist(d: date, t: time) -> datetime:
    return datetime.combine(d, t, IST)


class NseCalendar:
    def __init__(self, holidays: dict[int, frozenset[date]] | None = None, complete_years: set[int] | None = None):
        self._holidays = NSE_HOLIDAYS if holidays is None else holidays
        # Years whose full list is known; a year with only a few holidays entered still warns
        self._complete = set(self._holidays) if complete_years is None else set(complete_years)
        self._warned: set[int] = set()

    def has_year(self, year: int) -> bool:
        return year in self._complete

    def is_trading_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        if d.year not in self._holidays:
            if d.year not in self._warned:
                logger.warning("No NSE holiday list for %d; treating all weekdays as trading days", d.year)
                self._warned.add(d.year)
            return True
        return d not in self._holidays[d.year]

    def next_trading_day(self, d: date) -> date:
        d += timedelta(days=1)
        while not self.is_trading_day(d):
            d += timedelta(days=1)
        return d

    def previous_trading_day(self, d: date) -> date:
        d -= timedelta(days=1)
        while not self.is_trading_day(d):
            d -= timedelta(days=1)
        return d

    def trading_days_between(self, start: date, end: date) -> int:
        """Trading days after `start`, up to and including `end` (0 when end <= start)."""
        count, d = 0, start
        while d < end:
            d += timedelta(days=1)
            if self.is_trading_day(d):
                count += 1
        return count

    def session_phase(self, dt: datetime) -> str:
        dt = dt.astimezone(IST)
        if not self.is_trading_day(dt.date()):
            return "closed"
        t = dt.time()
        for end, phase in _PHASES:
            if t < end:
                return phase
        return "closed"

    def is_market_open(self, dt: datetime) -> bool:
        return self.session_phase(dt) in OPEN_PHASES

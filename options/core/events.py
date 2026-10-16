"""High-impact scheduled events (IST). Add new ones as they are announced.

Sources (checked 16 Oct 2026): RBI MPC calendar FY2026-27 (press release, 23 Mar 2026);
Federal Reserve FOMC 2026 calendar. US decisions land at 14:00 New York time, which is
after the Indian close, so they matter for positional holds rather than intraday entries.
"""

from dataclasses import dataclass
from datetime import datetime

from options.core.calendar import IST


@dataclass(frozen=True)
class Event:
    name: str
    at: datetime              # IST
    impact: str = "high"      # "high" | "medium"

    @property
    def during_market(self) -> bool:
        t = self.at.astimezone(IST).time()
        return (9, 15) <= (t.hour, t.minute) < (15, 30)


def _ist(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IST)


EVENTS: list[Event] = [
    Event("RBI MPC decision", _ist(2026, 12, 4, 10, 0)),
    Event("RBI MPC decision", _ist(2027, 2, 5, 10, 0)),
    Event("US FOMC decision", _ist(2026, 10, 28, 23, 30)),
    Event("US FOMC decision", _ist(2026, 12, 10, 0, 30)),
    Event("Union Budget (expected 1 Feb)", _ist(2027, 2, 1, 11, 0)),
]

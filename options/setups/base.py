"""Setup interface and the candidate a setup emits when its trigger fires."""

from dataclasses import dataclass
from typing import Protocol

from options.core.schemas import Status


@dataclass(frozen=True)
class Candidate:
    setup: str
    side: int                    # +1 → BUY CE, −1 → BUY PE
    horizon: str                 # "intraday" | "positional"
    trigger: float               # underlying price when the trigger fired
    invalidation: float          # underlying level; a close beyond it kills the idea
    underlying_token: int
    tf: str                      # "5min" | "day": the close that is checked against invalidation
    trigger_quality: Status
    note: str
    room: float | None = None    # optional override of the levels pillar (positional setups)
    room_unit: float | None = None
    room_label: str = ""


class Setup(Protocol):
    id: str
    label: str
    horizon: str
    regimes: frozenset[str]

    def detect(self, snap) -> Candidate | None: ...


def candle_quality(bar: dict, side: int) -> Status:
    """Strong candle in the trade direction: big body, close near the extreme."""
    rng = bar["high"] - bar["low"]
    if rng <= 0:
        return "warn"
    body = (bar["close"] - bar["open"]) * side
    close_loc = (bar["close"] - bar["low"]) / rng if side > 0 else (bar["high"] - bar["close"]) / rng
    if body / rng >= 0.5 and close_loc >= 0.7:
        return "pass"
    if body > 0 and body / rng >= 0.3:
        return "warn"
    return "fail"


def bounded_invalidation(trigger: float, raw: float, side: int, atr: float,
                         min_atr: float = 0.5, max_atr: float = 1.5) -> float:
    """Keep the stop distance between min_atr and max_atr ATRs from the trigger."""
    dist = (trigger - raw) * side
    dist = min(max(dist, min_atr * atr), max_atr * atr)
    return trigger - side * dist

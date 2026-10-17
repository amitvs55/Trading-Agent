"""Everything an analysis agent may read at one evaluation point."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from options.core.calendar import NseCalendar
from options.core.events import Event
from options.engine.state import MarketState
from options.reference import IndexReference


@dataclass
class Constituent:
    symbol: str
    weight: float
    token: int
    prev_close: float | None = None


@dataclass
class AgentContext:
    index: str
    ref: IndexReference
    state: MarketState
    now: datetime
    calendar: NseCalendar
    vix_token: int | None = None
    constituents: list[Constituent] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    vix_history: list[float] = field(default_factory=list)     # ~1 year of daily closes
    macro: dict | None = None                                  # latest MacroFetcher snapshot
    news: dict | None = None                                   # latest NewsFetcher snapshot
    r: float = 0.06                                            # risk-free rate for Black-76

    @property
    def spot(self) -> float | None:
        return self.state.last_price(self.ref.spot_token)

    @property
    def fut(self) -> float | None:
        return self.state.last_price(self.ref.future_token)

    def value_at(self, token: int, column: str, minutes_ago: int) -> float | None:
        """Value of a 1m-bar column as of `minutes_ago` before now (last bar at or before then)."""
        df = self.state.frame(token, "1min")
        if df.empty:
            return None
        cutoff = pd.Timestamp(self.now - timedelta(minutes=minutes_ago))
        past = df.loc[:cutoff, column].dropna()
        return float(past.iloc[-1]) if not past.empty else None

    def day_open_value(self, token: int, column: str) -> float | None:
        df = self.state.today(token, "1min")
        col = df[column].dropna() if not df.empty else df
        return float(col.iloc[0]) if len(col) else None

"""Named, rule-based setups (plan §5). Signals only ever come from one of these."""

from options.setups.base import Candidate, Setup
from options.setups.intraday import OIWallBreak, OpeningRangeBreakout, TrendPullback
from options.setups.positional import DailyTrendContinuation

INTRADAY_SETUPS: list[Setup] = [TrendPullback(), OpeningRangeBreakout(), OIWallBreak()]
POSITIONAL_SETUPS: list[Setup] = [DailyTrendContinuation()]
ALL_SETUPS = INTRADAY_SETUPS + POSITIONAL_SETUPS
SETUP_LABELS = {s.id: s.label for s in ALL_SETUPS}

__all__ = ["ALL_SETUPS", "INTRADAY_SETUPS", "POSITIONAL_SETUPS", "SETUP_LABELS", "Candidate", "Setup"]

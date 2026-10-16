"""Position sizing and the daily risk budget (plan §0: ₹1 lakh, 3% per trade, 10% daily stop)."""

import math
from dataclasses import dataclass

GAP_BUFFER = 1.5        # positional trades are sized as if the stop were 1.5× wider (overnight gaps)


@dataclass(frozen=True)
class RiskConfig:
    capital: float = 100_000
    risk_per_trade_pct: float = 3.0
    daily_loss_stop_pct: float = 10.0
    max_lots: int = 1
    max_open_intraday: int = 1
    max_open_positional: int = 1

    @property
    def per_trade_budget(self) -> float:
        return self.capital * self.risk_per_trade_pct / 100

    @property
    def daily_stop(self) -> float:
        return self.capital * self.daily_loss_stop_pct / 100


@dataclass(frozen=True)
class Sizing:
    lots: int
    risk_rupees: float           # at the suggested lots (one lot when over budget)
    over_budget: bool


def size(cfg: RiskConfig, entry_high: float, stop: float, lot_size: int, positional: bool = False) -> Sizing:
    per_lot = max(entry_high - stop, 0) * lot_size * (GAP_BUFFER if positional else 1.0)
    if per_lot <= 0:
        return Sizing(0, 0.0, True)
    lots = min(math.floor(cfg.per_trade_budget / per_lot), cfg.max_lots)
    if lots < 1:
        return Sizing(1, per_lot, True)
    return Sizing(lots, per_lot * lots, False)


def budget_gate(cfg: RiskConfig, realised_today: float, open_risk: float, new_risk: float,
                open_intraday: int, open_positional: int, positional: bool) -> str | None:
    """Reason a new signal is blocked, or None. realised_today is net ₹ P&L (losses negative)."""
    loss = -min(realised_today, 0)
    if loss >= cfg.daily_stop:
        return f"daily loss stop hit (₹{loss:,.0f} of ₹{cfg.daily_stop:,.0f})"
    if loss + open_risk + new_risk > cfg.daily_stop:
        return "this trade could breach the daily loss stop"
    if positional and open_positional >= cfg.max_open_positional:
        return "a positional signal is already open"
    if not positional and open_intraday >= cfg.max_open_intraday:
        return "an intraday signal is already open"
    return None

"""Paper trading account, derived from the signal record.

The account follows every signal (or grade A only) from the moment it was started. It enters
when a signal's entry filled, at that same live ask, and leaves at the signal's own exits, at
the live bid. Each position is sized from the paper balance at entry with the engine's own
rules (risk.size: 3% of balance, the same lot cap). An entry is skipped when the account has
hit its daily loss stop that day, or doesn't have the cash for the premium. Charges are the
same as the track record's.

Nothing here is stored: the account is rebuilt from the signals on every request, so it can
never drift from them. A reset just moves the start time (and can change the balance).
"""

import math
from dataclasses import dataclass
from datetime import date, datetime

from options.core.calendar import IST
from options.core.schemas import OPEN_STATES, Signal, SignalState
from options.engine.costs import charges
from options.engine.risk import RiskConfig, size

PAPER_KEY = "paper_account"
DEFAULT_BALANCE = 100_000.0
FOLLOW = {"all": "Every signal", "A": "Grade A only"}


@dataclass(frozen=True)
class PaperSettings:
    starting_balance: float
    started_at: datetime
    follow: str = "all"

    @classmethod
    def from_meta(cls, raw: dict) -> "PaperSettings":
        return cls(float(raw["starting_balance"]), datetime.fromisoformat(raw["started_at"]), raw.get("follow", "all"))

    def to_meta(self) -> dict:
        return {"starting_balance": self.starting_balance, "started_at": self.started_at.isoformat(),
                "follow": self.follow}


def _day(ts: datetime) -> date:
    return ts.astimezone(IST).date()


def _follows(sig: Signal, st: PaperSettings) -> bool:
    return st.follow == "all" or sig.grade.value == st.follow


def _close_value(lots: int, lot_size: int, fill: float, sig: Signal) -> tuple[float, float, float, int]:
    """(sell value, buy value, charges, orders) for closing a paper position on the signal's exits."""
    units = lots * lot_size
    half = (lots // 2) * lot_size if (lots >= 2 and sig.booked_t1 is not None) else 0
    sell = half * (sig.booked_t1 or 0) + (units - half) * (sig.exit_price or 0)
    buy = units * fill
    orders = 3 if half else 2
    return sell, buy, charges(buy, sell, orders).total, orders


def build(signals: list[Signal], st: PaperSettings, risk_pct: float, daily_stop_pct: float,
          bids: dict[str, float | None], now: datetime, max_lots: int = RiskConfig.max_lots) -> dict:
    """The whole account as of `now`. `bids` maps open signal ids to their latest option bid."""
    followed = [s for s in signals if s.filled_at and s.fill_price and s.filled_at >= st.started_at and _follows(s, st)]
    # Timeline: entries at fill time, exits at close time; an exit at the same instant settles first
    timeline = sorted([(s.filled_at, 1, s) for s in followed] +
                      [(s.closed_at, 0, s) for s in followed if s.state is SignalState.CLOSED and s.closed_at],
                      key=lambda e: (e[0], e[1]))

    cash, realised = st.starting_balance, 0.0
    positions: dict[str, dict] = {}
    trades, skipped, curve = [], [], [{"t": st.started_at.isoformat(), "balance": st.starting_balance}]
    day_start: dict[date, float] = {}
    realised_by_day: dict[date, float] = {}

    for ts, kind, sig in timeline:
        day = _day(ts)
        balance = st.starting_balance + realised
        day_start.setdefault(day, balance)
        if kind == 1:                                          # entry
            cfg = RiskConfig(capital=balance, risk_per_trade_pct=risk_pct, daily_loss_stop_pct=daily_stop_pct,
                             max_lots=max_lots)
            stop = sig.initial_stop if sig.initial_stop is not None else sig.stop_loss
            lots = size(cfg, sig.fill_price, stop, sig.contract.lot_size, sig.horizon == "positional").lots
            loss_today = -min(realised_by_day.get(day, 0.0), 0.0)
            daily_limit = day_start[day] * daily_stop_pct / 100
            unit_cost = sig.fill_price * sig.contract.lot_size
            affordable = math.floor(cash / unit_cost) if unit_cost > 0 else 0
            reason = None
            if loss_today >= daily_limit:
                reason = f"daily loss stop hit (₹{loss_today:,.0f} of ₹{daily_limit:,.0f})"
            elif lots < 1:
                reason = "no position size fits the risk rule"
            elif affordable < 1:
                reason = f"not enough paper cash (₹{cash:,.0f} free, 1 lot costs ₹{unit_cost:,.0f})"
            if reason:
                skipped.append({"signal_id": sig.signal_id, "at": ts.isoformat(), "reason": reason})
                continue
            lots = min(lots, affordable)
            cost = lots * unit_cost
            cash -= cost
            positions[sig.signal_id] = {"sig": sig, "lots": lots, "cost": cost, "risk": (sig.fill_price - stop) *
                                        lots * sig.contract.lot_size}
        elif sig.signal_id in positions:                       # exit of a position we hold
            pos = positions.pop(sig.signal_id)
            sell, buy, fees, _ = _close_value(pos["lots"], sig.contract.lot_size, sig.fill_price, sig)
            net = round(sell - buy - fees, 2)                  # rounded per trade, like the track record
            cash += sell - fees
            realised += net
            realised_by_day[day] = realised_by_day.get(day, 0.0) + net
            curve.append({"t": ts.isoformat(), "balance": round(st.starting_balance + realised, 2),
                          "id": sig.signal_id})
            trades.append(_trade(sig, pos, net, fees))

    today = _day(now)
    open_rows, unrealised = [], 0.0
    for sid, pos in positions.items():
        sig = pos["sig"]
        units = pos["lots"] * sig.contract.lot_size
        bid = bids.get(sid)
        mtm = (bid - sig.fill_price) * units if bid else 0.0
        unrealised += mtm
        open_rows.append({**_trade(sig, pos, None, None), "bid": bid, "unrealised": round(mtm, 2),
                          "value": round((bid or sig.fill_price) * units, 2)})

    balance = st.starting_balance + realised
    equity = balance + unrealised
    peak, max_dd, max_dd_pct = st.starting_balance, 0.0, 0.0
    for point in curve:
        peak = max(peak, point["balance"])
        if peak - point["balance"] > max_dd:
            max_dd, max_dd_pct = peak - point["balance"], (peak - point["balance"]) / peak * 100
    wins = [t for t in trades if t["pnl"] > 0]
    loss_today = -min(realised_by_day.get(today, 0.0), 0.0)
    today_limit = day_start.get(today, balance) * daily_stop_pct / 100
    return {
        "settings": {**st.to_meta(), "follow_label": FOLLOW.get(st.follow, st.follow)},
        "rules": {"risk_per_trade_pct": risk_pct, "daily_loss_stop_pct": daily_stop_pct, "max_lots": max_lots},
        "balance": round(balance, 2),
        "equity": round(equity, 2),
        "cash": round(cash, 2),
        "invested": round(sum(p["cost"] for p in positions.values()), 2),
        "unrealised": round(unrealised, 2),
        "realised": round(realised, 2),
        "return_pct": round((equity - st.starting_balance) / st.starting_balance * 100, 2),
        "today": {"realised": round(realised_by_day.get(today, 0.0), 2), "unrealised": round(unrealised, 2),
                  "pnl": round(realised_by_day.get(today, 0.0) + unrealised, 2),
                  "daily_stop": round(today_limit, 2), "daily_stop_hit": loss_today >= today_limit},
        "stats": {"trades": len(trades), "wins": len(wins), "win_rate": len(wins) / len(trades) if trades else None,
                  "max_drawdown": round(max_dd, 2), "max_drawdown_pct": round(max_dd_pct, 2),
                  "best": max((t["pnl"] for t in trades), default=None),
                  "worst": min((t["pnl"] for t in trades), default=None)},
        "open": sorted(open_rows, key=lambda r: r["entry_at"], reverse=True),
        "trades": sorted(trades, key=lambda r: r["exit_at"] or "", reverse=True),
        "skipped": sorted(skipped, key=lambda r: r["at"], reverse=True),
        "curve": curve,
        "as_of": now.isoformat(timespec="seconds"),
    }


def _trade(sig: Signal, pos: dict, net: float | None, fees: float | None) -> dict:
    units = pos["lots"] * sig.contract.lot_size
    return {
        "signal_id": sig.signal_id, "symbol": sig.contract.tradingsymbol, "action": sig.action.value,
        "grade": sig.grade.value, "score": sig.score, "mode": sig.mode, "setup": sig.setup,
        "lots": pos["lots"], "units": units, "entry": sig.fill_price, "entry_at": sig.filled_at.isoformat(),
        "stop": sig.stop_loss, "t1": sig.t1, "t2": sig.t2, "state": sig.state.value,
        "exit": sig.exit_price if sig.state not in OPEN_STATES else None,
        "exit_at": sig.closed_at.isoformat() if sig.closed_at and sig.state not in OPEN_STATES else None,
        "exit_reason": sig.exit_reason if sig.state not in OPEN_STATES else None,
        "cost": round(pos["cost"], 2), "risk": round(pos["risk"], 2),
        "pnl": round(net, 2) if net is not None else None, "charges": round(fees, 2) if fees is not None else None,
        "r": round(net / pos["risk"], 2) if net is not None and pos["risk"] > 0 else None,
    }

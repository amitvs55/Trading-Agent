"""Signal lifecycle and honest outcome tracking (plan §7).

Fills: entry at the live ask once it is inside the entry band, every exit at the live bid.
With one lot there is nothing to book "half" of, so at T1 a 1-lot signal locks in half the
open gain instead and runs on to T2 with a trailing stop.
"""

from dataclasses import dataclass
from datetime import datetime, time

from options.core.schemas import OPEN_STATES, Signal, SignalState
from options.engine.costs import charges

TRAIL_FROM_PEAK = 0.80          # after T1 the stop trails 20% below the best bid seen
SQUARE_OFF = time(15, 15)


@dataclass(frozen=True)
class Update:
    kind: str
    price: float | None
    message: str


def _units(sig: Signal) -> int:
    return sig.lots * sig.contract.lot_size


def close(sig: Signal, price: float, now: datetime, reason: str) -> Update:
    units = _units(sig)
    half = (sig.lots // 2) * sig.contract.lot_size if sig.booked_t1 is not None else 0
    rest = units - half
    sell_value = half * (sig.booked_t1 or 0) + rest * price
    buy_value = units * sig.fill_price
    orders = 3 if half else 2
    net = sell_value - buy_value - charges(buy_value, sell_value, orders).total
    risk = (sig.fill_price - sig.initial_stop) * units
    sig.state, sig.exit_price, sig.exit_reason, sig.closed_at = SignalState.CLOSED, price, reason, now
    sig.pnl_rupees = round(net, 2)
    sig.r_multiple = round(net / risk, 2) if risk > 0 else None
    r_text = f", {sig.r_multiple:+.2f}R" if sig.r_multiple is not None else ""
    return Update(reason, price, f"closed @ {price:.2f} ({reason.replace('_', ' ').lower()}): "
                                 f"₹{net:+,.0f} after charges{r_text}")


def on_quote(sig: Signal, bid: float | None, ask: float | None, now: datetime) -> Update | None:
    """Advance a signal on a live option quote."""
    if sig.state is SignalState.TRIGGERED:
        if now > sig.valid_until:
            sig.state, sig.closed_at, sig.exit_reason = SignalState.EXPIRED, now, "EXPIRED"
            return Update("EXPIRED", None, "entry price not reached in time; no trade")
        if ask and ask <= sig.stop_loss:
            # The premium fell through the stop before it was bought: "inside the entry band" by price,
            # but already a loser. No trade (the backtest found this filling and closing in one tick).
            sig.state, sig.closed_at, sig.exit_reason = SignalState.CANCELLED, now, "CANCELLED"
            return Update("CANCELLED", None, f"price fell through the stop ({sig.stop_loss:.2f}) before entry; no trade")
        if ask and ask <= sig.entry_high:
            sig.state, sig.fill_price, sig.filled_at, sig.initial_stop = SignalState.ACTIVE, ask, now, sig.stop_loss
            return Update("ENTRY_FILLED", ask, f"entry filled @ {ask:.2f}")
        return None

    if sig.state not in (SignalState.ACTIVE, SignalState.T1_HIT) or not bid:
        return None
    if bid <= sig.stop_loss:
        if sig.state is SignalState.ACTIVE:
            return close(sig, bid, now, "SL_HIT")
        return close(sig, bid, now, "TRAIL_STOP")
    if sig.state is SignalState.ACTIVE and bid >= sig.t1:
        sig.state, sig.peak_bid = SignalState.T1_HIT, bid
        if sig.lots >= 2:
            sig.booked_t1 = bid
            sig.stop_loss = sig.fill_price
            return Update("T1_HIT", bid, f"T1 hit @ {bid:.2f}: booked half, stop → cost {sig.fill_price:.2f}")
        sig.stop_loss = round(sig.fill_price + 0.5 * (bid - sig.fill_price), 2)
        return Update("T1_HIT", bid, f"T1 hit @ {bid:.2f}: stop raised to {sig.stop_loss:.2f} (half the gain locked), "
                                     f"riding to T2 {sig.t2:.2f}")
    if sig.state is SignalState.T1_HIT:
        if bid >= sig.t2:
            return close(sig, bid, now, "T2_HIT")
        if bid > (sig.peak_bid or 0):
            sig.peak_bid = bid
            sig.stop_loss = max(sig.stop_loss, round(bid * TRAIL_FROM_PEAK, 2))
    return None


def on_close_check(sig: Signal, underlying_close: float, bid: float | None, now: datetime) -> Update | None:
    """Run on each closed bar of the signal's timeframe, and at the session's exit times."""
    if sig.state not in OPEN_STATES:
        return None
    beyond = (underlying_close - sig.invalidation) * sig.side < 0
    if sig.state is SignalState.TRIGGERED:
        if beyond:
            sig.state, sig.closed_at, sig.exit_reason = SignalState.CANCELLED, now, "CANCELLED"
            return Update("CANCELLED", None, "invalidated before entry; no trade")
        return None
    if not bid:
        return None
    if beyond:
        return close(sig, bid, now, "INVALIDATED")
    if sig.horizon == "intraday":
        if sig.time_stop and now.time() >= sig.time_stop:
            return close(sig, bid, now, "TIME_STOP")
        if now.time() >= SQUARE_OFF:
            return close(sig, bid, now, "SQUARE_OFF")
    elif sig.exit_by and now.date() >= sig.exit_by and now.time() >= SQUARE_OFF:
        return close(sig, bid, now, "TIME_STOP")
    return None


def exit_now(sig: Signal, bid: float | None, now: datetime, reason: str) -> Update | None:
    """Exit on an engine decision (opposite grade-A signal, event approaching, kill)."""
    if sig.state is SignalState.TRIGGERED:
        sig.state, sig.closed_at, sig.exit_reason = SignalState.CANCELLED, now, reason
        return Update("CANCELLED", None, f"cancelled before entry: {reason.replace('_', ' ').lower()}")
    if sig.state in (SignalState.ACTIVE, SignalState.T1_HIT) and bid:
        return close(sig, bid, now, reason)
    return None

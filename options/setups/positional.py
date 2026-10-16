"""Positional setup P1: daily trend continuation, evaluated near the close (15:05–15:20)."""

from datetime import time

from options.quant import indicators as ind
from options.setups.base import Candidate


class DailyTrendContinuation:
    id = "P1_DAILY_TREND"
    label = "P1 Daily trend continuation"
    horizon = "positional"
    regimes = frozenset({"trend", "range", "neutral", "chop"})
    window = (time(15, 5), time(15, 20))

    def detect(self, snap) -> Candidate | None:
        ctx = snap.ctx
        if not (self.window[0] <= ctx.now.time() <= self.window[1]):
            return None
        daily = ctx.state.daily(ctx.ref.spot_token)
        if len(daily) < 55:
            return None
        close = daily["close"].astype(float)
        e20, e50 = ind.ema(close, 20).iloc[-1], ind.ema(close, 50).iloc[-1]
        atr_d = float(ind.atr(daily.astype(float), 14).iloc[-1])
        today, prev = daily.iloc[-1], daily.iloc[-2]
        c, hi, lo = float(today["close"]), float(today["high"]), float(today["low"])
        if c > float(prev["high"]) and e20 > e50 and c > e20:
            side, raw = 1, lo
        elif c < float(prev["low"]) and e20 < e50 and c < e20:
            side, raw = -1, hi
        else:
            return None

        dist = (c - raw) * side
        if dist < 0.3 * atr_d:
            raw = c - side * 0.5 * atr_d
        # Fresh positions behind the day's move (futures OI up on the day) make it a cleaner signal
        oi_open = ctx.day_open_value(ctx.ref.future_token, "oi")
        oi_now = ctx.value_at(ctx.ref.future_token, "oi", 0)
        oi_added = bool(oi_open and oi_now and oi_now > oi_open)
        quality = "pass" if oi_added and snap.flow.bias in (side, 0) else "warn"

        recent = daily.iloc[-21:-1]
        level = float(recent["high"].max()) if side > 0 else float(recent["low"].min())
        room = (level - c) * side
        return Candidate(self.id, side, "positional", c, raw, ctx.ref.spot_token, "day", quality,
                         f"daily close {'above' if side > 0 else 'below'} previous day "
                         f"{'high' if side > 0 else 'low'}, daily EMA20 {'>' if side > 0 else '<'} EMA50",
                         room=room if room > 0 else None, room_unit=atr_d,
                         room_label=f"20-day {'high' if side > 0 else 'low'} {level:,.0f}")

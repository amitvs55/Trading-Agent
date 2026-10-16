"""Intraday setups on 5-minute futures bars: S1 trend pullback, S2 ORB, S3 OI-wall break."""

from datetime import time

from options.setups.base import Candidate, bounded_invalidation, candle_quality


class TrendPullback:
    """S1: in a higher-timeframe trend, price dips to VWAP/EMA20 and closes back in trend."""
    id = "S1_TREND_PULLBACK"
    label = "S1 Trend pullback"
    horizon = "intraday"
    regimes = frozenset({"trend"})

    def detect(self, snap) -> Candidate | None:
        t = snap.tech
        if not t.ready or t.vwap is None or t.ema20_5m is None or not t.atr_5m:
            return None
        bar, atr = t.bar, t.atr_5m
        hi_anchor, lo_anchor = max(t.vwap, t.ema20_5m), min(t.vwap, t.ema20_5m)
        if t.htf_trend == "up" and bar["low"] <= hi_anchor * 1.0005 and bar["close"] > max(hi_anchor, bar["open"]):
            side, raw = 1, min(bar["low"], lo_anchor) - 0.25 * atr
        elif t.htf_trend == "down" and bar["high"] >= lo_anchor * 0.9995 and bar["close"] < min(lo_anchor, bar["open"]):
            side, raw = -1, max(bar["high"], hi_anchor) + 0.25 * atr
        else:
            return None
        anchor = "VWAP" if abs(bar["close"] - t.vwap) <= abs(bar["close"] - t.ema20_5m) else "EMA20"
        return Candidate(self.id, side, "intraday", bar["close"], bounded_invalidation(bar["close"], raw, side, atr),
                         snap.ctx.ref.future_token, "5min", candle_quality(bar, side),
                         f"pullback to fut {anchor}, {'bullish' if side > 0 else 'bearish'} 5m close")


class OpeningRangeBreakout:
    """S2: after 09:30, first 5m close beyond the 09:15–09:30 range on a volume surge."""
    id = "S2_ORB"
    label = "S2 Opening range breakout"
    horizon = "intraday"
    regimes = frozenset({"trend", "range", "neutral"})
    window = (time(9, 30), time(11, 30))

    def detect(self, snap) -> Candidate | None:
        t = snap.tech
        now = snap.ctx.now.time()
        if not t.ready or t.or_high is None or not t.atr_5m or not (self.window[0] <= now <= self.window[1]):
            return None
        bar, prev = t.bar, t.prev_bar
        if bar["close"] > t.or_high >= prev["close"]:
            side = 1
        elif bar["close"] < t.or_low <= prev["close"]:
            side = -1
        else:
            return None
        mid = (t.or_high + t.or_low) / 2
        vol_ok = (t.volume_ratio_5m or 0) >= 1.5
        quality = candle_quality(bar, side)
        if not vol_ok and quality == "pass":
            quality = "warn"
        return Candidate(self.id, side, "intraday", bar["close"],
                         bounded_invalidation(bar["close"], mid, side, t.atr_5m),
                         snap.ctx.ref.future_token, "5min", quality,
                         f"5m close {'above' if side > 0 else 'below'} opening range "
                         f"{t.or_high if side > 0 else t.or_low:,.0f}"
                         + (f", volume {t.volume_ratio_5m:.1f}× avg" if t.volume_ratio_5m else ""))


class OIWallBreak:
    """S3: spot closes through the strike with the biggest OI while writers there cover."""
    id = "S3_OI_WALL_BREAK"
    label = "S3 OI wall break"
    horizon = "intraday"
    regimes = frozenset({"trend", "neutral"})

    def detect(self, snap) -> Candidate | None:
        t, chain, feats = snap.tech, snap.chain, snap.oi.features
        spot5 = snap.ctx.state.frame(snap.ctx.ref.spot_token, "5min")
        if not t.ready or chain is None or not t.atr_5m or len(spot5) < 2:
            return None
        close, prev = float(spot5["close"].iloc[-1]), float(spot5["close"].iloc[-2])
        for side, key, right in ((1, "call_wall", "CE"), (-1, "put_wall", "PE")):
            wall = feats.get(f"{key}_30m") or feats.get(key)
            if not wall or not ((close - wall) * side > 0 >= (prev - wall) * side):
                continue
            row = chain.get(wall, right)
            if row is None or row.oi is None or row.oi_15m is None or row.oi >= row.oi_15m:
                continue                                   # writers still defending (OI not falling)
            covering = (row.oi_15m - row.oi) / row.oi_15m * 100
            quality = "pass" if snap.flow.bias == side else "warn"
            wall_fut = wall + snap.basis
            raw = wall_fut - side * 0.5 * t.atr_5m
            return Candidate(self.id, side, "intraday", t.bar["close"],
                             bounded_invalidation(t.bar["close"], raw, side, t.atr_5m),
                             snap.ctx.ref.future_token, "5min", quality,
                             f"spot through {wall:g} {right} wall, OI there −{covering:.1f}% in 15m")
        return None

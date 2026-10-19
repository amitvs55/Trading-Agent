"""Technical agent: trend (pillar 1), key levels (pillar 3) and momentum (pillar 4).

Works on the near-month future: index spot has no volume, so VWAP and every trigger
level are in futures points (plan §5).
"""

from dataclasses import dataclass, field

import pandas as pd

from options.agents.context import AgentContext
from options.core.schemas import PillarView
from options.quant import indicators as ind

# Bars needed before an indicator is trusted. The recursive ones (EMA50, Wilder RSI/ATR/ADX)
# take ~100-125 bars to forget their seed and match a reference library to 1e-4 (see
# docs/review/scripts/indicator_reference_check.py); the session loads 20 sessions of history,
# so these are met from the first bar of the day whenever history loaded.
TREND_MIN_BARS = 100          # 15m and 60m: EMA20/50 and Supertrend
MOMENTUM_MIN_BARS = 100       # 5m: RSI and MACD
ADX_MIN_BARS = 100            # 15m ADX (double smoothing)


@dataclass
class TechView:
    ready: bool
    htf_trend: str                     # "up" | "down" | "flat"
    trend: PillarView
    momentum: PillarView
    bar: dict = field(default_factory=dict)        # last closed 5m futures bar
    prev_bar: dict = field(default_factory=dict)
    vwap: float | None = None
    ema20_5m: float | None = None
    atr_5m: float | None = None
    adx_15m: float | None = None
    bb_width_15m: float | None = None
    bb_width_median: float | None = None
    volume_ratio_5m: float | None = None
    or_high: float | None = None
    or_low: float | None = None
    levels: dict[str, float] = field(default_factory=dict)   # named levels, futures points

    def room(self, side: int, price: float) -> tuple[float | None, str | None]:
        """Distance to the nearest level beyond `price` in the trade direction."""
        min_gap = 0.1 * (self.atr_5m or 0)
        beyond = [(abs(v - price), k) for k, v in self.levels.items()
                  if (v - price) * side > min_gap]
        return min(beyond) if beyond else (None, None)


def _trend_votes(df: pd.DataFrame, label: str) -> tuple[list[int], str]:
    if len(df) < TREND_MIN_BARS:
        return [], f"{label} warming up"
    close = df["close"]
    e20, e50 = ind.ema(close, 20).iloc[-1], ind.ema(close, 50).iloc[-1]
    st = int(ind.supertrend(df, 10, 3)["direction"].iloc[-1])
    ema_vote = 1 if e20 > e50 else -1
    arrow = {2: "↑", -2: "↓"}.get(ema_vote + st, "↔")
    return [ema_vote, st], (f"{label} {arrow} (EMA20{'>' if ema_vote > 0 else '<'}50, "
                            f"ST {'up' if st > 0 else 'down'})")


def analyse(ctx: AgentContext) -> TechView:
    token = ctx.ref.future_token
    f5 = ctx.state.frame(token, "5min")
    f15 = ctx.state.frame(token, "15min")
    f60 = ctx.state.frame(token, "60min")

    votes15, d15 = _trend_votes(f15, "15m")
    votes60, d60 = _trend_votes(f60, "60m")
    votes = votes15 + votes60
    score = sum(votes) / len(votes) if votes else 0.0
    htf = "up" if score >= 0.75 else "down" if score <= -0.75 else "flat"
    trend = PillarView("trend", f"{d15} · {d60}", bias=(1 if score >= 0.5 else -1 if score <= -0.5 else 0),
                       strength=abs(score), features={"score": score})

    if len(f5) < MOMENTUM_MIN_BARS:
        return TechView(False, htf, trend, PillarView("momentum", "5m warming up"))

    close = f5["close"]
    rsi = ind.rsi(close, 14)
    hist = ind.macd(close)["hist"]
    adx15 = ind.adx(f15, 14)["adx"].iloc[-1] if len(f15) >= ADX_MIN_BARS else float("nan")
    r_now, r_prev = float(rsi.iloc[-1]), float(rsi.iloc[-2])
    h_now, h_prev = float(hist.iloc[-1]), float(hist.iloc[-2])
    mom = (1 if r_now > 55 and r_now >= r_prev else -1 if r_now < 45 and r_now <= r_prev else 0) + \
          (1 if h_now > 0 and h_now > h_prev else -1 if h_now < 0 and h_now < h_prev else 0)
    trending = adx15 == adx15 and adx15 > 20
    momentum = PillarView(
        "momentum",
        f"RSI {r_now:.0f} {'↑' if r_now >= r_prev else '↓'}, MACD hist {'rising' if h_now > h_prev else 'falling'}"
        + (f", ADX {adx15:.0f}" if adx15 == adx15 else ""),
        bias=(1 if mom > 0 else -1 if mom < 0 else 0),
        strength=abs(mom) / 2 * (1.0 if trending else 0.7),
        features={"rsi": r_now, "macd_hist": h_now, "adx_15m": adx15})

    vwap = ind.session_vwap(f5)
    today = f5[f5.index.date == ctx.state.session_date]
    vol = f5["volume"]
    # Only against 20 bars that all traded: a spot stand-in for missing futures history has volume 0
    vol_ratio = float(vol.iloc[-1] / vol.iloc[-21:-1].mean()) if len(vol) > 21 and (vol.iloc[-21:-1] > 0).all() else None
    bbw = ind.bollinger_width(f15["close"]) if len(f15) >= 40 else None

    levels: dict[str, float] = {}
    pd_ = ctx.state.prev_day(token)
    if pd_:
        piv = ind.cpr(pd_["high"], pd_["low"], pd_["close"])
        levels.update({"PDH": pd_["high"], "PDL": pd_["low"], "PDC": pd_["close"], "CPR top": piv.tc,
                       "CPR bottom": piv.bc, "R1": piv.r1, "S1": piv.s1})
    orng = ind.opening_range(ctx.state.today(token, "1min"), minutes=15)
    if orng:
        levels.update({"OR high": orng[0], "OR low": orng[1]})
    recent = f15.iloc[-75:]                       # ~3 sessions; 15m swings are the ones traders watch
    swings = ind.swing_levels(recent, k=2, tolerance_pct=0.1)
    px = float(close.iloc[-1])
    for kind, values in (("swing high", swings["resistance"]), ("swing low", swings["support"])):
        for v in values:
            if abs(v - px) <= px * 0.015:        # only swings within 1.5% are relevant intraday
                levels[f"{kind} {v:,.0f}"] = v
    if not today.empty and pd.notna(vwap.iloc[-1]):
        levels["VWAP"] = float(vwap.iloc[-1])

    last, prev = f5.iloc[-1], f5.iloc[-2]
    return TechView(
        ready=True, htf_trend=htf, trend=trend, momentum=momentum,
        bar={k: float(last[k]) for k in ("open", "high", "low", "close")},
        prev_bar={k: float(prev[k]) for k in ("open", "high", "low", "close")},
        vwap=float(vwap.iloc[-1]) if pd.notna(vwap.iloc[-1]) else None,
        ema20_5m=float(ind.ema(close, 20).iloc[-1]),
        atr_5m=float(ind.atr(f5, 14).iloc[-1]),
        adx_15m=float(adx15) if adx15 == adx15 else None,
        bb_width_15m=float(bbw.iloc[-1]) if bbw is not None else None,
        bb_width_median=float(bbw.iloc[-120:].median()) if bbw is not None else None,
        volume_ratio_5m=vol_ratio,
        or_high=orng[0] if orng else None, or_low=orng[1] if orng else None,
        levels=levels,
    )

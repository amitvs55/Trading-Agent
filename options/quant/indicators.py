"""Technical indicators on OHLC(V) DataFrames indexed by bar start time.

Wilder smoothing (alpha = 1/period) for RSI, ATR and ADX, matching TradingView and most
Indian charting platforms, so levels quoted on signal cards line up with what you see.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def _wilder(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), period)
    loss = _wilder(-delta.clip(upper=0), period)
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).where(loss != 0, 100.0).where(gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()],
                     axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return _wilder(true_range(df), period)


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = _wilder(true_range(df), period)
    plus_di = 100 * _wilder(plus_dm, period) / tr
    minus_di = 100 * _wilder(minus_dm, period) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"adx": _wilder(dx, period), "plus_di": plus_di, "minus_di": minus_di})


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """Returns the Supertrend line and direction (+1 up, −1 down)."""
    hl2 = ((df["high"] + df["low"]) / 2).to_numpy()
    rng = (multiplier * atr(df, period)).to_numpy()
    close = df["close"].to_numpy()
    n = len(df)
    upper, lower = hl2 + rng, hl2 - rng
    line = np.full(n, np.nan)
    direction = np.zeros(n, dtype=int)
    for i in range(n):
        if np.isnan(rng[i]):
            continue
        if i > 0 and not np.isnan(line[i - 1]):
            if not (upper[i] < upper[i - 1] or close[i - 1] > upper[i - 1]):
                upper[i] = upper[i - 1]
            if not (lower[i] > lower[i - 1] or close[i - 1] < lower[i - 1]):
                lower[i] = lower[i - 1]
            if direction[i - 1] == 1:
                direction[i] = -1 if close[i] < lower[i] else 1
            else:
                direction[i] = 1 if close[i] > upper[i] else -1
        else:
            direction[i] = 1 if close[i] >= hl2[i] else -1
        line[i] = lower[i] if direction[i] == 1 else upper[i]
    return pd.DataFrame({"supertrend": line, "direction": direction}, index=df.index)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP reset each trading day; needs per-bar `volume` (use the futures, not the index)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.date
    pv = (typical * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum()
    return pv / vol.replace(0, np.nan)


def bollinger_width(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.Series:
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    return (2 * k * sd) / mid


@dataclass(frozen=True)
class Pivots:
    pivot: float
    bc: float
    tc: float
    r1: float
    s1: float
    r2: float
    s2: float


def cpr(high: float, low: float, close: float) -> Pivots:
    """Central Pivot Range and classic floor pivots from the previous session."""
    p = (high + low + close) / 3
    bc = (high + low) / 2
    tc = 2 * p - bc
    bc, tc = min(bc, tc), max(bc, tc)
    return Pivots(p, bc, tc, 2 * p - low, 2 * p - high, p + (high - low), p - (high - low))


def swing_levels(df: pd.DataFrame, k: int = 2, tolerance_pct: float = 0.1) -> dict[str, list[float]]:
    """Fractal swing highs/lows, merged within tolerance.

    A swing high beats the k bars before it and is not exceeded by the k bars after it, so
    of two equal adjacent highs (common: the next bar opens at the peak) the first counts.
    """
    highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
    sh, sl = [], []
    for i in range(k, len(df) - k):
        if highs[i] > highs[i - k:i].max() and highs[i] >= highs[i + 1:i + k + 1].max():
            sh.append(float(highs[i]))
        if lows[i] < lows[i - k:i].min() and lows[i] <= lows[i + 1:i + k + 1].min():
            sl.append(float(lows[i]))
    return {"resistance": _merge(sh, tolerance_pct), "support": _merge(sl, tolerance_pct)}


def _merge(levels: list[float], tolerance_pct: float) -> list[float]:
    merged: list[list[float]] = []
    for lv in sorted(levels):
        if merged and abs(lv - np.mean(merged[-1])) <= lv * tolerance_pct / 100:
            merged[-1].append(lv)
        else:
            merged.append([lv])
    return [round(float(np.mean(g)), 2) for g in merged]


def opening_range(df: pd.DataFrame, minutes: int = 15) -> tuple[float, float] | None:
    """High/low of today's first `minutes` (from 09:15) on 1-minute bars."""
    if df.empty:
        return None
    day = df.index[-1].date()
    today = df[df.index.date == day]
    start = today.index[0].replace(hour=9, minute=15, second=0, microsecond=0)
    first = today[(today.index >= start) & (today.index < start + pd.Timedelta(minutes=minutes))]
    if first.empty:
        return None
    return float(first["high"].max()), float(first["low"].min())

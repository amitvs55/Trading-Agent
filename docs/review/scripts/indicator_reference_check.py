"""Phase 4A: recompute the platform's indicators with a reference library and test for look-ahead.

Run from the repo root with the separate review venv (TA-Lib installed there, never in the project):

    <review-venv>/python -I docs/review/scripts/indicator_reference_check.py

Data: synthetic only (seeded random walk + the test suite's synthetic NIFTY market). No network.
Prints a JSON report; nothing in the repo is modified.
"""

import json
import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import talib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from options.quant import indicators as ind                      # noqa: E402
from options.quant import black76 as b76                         # noqa: E402
from options.core.calendar import IST                            # noqa: E402

WARMUP = 150            # bars ignored before comparing steady-state values


def synthetic_ohlcv(n: int = 3000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 25000 * np.exp(np.cumsum(rng.normal(0.00002, 0.0012, n)))
    spread = np.abs(rng.normal(0, 0.0008, n)) * close
    high = close + spread * rng.uniform(0.2, 1.0, n)
    low = close - spread * rng.uniform(0.2, 1.0, n)
    open_ = np.r_[close[0], close[:-1]]
    high, low = np.maximum.reduce([high, open_, close]), np.minimum.reduce([low, open_, close])
    vol = rng.integers(2_000, 9_000, n).astype(float)
    idx = pd.date_range("2026-01-05 09:15", periods=n, freq="5min", tz=IST)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def compare(name: str, ours: pd.Series, ref: np.ndarray, rel: bool = False) -> dict:
    a = np.asarray(ours, dtype=float)
    b = np.asarray(ref, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    steady = mask.copy()
    steady[:WARMUP] = False
    diff = np.abs(a - b)
    scale = np.abs(b) if rel else 1.0
    err = diff / np.where(scale == 0, 1, scale) if rel else diff
    first_ok = None
    tol = 1e-6 if not rel else 1e-6
    for i in range(len(a)):
        if mask[i] and np.all(err[i:][mask[i:]] < max(tol, 1e-4 * (np.nanmax(np.abs(b)) if not rel else 1))):
            first_ok = i
            break
    return {
        "indicator": name,
        "steady_state_max_abs_err": float(np.nanmax(diff[steady])) if steady.any() else None,
        "steady_state_max_rel_err": float(np.nanmax((diff / np.maximum(np.abs(b), 1e-12))[steady])) if steady.any() else None,
        "first_50_valid_max_abs_err": float(np.nanmax(diff[mask][:50])) if mask.any() else None,
        "bars_until_converged": first_ok,
        "nan_count_ours": int(np.isnan(a).sum()),
        "nan_count_ref": int(np.isnan(b).sum()),
    }


def supertrend_reference(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> np.ndarray:
    """Standard Supertrend (ATR with Wilder smoothing via TA-Lib), written independently."""
    atr = talib.ATR(df.high.values, df.low.values, df.close.values, period)
    hl2 = (df.high.values + df.low.values) / 2
    up, dn = hl2 - mult * atr, hl2 + mult * atr
    fu, fd = np.full(len(df), np.nan), np.full(len(df), np.nan)
    direction = np.zeros(len(df))
    c = df.close.values
    for i in range(len(df)):
        if np.isnan(atr[i]):
            continue
        if i == 0 or np.isnan(fu[i - 1]):
            fu[i], fd[i], direction[i] = up[i], dn[i], 1
            continue
        fu[i] = max(up[i], fu[i - 1]) if c[i - 1] > fu[i - 1] else up[i]
        fd[i] = min(dn[i], fd[i - 1]) if c[i - 1] < fd[i - 1] else dn[i]
        if direction[i - 1] == 1:
            direction[i] = -1 if c[i] < fu[i] else 1
        else:
            direction[i] = 1 if c[i] > fd[i] else -1
    return direction


def black76_reference(f, k, t, r, sigma, right):
    d1 = (math.log(f / k) + 0.5 * sigma * sigma * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    n = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    df = math.exp(-r * t)
    return df * (f * n(d1) - k * n(d2)) if right == "CE" else df * (k * n(-d2) - f * n(-d1))


def research_rsi_vs_wilder(df: pd.DataFrame) -> dict:
    sys.path.insert(0, str(ROOT))
    from agents.market_data import _compute_rsi                    # SMA-based RSI used by the research agent
    daily = df.close.iloc[::75].reset_index(drop=True)              # ~daily sampling of the synthetic path
    out = []
    for end in range(30, len(daily)):
        window = daily.iloc[end - 63:end] if end >= 63 else daily.iloc[:end]   # ~3 months of daily closes
        ours = _compute_rsi(window, 14)
        ref = talib.RSI(window.values, 14)[-1]
        if ours is not None and not np.isnan(ref):
            out.append(abs(ours - ref))
    out = np.array(out)
    return {"indicator": "research RSI(14) [SMA] vs TA-Lib RSI(14) [Wilder]", "samples": int(len(out)),
            "mean_abs_diff_points": round(float(out.mean()), 2), "p95_abs_diff_points": round(float(np.percentile(out, 95)), 2),
            "max_abs_diff_points": round(float(out.max()), 2),
            "share_crossing_30_70_bands_differently": None}


def repaint_test() -> dict:
    """A decision must not change when ticks of the still-forming bar arrive (closed bars only)."""
    from tests.options.market import build_market                # synthetic NIFTY market (no network)
    from options.engine.snapshot import take

    ctx = build_market(today_minutes=120)                         # now = 11:15:03, last full 5m bucket ends 11:15
    base = take(ctx)
    token = ctx.ref.future_token
    last = ctx.state.last(token)
    # Simulate 3 minutes of the next, still-forming 5m bar with an extreme move against the trend
    partial = []
    day_volume = ctx.state._counted[(token, last["ts"].date())]
    for m in range(3):
        ts = last["ts"] + timedelta(minutes=m + 1)
        px = last["close"] * (0.97 - 0.01 * m)
        partial.append({"instrument_token": token, "ts": ts, "open": px, "high": px, "low": px, "close": px,
                        "volume_day": day_volume + 1000 * (m + 1), "oi": last.get("oi"), "bid": None, "ask": None})
    if partial:
        ctx.state.add_bars(partial)
    again = take(ctx)
    keys = {
        "htf_trend": (base.tech.htf_trend, again.tech.htf_trend),
        "trend_bias": (base.tech.trend.bias, again.tech.trend.bias),
        "momentum_detail": (base.tech.momentum.detail, again.tech.momentum.detail),
        "atr_5m": (round(base.tech.atr_5m or 0, 6), round(again.tech.atr_5m or 0, 6)),
        "ema20_5m": (round(base.tech.ema20_5m or 0, 6), round(again.tech.ema20_5m or 0, 6)),
        "last_closed_5m_bar": (base.tech.bar, again.tech.bar),
    }
    changed = {k: v for k, v in keys.items() if v[0] != v[1]}
    return {"test": "partial (forming) 5m bar must not change 5m/15m/60m indicator outputs",
            "partial_minutes_added": len(partial), "changed_outputs": changed, "passed": not changed,
            "note": "futures_flow and the 1m-based opening range read the newest 1m bars by design"}


def main() -> None:
    df = synthetic_ohlcv()
    h, l, c, v = df.high.values, df.low.values, df.close.values, df.volume.values
    report = {"data": f"synthetic 5m OHLCV, {len(df)} bars, seed 11", "warmup_bars_ignored": WARMUP, "results": []}
    R = report["results"]
    R.append(compare("EMA(20)", ind.ema(df.close, 20), talib.EMA(c, 20)))
    R.append(compare("RSI(14) Wilder", ind.rsi(df.close, 14), talib.RSI(c, 14)))
    m = ind.macd(df.close)
    _, _, ref_hist = talib.MACD(c, 12, 26, 9)
    R.append(compare("MACD hist(12,26,9)", m["hist"], ref_hist))
    R.append(compare("ATR(14)", ind.atr(df, 14), talib.ATR(h, l, c, 14)))
    R.append(compare("ADX(14)", ind.adx(df, 14)["adx"], talib.ADX(h, l, c, 14)))
    up, mid, lo = talib.BBANDS(c, 20, 2, 2, 0)
    ours_bbw = ind.bollinger_width(df.close, 20, 2.0)
    ref_bbw = (up - lo) / mid
    R.append(compare("Bollinger width(20,2)", ours_bbw, ref_bbw))
    st_ours = ind.supertrend(df, 10, 3.0)["direction"].values
    st_ref = supertrend_reference(df, 10, 3.0)
    valid = (st_ref != 0) & ~np.isnan(st_ours)
    valid[:WARMUP] = False
    R.append({"indicator": "Supertrend(10,3) direction", "agreement_pct": round(float((st_ours[valid] == st_ref[valid]).mean() * 100), 2),
              "bars_compared": int(valid.sum())})
    # Session VWAP: cumulative (typical price × volume) per day
    tp = (df.high + df.low + df.close) / 3
    day = df.index.date
    ref_vwap = (tp * df.volume).groupby(day).cumsum() / df.volume.groupby(day).cumsum()
    R.append(compare("Session VWAP", ind.session_vwap(df), ref_vwap.values))
    # Black-76 against an independent closed form
    errs = []
    for k in range(24000, 26050, 50):
        for right in ("CE", "PE"):
            for t in (1 / 365, 3 / 365, 7 / 365, 30 / 365):
                ours = b76.price(25000.0, float(k), t, 0.06, 0.14, right)
                ref = black76_reference(25000.0, float(k), t, 0.06, 0.14, right)
                errs.append(abs(ours - ref))
    R.append({"indicator": "Black-76 price vs independent closed form", "cases": len(errs), "max_abs_err_rupees": float(max(errs))})
    R.append(research_rsi_vs_wilder(df))
    report["repaint_test"] = repaint_test()
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

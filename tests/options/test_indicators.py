import numpy as np
import pandas as pd
import pytest

from options.quant import indicators as ind


def frame(closes, start="2026-10-16 09:15", freq="5min", spread=2.0, volume=1000):
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="Asia/Kolkata")
    c = pd.Series(closes, index=idx, dtype=float)
    o = c.shift().fillna(c.iloc[0])
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c, "volume": volume}, index=idx)


def test_ema_matches_the_recursive_definition():
    s = pd.Series([1.0, 2, 3, 4, 5])
    e = ind.ema(s, 3)
    alpha = 2 / 4
    expected = 1.0
    for x in [2, 3, 4, 5]:
        expected = alpha * x + (1 - alpha) * expected
    assert e.iloc[-1] == pytest.approx(expected)


def test_rsi_extremes_and_range():
    up = ind.rsi(pd.Series(np.arange(1, 40, dtype=float)), 14)
    assert up.iloc[-1] == 100.0
    down = ind.rsi(pd.Series(np.arange(40, 1, -1, dtype=float)), 14)
    assert down.iloc[-1] == pytest.approx(0.0)
    rng = np.random.default_rng(1)
    r = ind.rsi(pd.Series(100 + rng.normal(0, 1, 300).cumsum()), 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()
    assert ind.rsi(pd.Series(np.arange(1, 10, dtype=float)), 14).isna().all()   # not enough data


def test_macd_histogram_is_line_minus_signal():
    m = ind.macd(pd.Series(np.linspace(100, 130, 80)))
    assert (m["hist"] - (m["macd"] - m["signal"])).abs().max() < 1e-9
    assert m["macd"].iloc[-1] > 0


def test_atr_of_constant_range_bars():
    df = frame([100.0] * 30, spread=5.0)
    assert ind.atr(df, 14).iloc[-1] == pytest.approx(10.0)


def test_adx_is_high_in_a_steady_trend_and_di_points_the_right_way():
    a = ind.adx(frame(np.linspace(25000, 25600, 80)), 14).iloc[-1]
    assert a["adx"] > 40 and a["plus_di"] > a["minus_di"]
    b = ind.adx(frame(np.linspace(25600, 25000, 80)), 14).iloc[-1]
    assert b["minus_di"] > b["plus_di"]


def test_supertrend_flips_with_the_trend():
    closes = list(np.linspace(25000, 25400, 40)) + list(np.linspace(25400, 24900, 40))
    st = ind.supertrend(frame(closes), 10, 3)
    assert st["direction"].iloc[38] == 1
    assert st["direction"].iloc[-1] == -1
    up = st.iloc[38]
    assert up["supertrend"] < closes[38]                                  # line below price in an uptrend


def test_vwap_resets_each_day():
    day1 = frame([100.0, 102, 104], start="2026-10-15 09:15", spread=0)
    day2 = frame([200.0, 200], start="2026-10-16 09:15", spread=0)
    v = ind.session_vwap(pd.concat([day1, day2]))
    assert v.iloc[2] == pytest.approx(np.mean([(100 + 100 + 100) / 3, (100 + 102 + 102) / 3, (102 + 104 + 104) / 3]))
    assert v.iloc[3] == pytest.approx(200.0)


def test_cpr_and_pivots():
    p = ind.cpr(25400, 25100, 25300)
    assert p.pivot == pytest.approx(25266.6667, abs=1e-3)
    assert p.bc <= p.pivot <= p.tc
    assert p.r1 > p.pivot > p.s1 and p.r2 > p.r1 and p.s2 < p.s1


def test_swing_levels_and_merging():
    closes = [100, 103, 108, 103, 100, 97, 92, 97, 100, 103, 108.05, 103, 100]
    df = frame(closes, spread=0)
    lv = ind.swing_levels(df, k=2, tolerance_pct=0.5)
    assert len(lv["resistance"]) == 1 and lv["resistance"][0] == pytest.approx(108.025, abs=0.01)   # merged mean, rounded
    assert lv["support"] == [92.0]


def test_opening_range_uses_the_first_minutes_of_today():
    df = frame([100, 105, 95, 101, 110, 90], start="2026-10-16 09:15", freq="5min", spread=0)
    # bars 09:15, 09:20, 09:25 (open = previous close): highs 100/105/105, lows 100/100/95
    assert ind.opening_range(df, minutes=15) == (105.0, 95.0)

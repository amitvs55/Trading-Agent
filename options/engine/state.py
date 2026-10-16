"""In-memory market state: history + live 1-minute bars, resampled for the agents.

Kite historical candles carry per-bar volume while live bars carry cumulative day volume
(`volume_day`); both are normalised to per-bar `volume` here so VWAP and volume surges
work across the seam. Buckets are aligned to the 09:15 open (09:15, 09:20, … for 5m).
"""

from collections import defaultdict
from datetime import date, datetime, time

import numpy as np
import pandas as pd

from options.core.calendar import IST, MARKET_OPEN, at_ist

COLUMNS = ["open", "high", "low", "close", "volume", "oi", "bid", "ask", "bid_qty", "ask_qty"]
_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "oi": "last",
        "bid": "last", "ask": "last", "bid_qty": "last", "ask_qty": "last"}


def _minutes(tf: str) -> int:
    return int(tf.removesuffix("min"))


class MarketState:
    def __init__(self, session_date: date):
        self.session_date = session_date
        self._origin = pd.Timestamp(at_ist(session_date, MARKET_OPEN))
        self._day_start = pd.Timestamp(at_ist(session_date, time(0, 0)))
        self._rows: dict[int, dict[pd.Timestamp, dict]] = defaultdict(dict)
        self._daily: dict[int, pd.DataFrame] = {}
        self._counted: dict[tuple[int, date], int] = defaultdict(int)   # day volume already assigned
        self._cache: dict[tuple[int, str, bool], pd.DataFrame] = {}

    # ── Loading ──────────────────────────────────────────────────────────────

    def load_history(self, token: int, candles: list[dict]) -> None:
        """Kite minute candles: {date, open, high, low, close, volume[, oi]}."""
        for c in candles:
            ts = pd.Timestamp(c["date"]).tz_convert(IST) if pd.Timestamp(c["date"]).tzinfo else \
                pd.Timestamp(c["date"]).tz_localize(IST)
            vol = int(c.get("volume") or 0)
            self._rows[token][ts] = {"open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"],
                                     "volume": vol, "oi": c.get("oi"), "bid": None, "ask": None,
                                     "bid_qty": None, "ask_qty": None}
            self._counted[(token, ts.date())] += vol
        self._invalidate(token)

    def load_daily(self, token: int, candles: list[dict]) -> None:
        """Kite day candles, oldest first."""
        df = pd.DataFrame(candles)
        if df.empty:
            return
        df["date"] = pd.to_datetime(df["date"]).dt.date
        self._daily[token] = df.set_index("date")[["open", "high", "low", "close", "volume"]]

    def add_bars(self, bars: list[dict]) -> None:
        """Live 1-minute bars as written by the recorder (Bar.as_row())."""
        touched = set()
        for b in bars:
            token, ts = b["instrument_token"], pd.Timestamp(b["ts"]).tz_convert(IST)
            day_volume = b.get("volume_day")
            volume = 0
            if day_volume is not None:
                key = (token, ts.date())
                volume = max(int(day_volume) - self._counted[key], 0)
                self._counted[key] = max(self._counted[key], int(day_volume))
            self._rows[token][ts] = {"open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"],
                                     "volume": volume, "oi": b.get("oi"), "bid": b.get("bid"), "ask": b.get("ask"),
                                     "bid_qty": b.get("bid_qty"), "ask_qty": b.get("ask_qty")}
            touched.add(token)
        for token in touched:
            self._invalidate(token)

    def _invalidate(self, token: int) -> None:
        for key in [k for k in self._cache if k[0] == token]:
            del self._cache[key]

    # ── Queries ──────────────────────────────────────────────────────────────

    def tokens(self) -> list[int]:
        return list(self._rows)

    def frame(self, token: int, tf: str = "5min", closed_only: bool = True) -> pd.DataFrame:
        key = (token, tf, closed_only)
        if key in self._cache:
            return self._cache[key]
        rows = self._rows.get(token)
        if not rows:
            return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], tz=IST), dtype=float)
        one = self._cache.get((token, "1min", True))
        if one is None:
            keys = sorted(rows)
            # Column-wise construction: far faster than DataFrame.from_dict on dict rows; None → NaN
            data = {c: np.array([rows[k].get(c) for k in keys], dtype=float) for c in COLUMNS}
            one = pd.DataFrame(data, index=pd.DatetimeIndex(keys))
            self._cache[(token, "1min", True)] = self._cache[(token, "1min", False)] = one
        if tf == "1min":
            out = one
        else:
            n = _minutes(tf)
            out = one.resample(f"{n}min", origin=self._origin, label="left", closed="left").agg(_AGG)
            out = out.dropna(subset=["open"])
            if closed_only and not out.empty:
                last_end = one.index[-1] + pd.Timedelta(minutes=1)
                if out.index[-1] + pd.Timedelta(minutes=n) > last_end:
                    out = out.iloc[:-1]
        self._cache[key] = out
        return out

    def today(self, token: int, tf: str = "5min", closed_only: bool = True) -> pd.DataFrame:
        key = (token, f"today:{tf}", closed_only)
        if key not in self._cache:
            df = self.frame(token, tf, closed_only)
            self._cache[key] = df[df.index >= self._day_start]
        return self._cache[key]

    def last(self, token: int) -> dict | None:
        rows = self._rows.get(token)
        if not rows:
            return None
        ts = max(rows)
        return {"ts": ts.to_pydatetime(), **rows[ts]}

    def last_price(self, token: int) -> float | None:
        bar = self.last(token)
        return float(bar["close"]) if bar else None

    def prev_day(self, token: int) -> dict | None:
        """Previous session's OHLC: from day candles if loaded, else from stored 1m history."""
        daily = self._daily.get(token)
        if daily is not None:
            before = daily[daily.index < self.session_date]
            if not before.empty:
                row = before.iloc[-1]
                return {"date": before.index[-1], **{k: float(row[k]) for k in ("open", "high", "low", "close")}}
        one = self.frame(token, "1min")
        earlier = one[one.index.date < self.session_date]
        if earlier.empty:
            return None
        day = earlier.index[-1].date()
        d = earlier[earlier.index.date == day]
        return {"date": day, "open": float(d["open"].iloc[0]), "high": float(d["high"].max()),
                "low": float(d["low"].min()), "close": float(d["close"].iloc[-1])}

    def daily(self, token: int, include_today: bool = True) -> pd.DataFrame:
        """Day candles (history) plus today's running candle built from 1m bars."""
        base = self._daily.get(token, pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
        base = base[base.index < self.session_date] if not base.empty else base
        if not include_today:
            return base
        today = self.today(token, "1min")
        if today.empty:
            return base
        row = pd.DataFrame({"open": [today["open"].iloc[0]], "high": [today["high"].max()],
                            "low": [today["low"].min()], "close": [today["close"].iloc[-1]],
                            "volume": [today["volume"].sum()]}, index=[self.session_date])
        return pd.concat([base, row]) if not base.empty else row

    def as_of(self) -> datetime | None:
        latest = [max(r) for r in self._rows.values() if r]
        return max(latest).to_pydatetime() if latest else None

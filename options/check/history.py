"""History's view: how NIFTY actually moved over the same stretch of the session in the past.

Built from the saved 1-minute NIFTY spot bars (two years once the backfill has run). A check at
10:42 held to 15:15 gets one sample from every past session: that day's path from 10:42 to 15:15.
Held to an expiry k sessions away, the path runs from 10:42 to the close k sessions later, overnight
gaps included. Sessions that looked like today (the same direction over the previous hour, India
VIX within ±20%) form the "similar sessions" sample when there are at least MIN_SIMILAR of them.

The paths are used as they happened (scaled to today's level), not fitted to a distribution: if
history had fat tails or trends, the numbers keep them.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time

import numpy as np

from options.core.calendar import IST, MARKET_OPEN

SESSION_MINUTES = 375                 # 09:15 … 15:29 bars
MIN_SIMILAR = 30
MIN_SESSIONS = 20


def minute_of(ts: datetime) -> int:
    t = ts.astimezone(IST)
    return (t.hour - MARKET_OPEN.hour) * 60 + (t.minute - MARKET_OPEN.minute)


@dataclass
class HistoryModel:
    days: list[date]
    closes: np.ndarray                          # sessions × 375 minute closes (NaN where missing)
    vix: dict[date, float] = field(default_factory=dict)

    @classmethod
    def from_rows(cls, spot_rows: list[dict], vix_rows: list[dict] | None = None, before: date | None = None) -> "HistoryModel":
        by_day: dict[date, dict[int, float]] = {}
        for r in spot_rows:
            ts = r["ts"] if r["ts"].tzinfo else r["ts"].replace(tzinfo=IST)
            d = ts.astimezone(IST).date()
            if before and d >= before:
                continue
            m = minute_of(ts)
            if 0 <= m < SESSION_MINUTES:
                by_day.setdefault(d, {})[m] = float(r["close"])
        days = sorted(d for d, mins in by_day.items() if len(mins) >= 300)      # full sessions only
        closes = np.full((len(days), SESSION_MINUTES), np.nan)
        for i, d in enumerate(days):
            for m, c in by_day[d].items():
                closes[i, m] = c
            # carry the last price into missing minutes so a path never has holes
            row = closes[i]
            idx = np.where(~np.isnan(row), np.arange(SESSION_MINUTES), 0)
            np.maximum.accumulate(idx, out=idx)
            closes[i] = row[idx]
            first = np.argmax(~np.isnan(closes[i]))
            closes[i, :first] = closes[i, first]
        vix: dict[date, float] = {}
        for r in vix_rows or []:
            ts = r["ts"] if r["ts"].tzinfo else r["ts"].replace(tzinfo=IST)
            vix[ts.astimezone(IST).date()] = float(r["close"])                 # rows come oldest first: last wins
        return cls(days, closes, vix)

    @property
    def sessions(self) -> int:
        return len(self.days)

    def paths(self, start_minute: int, days_ahead: int, end_minute: int, step: int = 5) -> tuple[np.ndarray, list[int]]:
        """Relative paths (1.0 at the start) from `start_minute` on each past session to `end_minute`
        `days_ahead` sessions later, sampled every `step` minutes (plus the exact end). Returns
        (paths × steps array, indices of the starting sessions)."""
        start_minute = min(max(start_minute, 0), SESSION_MINUTES - 1)
        end_minute = min(max(end_minute, 0), SESSION_MINUTES - 1)
        out, starts = [], []
        for i in range(self.sessions - days_ahead):
            if days_ahead == 0:
                seg = self.closes[i, start_minute:end_minute + 1]
            else:
                parts = [self.closes[i, start_minute:]]
                parts += [self.closes[j] for j in range(i + 1, i + days_ahead)]
                parts.append(self.closes[i + days_ahead, :end_minute + 1])
                seg = np.concatenate(parts)
            if seg.size < 2 or np.isnan(seg).any():
                continue
            picks = np.unique(np.r_[np.arange(0, seg.size, step), seg.size - 1])
            out.append(seg[picks] / seg[0])
            starts.append(i)
        if not out:
            return np.empty((0, 0)), []
        width = min(len(p) for p in out)
        return np.vstack([p[:width - 1].tolist() + [p[-1]] for p in out]), starts

    def similar(self, starts: list[int], start_minute: int, prior_move: float | None, vix_now: float | None) -> list[int]:
        """Positions in `starts` whose session looked like today at the start: the same direction over the
        previous hour (or since the open) and India VIX within ±20%."""
        keep = []
        for pos, i in enumerate(starts):
            ok = True
            if prior_move is not None:
                back = max(start_minute - 60, 0)
                if start_minute > back:
                    move = self.closes[i, start_minute] / self.closes[i, back] - 1
                elif i > 0:
                    move = self.closes[i, 0] / self.closes[i - 1, -1] - 1
                else:
                    move = 0.0
                ok = np.sign(move) == np.sign(prior_move) or abs(prior_move) < 0.0005
            if ok and vix_now and self.vix:
                v = self.vix.get(self.days[i - 1]) if i > 0 else None
                ok = v is not None and abs(v / vix_now - 1) <= 0.2
            if ok:
                keep.append(pos)
        return keep


def prior_move(closes_today: list[float], start_minute: int) -> float | None:
    """Today's move over the hour before the check (or since the open)."""
    if not closes_today or start_minute <= 0 or start_minute >= len(closes_today):
        return None
    back = max(start_minute - 60, 0)
    return closes_today[start_minute] / closes_today[back] - 1 if closes_today[back] else None


EXIT_INTRADAY = time(15, 15)

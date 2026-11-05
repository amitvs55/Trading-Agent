"""Replay recorded sessions through the live signal engine (plan §11, steps 1–2).

Bars are fed minute by minute exactly as the recorder would have delivered them, and the
engine's clock sits 4 seconds after each minute closes, so a replay sees what the live
system saw and nothing later: no look-ahead. Results go to a separate database so a
replay can never mix with the live track record.

    python -m options.backtest.replay --from 2026-10-19 --to 2026-11-30 --out sqlite:///data/replay.db
"""

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from options.agents.context import Constituent
from options.config import OptionsSettings, settings as default_settings
from options.core.calendar import IST, NseCalendar, at_ist
from options.core.constituents import HEAVYWEIGHTS
from options.core.schemas import Signal
from options.engine import performance
from options.engine.engine import SignalEngine
from options.engine.state import MarketState
from options.notify.base import Notifier
from options.reference import VIX_SYMBOL, build_reference, find_token
from options.setups.base import Setup
from options.storage import Store, make_engine

HISTORY_DAYS = 20               # the same warm-up the live session loads (session.HISTORY_SESSIONS)
DAILY_DAYS = 400                # day candles for VIX rank, RV20 and daily trends (session.DAILY_DAYS)
FLUSH_DELAY = timedelta(seconds=4)


class SilentNotifier:
    def __init__(self):
        self.messages: list[str] = []

    def send(self, text: str, buttons=None) -> bool:
        self.messages.append(text)
        return True


def _as_ist(ts) -> datetime:
    return ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)


def _daily(source: Store, token: int, day: date, cache: dict | None) -> list[dict]:
    """Day candles before `day`, built from saved minutes; `cache` keeps one read per token per run."""
    if cache is not None and token in cache:
        rows = cache[token]
    else:
        rows = source.daily_bars(token, at_ist(day - timedelta(days=DAILY_DAYS), time(0)), at_ist(day, time(0)))
    return [r for r in rows if r["date"] < day]


def replay_day(source: Store, target: Store, day: date, cfg: OptionsSettings, calendar: NseCalendar,
               notifier: Notifier | None = None, setups: list[Setup] | None = None,
               until: time | None = None, daily_cache: dict | None = None) -> list[Signal]:
    """Replay one recorded day (or its first part, up to `until`) into `target`."""
    rows = source.instruments_on(day)
    if not rows:
        return []
    nse = [r for r in rows if r["segment"] in ("INDICES", "NSE")]
    nfo = [r for r in rows if r["segment"] in ("NFO-FUT", "NFO-OPT")]
    refs = {}
    for i in cfg.OPTIONS_INDICES:          # an index added later has no contracts in older snapshots: skip it
        try:
            refs[i] = build_reference(i, nse, nfo, day)
        except LookupError:
            continue
    if not refs:
        return []
    vix_token = find_token(nse, VIX_SYMBOL)

    # Warm up on the previous recorded sessions (live-style rows, cumulative day volume)
    state = MarketState(day)
    hist_start = day
    for _ in range(HISTORY_DAYS):
        hist_start = calendar.previous_trading_day(hist_start)
    warm_tokens = {vix_token} | {t for r in refs.values() for t in (r.spot_token, r.future_token)}
    eq_tokens = {int(r["instrument_token"]): r["tradingsymbol"] for r in nse if r["segment"] == "NSE"}
    history = source.bars_between(at_ist(hist_start, time(0)), at_ist(day, time(0)), warm_tokens | set(eq_tokens))
    state.add_bars([{**b, "ts": _as_ist(b["ts"])} for b in history])
    # Day candles, as the live session loads them from the broker: India VIX's year sets its percentile,
    # the index's sets realised vol and the positional setup's daily trend
    vix_history: list[float] = []
    for token in {r.spot_token for r in refs.values()} | ({vix_token} if vix_token else set()):
        rows = _daily(source, token, day, daily_cache)
        if rows:
            state.load_daily(token, rows)
            if token == vix_token:
                vix_history = [float(r["close"]) for r in rows]

    constituents = {}
    for index in cfg.OPTIONS_INDICES:
        sym_tok = {s: t for t, s in eq_tokens.items()}
        constituents[index] = [Constituent(sym, w, sym_tok[sym], state.last_price(sym_tok[sym]))
                               for sym, w in HEAVYWEIGHTS.get(index, []) if sym in sym_tok]

    clock = {"now": at_ist(day, time(9, 0))}
    quotes: dict[int, tuple[float | None, float | None]] = {}
    engine = SignalEngine(refs, state, target, notifier or SilentNotifier(), cfg, calendar, vix_token=vix_token,
                          constituents=constituents, vix_history=vix_history, events=None,
                          quote_fn=lambda t: quotes.get(t, (None, None)),
                          now_fn=lambda: clock["now"], setups=setups)

    by_minute: dict[datetime, list[dict]] = defaultdict(list)
    for b in source.bars_between(at_ist(day, time(9, 0)), at_ist(day, until or time(15, 31))):
        b = {**b, "ts": _as_ist(b["ts"])}
        by_minute[b["ts"]].append(b)
    for minute in sorted(by_minute):
        bars = by_minute[minute]
        clock["now"] = minute + timedelta(minutes=1) + FLUSH_DELAY
        engine.on_bars(bars)
        for b in bars:
            if b.get("bid") or b.get("ask"):
                quotes[b["instrument_token"]] = (b.get("bid"), b.get("ask"))
        engine.on_tick(clock["now"])
    return target.signals_since(at_ist(day, time(0)), at_ist(day, time(0)) + timedelta(days=1))


def replay(source: Store, target: Store, start: date, end: date, cfg: OptionsSettings = default_settings,
           calendar: NseCalendar | None = None, setups: list[Setup] | None = None,
           on_day=None) -> dict:
    """Replay every recorded day in [start, end]. `on_day(done, total, day)` reports progress."""
    calendar = calendar or NseCalendar()
    days = [d for d in source.recorded_days() if start <= d <= end]
    signals: list[Signal] = []
    cache: dict[int, list[dict]] = {}
    if days:
        nse = [r for r in source.instruments_on(days[-1]) if r["segment"] in ("INDICES", "NSE")]
        tokens = {find_token(nse, VIX_SYMBOL)} | {int(r["instrument_token"]) for r in nse
                                                  if r["segment"] == "INDICES" and r["tradingsymbol"] != VIX_SYMBOL}
        lo, hi = at_ist(days[0] - timedelta(days=DAILY_DAYS), time(0)), at_ist(days[-1], time(0))
        cache = {t: source.daily_bars(t, lo, hi) for t in tokens if t}
    for i, d in enumerate(days):
        if on_day:
            on_day(i, len(days), d)
        signals += replay_day(source, target, d, cfg, calendar, setups=setups, daily_cache=cache)
    if on_day and days:
        on_day(len(days), len(days), days[-1])
    return {"days": [d.isoformat() for d in days], "signals": len(signals),
            "overall": performance.stats(signals), "by_setup": performance.by(signals, "setup")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    ap.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    ap.add_argument("--source", default=default_settings.DATABASE_URL, help="database with recorded bars")
    ap.add_argument("--out", required=True, help="separate database for replay signals")
    args = ap.parse_args(argv)
    if args.out == args.source:
        print("--out must differ from --source so replay signals never mix with the live record", file=sys.stderr)
        return 2
    report = replay(Store(make_engine(args.source)), Store(make_engine(args.out)), args.start, args.end)
    print(f"Replayed {len(report['days'])} day(s): {report['signals']} signal(s)")
    print("Overall:", performance.summary_line(report["overall"]))
    for setup, st in report["by_setup"].items():
        print(f"  {setup}: {performance.summary_line(st)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

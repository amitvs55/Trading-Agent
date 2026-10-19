"""Option Check when the live engine can't answer (market closed, or the recorder is down).

Rebuilds the engine's view from saved data exactly as a replay does: the last recorded session's
contract list and bars, with the 20 sessions before it for warm-up, then one snapshot at that
session's last bar. Cached per session and index, so more checks and what-ifs that evening are
instant. The history view's paths are cached per day too.
"""

import threading
import time as _clock
from datetime import date, datetime, time, timedelta

from options.agents.context import AgentContext, Constituent
from options.check.history import HistoryModel
from options.core.calendar import IST, NseCalendar, at_ist
from options.core.constituents import HEAVYWEIGHTS
from options.engine.snapshot import Snapshot, take
from options.engine.state import MarketState
from options.reference import VIX_SYMBOL, IndexReference, build_reference, find_token
from options.storage import Store

WARMUP_SESSIONS = 20
HISTORY_YEARS = 2
CACHE_S = 600

_lock = threading.Lock()
_refs: dict[tuple, tuple[float, dict]] = {}
_snaps: dict[tuple, tuple[float, Snapshot]] = {}
_history: dict[tuple, tuple[float, HistoryModel]] = {}


def _as_ist(ts) -> datetime:
    return ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)


def _cached(cache: dict, key: tuple, build, ttl: float = CACHE_S):
    with _lock:
        hit = cache.get(key)
        if hit and _clock.monotonic() - hit[0] < ttl:
            return hit[1]
    value = build()
    with _lock:
        cache[key] = (_clock.monotonic(), value)
    return value


def last_session(store: Store, on_or_before: date) -> date | None:
    days = [d for d in store.recorded_days() if d <= on_or_before]
    return days[-1] if days else None


def _split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    return ([r for r in rows if r["segment"] in ("INDICES", "NSE")],
            [r for r in rows if r["segment"] in ("NFO-FUT", "NFO-OPT")])


def references(store: Store, indices: list[str], day: date) -> tuple[dict[str, IndexReference], int | None]:
    """The contract lists saved for `day` (cached): (index → reference, India VIX token)."""
    def build():
        nse, nfo = _split(store.instruments_on(day))
        refs = {}
        for i in indices:
            try:
                refs[i] = build_reference(i, nse, nfo, day)
            except Exception:
                continue
        try:
            vix = find_token(nse, VIX_SYMBOL)
        except Exception:
            vix = None
        return refs, vix
    return _cached(_refs, (id(store.engine), day, tuple(indices)), build)


def snapshot(store: Store, calendar: NseCalendar, index: str, day: date, r: float, events: list,
             ttl: float = CACHE_S) -> Snapshot | None:
    """The engine's snapshot at the last bar of `day`, rebuilt from saved bars (cached for `ttl` s)."""
    def build():
        refs, vix = references(store, [index], day)
        ref = refs.get(index)
        if ref is None:
            return None
        nse, _ = _split(store.instruments_on(day))
        eq = {r_["tradingsymbol"]: int(r_["instrument_token"]) for r_ in nse if r_["segment"] == "NSE"}
        start = day
        for _ in range(WARMUP_SESSIONS):
            start = calendar.previous_trading_day(start)
        state = MarketState(day)
        warm = {ref.spot_token, ref.future_token} | ({vix} if vix else set()) | set(eq.values())
        state.add_bars([{**b, "ts": _as_ist(b["ts"])}
                        for b in store.bars_between(at_ist(start, time(0)), at_ist(day, time(0)), warm)])
        constituents = [Constituent(sym, w, eq[sym], state.last_price(eq[sym])) for sym, w in HEAVYWEIGHTS.get(index, [])
                        if sym in eq]
        todays = [{**b, "ts": _as_ist(b["ts"])} for b in store.bars_between(at_ist(day, time(9, 0)), at_ist(day, time(15, 31)))]
        state.add_bars(todays)
        last = state.as_of()
        if last is None:
            return None
        ctx = AgentContext(index, ref, state, last + timedelta(minutes=1), calendar, vix_token=vix,
                           constituents=constituents, events=events, r=r)
        return take(ctx)
    return _cached(_snaps, (id(store.engine), index, day), build, ttl=ttl)


def history(store: Store, spot_token: int, vix_token: int | None, today: date) -> HistoryModel:
    """Up to two years of saved NIFTY spot minutes (and India VIX closes) before today (cached)."""
    def build():
        since = at_ist(today - timedelta(days=365 * HISTORY_YEARS + 7), time(0))
        until = at_ist(today, time(0))
        spot = store.bars_between(since, until, {spot_token})
        vix = store.bars_between(since, until, {vix_token}) if vix_token else []
        return HistoryModel.from_rows(spot, vix, before=today)
    return _cached(_history, (id(store.engine), spot_token, today), build, ttl=3600)

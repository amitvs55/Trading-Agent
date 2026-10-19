"""A synthetic but internally consistent NIFTY market: instruments, twenty sessions of history
and a live morning priced with Black-76.

Used by the tests and by the Agents page self-test, which runs every analysis agent on it
when no recorded session exists yet (it proves the agents work, not that the market is real).
"""

from datetime import date, time, timedelta

import numpy as np

from options.agents.context import AgentContext, Constituent
from options.core.calendar import NseCalendar, at_ist
from options.core.constituents import NIFTY_HEAVYWEIGHTS
from options.engine.state import MarketState
from options.quant import black76 as b76
from options.reference import build_reference

TODAY = date(2026, 10, 16)              # Friday
WEEKLY = date(2026, 10, 19)             # Monday: Tue 20 Oct is Dussehra
MONTHLY = date(2026, 10, 27)
EXPIRED = date(2026, 10, 13)

NIFTY_SPOT_TOKEN = 256265
VIX_TOKEN = 264969
FUT_TOKEN = 9001
NEXT_FUT_TOKEN = 9002

NSE_ROWS = [
    {"instrument_token": NIFTY_SPOT_TOKEN, "tradingsymbol": "NIFTY 50", "name": "NIFTY 50",
     "segment": "INDICES", "instrument_type": "EQ", "expiry": "", "strike": 0.0, "lot_size": 0, "tick_size": 0.0},
    {"instrument_token": VIX_TOKEN, "tradingsymbol": "INDIA VIX", "name": "INDIA VIX",
     "segment": "INDICES", "instrument_type": "EQ", "expiry": "", "strike": 0.0, "lot_size": 0, "tick_size": 0.0},
    {"instrument_token": 738561, "tradingsymbol": "RELIANCE", "name": "RELIANCE INDUSTRIES",
     "segment": "NSE", "instrument_type": "EQ", "expiry": "", "strike": 0.0, "lot_size": 1, "tick_size": 0.1},
]


def option_token(expiry: date, strike: float, right: str) -> int:
    return int(f"{expiry:%m%d}{int(strike)}{1 if right == 'CE' else 2}")


def _option(expiry: date, strike: float, right: str, lot: int = 65) -> dict:
    return {"instrument_token": option_token(expiry, strike, right),
            "tradingsymbol": f"NIFTY{expiry:%y%b}{int(strike)}{right}".upper(),
            "name": "NIFTY", "segment": "NFO-OPT", "instrument_type": right, "expiry": expiry,
            "strike": float(strike), "lot_size": lot, "tick_size": 0.05}


def _strikes() -> list[int]:
    near = list(range(24500, 26001, 50))                     # 50-point steps near the money
    far = list(range(23000, 24500, 100)) + list(range(26100, 27600, 100))
    return sorted(near + far)


def nfo_rows() -> list[dict]:
    rows = [
        {"instrument_token": FUT_TOKEN, "tradingsymbol": "NIFTY26OCTFUT", "name": "NIFTY",
         "segment": "NFO-FUT", "instrument_type": "FUT", "expiry": MONTHLY, "strike": 0.0,
         "lot_size": 65, "tick_size": 0.1},
        {"instrument_token": NEXT_FUT_TOKEN, "tradingsymbol": "NIFTY26NOVFUT", "name": "NIFTY",
         "segment": "NFO-FUT", "instrument_type": "FUT", "expiry": date(2026, 11, 24), "strike": 0.0,
         "lot_size": 65, "tick_size": 0.1},
        # Other indices and expired contracts must be ignored
        {"instrument_token": 7777, "tradingsymbol": "BANKNIFTY26OCTFUT", "name": "BANKNIFTY",
         "segment": "NFO-FUT", "instrument_type": "FUT", "expiry": MONTHLY, "strike": 0.0,
         "lot_size": 30, "tick_size": 0.1},
        _option(EXPIRED, 25300, "CE"),
    ]
    for exp in (WEEKLY, MONTHLY):
        for k in _strikes():
            rows += [_option(exp, k, "CE"), _option(exp, k, "PE")]
    return rows



CAL = NseCalendar()
SESSION_MIN = 375
RECENT_DAYS = 10
R = 0.06
IV = 0.13


def _path(start: float, n: int, drift_day: float, vol_day: float, rng) -> np.ndarray:
    per_min = drift_day / SESSION_MIN
    noise = rng.normal(0, vol_day / np.sqrt(SESSION_MIN), n)
    return start * np.exp(np.cumsum(per_min + noise))


def history_days(n: int = 20) -> list:
    days, d = [], TODAY
    for _ in range(n):
        d = CAL.previous_trading_day(d)
        days.append(d)
    return sorted(days)


def build_market(trend: int = 1, today_minutes: int = 120, oi_flow: int = 1, writing: int = 1,
                 breadth: int = 1, seed: int = 7, spot0: float = 25000.0,
                 drift_day: float = 0.004) -> AgentContext:
    rng = np.random.default_rng(seed)
    nfo = nfo_rows()
    ref = build_reference("NIFTY", NSE_ROWS, nfo, TODAY, spot_price=spot0)
    state = MarketState(TODAY)
    drift = drift_day * trend

    # ── History: spot, future, VIX ──
    # The 10 most recent sessions (and today) come from `rng` exactly as they always have, so the
    # scenarios the tests are built on don't move; the 10 older ones come from a stream of their own.
    days = history_days()
    older, recent = days[:-RECENT_DAYS], days[-RECENT_DAYS:]
    spot_hist, fut_hist, vix_hist = [], [], []

    def session(d, level, oi, gen):
        path = _path(level, SESSION_MIN, drift, 0.006, gen)
        for i, px in enumerate(path):
            ts = at_ist(d, time(9, 15)) + timedelta(minutes=i)
            hi, lo = px * 1.0004, px * 0.9996
            spot_hist.append({"date": ts, "open": px, "high": hi, "low": lo, "close": px, "volume": 0})
            oi *= 1 + 0.00002 * oi_flow
            fut_hist.append({"date": ts, "open": px + 60, "high": hi + 60, "low": lo + 60, "close": px + 60,
                             "volume": int(gen.integers(2000, 5000)), "oi": oi})
            vix_hist.append({"date": ts, "open": 13, "high": 13.1, "low": 12.9, "close": 13.0, "volume": 0})
        return path[-1], oi

    old_rng = np.random.default_rng(seed + 10_000)
    level, oi = spot0 * (1 - drift * len(days)), 11_000_000.0
    for d in older:
        level, oi = session(d, level, oi, old_rng)
    level, oi = spot0 * (1 - drift * len(recent)), 12_000_000.0
    for d in recent:
        level, oi = session(d, level, oi, rng)
    state.load_history(ref.spot_token, spot_hist)
    state.load_history(ref.future_token, fut_hist)
    state.load_history(VIX_TOKEN, vix_hist)
    closes = [*_path(spot0 * 0.93, len(older), 0.002, 0.008, old_rng), *_path(spot0 * 0.95, len(recent), 0.002, 0.008, rng)]
    state.load_daily(ref.spot_token, [{"date": d, "open": 1, "high": 1, "low": 1, "close": c, "volume": 0}
                                      for d, c in zip(days, closes)])

    # ── Today ──
    start = at_ist(TODAY, time(9, 15))
    spot_path = _path(level, today_minutes, drift * 1.5, 0.005, rng)
    constituents = []
    for j, (sym, w) in enumerate(NIFTY_HEAVYWEIGHTS):
        constituents.append(Constituent(sym, w, 500_000 + j, prev_close=1000.0))

    bars, vol_cum, vix_level = [], 0, 13.0
    put_oi = {k: 2_000_000.0 for k in ref.strikes(ref.expiries[0])}
    call_oi = dict(put_oi)
    for i, px in enumerate(spot_path):
        ts = start + timedelta(minutes=i)
        oi *= 1 + 0.0002 * oi_flow
        vol_cum += int(rng.integers(3000, 6000))
        bars.append(_bar(ref.spot_token, ts, px, None, None))
        bars.append(_bar(ref.future_token, ts, px + 60, vol_cum, oi))
        bars.append(_bar(VIX_TOKEN, ts, vix_level, None, None))
        for j, c in enumerate(constituents):
            move = 1 + breadth * 0.00004 * (i + 1) * (1 + j % 3)
            bars.append(_bar(c.token, ts, 1000.0 * move, vol_cum // 10, None))
        t = b76.year_fraction(ts, ref.expiries[0])
        fwd = px * np.exp(R * t)
        atm = ref.atm_strike(px)
        for opt in ref.window(px, 15, 1):
            prem = b76.price(fwd, opt.strike, t, R, IV, opt.right)
            near = abs(opt.strike - atm) <= 3 * ref.strike_step
            book = put_oi if opt.right == "PE" else call_oi
            if near and ((opt.right == "PE") == (writing > 0)):
                book[opt.strike] *= 1.004              # writers adding positions
            spread = max(0.05, prem * 0.004)
            bars.append({**_bar(opt.token, ts, prem, vol_cum // 50, book[opt.strike]),
                         "bid": round(prem - spread / 2, 2), "ask": round(prem + spread / 2, 2)})
    state.add_bars(bars)
    state.load_daily(VIX_TOKEN, [{"date": d, "open": 13, "high": 13, "low": 13, "close": 13.0, "volume": 0}
                                 for d in days])

    now = start + timedelta(minutes=today_minutes, seconds=3)
    return AgentContext("NIFTY", ref, state, now, CAL, vix_token=VIX_TOKEN, constituents=constituents,
                        vix_history=list(np.linspace(10, 25, 252)), r=R)


def _bar(token, ts, px, volume_day, oi):
    return {"instrument_token": token, "ts": ts, "open": px, "high": px * 1.0003, "low": px * 0.9997,
            "close": px, "volume_day": volume_day, "oi": oi, "bid": None, "ask": None,
            "bid_qty": 650, "ask_qty": 650, "ticks": 3}


def save_market(store, ctx: AgentContext, extra_expiries: tuple = (), width: int = 10) -> int:
    """Write the synthetic market into a store as if it had been recorded: the contract list for TODAY,
    every bar the state holds (history and today, with cumulative day volume as live bars carry), and
    bars for options of every other listed expiry near the money, priced off today's spot path. For the
    API and browser tests of pages that read saved data (Option Check)."""
    from options.reference import index_rows

    nfo = nfo_rows() + [_option(e, k, rt) for e in extra_expiries for k in _strikes() for rt in ("CE", "PE")]
    store.save_instruments(TODAY, list(NSE_ROWS) + index_rows(nfo, "NIFTY", TODAY))
    rows, cum = [], {}
    for token, by_ts in ctx.state._rows.items():
        for ts in sorted(by_ts):
            b = by_ts[ts]
            key = (token, ts.date())
            cum[key] = cum.get(key, 0) + int(b.get("volume") or 0)
            rows.append({"instrument_token": token, "ts": ts.to_pydatetime(), "open": b["open"], "high": b["high"],
                         "low": b["low"], "close": b["close"], "volume_day": cum[key] or None, "oi": b.get("oi"),
                         "bid": b.get("bid"), "ask": b.get("ask"), "bid_qty": None, "ask_qty": None, "ticks": 1})
    spot = ctx.state.today(ctx.ref.spot_token, "1min")["close"]
    full = build_reference("NIFTY", NSE_ROWS, nfo, TODAY, spot_price=float(spot.iloc[-1]))
    for exp in full.expiries:
        if exp == ctx.ref.expiries[0]:
            continue                                    # recorded by build_market already
        strikes = full.strikes(exp)
        for ts, px in spot.items():
            t = b76.year_fraction(ts.to_pydatetime(), exp)
            fwd = px * np.exp(R * t)
            i = strikes.index(min(strikes, key=lambda s: abs(s - px)))
            for k in strikes[max(0, i - width): i + width + 1]:
                for right in ("CE", "PE"):
                    opt = full.options.get((exp, k, right))
                    if opt is None:
                        continue
                    prem = b76.price(fwd, k, t, R, IV, right)
                    spread = max(0.05, prem * 0.004)
                    rows.append({**_bar(opt.token, ts.to_pydatetime(), prem, None, 1_500_000.0),
                                 "bid": round(prem - spread / 2, 2), "ask": round(prem + spread / 2, 2)})
    store.write_bars(rows)
    return len(rows)

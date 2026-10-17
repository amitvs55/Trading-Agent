"""Proxy historical backtest (review finding F-01, roadmap R-15).

The live engine can only be replayed over days the recorder saw, which start on 19 Oct 2026.
To test the setups over years instead, this builds a *proxy market* from what the data provider
does keep a long history of, NIFTY 50 spot and India VIX at one minute, and feeds it through
the live engine with the same replay code (options/backtest/replay.py):

- the future is priced at fair value off spot (spot × e^(r·T)), with a flat synthetic volume;
- options are repriced every minute with Black-76 at India VIX as implied volatility (flat smile),
  quoted with a conservative spread (0.3% of premium, at least ₹0.05);
- expiries follow NSE's calendar: weekly on Thursday until 29 Aug 2025, Tuesday from 1 Sep 2025,
  moved to the previous trading day over a holiday; the monthly future is the month's last one.

What the proxy can't know, it holds neutral and the report says so. Option and futures open
interest are constant, so the option-chain and futures-flow pillars read "no signal", the OI-wall
setup (S3) can't fire, and the liquidity filter always passes. There are no constituents, so
breadth is n/a. Results show how the rules behave on real price paths; they are not a record
of trades that could have been made.

    python -m options.backtest.proxy fetch --from 2024-10-01 --to 2026-10-16 --history sqlite:///data/history.db
    python -m options.backtest.proxy run   --from 2024-11-01 --to 2026-10-16 --history sqlite:///data/history.db \
        --out sqlite:///data/backtest.db [--save]
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from options.backtest.replay import HISTORY_DAYS, replay
from options.config import OptionsSettings, settings as default_settings
from options.core.calendar import IST, MARKET_CLOSE, MARKET_OPEN, NseCalendar, at_ist, now_ist
from options.core.schemas import Signal
from options.engine import performance, statistics
from options.quant import black76 as b76
from options.storage import Store, make_engine
from utils.logger import setup_logger

logger = setup_logger("options.proxy")

SPOT_TOKEN, VIX_TOKEN = 256265, 264969          # the history database stores the series under these
TUESDAY_FROM = date(2025, 9, 1)                  # NIFTY weekly expiry moved from Thursday to Tuesday
STEP, TICK = 50.0, 0.05
SPREAD_PCT, MIN_SPREAD = 0.003, 0.05
SYNTH_OI = 5_000_000                             # constant: passes the liquidity filter, says nothing
FUT_VOLUME_PER_MIN = 1_000
STRIKE_PAD = 12                                  # strikes beyond the day's range, each side
RATE = 0.065
NOTES = [
    "Proxy backtest: NIFTY spot and India VIX history; future at fair value; options repriced by Black-76 "
    "at VIX implied volatility with a 0.3% spread.",
    "Open interest is constant, so option-chain and futures-flow read neutral and S3 (OI-wall break) can't fire.",
    "No constituents: breadth is n/a. Volume is flat, so VWAP behaves like a time-weighted average.",
    "Shows how the rules behave on real price paths; it is not a record of trades that could have been made.",
]


def fut_token(expiry: date) -> int:
    return 900_000_000 + int(f"{expiry:%y%m%d}")


def opt_token(expiry: date, strike: float, right: str) -> int:
    return int(f"{1 if right == 'CE' else 2}{expiry:%y%m%d}{int(strike):05d}")


def decode_option(token: int) -> tuple[date, float, str] | None:
    s = str(token)
    if len(s) != 12 or s[0] not in "12":
        return None
    return datetime.strptime(s[1:7], "%y%m%d").date(), float(s[7:]), "CE" if s[0] == "1" else "PE"


def calendar_from_days(days: list[date]) -> NseCalendar:
    """Trading days are the days with data; weekdays without data inside the range are holidays."""
    have = set(days)
    holidays: dict[int, set[date]] = defaultdict(set)
    d, last = min(days), max(days)
    while d <= last:
        if d.weekday() < 5 and d not in have:
            holidays[d.year].add(d)
        holidays.setdefault(d.year, set())
        d += timedelta(days=1)
    return NseCalendar({y: frozenset(v) for y, v in holidays.items()}, complete_years=set(holidays))


class ProxyMarket:
    """Store-shaped source for replay(): instruments_on, recorded_days, bars_between."""

    def __init__(self, history: Store, lot_size: int = 65, rate: float = RATE):
        self.history = history
        self.lot_size, self.rate = lot_size, rate
        days = sorted({_aware(b["ts"]).date() for b in history.bars_between(
            datetime(2000, 1, 1, tzinfo=IST), datetime(2100, 1, 1, tzinfo=IST), {SPOT_TOKEN})})
        self.days = days
        self._dayset = set(days)
        self.calendar = calendar_from_days(days) if days else NseCalendar()
        self._day_cache: dict[date, dict] = {}

    # ── Calendar ─────────────────────────────────────────────────────────────

    def recorded_days(self) -> list[date]:
        return list(self.days)

    def _expiry_on_or_before(self, d: date) -> date:
        while not self.calendar.is_trading_day(d):
            d -= timedelta(days=1)
        return d

    def weekly_expiries(self, day: date, n: int = 2) -> list[date]:
        out, d = [], day
        while len(out) < n:
            weekday = 1 if d >= TUESDAY_FROM else 3
            if d.weekday() == weekday:
                exp = self._expiry_on_or_before(d)
                if exp >= day:
                    out.append(exp)
            d += timedelta(days=1)
        return out

    def monthly_expiry(self, year: int, month: int) -> date:
        first_next = date(year + month // 12, month % 12 + 1, 1)
        weekday = 1 if first_next - timedelta(days=1) >= TUESDAY_FROM else 3
        d = first_next - timedelta(days=1)
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return self._expiry_on_or_before(d)

    def futures(self, day: date) -> list[date]:
        this = self.monthly_expiry(day.year, day.month)
        nxt_month = date(day.year + day.month // 12, day.month % 12 + 1, 1)
        nxt = self.monthly_expiry(nxt_month.year, nxt_month.month)
        return [this, nxt] if this >= day else [nxt, self.monthly_expiry(nxt.year + nxt.month // 12, nxt.month % 12 + 1)]

    # ── One day ──────────────────────────────────────────────────────────────

    def _day(self, day: date) -> dict:
        if day in self._day_cache:
            return self._day_cache[day]
        start, end = at_ist(day, MARKET_OPEN), at_ist(day, MARKET_CLOSE)
        bars = [{**b, "ts": _aware(b["ts"])} for b in self.history.bars_between(start, end, {SPOT_TOKEN, VIX_TOKEN})]
        spot = [b for b in bars if b["instrument_token"] == SPOT_TOKEN]
        vix = {b["ts"]: b["close"] for b in bars if b["instrument_token"] == VIX_TOKEN}
        info = {"spot": spot, "vix": vix}
        if spot:
            lo, hi = min(b["low"] for b in spot), max(b["high"] for b in spot)
            k_lo = math.floor(lo / STEP) * STEP - STRIKE_PAD * STEP
            k_hi = math.ceil(hi / STEP) * STEP + STRIKE_PAD * STEP
            info["strikes"] = [k_lo + i * STEP for i in range(int((k_hi - k_lo) / STEP) + 1)]
            info["weeklies"] = self.weekly_expiries(day)
            info["futures"] = self.futures(day)
        if len(self._day_cache) > 64:
            self._day_cache.clear()
        self._day_cache[day] = info
        return info

    def instruments_on(self, day: date) -> list[dict]:
        info = self._day(day)
        if not info["spot"]:
            return []
        rows = [
            {"instrument_token": SPOT_TOKEN, "tradingsymbol": "NIFTY 50", "name": "NIFTY 50", "segment": "INDICES",
             "instrument_type": "EQ", "expiry": None, "strike": 0.0, "lot_size": 0, "tick_size": 0.0},
            {"instrument_token": VIX_TOKEN, "tradingsymbol": "INDIA VIX", "name": "INDIA VIX", "segment": "INDICES",
             "instrument_type": "EQ", "expiry": None, "strike": 0.0, "lot_size": 0, "tick_size": 0.0},
        ]
        for exp in info["futures"]:
            rows.append({"instrument_token": fut_token(exp), "tradingsymbol": f"NIFTY{exp:%y%b}FUT".upper(),
                         "name": "NIFTY", "segment": "NFO-FUT", "instrument_type": "FUT", "expiry": exp,
                         "strike": 0.0, "lot_size": self.lot_size, "tick_size": 0.1})
        for exp in info["weeklies"]:
            for k in info["strikes"]:
                for right in ("CE", "PE"):
                    rows.append({"instrument_token": opt_token(exp, k, right),
                                 "tradingsymbol": f"NIFTY{exp:%y%m%d}{int(k)}{right}", "name": "NIFTY",
                                 "segment": "NFO-OPT", "instrument_type": right, "expiry": exp, "strike": k,
                                 "lot_size": self.lot_size, "tick_size": TICK})
        return rows

    def _vix_at(self, info: dict, ts: datetime, last: float) -> float:
        v = info["vix"].get(ts)
        return float(v) if v else last

    def bars_between(self, start: datetime, end: datetime, tokens: set[int] | None = None) -> list[dict]:
        out: list[dict] = []
        d = start.astimezone(IST).date()
        while at_ist(d, time(0)) < end:
            if d in self._dayset:
                out += self._bars_for_day(d, start, end, tokens)
            d += timedelta(days=1)
        return sorted(out, key=lambda b: (b["ts"], b["instrument_token"]))

    def _bars_for_day(self, day: date, start: datetime, end: datetime, tokens: set[int] | None) -> list[dict]:
        info = self._day(day)
        spot = [b for b in info["spot"] if start <= b["ts"] < end]
        if not spot:
            return []
        want = (lambda t: True) if tokens is None else (lambda t: t in tokens)
        out = []
        vix_last, vol_cum = 15.0, 0
        fut_tokens = {fut_token(e): e for e in info["futures"]}
        extra_futs = {t: e for t in (tokens or ()) if 900_000_000 <= t < 1_000_000_000
                      for e in [datetime.strptime(str(t - 900_000_000).zfill(6), "%y%m%d").date()]}
        fut_tokens.update(extra_futs)
        opts = [(opt_token(e, k, r), e, k, r) for e in info["weeklies"] for k in info["strikes"] for r in ("CE", "PE")]
        for b in spot:
            ts = b["ts"]
            vix_last = self._vix_at(info, ts, vix_last)
            vol_cum += FUT_VOLUME_PER_MIN
            if want(SPOT_TOKEN):
                out.append({**_row(SPOT_TOKEN, ts, b["open"], b["high"], b["low"], b["close"])})
            if want(VIX_TOKEN) and ts in info["vix"]:
                out.append(_row(VIX_TOKEN, ts, vix_last, vix_last, vix_last, vix_last))
            for tok, exp in fut_tokens.items():
                if want(tok):
                    carry = math.exp(self.rate * b76.year_fraction(ts, exp))
                    out.append({**_row(tok, ts, b["open"] * carry, b["high"] * carry, b["low"] * carry, b["close"] * carry),
                                "volume_day": vol_cum, "oi": SYNTH_OI})
            sigma = max(vix_last, 5.0) / 100
            for tok, exp, k, right in opts:
                if not want(tok) or exp < day:
                    continue
                t = b76.year_fraction(ts, exp)
                fwd = b["close"] * math.exp(self.rate * t)
                mid = max(b76.price(fwd, k, t, self.rate, sigma, right), TICK)
                half = max(MIN_SPREAD, mid * SPREAD_PCT) / 2
                bid, ask = max(TICK, _tick(mid - half)), _tick(mid + half)
                out.append({**_row(tok, ts, mid, mid, mid, mid), "bid": bid, "ask": ask, "bid_qty": 1950,
                            "ask_qty": 1950, "oi": SYNTH_OI, "volume_day": None})
        return out


def _aware(ts: datetime) -> datetime:
    return ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)


def _tick(x: float) -> float:
    return round(round(x / TICK) * TICK, 2)


def _row(token: int, ts: datetime, o: float, h: float, low: float, c: float) -> dict:
    return {"instrument_token": token, "ts": ts, "open": float(o), "high": float(h), "low": float(low),
            "close": float(c), "volume_day": None, "oi": None, "bid": None, "ask": None, "bid_qty": None,
            "ask_qty": None, "ticks": 1}


# ── Report ───────────────────────────────────────────────────────────────────

def report(signals: list[Signal], market: ProxyMarket, start: date, end: date) -> dict:
    """Per-setup uncertainty, month by month, first half against second half, and NIFTY over the span."""
    traded = sorted(performance.traded(signals), key=lambda s: s.closed_at)
    monthly: dict[str, list[Signal]] = defaultdict(list)
    for s in traded:
        monthly[f"{s.closed_at:%Y-%m}"].append(s)
    half = len(traded) // 2
    days = [d for d in market.days if start <= d <= end]
    first_close = market._day(days[0])["spot"][0]["open"] if days and market._day(days[0])["spot"] else None
    last_close = market._day(days[-1])["spot"][-1]["close"] if days and market._day(days[-1])["spot"] else None
    return {
        "kind": "proxy", "generated_at": now_ist().isoformat(timespec="seconds"),
        "from": start.isoformat(), "to": end.isoformat(), "days": len(days), "signals": len(signals),
        "overall": performance.stats(signals),
        "evidence": statistics.record_stats(signals),
        "by_setup": performance.by(signals, "setup"),
        "evidence_by_setup": statistics.setup_report(signals),
        "monthly": {m: performance.stats(v) for m, v in sorted(monthly.items())},
        "stability": {"first_half": statistics.record_stats(traded[:half]),
                      "second_half": statistics.record_stats(traded[half:])},
        "benchmark": ({"index": "NIFTY 50", "return_pct": (last_close / first_close - 1) * 100}
                      if first_close and last_close else None),
        "notes": NOTES,
    }


def run(history: Store, target: Store, start: date, end: date, cfg: OptionsSettings | None = None,
        lot_size: int = 65, setups=None) -> dict:
    cfg = cfg or OptionsSettings(OPTIONS_INDICES=["NIFTY"], OPTIONS_LIVE_SETUPS=[])
    market = ProxyMarket(history, lot_size=lot_size)
    warm = [d for d in market.days if d < start]
    if len(warm) < HISTORY_DAYS:
        logger.warning("Only %d days of history before %s; indicators need %d to warm up", len(warm), start, HISTORY_DAYS)
    replay(market, target, start, end, cfg, market.calendar, setups=setups)
    signals = target.signals_since(at_ist(start, time(0)), at_ist(end, time(0)) + timedelta(days=1))
    return report(signals, market, start, end)


# ── Fetching the history (needs the Angel One credentials saved on the Connectors page) ─────

def fetch(history: Store, start: date, end: date, broker=None) -> dict:
    """NIFTY 50 and India VIX one-minute candles from the data provider, into the history database."""
    from options.reference import VIX_SYMBOL, find_token
    from options.session import history_rows

    if broker is None:
        from options.admin.connectors import load_effective_settings
        from options.brokers import make_broker
        broker = make_broker(load_effective_settings())
        if getattr(broker, "auto_login", False):
            broker.login()
    nse = broker.instruments("NSE")
    counts = {}
    for label, symbol, token in (("NIFTY 50", "NIFTY 50", SPOT_TOKEN), ("India VIX", VIX_SYMBOL, VIX_TOKEN)):
        source_token = find_token(nse, symbol)
        candles = broker.historical(source_token, at_ist(start, MARKET_OPEN), at_ist(end, MARKET_CLOSE), "minute")
        rows = history_rows(token, candles)
        history.insert_bars_if_missing(rows)
        counts[label] = len(rows)
        logger.info("%s: %d one-minute bars", label, len(rows))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Proxy historical backtest of the live signal engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "run"):
        p = sub.add_parser(name)
        p.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
        p.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
        p.add_argument("--history", required=True, help="database for the NIFTY/VIX history (separate from live)")
    run_p = sub.choices["run"]
    run_p.add_argument("--out", required=True, help="separate database for the backtest's signals")
    run_p.add_argument("--lot", type=int, default=65)
    run_p.add_argument("--save", action="store_true", help="store the report for the Performance page")
    args = ap.parse_args(argv)

    if args.history == default_settings.DATABASE_URL:
        print("--history must be its own database, not the live one", file=sys.stderr)
        return 2
    history = Store(make_engine(args.history))
    if args.cmd == "fetch":
        print(json.dumps(fetch(history, args.start, args.end), indent=2))
        return 0
    if args.out in (args.history, default_settings.DATABASE_URL):
        print("--out must be a separate database so backtest signals never mix with the live record", file=sys.stderr)
        return 2
    rep = run(history, Store(make_engine(args.out)), args.start, args.end, lot_size=args.lot)
    print(json.dumps({k: rep[k] for k in ("from", "to", "days", "signals", "overall")}, indent=2, default=str))
    for setup, st in rep["by_setup"].items():
        print(f"  {setup}: {performance.summary_line(st)}")
    if args.save:
        live = Store(make_engine(default_settings.DATABASE_URL))
        live.set_meta_json("backtest_report", rep, now_ist())
        print("Saved for the Performance page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

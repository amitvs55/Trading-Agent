"""How past checks turned out, so the checker earns (or loses) trust with a real record.

Measured from the saved 1-minute bars once each moment has passed: the contract's price 30 minutes
after a check made during market hours, and at the end of the check's horizon. A horizon that runs
to expiry is settled at intrinsic value from NIFTY's last close that day (≈ the exchange settlement).
P&L uses the check's own entry, size and charges. A followed paper trade is settled the same way.

The record then compares what the checker said with what happened: per verdict, how often the trade
made money, and whether its "chance of profit" was calibrated.
"""

from datetime import date, datetime, time, timedelta

from options.core.calendar import IST, at_ist
from options.engine.costs import charges

AFTER = timedelta(minutes=30)
BINS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]


def _pnl(entry: float, exit_: float, units: int) -> float:
    return (exit_ - entry) * units - charges(entry * units, max(exit_, 0) * units, 2).total


def _price_at(store, token: int, at: datetime, not_before: datetime) -> float | None:
    rows = store.bars_between(not_before, at + timedelta(minutes=1), {token})
    return float(rows[-1]["close"]) if rows else None


def settlement(store, spot_token: int, expiry: date, strike: float, right: str) -> float | None:
    rows = store.bars_between(at_ist(expiry, time(15, 0)), at_ist(expiry, time(15, 31)), {spot_token})
    if not rows:
        return None
    spot = float(rows[-1]["close"])
    return max(spot - strike, 0.0) if right == "CE" else max(strike - spot, 0.0)


def evaluate(check: dict, store, now: datetime) -> tuple[dict, bool]:
    """(outcome, finished) for one check; only moments that have passed are filled in."""
    summ = check.get("summary") or {}
    out = dict(check.get("outcome") or {})
    entry, units, token = summ.get("entry"), summ.get("units"), check.get("token")
    if not entry or not units or not token:
        return out, True
    created = check["created_at"] if check["created_at"].tzinfo else check["created_at"].replace(tzinfo=IST)
    end = datetime.fromisoformat(summ["horizon_end"]) if summ.get("horizon_end") else None
    start = datetime.fromisoformat(summ["horizon_start"]) if summ.get("horizon_start") else created

    if "after_30m" not in out and summ.get("market_open") and now >= created + AFTER + timedelta(minutes=2):
        px = _price_at(store, token, created + AFTER, created)
        out["after_30m"] = {"price": px, "pnl": round(_pnl(entry, px, units), 0) if px is not None else None}
    if "at_exit" not in out and end is not None and now >= end + timedelta(minutes=2):
        if summ.get("settles"):
            px = settlement(store, summ.get("spot_token"), check["expiry"], check["strike"], check["option_right"])
        else:
            px = _price_at(store, token, end, start)
        out["at_exit"] = {"price": px, "pnl": round(_pnl(entry, px, units), 0) if px is not None else None,
                          "at": end.isoformat()}
    finished = "at_exit" in out and ("after_30m" in out or not summ.get("market_open"))
    return out, finished


def settle_paper(check: dict, store, now: datetime) -> dict | None:
    """A paper trade still open after its expiry is closed at the settlement value."""
    if not check.get("paper") or check.get("paper_closed_at") or not check.get("expiry"):
        return None
    settle_at = at_ist(check["expiry"], time(15, 30))
    if now < settle_at + timedelta(minutes=2):
        return None
    px = settlement(store, (check.get("summary") or {}).get("spot_token"), check["expiry"], check["strike"],
                    check["option_right"])
    return None if px is None else {"paper_exit": px, "paper_closed_at": settle_at}


def record(checks: list[dict]) -> dict:
    """The checker's track record from finished checks: per verdict, and calibration of its odds."""
    scored = [c for c in checks if ((c.get("outcome") or {}).get("at_exit") or {}).get("pnl") is not None]
    by: dict[str, dict] = {}
    for c in scored:
        v = (c.get("summary") or {}).get("verdict", "?")
        pnl = c["outcome"]["at_exit"]["pnl"]
        used = (c.get("summary") or {}).get("capital_used") or 0
        b = by.setdefault(v, {"verdict": v, "checks": 0, "made_money": 0, "pnl_pct": []})
        b["checks"] += 1
        b["made_money"] += pnl > 0
        if used:
            b["pnl_pct"].append(pnl / used * 100)
    verdicts = [{"verdict": b["verdict"], "checks": b["checks"], "made_money_rate": b["made_money"] / b["checks"],
                 "avg_pnl_pct": (sum(b["pnl_pct"]) / len(b["pnl_pct"])) if b["pnl_pct"] else None}
                for b in by.values()]
    calib = []
    for lo, hi in BINS:
        inside = [c for c in scored if (p := (c.get("summary") or {}).get("p_profit")) is not None and lo <= p < hi]
        if inside:
            calib.append({"from": lo, "to": min(hi, 1.0), "checks": len(inside),
                          "said": sum(c["summary"]["p_profit"] for c in inside) / len(inside),
                          "happened": sum(c["outcome"]["at_exit"]["pnl"] > 0 for c in inside) / len(inside)})
    return {"checks": len(checks), "scored": len(scored), "verdicts": sorted(verdicts, key=lambda v: v["verdict"]),
            "calibration": calib, "enough": len(scored) >= 30}

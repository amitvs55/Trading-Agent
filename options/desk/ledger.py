"""One user's desk account, rebuilt from their filled orders: funds, positions, trades and P&L.

Average-price accounting, as Indian brokers show it: buys add to a position at their average price;
a sell realises (sell price − average) × qty, less the sell's own charges and the matching share of
the buys' charges. Open positions are marked at the last traded price, like a broker's positions
page. Nothing is stored: every read rebuilds the account from the orders, so it can't drift.
"""

from datetime import datetime

from options.core.calendar import IST
from options.desk.rules import ACTIVE, PRODUCTS, Quote

CHARGE_PARTS = ("brokerage", "stt", "exchange", "sebi", "stamp", "gst")
EXIT_LABELS = {"exit": "You exited", "ticket": "You sold", "squareoff": "Auto square-off 15:20",
               "expiry": "Settled at expiry"}


def _ts(v: datetime | None) -> str | None:
    return v.astimezone(IST).isoformat() if v else None


def _zero() -> dict:
    return {k: 0.0 for k in CHARGE_PARTS}


def _add(into: dict, parts: dict | None, share: float = 1.0) -> None:
    for k in CHARGE_PARTS:
        into[k] += float((parts or {}).get(k) or 0.0) * share


def _exit_label(source: str | None) -> str:
    if source and source.startswith("signal:"):
        return "You sold"
    return EXIT_LABELS.get(source or "", "You sold")


def book(account: dict, orders: list[dict], marks: dict[int, Quote], now: datetime) -> dict:
    """The whole account as of `now`. `marks` maps instrument tokens to their latest quote."""
    today = now.astimezone(IST).date()
    start = float(account["funds"]) + float(account.get("added") or 0.0)
    filled = sorted((o for o in orders if o["status"] == "FILLED" and o.get("filled_at")),
                    key=lambda o: (o["filled_at"], o["id"]))

    cash, realised = start, 0.0
    positions: dict[tuple[int, str], dict] = {}
    trades, curve = [], [{"t": _ts(account["started_at"]), "balance": round(start, 2)}]
    paid, paid_total = _zero(), 0.0
    for o in filled:
        key = (int(o["token"]), o["product"])
        qty, px = int(o["qty"]), float(o["fill_price"])
        value = px * qty
        ch = o.get("charges") or {}
        fee = float(ch.get("total") or 0.0)
        _add(paid, ch)
        paid_total += fee
        p = positions.setdefault(key, {
            "symbol": o["symbol"], "token": int(o["token"]), "product": o["product"], "index_name": o.get("index_name"),
            "expiry": o["expiry"].isoformat() if o.get("expiry") else None, "strike": o.get("strike"),
            "right": o.get("option_right"), "lot_size": int(o["lot_size"]), "qty": 0, "cost": 0.0,
            "open_charges": 0.0, "open_parts": _zero(), "opened_at": None, "bought": 0, "sold": 0,
            "buy_value": 0.0, "sell_value": 0.0, "realised": 0.0, "realised_today": 0.0, "last_at": None})
        p["last_at"] = o["filled_at"]
        if o["side"] == "BUY":
            cash -= value + fee
            if p["qty"] == 0:
                p["opened_at"] = o["filled_at"]
            p["qty"] += qty
            p["cost"] += value
            p["open_charges"] += fee
            _add(p["open_parts"], ch)
            p["bought"] += qty
            p["buy_value"] += value
            continue
        # A sell closes part or all of the position at its average price
        cash += value - fee
        held = p["qty"] or qty
        share = qty / held
        avg = p["cost"] / held if p["qty"] else px
        cost, buy_fee = avg * qty, p["open_charges"] * share
        parts = _zero()
        _add(parts, ch)
        _add(parts, p["open_parts"], share)
        for k in CHARGE_PARTS:
            p["open_parts"][k] -= p["open_parts"][k] * share
        net = round(value - cost - fee - buy_fee, 2)
        realised += net
        p["qty"] -= qty
        p["cost"] -= cost
        p["open_charges"] -= buy_fee
        p["sold"] += qty
        p["sell_value"] += value
        p["realised"] += net
        if o["filled_at"].astimezone(IST).date() == today:
            p["realised_today"] += net
        trades.append({
            "id": o["id"], "symbol": o["symbol"], "token": int(o["token"]), "product": o["product"],
            "qty": qty, "lots": qty // int(o["lot_size"]), "entry": round(avg, 2), "exit": px,
            "entry_at": _ts(p["opened_at"]), "exit_at": _ts(o["filled_at"]), "reason": _exit_label(o.get("source")),
            "source": o.get("source"), "gross": round(value - cost, 2), "charges": round(fee + buy_fee, 2),
            "charges_detail": {k: round(v, 2) for k, v in parts.items()}, "net": net,
            "net_pct": round(net / cost * 100, 2) if cost else None})
        curve.append({"t": _ts(o["filled_at"]), "balance": round(start + realised, 2), "id": o["id"]})
        if p["qty"] == 0:
            p["cost"], p["open_charges"], p["opened_at"] = 0.0, 0.0, None
            p["open_parts"] = _zero()

    rows, unrealised, value_now, invested = [], 0.0, 0.0, 0.0
    for p in positions.values():
        if p["qty"] == 0 and (p["last_at"] is None or p["last_at"].astimezone(IST).date() != today):
            continue                                     # closed before today: in the trades, not the positions
        q = marks.get(p["token"])
        avg = p["cost"] / p["qty"] if p["qty"] else None
        ltp = q.ltp if q and q.ltp else None
        pnl = (ltp - avg) * p["qty"] if p["qty"] and ltp and avg is not None else None
        if p["qty"]:
            invested += p["cost"]
            value_now += (ltp or avg) * p["qty"]
            unrealised += pnl or 0.0
        rows.append({
            "symbol": p["symbol"], "token": p["token"], "product": p["product"], "product_label": PRODUCTS[p["product"]],
            "index_name": p["index_name"], "expiry": p["expiry"], "strike": p["strike"], "right": p["right"],
            "lot_size": p["lot_size"], "qty": p["qty"], "lots": p["qty"] // p["lot_size"],
            "avg": round(avg, 2) if avg is not None else None, "invested": round(p["cost"], 2),
            "ltp": ltp, "bid": q.bid if q else None, "ask": q.ask if q else None, "mark_source": q.source if q else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl / p["cost"] * 100, 2) if pnl is not None and p["cost"] else None,
            "buy_charges": round(p["open_charges"], 2), "realised": round(p["realised"], 2),
            "realised_today": round(p["realised_today"], 2), "bought": p["bought"], "sold": p["sold"],
            "avg_buy": round(p["buy_value"] / p["bought"], 2) if p["bought"] else None,
            "avg_sell": round(p["sell_value"] / p["sold"], 2) if p["sold"] else None,
            "opened_at": _ts(p["opened_at"]), "open": p["qty"] > 0})

    blocked = sum(float(o.get("block") or 0.0) for o in orders if o["status"] in ACTIVE and o["side"] == "BUY")
    equity = cash + value_now
    wins = [t for t in trades if t["net"] > 0]
    realised_today = sum(t["net"] for t in trades if t["exit_at"] and datetime.fromisoformat(t["exit_at"]).date() == today)
    charges_today = sum(float((o.get("charges") or {}).get("total") or 0.0) for o in filled
                        if o["filled_at"].astimezone(IST).date() == today)
    peak, max_dd = start, 0.0
    for point in curve:
        peak = max(peak, point["balance"])
        max_dd = max(max_dd, peak - point["balance"])
    by_day: dict[str, dict] = {}
    for t in trades:
        d = by_day.setdefault(t["exit_at"][:10], {"day": t["exit_at"][:10], "trades": 0, "net": 0.0, "charges": 0.0})
        d["trades"] += 1
        d["net"] = round(d["net"] + t["net"], 2)
        d["charges"] = round(d["charges"] + t["charges"], 2)

    return {
        "account": {"funds": float(account["funds"]), "added": float(account.get("added") or 0.0),
                    "started_at": _ts(account["started_at"]), "epoch": int(account["epoch"])},
        "funds": {"start": round(start, 2), "cash": round(cash, 2), "blocked": round(blocked, 2),
                  "available": round(cash - blocked, 2), "invested": round(invested, 2), "value": round(value_now, 2),
                  "equity": round(equity, 2), "total_pnl": round(equity - start, 2),
                  "return_pct": round((equity - start) / start * 100, 2) if start else None},
        "today": {"realised": round(realised_today, 2), "unrealised": round(unrealised, 2),
                  "pnl": round(realised_today + unrealised, 2), "charges": round(charges_today, 2)},
        "stats": {"trades": len(trades), "wins": len(wins), "win_rate": len(wins) / len(trades) if trades else None,
                  "realised": round(realised, 2), "best": max((t["net"] for t in trades), default=None),
                  "worst": min((t["net"] for t in trades), default=None), "max_drawdown": round(max_dd, 2),
                  "charges_paid": round(paid_total, 2), "charges_detail": {k: round(v, 2) for k, v in paid.items()}},
        "positions": sorted(rows, key=lambda r: (not r["open"], r["opened_at"] or "", r["symbol"])),
        "trades": sorted(trades, key=lambda t: t["exit_at"] or "", reverse=True),
        "days": sorted(by_day.values(), key=lambda d: d["day"], reverse=True),
        "curve": curve,
        "as_of": now.astimezone(IST).isoformat(timespec="seconds"),
    }


def holdings(orders: list[dict]) -> dict[tuple[int, str], int]:
    """Units held per (token, product) from the filled orders."""
    held: dict[tuple[int, str], int] = {}
    for o in orders:
        if o["status"] == "FILLED":
            key = (int(o["token"]), o["product"])
            held[key] = held.get(key, 0) + (int(o["qty"]) if o["side"] == "BUY" else -int(o["qty"]))
    return held


def selling(orders: list[dict]) -> dict[tuple[int, str], int]:
    """Units already in working sell orders per (token, product)."""
    out: dict[tuple[int, str], int] = {}
    for o in orders:
        if o["status"] in ACTIVE and o["side"] == "SELL":
            key = (int(o["token"]), o["product"])
            out[key] = out.get(key, 0) + int(o["qty"])
    return out

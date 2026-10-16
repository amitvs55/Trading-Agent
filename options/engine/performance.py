"""Track-record statistics from closed signals (losses count exactly like wins)."""

from collections import defaultdict

from options.core.schemas import Signal, SignalState


def traded(signals: list[Signal]) -> list[Signal]:
    """Closed signals that were actually entered (expired/cancelled ones never filled)."""
    return [s for s in signals if s.state is SignalState.CLOSED and s.pnl_rupees is not None]


def stats(signals: list[Signal]) -> dict:
    done = traded(signals)
    n = len(done)
    if not n:
        return {"trades": 0, "wins": 0, "win_rate": None, "avg_r": None, "expectancy_rupees": None,
                "total_rupees": 0.0, "max_drawdown_rupees": 0.0, "profit_factor": None}
    wins = [s for s in done if s.pnl_rupees > 0]
    gross_win = sum(s.pnl_rupees for s in wins)
    gross_loss = -sum(s.pnl_rupees for s in done if s.pnl_rupees <= 0)
    rs = [s.r_multiple for s in done if s.r_multiple is not None]
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for s in sorted(done, key=lambda s: s.closed_at):
        equity += s.pnl_rupees
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    total = sum(s.pnl_rupees for s in done)
    return {
        "trades": n,
        "wins": len(wins),
        "win_rate": len(wins) / n,
        "avg_r": sum(rs) / len(rs) if rs else None,
        "expectancy_rupees": total / n,
        "total_rupees": total,
        "max_drawdown_rupees": max_dd,
        "profit_factor": gross_win / gross_loss if gross_loss else None,
    }


def by(signals: list[Signal], key: str) -> dict[str, dict]:
    groups: dict[str, list[Signal]] = defaultdict(list)
    for s in signals:
        value = getattr(s, key)
        groups[getattr(value, "value", value)].append(s)
    return {k: stats(v) for k, v in sorted(groups.items())}


def summary_line(st: dict) -> str:
    if not st["trades"]:
        return "no completed trades yet"
    avg_r = f" · avg {st['avg_r']:+.2f}R" if st["avg_r"] is not None else ""
    return f"{st['trades']} trades · {st['win_rate'] * 100:.0f}% wins{avg_r} · ₹{st['total_rupees']:+,.0f}"

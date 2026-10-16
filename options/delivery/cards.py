"""Telegram messages: signal cards, follow-ups, morning brief and end-of-day report (plan §3)."""

from collections import Counter
from datetime import date
from html import escape

from options.core.schemas import STATUS_ICON, Action, PillarCheck, Signal
from options.setups import SETUP_LABELS

PILLAR_NAMES = {"trend": "Trend", "trigger": "Trigger", "levels": "Levels", "momentum": "Momentum",
                "futures_flow": "Fut flow", "option_chain": "Chain", "volatility": "Volatility",
                "option_quality": "Option", "breadth": "Breadth", "macro": "Macro", "events": "Events",
                "news": "News", "timing": "Timing"}

UPDATE_ICONS = {"ENTRY_FILLED": "▶️", "T1_HIT": "🎯", "T2_HIT": "🏁", "SL_HIT": "🔴", "TRAIL_STOP": "🟠",
                "INVALIDATED": "🔴", "TIME_STOP": "⏱️", "SQUARE_OFF": "⏱️", "EXPIRED": "⌛", "CANCELLED": "✖️",
                "EXIT_SIGNAL": "🔁", "EVENT_EXIT": "📅", "KILL": "🛑"}


def _rupees(x: float) -> str:
    return f"₹{x:,.0f}"


def checks_block(checks: list[PillarCheck]) -> str:
    counts = Counter(c.status for c in checks)
    head = " ".join(f"{counts[s]}{STATUS_ICON[s]}" for s in ("pass", "warn", "fail", "na") if counts[s])
    lines = [f"{STATUS_ICON[c.status]} <b>{PILLAR_NAMES.get(c.pillar, c.pillar)}</b> {escape(c.detail)}" for c in checks]
    return f"<b>Analysis</b> {head}\n" + "\n".join(lines)


def signal_card(sig: Signal, capital: float, setup_stats: str | None = None) -> str:
    c = sig.contract
    buy = sig.action is Action.BUY_CE
    head = (f"{'🟢' if buy else '🔴'} <b>{'BUY CE' if buy else 'BUY PE'} · {escape(sig.index)}</b> · "
            f"Grade {sig.grade.value} ({sig.score:.0f}/100) · {escape(SETUP_LABELS.get(sig.setup, sig.setup))}")
    mode = "\n<i>SHADOW TEST: tracked automatically, not for trading yet</i>" if sig.mode == "SHADOW" else ""
    t1_note = "book half" if sig.lots >= 2 else "lock half the gain"
    rr1 = (sig.t1 - sig.entry_high) / (sig.entry_high - sig.stop_loss)
    rr2 = (sig.t2 - sig.entry_high) / (sig.entry_high - sig.stop_loss)
    hold = (f"Time stop {sig.time_stop:%H:%M}" if sig.horizon == "intraday"
            else f"Hold until {sig.exit_by:%d %b} 15:15 at most")
    body = "\n".join([
        f"{c.tradingsymbol}  ({c.expiry:%d %b}, lot {c.lot_size})",
        f"Entry  {sig.entry_low:.2f}–{sig.entry_high:.2f} limit · valid till {sig.valid_until:%H:%M}",
        f"SL     {sig.stop_loss:.2f}  or {sig.invalidation_rule}",
        f"T1     {sig.t1:.2f} ({t1_note})   T2 {sig.t2:.2f}",
        f"R:R    1 : {rr1:.1f} / 1 : {rr2:.1f}   {hold}",
        f"Size   {sig.lots} lot = {_rupees(sig.risk_rupees)} risk ({sig.risk_rupees / capital * 100:.1f}% of capital)",
        f"ID     {sig.signal_id}",
    ])
    stats = f"\n<i>{escape(SETUP_LABELS.get(sig.setup, sig.setup))} history: {escape(setup_stats)}</i>" if setup_stats else ""
    return f"{head}{mode}\n<pre>{escape(body)}</pre>\n{checks_block(sig.checks)}{stats}"


def update_message(sig: Signal, kind: str, message: str) -> str:
    icon = UPDATE_ICONS.get(kind, "🔄")
    return f"{icon} <b>{escape(sig.signal_id)}</b> {escape(sig.contract.tradingsymbol)}: {escape(message)}"


def morning_brief(today: date, sections: list[dict]) -> str:
    """sections: one dict per index with keys title, lines (list[str])."""
    parts = [f"🌅 <b>Morning brief · {today:%a %d %b %Y}</b>"]
    for sec in sections:
        parts.append(f"\n<b>{escape(sec['title'])}</b>\n" + "\n".join(f"• {escape(x)}" for x in sec["lines"]))
    parts.append("\n<i>Signals start after 09:30 on a 5-minute close. NO TRADE is a valid outcome.</i>")
    return "\n".join(parts)


def eod_report(today: date, todays: list[Signal], overall: str, by_setup: dict[str, str],
               tomorrow_levels: list[str]) -> str:
    lines = [f"📊 <b>End of day · {today:%a %d %b %Y}</b>"]
    if not todays:
        lines.append("No signals today: no setup met every rule.")
    for s in todays:
        result = (f"₹{s.pnl_rupees:+,.0f} ({s.r_multiple:+.2f}R)" if s.pnl_rupees is not None
                  else s.exit_reason or s.state.value)
        lines.append(f"• {escape(s.signal_id)} {'CE' if s.action is Action.BUY_CE else 'PE'} "
                     f"{escape(s.contract.tradingsymbol)} [{s.mode}] → {escape(result)}")
    lines.append(f"\n<b>Track record</b>: {escape(overall)}")
    for setup, line in by_setup.items():
        lines.append(f"• {escape(SETUP_LABELS.get(setup, setup))}: {escape(line)}")
    if tomorrow_levels:
        lines.append("\n<b>Tomorrow's levels</b>\n" + "\n".join(f"• {escape(x)}" for x in tomorrow_levels))
    return "\n".join(lines)

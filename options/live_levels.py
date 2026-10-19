"""Off-hours levels for the dashboard ticker: the last session's close and change.

The session saves the closing levels itself at 15:36. When the recorder starts outside a session
(a deploy in the evening, a restart on a holiday) and nothing is saved for the last session yet,
the supervisor runs this once (as part of `python -m options.offhours`).

Out of market hours a quote describes the last session, and its last price minus its net change is
that session's previous close, so the ticker shows the right close, points and % ("Closed · 15:30").
Between 09:00 and 15:31 it does nothing: the pre-open and the live session belong to options.session.
"""

import sys
from datetime import date, datetime, time

from options.core.calendar import NseCalendar, now_ist
from options.market_data.live import LiveIndexFeed, market_window
from utils.logger import setup_logger

logger = setup_logger("options.live_levels")

QUIET_FROM, QUIET_UNTIL = time(9, 0), time(15, 31)


def due(store, calendar: NseCalendar, now: datetime) -> date | None:
    """The last session to save levels for, or None if they are saved already or a session owns it."""
    if calendar.is_trading_day(now.date()) and QUIET_FROM <= now.time() < QUIET_UNTIL:
        return None
    last = date.fromisoformat(market_window(calendar, now)["last_session"])
    snap = store.live_snapshot() or {}
    if snap.get("session") == last.isoformat() and all(i.get("ltp") and i.get("prev_close") for i in snap.get("items", [])):
        return None
    return last


def publish_closing_levels(store, broker, calendar: NseCalendar, now: datetime) -> bool:
    last = due(store, calendar, now)
    if last is None:
        return False
    tokens = broker.live_index_tokens()
    quotes = broker.quotes(tokens)
    feed = LiveIndexFeed(store, tokens, last, now_fn=lambda: now)
    for sym, q in quotes.items():
        ltp, change = q.get("ltp"), q.get("net_change")
        feed.set_prev_close(sym, round(ltp - change, 2) if ltp and change is not None else q.get("close"), "quote")
    feed.close_out(quotes, now)                    # stamped when taken: never older than a level already shown
    logger.info("Saved the %s closing levels: %s", last,
                ", ".join(f"{s} {q.get('ltp')}" for s, q in quotes.items()))
    return True


def main() -> int:
    from options.offhours import main as run
    return run()                                     # one login for all the evening jobs


if __name__ == "__main__":
    sys.exit(main())

"""Evening and holiday jobs for the recorder, with one Angel login:

1. the last session's closing NIFTY 50 / SENSEX for the dashboard ticker (options/live_levels.py),
   if they aren't saved yet;
2. topping up two years of NIFTY spot and India VIX minutes for the Option Check history view
   (options/history_backfill.py), at most once a day.

    python -m options.offhours

The supervisor runs it when it starts outside a session and each evening after the close. Between
09:00 and 15:31 on a trading day it does nothing.
"""

import sys
from datetime import time

from options.core.calendar import now_ist
from utils.logger import setup_logger

logger = setup_logger("options.offhours")

QUIET_FROM, QUIET_UNTIL = time(9, 0), time(15, 31)


def main() -> int:
    from options import history_backfill, live_levels
    from options.admin.connectors import load_effective_settings
    from options.brokers import make_broker
    from options.brokers.angel import INDEX_TOKENS, brief_error
    from options.session import load_calendar
    from options.storage import Store, make_engine

    now = now_ist()
    cfg = load_effective_settings()
    store = Store(make_engine(cfg.DATABASE_URL))
    calendar = load_calendar(store)
    if calendar.is_trading_day(now.date()) and QUIET_FROM <= now.time() < QUIET_UNTIL:
        return 0
    levels_due = live_levels.due(store, calendar, now) is not None
    done = store.get_meta_json(history_backfill.META_KEY) or {}
    backfill_due = str(done.get("at", ""))[:10] != now.date().isoformat()
    if not (levels_due or backfill_due) or cfg.missing_provider_keys():
        return 0
    broker = make_broker(cfg)
    if not getattr(broker, "auto_login", False):
        return 0                                    # Kite needs the person's daily login
    try:
        broker.login()
    except Exception as e:
        logger.warning("Off-hours jobs skipped, login failed: %s", brief_error(e))
        return 0
    if levels_due and hasattr(broker, "quotes"):
        try:
            live_levels.publish_closing_levels(store, broker, calendar, now)
        except Exception as e:
            logger.warning("Closing levels not saved: %s", brief_error(e))
    if backfill_due:
        try:
            history_backfill.backfill(store, broker, {"NIFTY 50": INDEX_TOKENS["NIFTY 50"],
                                                      "INDIA VIX": INDEX_TOKENS["INDIA VIX"]}, calendar, now)
        except Exception as e:
            logger.warning("History backfill stopped: %s", brief_error(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())

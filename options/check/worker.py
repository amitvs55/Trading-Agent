"""Answers Option Check requests inside the recorder, from the live engine.

The API saves a request as a pending row and NOTIFYs `option_check`; the recorder's main loop wakes
at once and calls `maybe()`, which runs on the main thread (the market state is not thread-safe):
it starts recording the contract (for live P&L and a later outcome), takes the broker's quote, runs
every agent for a fresh snapshot and saves the market facts. The API turns them into the report.
"""

from datetime import datetime, timedelta

from options.check.facts import market_facts
from options.engine.snapshot import SnapshotError, take
from utils.logger import setup_logger

logger = setup_logger("options.check")

CHANNEL = "option_check"
STALE_AFTER = timedelta(seconds=30)        # an older request was answered from saved data by the API


class CheckWorker:
    def __init__(self, engine, recorder, broker, store, live=None):
        self.engine, self.recorder, self.broker, self.store, self.live = engine, recorder, broker, store, live
        self._poke = True                       # look for pending requests on the first turn
        self._last_look: datetime | None = None

    def poke(self, _payload: str = "") -> None:
        """From the LISTEN thread: a request is waiting."""
        self._poke = True
        self.recorder.wake()

    def follow(self, symbol: str, token: int) -> None:
        """Record the contract and publish it live from now on."""
        try:
            self.recorder.watch(token)
            if self.live is not None:
                self.live.watch(symbol, token)
        except Exception:
            logger.exception("Couldn't start following %s", symbol)

    def follow_open(self, now: datetime) -> None:
        """At session start: contracts held as paper trades and today's checks keep streaming."""
        try:
            rows = self.store.checks_open_paper() + self.store.checks_since(now.replace(hour=0, minute=0, second=0))
        except Exception:
            logger.exception("Couldn't read checks to follow")
            return
        for r in rows:
            if r.get("token") and r.get("symbol") and r.get("expiry") and r["expiry"] >= now.date():
                self.follow(r["symbol"], int(r["token"]))

    def maybe(self, now: datetime) -> None:
        if not self._poke and self._last_look and (now - self._last_look).total_seconds() < 1:
            return
        self._poke, self._last_look = False, now
        try:
            pending = self.store.checks_pending(now - STALE_AFTER)
        except Exception:
            logger.exception("Couldn't read pending checks")
            return
        for req in pending:
            self._answer(req, now)

    def _answer(self, req: dict, now: datetime) -> None:
        check_id = req["id"]
        if not self.store.check_claim(check_id, "pending", "working"):
            return                                  # the API has already answered it from saved data
        try:
            ref = self.engine.refs.get(req["index_name"])
            opt = None
            if ref is not None:
                opt = ref.options.get((req["expiry"], req["strike"], req["option_right"]))
            if opt is None:
                self.store.check_update(check_id, status="error", error="The live engine doesn't list this contract")
                return
            self.follow(opt.tradingsymbol, opt.token)
            quote = None
            if hasattr(self.broker, "quotes"):
                try:
                    quote = self.broker.quotes({opt.tradingsymbol: opt.token}).get(opt.tradingsymbol)
                except Exception as e:
                    from options.brokers.angel import brief_error
                    logger.warning("Quote for %s failed: %s; using the last recorded minute", opt.tradingsymbol, brief_error(e))
            snap = take(self.engine.context(req["index_name"], now))
            params = req.get("params") or {}
            facts = market_facts(snap, opt, params.get("horizon", "intraday"), now, quote, self.engine.open)
            self.store.check_update(check_id, status="facts", facts=facts)
            self.store.notify(CHANNEL + "_done", check_id)
        except SnapshotError as e:
            self.store.check_update(check_id, status="error", error=f"Analysis agents not ready: {e}")
        except Exception as e:
            logger.exception("Option check %s failed", check_id)
            self.store.check_update(check_id, status="error", error=f"{type(e).__name__}: {str(e)[:200]}")

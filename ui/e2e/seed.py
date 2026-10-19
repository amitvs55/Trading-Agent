"""Seed a throwaway database for the browser end-to-end tests (ui/e2e).

    python ui/e2e/seed.py <sqlite path> <admin password> <viewer password>

Creates an admin ("e2e-admin") and a viewer ("e2e-viewer") with the given passwords (generated
fresh by the test run, never stored), one synthetic signal so the signal pages have content, and
live NIFTY 50 / SENSEX levels for the ticker.
Never point this at a real database: it refuses anything but a local SQLite file.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from options.admin.repo import AdminRepo  # noqa: E402
from options.backtest.synthetic import CAL, build_market, save_market  # noqa: E402
from options.config import OptionsSettings  # noqa: E402
from options.engine.engine import SignalEngine  # noqa: E402
from options.notify.base import LogNotifier  # noqa: E402
from options.setups.base import Candidate  # noqa: E402
from options.storage import Store, make_engine  # noqa: E402


def far_expiry(today: date) -> date:
    """The last trading Tuesday of the month about two months ahead (a monthly NIFTY expiry)."""
    d = today + timedelta(days=60)
    last = date(d.year + (d.month == 12), d.month % 12 + 1, 1) - timedelta(days=1)
    while last.weekday() != 1 or not CAL.is_trading_day(last):
        last -= timedelta(days=1)
    return last


class AlwaysBull:
    id, label, horizon = "S1_TREND_PULLBACK", "S1 Trend pullback", "intraday"
    regimes = frozenset({"trend", "range", "neutral", "chop"})

    def detect(self, snap):
        f = snap.ctx.fut
        return Candidate(self.id, 1, "intraday", f, f - 30, snap.ctx.ref.future_token, "5min", "pass", "seeded trigger",
                         room=150, room_unit=30, room_label="test level")


def main(db_path: str, admin_pw: str, viewer_pw: str) -> None:
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    repo = AdminRepo(engine, secret_key="e2e-only")
    repo.create_user("e2e-admin", admin_pw, role="admin", full_name="E2E Admin")
    repo.create_user("e2e-viewer", viewer_pw, role="viewer", full_name="E2E Viewer")
    ctx = build_market(trend=1)
    store = Store(engine)
    SignalEngine({"NIFTY": ctx.ref}, ctx.state, store, LogNotifier(), OptionsSettings(_env_file=None), ctx.calendar,
                 vix_token=ctx.vix_token, constituents={"NIFTY": ctx.constituents}, vix_history=ctx.vix_history,
                 events=[], now_fn=lambda: ctx.now, setups=[AlwaysBull()]).evaluate(ctx.now)
    from live_tick import publish                     # the live ticker's first levels
    publish(str(path), 23096.95, 75512.10)
    # Option Check reads saved bars: the synthetic session, plus an expiry ~2 months from the real date,
    # so the check page always has a live contract to test whatever day the tests run
    save_market(store, ctx, (far_expiry(date.today()),))
    print(f"seeded {path}")


if __name__ == "__main__":
    if len(sys.argv) != 4 or not sys.argv[1].endswith(".db"):
        sys.exit("usage: seed.py <file.db> <admin password> <viewer password>")
    main(*sys.argv[1:])

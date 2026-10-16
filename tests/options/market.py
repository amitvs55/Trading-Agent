"""The synthetic market lives in the app (options/backtest/synthetic.py) so the Agents page
self-test can use it too; tests import it from here as before."""

from options.backtest.synthetic import CAL, IV, R, build_market, history_days  # noqa: F401

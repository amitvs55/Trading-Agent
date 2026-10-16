"""NIFTY 50 heavyweights used by the breadth pillar.

Weights are APPROXIMATE free-float weights (% of the index) for orientation only. NSE
publishes exact weights monthly in the NIFTY 50 factsheet; update this table from it.
Only the direction and relative size matter for the breadth score, so small drift is
harmless, but a constituent change (semi-annual rebalance) must be reflected here.
"""

NIFTY_HEAVYWEIGHTS: list[tuple[str, float]] = [
    ("HDFCBANK", 13.0),
    ("ICICIBANK", 9.0),
    ("RELIANCE", 8.5),
    ("INFY", 5.0),
    ("BHARTIARTL", 4.5),
    ("LT", 4.0),
    ("ITC", 3.5),
    ("TCS", 3.0),
    ("AXISBANK", 3.0),
    ("KOTAKBANK", 3.0),
    ("SBIN", 3.0),
    ("M&M", 2.5),
    ("BAJFINANCE", 2.0),
]

HEAVYWEIGHTS = {"NIFTY": NIFTY_HEAVYWEIGHTS}

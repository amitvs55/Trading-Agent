"""Round-trip charges for NSE index options at a discount broker (Zerodha-style).

Rates as of Oct 2026. STT is from the Finance Act 2026, effective 1 Apr 2026. The others
are the published exchange, SEBI and stamp rates; update them here if they change.
"""

from dataclasses import dataclass

BROKERAGE_PER_ORDER = 20.0          # ₹ flat per executed order
STT_SELL_PCT = 0.15                 # % of sell-side premium (was 0.10% before Apr 2026)
EXCHANGE_TXN_PCT = 0.03503          # NSE options, % of premium turnover
SEBI_FEE_PCT = 0.0001               # ₹10 per crore
STAMP_BUY_PCT = 0.003               # % of buy-side premium
GST_PCT = 18.0                      # on brokerage + exchange + SEBI fees


@dataclass(frozen=True)
class Charges:
    brokerage: float
    stt: float
    exchange: float
    sebi: float
    stamp: float
    gst: float

    @property
    def total(self) -> float:
        return self.brokerage + self.stt + self.exchange + self.sebi + self.stamp + self.gst


def charges(buy_value: float, sell_value: float, orders: int) -> Charges:
    """Charges for buying `buy_value` and selling `sell_value` of premium (₹) in `orders` orders."""
    turnover = buy_value + sell_value
    brokerage = BROKERAGE_PER_ORDER * orders
    exchange = turnover * EXCHANGE_TXN_PCT / 100
    sebi = turnover * SEBI_FEE_PCT / 100
    return Charges(
        brokerage=brokerage,
        stt=sell_value * STT_SELL_PCT / 100,
        exchange=exchange,
        sebi=sebi,
        stamp=buy_value * STAMP_BUY_PCT / 100,
        gst=(brokerage + exchange + sebi) * GST_PCT / 100,
    )


def order_charges(side: str, value: float, orders: int = 1) -> Charges:
    """Charges for one executed order: a "BUY" or "SELL" of `value` (₹) of premium. Every rate is linear,
    so a buy's and a sell's charges add up exactly to charges(buy, sell, 2)."""
    return charges(value if side == "BUY" else 0.0, value if side == "SELL" else 0.0, orders)

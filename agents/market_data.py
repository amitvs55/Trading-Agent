"""Market Data Analyst — fetches Yahoo Finance data and computes technical indicators."""

import json
from typing import Any

import pandas as pd
import yfinance as yf

from agents.base import BaseAgent
from config.prompts import MARKET_DATA_ANALYST
from models.schemas import MarketDataOutput, TechnicalIndicators
from utils.logger import setup_logger

logger = setup_logger("market_data")


def _compute_rsi(prices: pd.Series, period: int = 14) -> float | None:
    """Wilder's RSI, as charting platforms and TA-Lib compute it: seeded with the simple average of
    the first `period` moves, then smoothed by 1/period. (A plain rolling mean, used before, read
    3–7 points away from what traders see.)"""
    if len(prices) < period + 1:
        return None
    delta = prices.astype(float).diff().dropna()
    gain, loss = delta.clip(lower=0.0), -delta.clip(upper=0.0)
    avg_gain, avg_loss = float(gain.iloc[:period].mean()), float(loss.iloc[:period].mean())
    for g, l in zip(gain.iloc[period:], loss.iloc[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    return round(float(100 - 100 / (1 + avg_gain / avg_loss)), 2)


def _compute_macd(
    prices: pd.Series,
) -> tuple[float | None, float | None, float | None]:
    if len(prices) < 26:
        return None, None, None
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal
    return (
        round(float(macd_line.iloc[-1]), 4),
        round(float(signal.iloc[-1]), 4),
        round(float(histogram.iloc[-1]), 4),
    )


def _compute_bollinger(
    prices: pd.Series, period: int = 20
) -> tuple[float | None, float | None, float | None]:
    if len(prices) < period:
        return None, None, None
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return (
        round(float(upper.iloc[-1]), 2),
        round(float(sma.iloc[-1]), 2),
        round(float(lower.iloc[-1]), 2),
    )


def fetch_market_data(ticker: str) -> dict[str, Any]:
    """Fetch price data and compute technical indicators from Yahoo Finance."""
    stock = yf.Ticker(ticker)
    info = stock.info
    hist = stock.history(period="3mo")

    if hist.empty:
        raise ValueError(f"No historical data found for {ticker}")

    close = hist["Close"]
    current_price = round(float(close.iloc[-1]), 2)

    # Price changes
    pct_1d = None
    pct_5d = None
    if len(close) >= 2:
        pct_1d = round(float((close.iloc[-1] / close.iloc[-2] - 1) * 100), 2)
    if len(close) >= 6:
        pct_5d = round(float((close.iloc[-1] / close.iloc[-6] - 1) * 100), 2)

    # Volume
    vol = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else None
    avg_vol = (
        int(hist["Volume"].tail(10).mean()) if "Volume" in hist.columns else None
    )

    # Technical indicators
    rsi = _compute_rsi(close)
    macd_line, macd_signal, macd_hist = _compute_macd(close)
    bb_upper, bb_middle, bb_lower = _compute_bollinger(close)

    sma_20 = round(float(close.rolling(20).mean().iloc[-1]), 2) if len(close) >= 20 else None
    sma_50 = round(float(close.rolling(50).mean().iloc[-1]), 2) if len(close) >= 50 else None
    ema_12 = round(float(close.ewm(span=12, adjust=False).mean().iloc[-1]), 2)
    ema_26 = (
        round(float(close.ewm(span=26, adjust=False).mean().iloc[-1]), 2)
        if len(close) >= 26
        else None
    )

    indicators = TechnicalIndicators(
        rsi_14=rsi,
        macd_line=macd_line,
        macd_signal=macd_signal,
        macd_histogram=macd_hist,
        bollinger_upper=bb_upper,
        bollinger_middle=bb_middle,
        bollinger_lower=bb_lower,
        sma_20=sma_20,
        sma_50=sma_50,
        ema_12=ema_12,
        ema_26=ema_26,
    )

    return {
        "current_price": current_price,
        "price_change_pct_1d": pct_1d,
        "price_change_pct_5d": pct_5d,
        "volume": vol,
        "avg_volume_10d": avg_vol,
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "indicators": indicators.model_dump(),
    }


class MarketDataAgent(BaseAgent):
    name = "market_data_analyst"
    system_prompt = MARKET_DATA_ANALYST
    output_model = MarketDataOutput

    def run(self, context: dict[str, Any]) -> MarketDataOutput:
        ticker = context["ticker"]
        logger.info("Fetching market data for %s", ticker)

        # Fetch real data
        market_data = fetch_market_data(ticker)

        # Ask LLM to interpret the data
        user_prompt = (
            f"Analyze the following market data for {ticker} and provide your "
            f"technical analysis.\n\n{json.dumps(market_data, indent=2)}"
        )

        schema_json = json.dumps(self.output_model.model_json_schema(), indent=2)
        system = (
            f"{self.system_prompt}\n\n"
            f"You MUST respond with valid JSON matching this schema:\n{schema_json}"
        )

        raw = self.llm.call(system, user_prompt)

        # Merge real data with LLM interpretation
        raw.update(
            {
                "agent_name": self.name,
                "ticker": ticker,
                "current_price": market_data["current_price"],
                "price_change_pct_1d": market_data["price_change_pct_1d"],
                "price_change_pct_5d": market_data["price_change_pct_5d"],
                "volume": market_data["volume"],
                "avg_volume_10d": market_data["avg_volume_10d"],
                "fifty_two_week_high": market_data["fifty_two_week_high"],
                "fifty_two_week_low": market_data["fifty_two_week_low"],
                "indicators": market_data["indicators"],
            }
        )

        return MarketDataOutput.model_validate(raw)

"""Fundamentals Analyst — evaluates company financials from Yahoo Finance."""

import json
from typing import Any

import yfinance as yf

from agents.base import BaseAgent
from config.prompts import FUNDAMENTALS_ANALYST
from models.schemas import FundamentalsOutput
from utils.logger import setup_logger

logger = setup_logger("fundamentals")


def fetch_fundamentals(ticker: str) -> dict[str, Any]:
    """Fetch company fundamentals from Yahoo Finance."""
    stock = yf.Ticker(ticker)
    info = stock.info

    # Insider transactions
    insider_buy_pct = None
    try:
        insider_txns = stock.insider_transactions
        if insider_txns is not None and not insider_txns.empty:
            buys = len(insider_txns[insider_txns["Shares"].fillna(0) > 0])
            total = len(insider_txns)
            insider_buy_pct = round(buys / total * 100, 1) if total > 0 else None
    except Exception:
        pass

    return {
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "eps": info.get("trailingEps"),
        "revenue_growth": info.get("revenueGrowth"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "insider_buy_pct": insider_buy_pct,
        "sector": info.get("sector"),
        "business_summary": (info.get("longBusinessSummary") or "")[:500],
    }


class FundamentalsAgent(BaseAgent):
    name = "fundamentals_analyst"
    system_prompt = FUNDAMENTALS_ANALYST
    output_model = FundamentalsOutput

    def run(self, context: dict[str, Any]) -> FundamentalsOutput:
        ticker = context["ticker"]
        logger.info("Analyzing fundamentals for %s", ticker)

        fundamentals = fetch_fundamentals(ticker)

        user_prompt = (
            f"Evaluate the following financial data for {ticker} and provide "
            f"your fundamental analysis.\n\n"
            f"{json.dumps(fundamentals, indent=2, default=str)}"
        )

        schema_json = json.dumps(self.output_model.model_json_schema(), indent=2)
        system = (
            f"{self.system_prompt}\n\n"
            f"You MUST respond with valid JSON matching this schema:\n{schema_json}"
        )

        raw = self.llm.call(system, user_prompt)

        # Merge real data with LLM interpretation
        raw["agent_name"] = self.name
        raw["ticker"] = ticker
        for key in ["market_cap", "pe_ratio", "forward_pe", "eps", "revenue_growth",
                     "profit_margin", "debt_to_equity", "insider_buy_pct", "sector",
                     "business_summary"]:
            if key in fundamentals and fundamentals[key] is not None:
                raw[key] = fundamentals[key]

        return FundamentalsOutput.model_validate(raw)

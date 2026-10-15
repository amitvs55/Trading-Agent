"""Trader Agent — proposes a specific trade based on research verdict and market data."""

import json
from typing import Any

from agents.base import BaseAgent
from config.prompts import TRADER
from models.schemas import TradeProposal


class TraderAgent(BaseAgent):
    name = "trader"
    system_prompt = TRADER
    output_model = TradeProposal

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        ticker = context.get("ticker", "Unknown")
        verdict = context.get("verdict")
        market = context.get("market")

        verdict_data = verdict.model_dump(mode="json") if hasattr(verdict, "model_dump") else verdict
        market_data = market.model_dump(mode="json") if hasattr(market, "model_dump") else market

        return (
            f"Based on the research verdict and market data for {ticker}, "
            f"propose a specific trade.\n\n"
            f"## RESEARCH VERDICT\n{json.dumps(verdict_data, indent=2, default=str)}\n\n"
            f"## CURRENT MARKET DATA\n{json.dumps(market_data, indent=2, default=str)}"
        )

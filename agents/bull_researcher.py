"""Bullish Researcher — builds the strongest bull case from analyst data."""

import json
from typing import Any

from agents.base import BaseAgent
from config.prompts import BULL_RESEARCHER
from models.schemas import ResearchOutput


class BullResearcherAgent(BaseAgent):
    name = "bull_researcher"
    system_prompt = BULL_RESEARCHER
    output_model = ResearchOutput

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        ticker = context.get("ticker", "Unknown")
        sections = []
        for key in ["market", "sentiment", "news", "fundamentals"]:
            if key in context:
                obj = context[key]
                data = obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
                sections.append(f"## {key.upper()} ANALYSIS\n{json.dumps(data, indent=2, default=str)}")

        return (
            f"Build the strongest possible BULL CASE for {ticker}.\n\n"
            f"Analyst reports:\n\n" + "\n\n".join(sections)
        )

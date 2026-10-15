"""Discussion Moderator — debates bull vs bear and produces final research verdict."""

import json
from typing import Any

from agents.base import BaseAgent
from config.prompts import DEBATE_MODERATOR
from models.schemas import DebateVerdict


class ModeratorAgent(BaseAgent):
    name = "debate_moderator"
    system_prompt = DEBATE_MODERATOR
    output_model = DebateVerdict

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        ticker = context.get("ticker", "Unknown")
        bull = context.get("bull")
        bear = context.get("bear")

        bull_data = bull.model_dump(mode="json") if hasattr(bull, "model_dump") else bull
        bear_data = bear.model_dump(mode="json") if hasattr(bear, "model_dump") else bear

        return (
            f"Evaluate the following Bull and Bear cases for {ticker} and "
            f"provide your verdict.\n\n"
            f"## BULL CASE\n{json.dumps(bull_data, indent=2, default=str)}\n\n"
            f"## BEAR CASE\n{json.dumps(bear_data, indent=2, default=str)}"
        )

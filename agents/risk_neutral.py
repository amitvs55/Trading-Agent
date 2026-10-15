"""Neutral Risk Manager — evaluates trades with balanced risk parameters."""

import json
from typing import Any

from agents.base import BaseAgent
from config.prompts import RISK_NEUTRAL
from models.schemas import RiskAssessment, RiskProfile


class NeutralRiskAgent(BaseAgent):
    name = "risk_manager_neutral"
    system_prompt = RISK_NEUTRAL
    output_model = RiskAssessment

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        proposal = context.get("proposal")
        data = proposal.model_dump(mode="json") if hasattr(proposal, "model_dump") else proposal
        return (
            f"Evaluate this trade proposal from a NEUTRAL/BALANCED risk perspective.\n\n"
            f"## TRADE PROPOSAL\n{json.dumps(data, indent=2, default=str)}"
        )

    def run(self, context: dict[str, Any]) -> RiskAssessment:
        result = super().run(context)
        result.profile = RiskProfile.NEUTRAL
        return result

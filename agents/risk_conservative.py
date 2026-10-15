"""Conservative Risk Manager — evaluates trades with capital preservation priority."""

import json
from typing import Any

from agents.base import BaseAgent
from config.prompts import RISK_CONSERVATIVE
from models.schemas import RiskAssessment, RiskProfile


class ConservativeRiskAgent(BaseAgent):
    name = "risk_manager_conservative"
    system_prompt = RISK_CONSERVATIVE
    output_model = RiskAssessment

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        proposal = context.get("proposal")
        data = proposal.model_dump(mode="json") if hasattr(proposal, "model_dump") else proposal
        return (
            f"Evaluate this trade proposal from a CONSERVATIVE risk perspective.\n\n"
            f"## TRADE PROPOSAL\n{json.dumps(data, indent=2, default=str)}"
        )

    def run(self, context: dict[str, Any]) -> RiskAssessment:
        result = super().run(context)
        result.profile = RiskProfile.CONSERVATIVE
        return result

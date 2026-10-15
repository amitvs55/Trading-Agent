"""Portfolio Manager — makes the final execute/hold/reject decision."""

import json
from typing import Any

from agents.base import BaseAgent
from config.prompts import PORTFOLIO_MANAGER
from models.schemas import FinalDecision


class PortfolioManagerAgent(BaseAgent):
    name = "portfolio_manager"
    system_prompt = PORTFOLIO_MANAGER
    output_model = FinalDecision

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        ticker = context.get("ticker", "Unknown")
        proposal = context.get("proposal")
        risks = context.get("risks", [])

        proposal_data = proposal.model_dump(mode="json") if hasattr(proposal, "model_dump") else proposal
        risk_data = []
        for r in risks:
            risk_data.append(r.model_dump(mode="json") if hasattr(r, "model_dump") else r)

        return (
            f"Make the final trading decision for {ticker}.\n\n"
            f"## TRADE PROPOSAL\n{json.dumps(proposal_data, indent=2, default=str)}\n\n"
            f"## RISK ASSESSMENTS\n{json.dumps(risk_data, indent=2, default=str)}"
        )

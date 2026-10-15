"""Tests for individual agents with mocked LLM."""

import pytest

from models.schemas import (
    DebateVerdict,
    FinalDecision,
    ResearchOutput,
    RiskAssessment,
    RiskProfile,
    SentimentOutput,
    TradeProposal,
)
from tests.conftest import (
    MOCK_BEAR_RESEARCH,
    MOCK_BULL_RESEARCH,
    MOCK_FUNDAMENTALS_LLM,
    MOCK_MARKET_DATA_LLM,
    MOCK_NEWS_LLM,
    MOCK_SENTIMENT_LLM,
)


class TestBullResearcher:
    def test_produces_research_output(self, mock_llm):
        from agents.bull_researcher import BullResearcherAgent

        agent = BullResearcherAgent()
        result = agent.run({
            "ticker": "AAPL",
            "market": MOCK_MARKET_DATA_LLM,
            "sentiment": MOCK_SENTIMENT_LLM,
            "news": MOCK_NEWS_LLM,
            "fundamentals": MOCK_FUNDAMENTALS_LLM,
        })
        assert isinstance(result, ResearchOutput)
        assert 0 <= result.confidence <= 1


class TestBearResearcher:
    def test_produces_research_output(self, mock_llm):
        from agents.bear_researcher import BearResearcherAgent

        agent = BearResearcherAgent()
        result = agent.run({
            "ticker": "AAPL",
            "market": MOCK_MARKET_DATA_LLM,
            "sentiment": MOCK_SENTIMENT_LLM,
            "news": MOCK_NEWS_LLM,
            "fundamentals": MOCK_FUNDAMENTALS_LLM,
        })
        assert isinstance(result, ResearchOutput)
        assert len(result.key_arguments) > 0


class TestModerator:
    def test_produces_verdict(self, mock_llm):
        from agents.moderator import ModeratorAgent

        agent = ModeratorAgent()
        result = agent.run({
            "ticker": "AAPL",
            "bull": MOCK_BULL_RESEARCH,
            "bear": MOCK_BEAR_RESEARCH,
        })
        assert isinstance(result, DebateVerdict)
        assert result.winner in ("bull", "bear", "neutral")


class TestTrader:
    def test_produces_trade_proposal(self, mock_llm):
        from agents.trader import TraderAgent
        from tests.conftest import MOCK_VERDICT

        agent = TraderAgent()
        result = agent.run({
            "ticker": "AAPL",
            "verdict": MOCK_VERDICT,
            "market": MOCK_MARKET_DATA_LLM,
        })
        assert isinstance(result, TradeProposal)
        assert result.direction.value in ("long", "short", "hold")


class TestRiskManagers:
    def test_aggressive_risk(self, mock_llm):
        from agents.risk_aggressive import AggressiveRiskAgent
        from tests.conftest import MOCK_TRADE_PROPOSAL

        agent = AggressiveRiskAgent()
        result = agent.run({"proposal": MOCK_TRADE_PROPOSAL})
        assert isinstance(result, RiskAssessment)
        assert result.profile == RiskProfile.AGGRESSIVE

    def test_neutral_risk(self, mock_llm):
        from agents.risk_neutral import NeutralRiskAgent
        from tests.conftest import MOCK_TRADE_PROPOSAL

        agent = NeutralRiskAgent()
        result = agent.run({"proposal": MOCK_TRADE_PROPOSAL})
        assert isinstance(result, RiskAssessment)
        assert result.profile == RiskProfile.NEUTRAL

    def test_conservative_risk(self, mock_llm):
        from agents.risk_conservative import ConservativeRiskAgent
        from tests.conftest import MOCK_TRADE_PROPOSAL

        agent = ConservativeRiskAgent()
        result = agent.run({"proposal": MOCK_TRADE_PROPOSAL})
        assert isinstance(result, RiskAssessment)
        assert result.profile == RiskProfile.CONSERVATIVE


class TestPortfolioManager:
    def test_produces_decision(self, mock_llm):
        from agents.portfolio_manager import PortfolioManagerAgent
        from tests.conftest import (
            MOCK_RISK_AGGRESSIVE,
            MOCK_RISK_CONSERVATIVE,
            MOCK_RISK_NEUTRAL,
            MOCK_TRADE_PROPOSAL,
        )

        agent = PortfolioManagerAgent()
        result = agent.run({
            "ticker": "AAPL",
            "proposal": MOCK_TRADE_PROPOSAL,
            "risks": [MOCK_RISK_AGGRESSIVE, MOCK_RISK_NEUTRAL, MOCK_RISK_CONSERVATIVE],
        })
        assert isinstance(result, FinalDecision)
        assert result.action in ("execute", "hold", "reject")

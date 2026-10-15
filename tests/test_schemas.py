"""Tests for Pydantic data models."""

import pytest
from pydantic import ValidationError

from models.schemas import (
    DebateVerdict,
    ExecutionResult,
    FinalDecision,
    FundamentalsOutput,
    MarketDataOutput,
    NewsImpact,
    NewsItem,
    NewsOutput,
    RiskAssessment,
    RiskProfile,
    SentimentOutput,
    TechnicalIndicators,
    TradeDirection,
    TradeProposal,
)


class TestTechnicalIndicators:
    def test_all_optional(self):
        ti = TechnicalIndicators()
        assert ti.rsi_14 is None

    def test_with_values(self):
        ti = TechnicalIndicators(rsi_14=55.0, macd_line=1.2)
        assert ti.rsi_14 == 55.0
        assert ti.macd_line == 1.2


class TestSentimentOutput:
    def test_valid_score(self):
        s = SentimentOutput(
            agent_name="test", ticker="AAPL",
            overall_score=0.5, summary="positive"
        )
        assert s.overall_score == 0.5

    def test_score_out_of_range(self):
        with pytest.raises(ValidationError):
            SentimentOutput(
                agent_name="test", ticker="AAPL",
                overall_score=1.5, summary="invalid"
            )

    def test_negative_score(self):
        s = SentimentOutput(
            agent_name="test", ticker="AAPL",
            overall_score=-0.8, summary="bearish"
        )
        assert s.overall_score == -0.8


class TestNewsItem:
    def test_valid_item(self):
        item = NewsItem(
            headline="Test", source="Reuters",
            impact=NewsImpact.POSITIVE, relevance_score=0.9
        )
        assert item.impact == NewsImpact.POSITIVE

    def test_relevance_out_of_range(self):
        with pytest.raises(ValidationError):
            NewsItem(
                headline="Test", source="Reuters",
                impact=NewsImpact.POSITIVE, relevance_score=1.5
            )


class TestTradeProposal:
    def test_hold_trade(self):
        tp = TradeProposal(
            agent_name="trader", ticker="AAPL",
            direction=TradeDirection.HOLD,
            position_size_pct=0.0,
            rationale="No trade"
        )
        assert tp.direction == TradeDirection.HOLD
        assert tp.entry_price is None

    def test_long_trade(self):
        tp = TradeProposal(
            agent_name="trader", ticker="AAPL",
            direction=TradeDirection.LONG,
            entry_price=175.0, stop_loss=170.0, take_profit=190.0,
            position_size_pct=5.0, risk_reward_ratio=3.0,
            rationale="Bullish setup"
        )
        assert tp.direction == TradeDirection.LONG
        assert tp.position_size_pct == 5.0


class TestRiskAssessment:
    def test_valid_assessment(self):
        ra = RiskAssessment(
            agent_name="risk", ticker="AAPL",
            profile=RiskProfile.NEUTRAL,
            approve=True, risk_score=4.5,
            max_position_size_pct=5.0,
            recommendation="Approve"
        )
        assert ra.approve is True

    def test_risk_score_out_of_range(self):
        with pytest.raises(ValidationError):
            RiskAssessment(
                agent_name="risk", ticker="AAPL",
                profile=RiskProfile.NEUTRAL,
                approve=True, risk_score=11.0,
                max_position_size_pct=5.0,
                recommendation="Invalid"
            )


class TestFinalDecision:
    def test_execute(self):
        fd = FinalDecision(
            agent_name="pm", ticker="AAPL",
            action="execute", final_entry=175.0,
            final_stop_loss=170.0, final_take_profit=190.0,
            final_position_size_pct=4.0,
            reasoning="Approved", risk_consensus="Unanimous"
        )
        assert fd.action == "execute"

    def test_reject(self):
        fd = FinalDecision(
            agent_name="pm", ticker="AAPL",
            action="reject",
            reasoning="Too risky", risk_consensus="0/3 approve"
        )
        assert fd.action == "reject"
        assert fd.final_entry is None

"""Pydantic data models for all agent inputs and outputs."""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ─── Shared ───────────────────────────────────────────────────────────────────


class AgentMetadata(BaseModel):
    agent_name: str
    ticker: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_used: str = "gpt-4"


# ─── Stage 1: Data Collection ────────────────────────────────────────────────


class TechnicalIndicators(BaseModel):
    rsi_14: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None


class MarketDataOutput(AgentMetadata):
    current_price: float
    price_change_pct_1d: Optional[float] = None
    price_change_pct_5d: Optional[float] = None
    volume: Optional[int] = None
    avg_volume_10d: Optional[int] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    indicators: TechnicalIndicators
    trend_signal: Literal["bullish", "bearish", "neutral"] = "neutral"
    summary: str


class SentimentOutput(AgentMetadata):
    overall_score: float = Field(ge=-1.0, le=1.0)
    twitter_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    reddit_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    sample_posts: list[str] = Field(default_factory=list)
    data_source: str = "llm_estimated"
    summary: str


class NewsImpact(str, Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class NewsItem(BaseModel):
    headline: str
    source: str
    impact: NewsImpact
    relevance_score: float = Field(ge=0.0, le=1.0)


class NewsOutput(AgentMetadata):
    articles: list[NewsItem] = Field(default_factory=list)
    overall_impact: NewsImpact = NewsImpact.NEUTRAL
    summary: str


class FundamentalsOutput(AgentMetadata):
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    eps: Optional[float] = None
    revenue_growth: Optional[float] = None
    profit_margin: Optional[float] = None
    debt_to_equity: Optional[float] = None
    insider_buy_pct: Optional[float] = None
    sector: Optional[str] = None
    business_summary: Optional[str] = None
    health_score: Literal["strong", "moderate", "weak"] = "moderate"
    summary: str


# ─── Stage 2: Research ───────────────────────────────────────────────────────


class ResearchOutput(AgentMetadata):
    thesis: str
    key_arguments: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_data: dict = Field(default_factory=dict)


class DebateVerdict(AgentMetadata):
    winner: Literal["bull", "bear", "neutral"]
    bull_score: float = Field(ge=0.0, le=10.0)
    bear_score: float = Field(ge=0.0, le=10.0)
    key_consensus_points: list[str] = Field(default_factory=list)
    key_disagreement_points: list[str] = Field(default_factory=list)
    final_recommendation: Literal[
        "strong_buy", "buy", "hold", "sell", "strong_sell"
    ]
    rationale: str


# ─── Stage 3: Trading ────────────────────────────────────────────────────────


class TradeDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    HOLD = "hold"


class TradeProposal(AgentMetadata):
    direction: TradeDirection
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_pct: float = Field(ge=0.0, le=100.0, default=0.0)
    risk_reward_ratio: Optional[float] = None
    time_horizon: str = "1w"
    rationale: str


# ─── Stage 4: Risk Management ────────────────────────────────────────────────


class RiskProfile(str, Enum):
    AGGRESSIVE = "aggressive"
    NEUTRAL = "neutral"
    CONSERVATIVE = "conservative"


class RiskAssessment(AgentMetadata):
    profile: RiskProfile
    approve: bool
    risk_score: float = Field(ge=0.0, le=10.0)
    max_position_size_pct: float = Field(ge=0.0, le=100.0)
    adjusted_stop_loss: Optional[float] = None
    adjusted_take_profit: Optional[float] = None
    concerns: list[str] = Field(default_factory=list)
    recommendation: str


# ─── Stage 5: Portfolio Decision ──────────────────────────────────────────────


class FinalDecision(AgentMetadata):
    action: Literal["execute", "hold", "reject"]
    final_entry: Optional[float] = None
    final_stop_loss: Optional[float] = None
    final_take_profit: Optional[float] = None
    final_position_size_pct: Optional[float] = None
    reasoning: str
    risk_consensus: str


# ─── Stage 6: Execution ──────────────────────────────────────────────────────


class ExecutionResult(AgentMetadata):
    order_id: str
    status: Literal["executed_simulated", "held", "rejected"]
    details: str
    logged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Full Pipeline Result ────────────────────────────────────────────────────


class PipelineResult(BaseModel):
    ticker: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    market_data: MarketDataOutput
    sentiment: SentimentOutput
    news: NewsOutput
    fundamentals: FundamentalsOutput
    bull_case: ResearchOutput
    bear_case: ResearchOutput
    debate_verdict: DebateVerdict
    trade_proposal: TradeProposal
    risk_assessments: list[RiskAssessment]
    final_decision: FinalDecision
    execution: ExecutionResult
    total_duration_seconds: float

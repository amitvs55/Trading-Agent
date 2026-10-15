"""Shared test fixtures with mock LLM responses."""

import pytest


# ─── Mock LLM Responses ─────────────────────────────────────────────────────

MOCK_MARKET_DATA_LLM = {
    "agent_name": "market_data_analyst",
    "ticker": "AAPL",
    "current_price": 175.50,
    "price_change_pct_1d": 1.2,
    "price_change_pct_5d": 3.5,
    "volume": 55000000,
    "avg_volume_10d": 50000000,
    "fifty_two_week_high": 199.62,
    "fifty_two_week_low": 124.17,
    "indicators": {
        "rsi_14": 58.3,
        "macd_line": 1.25,
        "macd_signal": 0.98,
        "macd_histogram": 0.27,
        "bollinger_upper": 180.0,
        "bollinger_middle": 173.0,
        "bollinger_lower": 166.0,
        "sma_20": 172.5,
        "sma_50": 168.0,
        "ema_12": 174.0,
        "ema_26": 171.5,
    },
    "trend_signal": "bullish",
    "summary": "AAPL shows bullish momentum with price above SMA20/50, RSI at 58 (neutral-bullish), and positive MACD histogram.",
}

MOCK_SENTIMENT_LLM = {
    "agent_name": "sentiment_analyst",
    "ticker": "AAPL",
    "overall_score": 0.45,
    "twitter_score": 0.5,
    "reddit_score": 0.4,
    "sample_posts": [
        "AAPL looking strong going into earnings",
        "Apple AI features could be a game changer",
    ],
    "data_source": "llm_estimated",
    "summary": "Moderately positive sentiment driven by AI product expectations.",
}

MOCK_NEWS_LLM = {
    "agent_name": "news_analyst",
    "ticker": "AAPL",
    "articles": [
        {
            "headline": "Apple Reports Record Services Revenue",
            "source": "Reuters",
            "impact": "positive",
            "relevance_score": 0.9,
        }
    ],
    "overall_impact": "positive",
    "summary": "Recent news is positive, driven by strong services revenue growth.",
}

MOCK_FUNDAMENTALS_LLM = {
    "agent_name": "fundamentals_analyst",
    "ticker": "AAPL",
    "market_cap": 2750000000000,
    "pe_ratio": 28.5,
    "forward_pe": 26.0,
    "eps": 6.15,
    "revenue_growth": 0.08,
    "profit_margin": 0.26,
    "debt_to_equity": 1.5,
    "insider_buy_pct": 30.0,
    "sector": "Technology",
    "business_summary": "Apple Inc. designs and sells consumer electronics.",
    "health_score": "strong",
    "summary": "Strong fundamentals with healthy margins and growing services revenue.",
}

MOCK_BULL_RESEARCH = {
    "agent_name": "bull_researcher",
    "ticker": "AAPL",
    "thesis": "Apple is well-positioned for growth driven by AI integration and services expansion.",
    "key_arguments": [
        "Services revenue growing at double digits",
        "AI features will drive upgrade cycle",
        "Strong cash flow supports buybacks",
    ],
    "confidence": 0.75,
    "supporting_data": {"pe_ratio": 28.5, "revenue_growth": 0.08},
}

MOCK_BEAR_RESEARCH = {
    "agent_name": "bear_researcher",
    "ticker": "AAPL",
    "thesis": "Apple faces headwinds from China slowdown and premium valuation.",
    "key_arguments": [
        "China iPhone sales declining",
        "PE ratio above historical average",
        "Regulatory risks in EU and US",
    ],
    "confidence": 0.55,
    "supporting_data": {"pe_ratio": 28.5, "china_risk": "high"},
}

MOCK_VERDICT = {
    "agent_name": "debate_moderator",
    "ticker": "AAPL",
    "winner": "bull",
    "bull_score": 7.5,
    "bear_score": 5.5,
    "key_consensus_points": ["Strong brand and ecosystem"],
    "key_disagreement_points": ["China exposure impact"],
    "final_recommendation": "buy",
    "rationale": "Bull case is stronger. Growth catalysts outweigh near-term risks.",
}

MOCK_TRADE_PROPOSAL = {
    "agent_name": "trader",
    "ticker": "AAPL",
    "direction": "long",
    "entry_price": 175.50,
    "stop_loss": 170.00,
    "take_profit": 190.00,
    "position_size_pct": 5.0,
    "risk_reward_ratio": 2.6,
    "time_horizon": "1m",
    "rationale": "Buy on bullish verdict with clear support at SMA50.",
}

MOCK_RISK_AGGRESSIVE = {
    "agent_name": "risk_manager_aggressive",
    "ticker": "AAPL",
    "profile": "aggressive",
    "approve": True,
    "risk_score": 4.0,
    "max_position_size_pct": 10.0,
    "adjusted_stop_loss": 168.0,
    "adjusted_take_profit": 195.0,
    "concerns": ["Earnings volatility"],
    "recommendation": "Approve with wider targets for higher reward.",
}

MOCK_RISK_NEUTRAL = {
    "agent_name": "risk_manager_neutral",
    "ticker": "AAPL",
    "profile": "neutral",
    "approve": True,
    "risk_score": 4.5,
    "max_position_size_pct": 5.0,
    "adjusted_stop_loss": 170.0,
    "adjusted_take_profit": 190.0,
    "concerns": ["Market volatility"],
    "recommendation": "Approve at proposed levels.",
}

MOCK_RISK_CONSERVATIVE = {
    "agent_name": "risk_manager_conservative",
    "ticker": "AAPL",
    "profile": "conservative",
    "approve": True,
    "risk_score": 4.5,
    "max_position_size_pct": 3.0,
    "adjusted_stop_loss": 172.0,
    "adjusted_take_profit": 185.0,
    "concerns": ["Position size should be reduced", "Tighter stop needed"],
    "recommendation": "Approve with reduced size and tighter stops.",
}

MOCK_FINAL_DECISION = {
    "agent_name": "portfolio_manager",
    "ticker": "AAPL",
    "action": "execute",
    "final_entry": 175.50,
    "final_stop_loss": 171.00,
    "final_take_profit": 188.00,
    "final_position_size_pct": 4.0,
    "reasoning": "All three risk managers approve. Using conservative-adjusted parameters.",
    "risk_consensus": "Unanimous approval with varying position size recommendations.",
}


def _get_mock_response(system_prompt: str) -> dict:
    """Return appropriate mock based on system prompt content."""
    prompt_lower = system_prompt.lower()
    if "market data analyst" in prompt_lower:
        return MOCK_MARKET_DATA_LLM
    elif "sentiment analyst" in prompt_lower:
        return MOCK_SENTIMENT_LLM
    elif "news analyst" in prompt_lower:
        return MOCK_NEWS_LLM
    elif "fundamentals analyst" in prompt_lower:
        return MOCK_FUNDAMENTALS_LLM
    elif "bullish" in prompt_lower and "researcher" in prompt_lower:
        return MOCK_BULL_RESEARCH
    elif "bearish" in prompt_lower and "researcher" in prompt_lower:
        return MOCK_BEAR_RESEARCH
    elif "moderator" in prompt_lower:
        return MOCK_VERDICT
    elif "professional trader" in prompt_lower:
        return MOCK_TRADE_PROPOSAL
    elif "aggressive risk" in prompt_lower:
        return MOCK_RISK_AGGRESSIVE
    elif "neutral risk" in prompt_lower:
        return MOCK_RISK_NEUTRAL
    elif "conservative risk" in prompt_lower:
        return MOCK_RISK_CONSERVATIVE
    elif "portfolio manager" in prompt_lower:
        return MOCK_FINAL_DECISION
    return {}


@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLMClient.call to return test fixtures."""
    from utils.llm import LLMClient

    def mock_call(self, system_prompt, user_prompt, temperature=None):
        return _get_mock_response(system_prompt)

    monkeypatch.setattr(LLMClient, "call", mock_call)

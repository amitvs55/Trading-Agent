"""End-to-end pipeline test with mocked LLM and yfinance."""

import pytest

from models.schemas import PipelineResult


@pytest.fixture
def mock_yfinance(monkeypatch):
    """Mock yfinance to avoid real API calls in tests."""
    import pandas as pd
    import numpy as np
    from unittest.mock import MagicMock

    # Create mock price data (60 days)
    dates = pd.date_range(end="2024-01-15", periods=60, freq="B")
    np.random.seed(42)
    prices = 170 + np.cumsum(np.random.randn(60) * 0.5)
    volumes = np.random.randint(40_000_000, 70_000_000, size=60)

    mock_hist = pd.DataFrame({
        "Open": prices - 0.5,
        "High": prices + 1,
        "Low": prices - 1,
        "Close": prices,
        "Volume": volumes,
    }, index=dates)

    mock_info = {
        "fiftyTwoWeekHigh": 199.62,
        "fiftyTwoWeekLow": 124.17,
        "marketCap": 2750000000000,
        "trailingPE": 28.5,
        "forwardPE": 26.0,
        "trailingEps": 6.15,
        "revenueGrowth": 0.08,
        "profitMargins": 0.26,
        "debtToEquity": 1.5,
        "sector": "Technology",
        "longBusinessSummary": "Apple Inc. designs and sells consumer electronics.",
    }

    mock_news = [
        {"title": "Apple Reports Strong Earnings", "publisher": "Reuters", "link": ""},
        {"title": "iPhone Sales Beat Expectations", "publisher": "Bloomberg", "link": ""},
    ]

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist
    mock_ticker.info = mock_info
    mock_ticker.news = mock_news
    mock_ticker.insider_transactions = None

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", lambda symbol: mock_ticker)


def test_full_pipeline(mock_llm, mock_yfinance):
    """Test the complete pipeline end-to-end with mocks."""
    from orchestrator.pipeline import TradingPipeline

    pipeline = TradingPipeline("AAPL")
    result = pipeline.run()

    assert isinstance(result, PipelineResult)
    assert result.ticker == "AAPL"
    assert result.total_duration_seconds >= 0

    # Verify all stages produced output
    assert result.market_data is not None
    assert result.sentiment is not None
    assert result.news is not None
    assert result.fundamentals is not None
    assert result.bull_case is not None
    assert result.bear_case is not None
    assert result.debate_verdict is not None
    assert result.trade_proposal is not None
    assert len(result.risk_assessments) == 3
    assert result.final_decision is not None
    assert result.execution is not None
    assert result.final_decision.action in ("execute", "hold", "reject")

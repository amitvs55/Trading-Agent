"""Social Media Sentiment Analyst — estimates sentiment via LLM from available data."""

import json
from typing import Any

import yfinance as yf

from agents.base import BaseAgent
from config.prompts import SENTIMENT_ANALYST
from models.schemas import SentimentOutput
from utils.logger import setup_logger

logger = setup_logger("sentiment")


def fetch_news_for_sentiment(ticker: str) -> list[str]:
    """Fetch news headlines from yfinance as proxy for social sentiment."""
    stock = yf.Ticker(ticker)
    news = stock.news or []
    headlines = []
    for item in news[:10]:
        title = item.get("title", "")
        if title:
            headlines.append(title)
    return headlines


class SentimentAgent(BaseAgent):
    name = "sentiment_analyst"
    system_prompt = SENTIMENT_ANALYST
    output_model = SentimentOutput

    def run(self, context: dict[str, Any]) -> SentimentOutput:
        ticker = context["ticker"]
        logger.info("Analyzing sentiment for %s", ticker)

        headlines = fetch_news_for_sentiment(ticker)

        user_prompt = (
            f"Analyze the social media and public sentiment for {ticker}.\n\n"
            f"Available news headlines (use as proxy for public discourse):\n"
            f"{json.dumps(headlines, indent=2)}\n\n"
            f"Based on these headlines and your knowledge of current market sentiment "
            f"around {ticker}, estimate sentiment scores and provide analysis.\n"
            f"Note: Mark data_source as 'llm_estimated' since these are not live social API feeds."
        )

        schema_json = json.dumps(self.output_model.model_json_schema(), indent=2)
        system = (
            f"{self.system_prompt}\n\n"
            f"You MUST respond with valid JSON matching this schema:\n{schema_json}"
        )

        raw = self.llm.call(system, user_prompt)
        raw["agent_name"] = self.name
        raw["ticker"] = ticker
        raw["data_source"] = "llm_estimated"

        return SentimentOutput.model_validate(raw)

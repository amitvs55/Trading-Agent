"""Social Media Sentiment Analyst — estimates sentiment via LLM from available data."""

import json
from typing import Any

import yfinance as yf

from agents.base import BaseAgent
from config.prompts import SENTIMENT_ANALYST
from models.schemas import SentimentOutput
from utils.logger import setup_logger
from utils.untrusted import UNTRUSTED_NOTE, fence

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

        # Only the headlines given here count: the model's own memory of "current sentiment" is
        # out of date and can't be checked, so it isn't asked for (review finding F-17)
        user_prompt = (
            f"Estimate public sentiment for {ticker} using ONLY the recent headlines below, as a proxy "
            f"for public discourse.\n\n{fence('yahoo_finance_headlines', headlines)}\n\n"
            f"Do not use outside knowledge about {ticker} or the market. If there are no headlines, or "
            f"they say nothing about sentiment, return neutral scores with low confidence and say so.\n"
            f"Mark data_source as 'llm_estimated' since these are not live social API feeds."
        )

        schema_json = json.dumps(self.output_model.model_json_schema(), indent=2)
        system = (
            f"{self.system_prompt}\n\n{UNTRUSTED_NOTE}\n\n"
            f"You MUST respond with valid JSON matching this schema:\n{schema_json}"
        )

        raw = self.llm.call(system, user_prompt)
        raw["agent_name"] = self.name
        raw["ticker"] = ticker
        raw["data_source"] = "llm_estimated"

        return SentimentOutput.model_validate(raw)

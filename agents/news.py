"""News Analyst — analyzes financial news from Yahoo Finance feed."""

import json
from typing import Any

import yfinance as yf

from agents.base import BaseAgent
from config.prompts import NEWS_ANALYST
from models.schemas import NewsOutput
from utils.logger import setup_logger

logger = setup_logger("news")


def fetch_news(ticker: str) -> list[dict[str, str]]:
    """Fetch recent news articles from Yahoo Finance."""
    stock = yf.Ticker(ticker)
    news = stock.news or []
    articles = []
    for item in news[:15]:
        article = {
            "title": item.get("title", ""),
            "publisher": item.get("publisher", "Unknown"),
            "link": item.get("link", ""),
        }
        if article["title"]:
            articles.append(article)
    return articles


class NewsAgent(BaseAgent):
    name = "news_analyst"
    system_prompt = NEWS_ANALYST
    output_model = NewsOutput

    def run(self, context: dict[str, Any]) -> NewsOutput:
        ticker = context["ticker"]
        logger.info("Analyzing news for %s", ticker)

        articles = fetch_news(ticker)

        user_prompt = (
            f"Analyze the following recent news for {ticker} and classify each "
            f"article's impact on the stock.\n\n"
            f"Recent articles:\n{json.dumps(articles, indent=2)}"
        )

        schema_json = json.dumps(self.output_model.model_json_schema(), indent=2)
        system = (
            f"{self.system_prompt}\n\n"
            f"You MUST respond with valid JSON matching this schema:\n{schema_json}"
        )

        raw = self.llm.call(system, user_prompt)
        raw["agent_name"] = self.name
        raw["ticker"] = ticker

        return NewsOutput.model_validate(raw)

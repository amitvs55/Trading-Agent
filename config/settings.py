"""Central configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    MODEL_NAME: str = "gpt-4"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_RETRIES: int = 3
    # Optional USD-per-1M-token prices for the cost monitor; override utils/usage.PRICING
    OPENAI_PRICE_INPUT_PER_1M: float | None = None
    OPENAI_PRICE_OUTPUT_PER_1M: float | None = None
    MAX_PARALLEL_WORKERS: int = 4
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    TRADE_LOG_FILE: str = "logs/trades.jsonl"
    DATA_DIR: str = "data"

    # extra="ignore": .env also holds the options tool's KITE_/TELEGRAM_/OPTIONS_ settings
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

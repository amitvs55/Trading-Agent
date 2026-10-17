"""Central configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    # A dated snapshot, not an alias: an alias silently moves to a new model and the same inputs
    # stop giving the same answers. Each call also records the snapshot the API actually used.
    MODEL_NAME: str = "gpt-4o-mini-2024-07-18"
    LLM_TEMPERATURE: float = 0.0           # deterministic as far as the API allows
    LLM_SEED: int = 7                      # OpenAI's best-effort reproducibility seed
    LLM_TIMEOUT_S: float = 60.0
    LLM_MAX_RETRIES: int = 3               # transport retries (timeouts, 429, 5xx); the only retry layer
    # Research pipeline guard rails (the API refuses new runs past these)
    RESEARCH_DAILY_BUDGET_USD: float = 2.0
    RESEARCH_MAX_CONCURRENT: int = 2
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

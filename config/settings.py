"""Central configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    MODEL_NAME: str = "gpt-4"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_RETRIES: int = 3
    MAX_PARALLEL_WORKERS: int = 4
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    TRADE_LOG_FILE: str = "logs/trades.jsonl"
    DATA_DIR: str = "data"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

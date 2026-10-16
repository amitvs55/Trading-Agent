"""Settings for the options signal tool, loaded from environment variables (or .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class OptionsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Zerodha Kite Connect app (developers.kite.trade). KITE_USER_ID is your Zerodha client ID;
    # when set, logins from any other account are rejected at /kite/callback.
    KITE_API_KEY: str = ""
    KITE_API_SECRET: str = ""
    KITE_USER_ID: str = ""

    # Telegram alerts: bot token from @BotFather and your chat id (see Appendix C of the plan)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Dashboard password: when set, /api/options/* needs "Authorization: Bearer <token>".
    # Live NSE data is licensed for personal use, so set this on any public deployment.
    DASHBOARD_TOKEN: str = ""

    # Postgres on Railway; SQLite file for local runs
    DATABASE_URL: str = "sqlite:///data/options.db"

    # Scope and risk (plan §0). OPTIONS_INDICES is JSON, e.g. ["NIFTY"]
    OPTIONS_INDICES: list[str] = ["NIFTY"]
    OPTIONS_CAPITAL: float = 100_000
    OPTIONS_RISK_PER_TRADE_PCT: float = 3.0
    OPTIONS_DAILY_LOSS_STOP_PCT: float = 10.0

    # Signals. Setups listed here are LIVE; all others run in SHADOW mode (plan §1, rule 8)
    OPTIONS_LIVE_SETUPS: list[str] = []
    OPTIONS_RISK_FREE_RATE: float = 0.06

    # Recording
    OPTIONS_STRIKE_WINDOW: int = 15          # strikes each side of ATM, per expiry
    OPTIONS_EXPIRIES_TRACKED: int = 2        # nearest N option expiries
    OPTIONS_STALE_AFTER_S: int = 60          # alert when no ticks arrive for this long in market hours


settings = OptionsSettings()

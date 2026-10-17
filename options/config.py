"""Settings for the options signal tool, loaded from environment variables (or .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class OptionsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Where market data comes from: "angel" (Angel One SmartAPI, free, logs in by itself)
    # or "kite" (Zerodha Kite Connect, paid data plan, daily login from Telegram)
    DATA_PROVIDER: str = "angel"

    # Angel One SmartAPI app (smartapi.angelone.in): the app's API key, your client code,
    # your 4-digit MPIN and the TOTP secret shown when you enable TOTP for the account
    ANGEL_API_KEY: str = ""
    ANGEL_CLIENT_CODE: str = ""
    ANGEL_PIN: str = ""
    ANGEL_TOTP_SECRET: str = ""
    # Only if your SmartAPI account gave historical data a key of its own; else leave empty
    ANGEL_HISTORICAL_API_KEY: str = ""

    # Zerodha Kite Connect app (developers.kite.trade). KITE_USER_ID is your Zerodha client ID;
    # when set, logins from any other account are rejected at /kite/callback.
    KITE_API_KEY: str = ""
    KITE_API_SECRET: str = ""
    KITE_USER_ID: str = ""

    # Telegram alerts: bot token from @BotFather and your chat id (see Appendix C of the plan)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # E-mail alerts (optional): the fallback when Telegram can't deliver, e.g. Gmail with an app password
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_TO: str = ""

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
    OPTIONS_BARS_RETENTION_DAYS: int = 730   # 1-minute bars are the backtest data: keep two years

    @property
    def provider(self) -> str:
        return (self.DATA_PROVIDER or "angel").strip().lower()

    @property
    def provider_name(self) -> str:
        return "Kite" if self.provider == "kite" else "Angel One"

    def missing_provider_keys(self) -> list[str]:
        """Names of the credentials the chosen data provider still needs."""
        if self.provider == "kite":
            needed = {"KITE_API_KEY": self.KITE_API_KEY, "KITE_API_SECRET": self.KITE_API_SECRET}
        else:
            needed = {"ANGEL_API_KEY": self.ANGEL_API_KEY, "ANGEL_CLIENT_CODE": self.ANGEL_CLIENT_CODE,
                      "ANGEL_PIN": self.ANGEL_PIN, "ANGEL_TOTP_SECRET": self.ANGEL_TOTP_SECRET}
        return [name for name, value in needed.items() if not value]


settings = OptionsSettings()

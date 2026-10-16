"""Fake Kite instrument dumps and clocks shared by the options tests."""

from datetime import date, datetime, timedelta

from options.core.calendar import IST
from options.backtest.synthetic import (  # noqa: F401  (re-exported for the tests)
    EXPIRED, FUT_TOKEN, MONTHLY, NEXT_FUT_TOKEN, NIFTY_SPOT_TOKEN, NSE_ROWS, TODAY, VIX_TOKEN, WEEKLY,
    _option, _strikes, nfo_rows, option_token,
)


class Clock:
    """Deterministic clock; sleep() advances it."""

    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def ist(y, m, d, hh, mm, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=IST)


class FakeTicker:
    def __init__(self):
        self.callbacks = None
        self.subscriptions: list[list[int]] = []
        self.stopped = False

    def start(self, on_ticks, on_connect, on_event):
        self.callbacks = {"ticks": on_ticks, "connect": on_connect, "event": on_event}

    def subscribe(self, tokens):
        self.subscriptions.append(list(tokens))

    def stop(self):
        self.stopped = True


class RecordingNotifier:
    def __init__(self):
        self.messages: list[tuple[str, list | None]] = []

    def send(self, text, buttons=None):
        self.messages.append((text, buttons))
        return True

    def texts(self) -> list[str]:
        return [t for t, _ in self.messages]


class FakeBroker:
    LOGIN_URL = "https://kite.zerodha.com/connect/login?api_key=testkey&v=3"

    def __init__(self, bad_tokens=(), user_id="AB1234"):
        self.token = None
        self.bad_tokens = set(bad_tokens)
        self.user_id = user_id
        self.ticker_obj = FakeTicker()

    def login_url(self):
        return self.LOGIN_URL

    def create_session(self, request_token):
        if request_token == "bad":
            raise RuntimeError("TokenException")
        return "tok-123", self.user_id

    def set_access_token(self, token):
        self.token = token

    def profile(self):
        if self.token in self.bad_tokens:
            raise RuntimeError("TokenException")
        return {"user_id": self.user_id}

    def instruments(self, exchange):
        return NSE_ROWS if exchange == "NSE" else nfo_rows()

    def index_prices(self, symbols):
        return {s: 25262.0 for s in symbols}

    def previous_closes(self, symbols):
        return {}

    def historical(self, token, start, end, interval="minute", oi=False):
        return []

    def ticker(self):
        return self.ticker_obj

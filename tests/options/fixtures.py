"""Fake Kite instrument dumps and clocks shared by the options tests."""

from datetime import date, datetime, timedelta

from options.core.calendar import IST

TODAY = date(2026, 10, 16)              # Friday
WEEKLY = date(2026, 10, 19)             # Monday: Tue 20 Oct is Dussehra
MONTHLY = date(2026, 10, 27)
EXPIRED = date(2026, 10, 13)

NIFTY_SPOT_TOKEN = 256265
VIX_TOKEN = 264969
FUT_TOKEN = 9001
NEXT_FUT_TOKEN = 9002

NSE_ROWS = [
    {"instrument_token": NIFTY_SPOT_TOKEN, "tradingsymbol": "NIFTY 50", "name": "NIFTY 50",
     "segment": "INDICES", "instrument_type": "EQ", "expiry": "", "strike": 0.0, "lot_size": 0, "tick_size": 0.0},
    {"instrument_token": VIX_TOKEN, "tradingsymbol": "INDIA VIX", "name": "INDIA VIX",
     "segment": "INDICES", "instrument_type": "EQ", "expiry": "", "strike": 0.0, "lot_size": 0, "tick_size": 0.0},
    {"instrument_token": 738561, "tradingsymbol": "RELIANCE", "name": "RELIANCE INDUSTRIES",
     "segment": "NSE", "instrument_type": "EQ", "expiry": "", "strike": 0.0, "lot_size": 1, "tick_size": 0.1},
]


def option_token(expiry: date, strike: float, right: str) -> int:
    return int(f"{expiry:%m%d}{int(strike)}{1 if right == 'CE' else 2}")


def _option(expiry: date, strike: float, right: str, lot: int = 65) -> dict:
    return {"instrument_token": option_token(expiry, strike, right),
            "tradingsymbol": f"NIFTY{expiry:%y%b}{int(strike)}{right}".upper(),
            "name": "NIFTY", "segment": "NFO-OPT", "instrument_type": right, "expiry": expiry,
            "strike": float(strike), "lot_size": lot, "tick_size": 0.05}


def _strikes() -> list[int]:
    near = list(range(24500, 26001, 50))                     # 50-point steps near the money
    far = list(range(23000, 24500, 100)) + list(range(26100, 27600, 100))
    return sorted(near + far)


def nfo_rows() -> list[dict]:
    rows = [
        {"instrument_token": FUT_TOKEN, "tradingsymbol": "NIFTY26OCTFUT", "name": "NIFTY",
         "segment": "NFO-FUT", "instrument_type": "FUT", "expiry": MONTHLY, "strike": 0.0,
         "lot_size": 65, "tick_size": 0.1},
        {"instrument_token": NEXT_FUT_TOKEN, "tradingsymbol": "NIFTY26NOVFUT", "name": "NIFTY",
         "segment": "NFO-FUT", "instrument_type": "FUT", "expiry": date(2026, 11, 24), "strike": 0.0,
         "lot_size": 65, "tick_size": 0.1},
        # Other indices and expired contracts must be ignored
        {"instrument_token": 7777, "tradingsymbol": "BANKNIFTY26OCTFUT", "name": "BANKNIFTY",
         "segment": "NFO-FUT", "instrument_type": "FUT", "expiry": MONTHLY, "strike": 0.0,
         "lot_size": 30, "tick_size": 0.1},
        _option(EXPIRED, 25300, "CE"),
    ]
    for exp in (WEEKLY, MONTHLY):
        for k in _strikes():
            rows += [_option(exp, k, "CE"), _option(exp, k, "PE")]
    return rows


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

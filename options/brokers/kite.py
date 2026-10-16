"""Thin wrapper over Zerodha's official kiteconnect SDK.

The SDK (and Twisted, which KiteTicker runs on) is imported lazily so the rest of the
package and its tests don't need it installed. Market data only: this tool places no
orders, so Zerodha's static-IP rule for order endpoints does not apply (plan §10).
"""

from datetime import datetime
from typing import Callable


class KiteBroker:
    def __init__(self, api_key: str, api_secret: str, access_token: str | None = None):
        from kiteconnect import KiteConnect

        self._api_key = api_key
        self._api_secret = api_secret
        self._access_token = access_token
        self.kite = KiteConnect(api_key=api_key)
        if access_token:
            self.kite.set_access_token(access_token)

    def login_url(self) -> str:
        return self.kite.login_url()

    def create_session(self, request_token: str) -> tuple[str, str | None]:
        """Exchange the request_token from the login redirect for today's access token."""
        data = self.kite.generate_session(request_token, api_secret=self._api_secret)
        self.set_access_token(data["access_token"])
        return data["access_token"], data.get("user_id")

    def set_access_token(self, access_token: str) -> None:
        self._access_token = access_token
        self.kite.set_access_token(access_token)

    def profile(self) -> dict:
        return self.kite.profile()

    def instruments(self, exchange: str) -> list[dict]:
        return self.kite.instruments(exchange)

    def index_prices(self, tradingsymbols: list[str]) -> dict[str, float]:
        """Last traded value of NSE indices, e.g. ["NIFTY 50"] → {"NIFTY 50": 25262.4}."""
        data = self.kite.ltp([f"NSE:{s}" for s in tradingsymbols])
        return {s: float(data[f"NSE:{s}"]["last_price"]) for s in tradingsymbols}

    def previous_closes(self, symbols: list[str]) -> dict[str, float]:
        """Previous session close of NSE equities, e.g. ["HDFCBANK"] → {"HDFCBANK": 1712.3}."""
        data = self.kite.ohlc([f"NSE:{s}" for s in symbols])
        return {s: float(data[f"NSE:{s}"]["ohlc"]["close"]) for s in symbols if f"NSE:{s}" in data}

    def historical(self, token: int, start: datetime, end: datetime, interval: str = "minute",
                   oi: bool = False) -> list[dict]:
        """Candles {date, open, high, low, close, volume[, oi]}; interval e.g. "minute", "day"."""
        return self.kite.historical_data(token, start, end, interval, continuous=False, oi=oi)

    def ticker(self) -> "KiteTickerAdapter":
        return KiteTickerAdapter(self._api_key, self._access_token)


class KiteTickerAdapter:
    """KiteTicker on Twisted's reactor thread, with subscribe/stop marshalled onto that thread."""

    def __init__(self, api_key: str, access_token: str):
        from kiteconnect import KiteTicker

        self._kws = KiteTicker(api_key, access_token, reconnect=True,
                               reconnect_max_tries=300, reconnect_max_delay=60)

    def start(self, on_ticks: Callable[[list[dict]], None], on_connect: Callable[[], None],
              on_event: Callable[[str, str], None]) -> None:
        kws = self._kws
        kws.on_ticks = lambda ws, ticks: on_ticks(ticks)
        kws.on_connect = lambda ws, response: on_connect()
        kws.on_close = lambda ws, code, reason: on_event("close", f"{code} {reason}")
        kws.on_error = lambda ws, code, reason: on_event("error", f"{code} {reason}")
        kws.on_reconnect = lambda ws, attempt: on_event("reconnect", f"attempt {attempt}")
        kws.on_noreconnect = lambda ws: on_event("noreconnect", "gave up reconnecting")
        kws.connect(threaded=True)

    def subscribe(self, tokens: list[int]) -> None:
        """Subscribe in FULL mode (LTP, OI, 5-level depth). Tokens added while disconnected
        are picked up by the recorder's on_connect resubscription."""
        from twisted.internet import reactor

        def _do():
            if self._kws.is_connected():
                self._kws.subscribe(tokens)
                self._kws.set_mode(self._kws.MODE_FULL, tokens)

        reactor.callFromThread(_do)

    def stop(self) -> None:
        from twisted.internet import reactor

        reactor.callFromThread(self._kws.close)

"""Angel One SmartAPI adapter: free market data, handed over in Kite's shapes.

Everything downstream (contract reference, recorder, bar aggregator, engine, storage) was
written against Kite's instrument dump, tick dicts and candles, so this adapter translates
Angel's into exactly those. Market data only: it places no orders.

Login is automatic: client code + MPIN + a TOTP generated from the account's TOTP secret,
so the daily session starts without anyone tapping a link.

The SDK (smartapi-python, pyotp) is imported lazily so the rest of the package and its
tests don't need it installed.
"""

import logging
import threading
import time as _time
from datetime import date, datetime, timedelta
from typing import Callable

from options.core.calendar import IST

logger = logging.getLogger("options.angel")

SCRIP_MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"

# Angel numbers instruments per exchange; Kite's tokens are unique across exchanges, and the
# bar store keys on the token alone. F&O and BSE tokens are shifted out of the NSE cash range.
NFO_OFFSET = 1_000_000_000
BSE_OFFSET = 3_000_000_000

# Angel's index tokens → the tradingsymbols the rest of the tool uses (Kite's names)
INDEX_SYMBOLS = {
    "99926000": "NIFTY 50",
    "99926009": "NIFTY BANK",
    "99926037": "NIFTY FIN SERVICE",
    "99926017": "INDIA VIX",
}
INDEX_TOKENS = {symbol: int(token) for token, symbol in INDEX_SYMBOLS.items()}
BSE_INDEX_SYMBOLS = {"99919000": "SENSEX"}            # display only: the dashboard's live ticker

INTERVALS = {"minute": "ONE_MINUTE", "3minute": "THREE_MINUTE", "5minute": "FIVE_MINUTE",
             "15minute": "FIFTEEN_MINUTE", "30minute": "THIRTY_MINUTE", "60minute": "ONE_HOUR",
             "day": "ONE_DAY"}
# At least this long between two history requests (candles or OI), on every path. Angel documents
# 3 a second, but on 19 Oct 2026 it answered "Access denied because of exceeding access rate" to
# requests 0.35–0.4 s apart and kept refusing for over an hour.
HISTORY_GAP_S = 1.0
# The longest span one historical request may cover, per interval (Angel's documented limits)
MAX_SPAN_DAYS = {"ONE_MINUTE": 30, "THREE_MINUTE": 60, "FIVE_MINUTE": 100, "FIFTEEN_MINUTE": 200,
                 "THIRTY_MINUTE": 200, "ONE_HOUR": 400, "ONE_DAY": 2000}

# WebSocket exchange types and modes (SmartWebSocketV2)
NSE_CM, NSE_FO, BSE_CM = 1, 2, 3
LTP_MODE, QUOTE_MODE, SNAP_QUOTE_MODE = 1, 2, 3


class AngelError(RuntimeError):
    pass


def brief_error(e: Exception) -> str:
    """Type and message, safe to log: AngelError carries Angel's own code and message, and the SDK's
    errors carry Angel's reply body (e.g. "Couldn't parse the JSON response … b'Access denied …'"),
    never the request headers. Anything else (requests, sockets) is logged by type only, since
    those messages can include request URLs."""
    sdk = type(e).__module__.startswith("SmartApi")
    if isinstance(e, AngelError) or sdk:
        return f"{type(e).__name__}: {' '.join(str(e).split())[:200]}"
    return type(e).__name__


# ── Pure translation (no SDK, no network) ─────────────────────────────────────

def to_internal(exchange: str, token: str | int) -> int:
    return int(token) + {"NFO": NFO_OFFSET, "BSE": BSE_OFFSET}.get(exchange, 0)


def to_angel(internal: int) -> tuple[str, str]:
    """Internal token → (exchange, Angel token string)."""
    if internal >= BSE_OFFSET:
        return "BSE", str(internal - BSE_OFFSET)
    if internal >= NFO_OFFSET:
        return "NFO", str(internal - NFO_OFFSET)
    return "NSE", str(internal)


def _expiry(value: str) -> date | None:
    return datetime.strptime(value, "%d%b%Y").date() if value else None


def to_kite_rows(master: list[dict], exchange: str) -> list[dict]:
    """Angel scrip-master rows of one exchange as Kite instrument-dump rows.

    NSE: the indices (segment INDICES, Kite's names) and the cash equities (-EQ series).
    NFO: index futures and options. Angel states strikes and tick sizes in paise.
    """
    out: list[dict] = []
    for r in master:
        if r.get("exch_seg") != exchange:
            continue
        kind = r.get("instrumenttype") or ""
        if exchange == "NSE":
            if kind == "AMXIDX":
                out.append({"instrument_token": int(r["token"]),
                            "tradingsymbol": INDEX_SYMBOLS.get(r["token"], r["symbol"].upper()),
                            "name": r["name"], "segment": "INDICES", "instrument_type": "EQ",
                            "exchange": "NSE", "expiry": "", "strike": 0.0, "lot_size": 0, "tick_size": 0.0})
            elif kind == "" and r["symbol"].endswith("-EQ"):
                out.append({"instrument_token": int(r["token"]), "tradingsymbol": r["symbol"][:-3],
                            "name": r["name"], "segment": "NSE", "instrument_type": "EQ", "exchange": "NSE",
                            "expiry": "", "strike": 0.0, "lot_size": int(r.get("lotsize") or 1),
                            "tick_size": float(r.get("tick_size") or 0) / 100})
        elif exchange == "NFO" and kind in ("OPTIDX", "FUTIDX"):
            is_option = kind == "OPTIDX"
            out.append({"instrument_token": to_internal("NFO", r["token"]), "tradingsymbol": r["symbol"],
                        "name": r["name"], "segment": "NFO-OPT" if is_option else "NFO-FUT",
                        "instrument_type": r["symbol"][-2:] if is_option else "FUT", "exchange": "NFO",
                        "expiry": _expiry(r.get("expiry") or ""),
                        "strike": float(r["strike"]) / 100 if is_option else 0.0,
                        "lot_size": int(r.get("lotsize") or 0),
                        "tick_size": float(r.get("tick_size") or 0) / 100})
    return out


def _timestamp(value) -> datetime:
    ts = datetime.fromisoformat(str(value))
    return ts.astimezone(IST) if ts.tzinfo else ts.replace(tzinfo=IST)


def candles_to_kite(data: list | None) -> list[dict]:
    """[[ts, o, h, l, c, v], ...] → Kite candles {date, open, high, low, close, volume}."""
    return [{"date": _timestamp(c[0]), "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
             "close": float(c[4]), "volume": int(c[5] or 0)} for c in data or []]


def merge_oi(candles: list[dict], oi_rows: list | None) -> list[dict]:
    """Attach open interest by candle time; rows come as {time, oi} (or [time, oi]). A minute with no
    OI row gets None (unknown), never 0, which the flow agent would read as all positions closed."""
    by_time: dict[datetime, int] = {}
    for row in oi_rows or []:
        ts, oi = (row.get("time"), row.get("oi")) if isinstance(row, dict) else (row[0], row[1])
        if ts is not None and oi is not None:
            by_time[_timestamp(ts)] = int(oi)
    return [{**c, "oi": by_time.get(c["date"])} for c in candles]


def _levels(side: list[dict] | None) -> list[dict]:
    return [{"price": lvl["price"] / 100, "quantity": int(lvl.get("quantity") or 0),
             "orders": int(lvl.get("no of orders") or 0)}
            for lvl in side or [] if lvl.get("price")]


def tick_to_kite(msg: dict) -> dict | None:
    """One parsed SmartWebSocketV2 message → a Kite FULL-mode tick dict (prices in rupees)."""
    if msg.get("token") in (None, "") or not msg.get("last_traded_price"):
        return None
    exchange = {NSE_FO: "NFO", BSE_CM: "BSE"}.get(msg.get("exchange_type"), "NSE")
    tick: dict = {"instrument_token": to_internal(exchange, msg["token"]),
                  "last_price": msg["last_traded_price"] / 100}
    if msg.get("exchange_timestamp"):
        tick["exchange_timestamp"] = datetime.fromtimestamp(msg["exchange_timestamp"] / 1000, tz=IST)
    if msg.get("volume_trade_for_the_day") is not None:
        tick["volume_traded"] = int(msg["volume_trade_for_the_day"])
    if msg.get("open_interest") is not None:
        tick["oi"] = int(msg["open_interest"])

    # The SDK's two book sides are labelled inconsistently across versions; the side with
    # the lower best price is the bid.
    a, b = _levels(msg.get("best_5_buy_data")), _levels(msg.get("best_5_sell_data"))
    if a or b:
        if a and b and a[0]["price"] > b[0]["price"]:
            a, b = b, a
        tick["depth"] = {"buy": a, "sell": b}
    return tick


def subscription_groups(tokens: list[int]) -> dict[int, list[dict]]:
    """Internal tokens → {mode: token_list} for SmartWebSocketV2.subscribe.

    Indices stream LTP only; equities QUOTE (price + volume); F&O SNAP_QUOTE (+ OI and depth).
    """
    groups: dict[int, dict[int, list[str]]] = {}
    for internal in tokens:
        exchange, token = to_angel(internal)
        if exchange == "NFO":
            mode, ex_type = SNAP_QUOTE_MODE, NSE_FO
        elif exchange == "BSE":
            mode, ex_type = (LTP_MODE if token in BSE_INDEX_SYMBOLS else QUOTE_MODE), BSE_CM
        elif token in INDEX_SYMBOLS:
            mode, ex_type = LTP_MODE, NSE_CM
        else:
            mode, ex_type = QUOTE_MODE, NSE_CM
        groups.setdefault(mode, {}).setdefault(ex_type, []).append(token)
    return {mode: [{"exchangeType": ex, "tokens": toks} for ex, toks in by_ex.items()]
            for mode, by_ex in groups.items()}


def _quiet_sdk_logs() -> None:
    """The SDK's logger writes request headers (API key, JWT) on errors and every ping to a
    file under logs/. Nothing of it is wanted: this tool logs through utils.logger."""
    try:
        import logzero
        logzero.logger.disabled = True
    except ImportError:
        pass


# ── The broker ────────────────────────────────────────────────────────────────

class AngelBroker:
    """Kite-compatible market data from Angel One SmartAPI."""

    auto_login = True
    name = "Angel One"

    def __init__(self, api_key: str, client_code: str, pin: str, totp_secret: str,
                 master_fn: Callable[[], list[dict]] | None = None, pause: Callable[[float], None] = _time.sleep,
                 api=None, historical_api_key: str = "", historical_api=None):
        self._api_key = api_key
        self.client_code = client_code
        self._pin = pin
        self._totp_secret = totp_secret
        self._master_fn = master_fn or self._download_master
        self._master: list[dict] | None = None
        self._pause = pause
        self._jwt: str | None = None
        self._feed_token: str | None = None
        self.api = api if api is not None else self._client(api_key)
        # Some SmartAPI accounts issue a separate key for historical data; it logs in on its own
        if historical_api is None and historical_api_key and historical_api_key != api_key:
            historical_api = self._client(historical_api_key)
        self.history_api = historical_api

    @staticmethod
    def _client(api_key: str):
        from SmartApi import SmartConnect

        client = SmartConnect(api_key=api_key)
        _quiet_sdk_logs()
        return client

    # Login ────────────────────────────────────────────────────────────────────

    def login(self) -> str:
        """Log in with MPIN + TOTP; returns the client code. Raises AngelError on refusal."""
        data = self._session(self.api)
        self._jwt = data["jwtToken"]                   # "Bearer …", as the WebSocket wants it
        self._feed_token = data.get("feedToken") or self.api.getfeedToken()
        if self.history_api is not None:
            self._session(self.history_api, "historical-data key")
        return data.get("clientcode") or self.client_code

    def _session(self, client, which: str = "login") -> dict:
        import pyotp

        totp = pyotp.TOTP(self._totp_secret.replace(" ", "")).now()
        resp = client.generateSession(self.client_code, self._pin, totp) or {}
        data = resp.get("data") or {}
        if not resp.get("status") or not data.get("jwtToken"):
            raise AngelError(f"{which} refused ({resp.get('errorcode') or 'no code'}): "
                             f"{resp.get('message') or 'no message'}")
        return data

    def profile(self) -> dict:
        return {"user_id": self.client_code}

    # Reference data ───────────────────────────────────────────────────────────

    @staticmethod
    def _download_master() -> list[dict]:
        import requests

        resp = requests.get(SCRIP_MASTER_URL, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def _scrip_master(self) -> list[dict]:
        if self._master is None:
            self._master = self._master_fn()
        return self._master

    def instruments(self, exchange: str) -> list[dict]:
        return to_kite_rows(self._scrip_master(), exchange)

    # REST market data ─────────────────────────────────────────────────────────

    def _checked(self, resp: dict | None, what: str):
        if not resp or not resp.get("status"):
            resp = resp or {}
            raise AngelError(f"{what} failed ({resp.get('errorcode') or 'no code'}): {resp.get('message') or 'no message'}")
        return resp.get("data")

    def index_prices(self, tradingsymbols: list[str]) -> dict[str, float]:
        """Last value of NSE indices by Kite name, e.g. ["NIFTY 50"] → {"NIFTY 50": 25262.4}."""
        tokens = {str(INDEX_TOKENS[s]): s for s in tradingsymbols}
        data = self._checked(self.api.getMarketData("LTP", {"NSE": list(tokens)}), "index prices")
        fetched = {str(row["symbolToken"]): float(row["ltp"]) for row in (data or {}).get("fetched", [])}
        missing = [s for t, s in tokens.items() if t not in fetched]
        if missing:
            raise AngelError(f"no price for {', '.join(missing)}")
        return {tokens[t]: price for t, price in fetched.items() if t in tokens}

    def live_index_tokens(self) -> dict[str, int]:
        """The dashboard ticker's indices → internal tokens. SENSEX is looked up in the scrip master
        (BSE, AMXIDX) and falls back to Angel's long-standing token if the lookup finds nothing."""
        sensex = next(iter(BSE_INDEX_SYMBOLS))
        try:
            for r in self._scrip_master():
                if (r.get("exch_seg") == "BSE" and r.get("instrumenttype") == "AMXIDX"
                        and "SENSEX" in {(r.get("symbol") or "").upper(), (r.get("name") or "").upper()}):
                    sensex = str(r["token"])
                    break
        except Exception as e:
            logger.warning("SENSEX lookup in the scrip master failed (%s); using token %s", brief_error(e), sensex)
        BSE_INDEX_SYMBOLS.setdefault(sensex, "SENSEX")
        return {"NIFTY 50": INDEX_TOKENS["NIFTY 50"], "SENSEX": to_internal("BSE", sensex)}

    def quotes(self, tokens: dict[str, int]) -> dict[str, dict]:
        """name → internal token, to name → {ltp, close, net_change, bid, ask, oi, volume} from one FULL
        market-data call per 50 instruments. In market hours `close` is the previous session's close
        (ltp − net change); bid and ask are the best of the 5-level depth (prices in rupees)."""
        wanted: dict[tuple[str, str], str] = {}
        for name, internal in tokens.items():
            wanted[to_angel(internal)] = name
        out: dict[str, dict] = {}
        keys = list(wanted)
        for i in range(0, len(keys), 50):
            req: dict[str, list[str]] = {}
            for ex, tok in keys[i:i + 50]:
                req.setdefault(ex, []).append(tok)
            data = self._checked(self.api.getMarketData("FULL", req), "quotes")
            for row in (data or {}).get("fetched", []):
                name = wanted.get((row.get("exchange"), str(row.get("symbolToken"))))
                if name is None:
                    continue
                def num(key, src=row):
                    v = src.get(key) if src else None
                    return float(v) if v not in (None, "") else None
                depth = row.get("depth") or {}
                best = {side: max((lvl for lvl in depth.get(side) or [] if num("price", lvl)),
                                  key=lambda lvl: num("price", lvl) * (1 if side == "buy" else -1), default=None)
                        for side in ("buy", "sell")}
                out[name] = {"ltp": num("ltp"), "close": num("close"), "net_change": num("netChange"),
                             "bid": num("price", best["buy"]), "ask": num("price", best["sell"]),
                             "oi": num("opnInterest"), "volume": num("tradeVolume")}
        return out

    def previous_closes(self, symbols: list[str]) -> dict[str, float]:
        """Previous session close of NSE equities, from daily candles (unambiguous semantics)."""
        tokens = {r["tradingsymbol"]: int(r["instrument_token"]) for r in self.instruments("NSE")
                  if r["segment"] == "NSE"}
        today = datetime.now(IST).date()
        out: dict[str, float] = {}
        for sym in symbols:
            if sym not in tokens:
                continue
            candles = self.historical(tokens[sym], datetime.now(IST) - timedelta(days=12), datetime.now(IST), "day")
            before = [c for c in candles if c["date"].date() < today]
            if before:
                out[sym] = before[-1]["close"]
        return out

    def historical(self, token: int, start: datetime, end: datetime, interval: str = "minute",
                   oi: bool = False) -> list[dict]:
        """Kite-shaped candles; long ranges are split into the spans Angel allows per request.

        Open interest is a bonus, not a requirement: if Angel's OI-history call fails, the candles
        are kept with OI unknown (on 19 Oct 2026 a failing OI call took the whole futures history down
        with it, and with it every signal for the day). A span Angel refuses is retried in 7-day pieces.

        If the separate historical-data key fails (on 19 Oct 2026 every request through it came back as
        a non-JSON DataException while the live feed was fine), the main login is used instead, and
        stays in use for the rest of the session once it has worked.
        """
        self.history_notes: list[str] = []
        if self.history_api is not None and not getattr(self, "_history_via_main", False):
            try:
                return self._historical(self.history_api, token, start, end, interval, oi)
            except Exception as e:
                self.history_notes.append(f"historical-data key failed ({brief_error(e)}); trying the main login")
            out = self._historical(self.api, token, start, end, interval, oi)
            self._history_via_main = True
            self.history_notes.append("main login worked; using it for history from now on")
            return out
        return self._historical(self.api, token, start, end, interval, oi)

    def _historical(self, api, token: int, start: datetime, end: datetime, interval: str, oi: bool) -> list[dict]:
        exchange, angel_token = to_angel(token)
        span = timedelta(days=MAX_SPAN_DAYS[INTERVALS[interval]])
        candles: list[dict] = []
        frm = start
        while frm < end:
            to = min(end, frm + span)
            candles += self._history_span(api, exchange, angel_token, interval, frm, to, oi)
            frm = to
        seen: set[datetime] = set()
        return [c for c in candles if not (c["date"] in seen or seen.add(c["date"]))]

    def _history_span(self, api, exchange: str, angel_token: str, interval: str, frm: datetime, to: datetime,
                      oi: bool, piece: timedelta = timedelta(days=7)) -> list[dict]:
        params = {"exchange": exchange, "symboltoken": angel_token, "interval": INTERVALS[interval],
                  "fromdate": frm.astimezone(IST).strftime("%Y-%m-%d %H:%M"),
                  "todate": to.astimezone(IST).strftime("%Y-%m-%d %H:%M")}
        try:
            part = candles_to_kite(self._history_request(lambda: api.getCandleData(dict(params)), "historical candles"))
        except AngelError as e:
            if to - frm <= piece:
                raise
            self.history_notes.append(f"candles in pieces after: {e}")
            out, a = [], frm
            while a < to:                              # smaller requests; a piece that still fails raises
                b = min(to, a + piece)
                out += self._history_span(api, exchange, angel_token, interval, a, b, oi, piece)
                a = b
            return out
        if oi and exchange == "NFO":
            try:
                part = merge_oi(part, self._history_request(lambda: api.getOIData(dict(params)), "historical OI"))
            except AngelError as e:
                self.history_notes.append(f"no OI history: {e}")
                part = [{**c, "oi": None} for c in part]
        return part

    def _history_request(self, call: Callable[[], dict | None], what: str):
        """One history request, at least HISTORY_GAP_S after the previous one ended (whichever login,
        thread or caller made it): the only place history requests are sent from."""
        lock = self.__dict__.setdefault("_history_lock", threading.Lock())
        clock = getattr(self, "_clock", _time.monotonic)
        with lock:
            last = getattr(self, "_last_history_at", None)
            if last is not None and (wait := HISTORY_GAP_S - (clock() - last)) > 0:
                self._pause(wait)
            try:
                return self._checked(call(), what)
            finally:
                self._last_history_at = clock()

    # Streaming ────────────────────────────────────────────────────────────────

    def ticker(self) -> "AngelTickerAdapter":
        if not (self._jwt and self._feed_token):
            raise AngelError("log in before starting the market-data stream")
        return AngelTickerAdapter(self._api_key, self.client_code, self._jwt, self._feed_token)


class AngelTickerAdapter:
    """SmartWebSocketV2 on a thread of its own, reconnecting with backoff.

    The SDK's own retry runs inside its error callback and its close callback doesn't match
    the websocket library's signature, so each connection here is a fresh socket and this
    loop does the reconnecting; the recorder resubscribes on every connect, as with Kite.
    """

    def __init__(self, api_key: str, client_code: str, jwt: str, feed_token: str, *,
                 max_reconnects: int = 300, max_delay_s: float = 60,
                 socket_factory: Callable[[], object] | None = None,
                 sleep: Callable[[float], None] = _time.sleep):
        self._api_key, self._client_code, self._jwt, self._feed_token = api_key, client_code, jwt, feed_token
        self._max_reconnects = max_reconnects
        self._max_delay_s = max_delay_s
        self._factory = socket_factory or self._new_socket
        self._sleep = sleep
        self._sws = None
        self._connected = False
        self._stopping = False
        self._lock = threading.Lock()
        self._correlation = 0
        self._thread: threading.Thread | None = None
        self._on_ticks: Callable[[list[dict]], None] = lambda ticks: None
        self._on_connect: Callable[[], None] = lambda: None
        self._on_event: Callable[[str, str], None] = lambda kind, detail: None

    def _new_socket(self):
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2

        sws = SmartWebSocketV2(self._jwt, self._api_key, self._client_code, self._feed_token, max_retry_attempt=0)
        _quiet_sdk_logs()
        sws.input_request_dict = {}                    # the SDK shares this dict across instances
        sws._on_close = lambda *args: None             # its signature doesn't match websocket-client's
        return sws

    def start(self, on_ticks: Callable[[list[dict]], None], on_connect: Callable[[], None],
              on_event: Callable[[str, str], None]) -> None:
        self._on_ticks, self._on_connect, self._on_event = on_ticks, on_connect, on_event
        self._thread = threading.Thread(target=self._run, name="angel-ws", daemon=True)
        self._thread.start()

    def _data(self, msg: dict) -> None:
        try:
            tick = tick_to_kite(msg)
        except Exception as e:                         # a malformed packet must not end the stream
            self._on_event("error", f"bad packet: {type(e).__name__}")
            return
        if tick:
            self._on_ticks([tick])

    def _opened(self) -> None:
        self._connected = True
        self._on_connect()

    def _run(self) -> None:
        attempt = 0
        while not self._stopping:
            sws = self._factory()
            sws.on_open = lambda wsapp: self._opened()
            sws.on_data = lambda wsapp, msg: self._data(msg)
            sws.on_error = lambda *args: self._on_event("error", " ".join(str(a) for a in args)[:200])
            with self._lock:
                self._sws = sws
            try:
                sws.connect()                          # blocks until the socket closes
            except Exception as e:
                self._on_event("error", type(e).__name__)
            was_open, self._connected = self._connected, False
            with self._lock:
                self._sws = None
            if self._stopping:
                break

            self._on_event("close", "socket closed")
            attempt = 1 if was_open else attempt + 1
            if attempt > self._max_reconnects:
                self._on_event("noreconnect", "gave up reconnecting")
                break
            self._on_event("reconnect", f"attempt {attempt}")
            waited, delay = 0.0, min(self._max_delay_s, 2 ** min(attempt, 6))
            while waited < delay and not self._stopping:
                self._sleep(0.5)
                waited += 0.5

    def subscribe(self, tokens: list[int]) -> None:
        """Tokens added while disconnected are picked up by the recorder's resubscription on connect."""
        with self._lock:
            sws = self._sws
        if sws is None or not self._connected or not tokens:
            return
        for mode, token_list in subscription_groups(tokens).items():
            self._correlation += 1
            try:
                sws.subscribe(f"ow{self._correlation:08d}", mode, token_list)
            except Exception as e:
                self._on_event("error", f"subscribe failed: {type(e).__name__}")

    def stop(self) -> None:
        self._stopping = True
        with self._lock:
            sws = self._sws
        if sws is not None:
            try:
                sws.close_connection()
            except Exception:
                logging.getLogger("options.angel").debug("closing the socket failed", exc_info=True)

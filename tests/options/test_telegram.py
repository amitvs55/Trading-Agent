import logging

import requests

from options.notify import LogNotifier, TelegramNotifier, make_notifier
from options.config import OptionsSettings

SECRET = "123456:SECRET-TOKEN"


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}
        self.text = str(self._body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def notifier(responses, sleeps=None):
    return TelegramNotifier(SECRET, "42", session=FakeSession(responses),
                            sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_payload_uses_html_and_inline_url_buttons():
    n = notifier([])
    body = n.payload("<b>hi</b>", [("Login to Kite", "https://kite.zerodha.com/connect/login")])
    assert body["chat_id"] == "42" and body["parse_mode"] == "HTML"
    assert body["reply_markup"] == {"inline_keyboard": [[{"text": "Login to Kite",
                                                          "url": "https://kite.zerodha.com/connect/login"}]]}
    assert len(n.payload("x" * 5000)["text"]) == 4096


def test_send_success():
    n = notifier([FakeResponse(200, {"ok": True})])
    assert n.send("hello") is True
    assert n._session.calls[0][0].endswith("/sendMessage")


def test_rate_limit_is_retried_after_the_given_delay():
    sleeps = []
    n = notifier([FakeResponse(429, {"parameters": {"retry_after": 7}}), FakeResponse(200)], sleeps)
    assert n.send("hello") is True
    assert sleeps == [7.0]


def test_client_errors_are_not_retried():
    n = notifier([FakeResponse(400, {"description": "can't parse entities"})])
    assert n.send("<b>broken") is False
    assert len(n._session.calls) == 1


def test_network_errors_never_leak_the_bot_token(caplog):
    err = requests.ConnectionError(f"Max retries exceeded with url: /bot{SECRET}/sendMessage")
    n = notifier([err, err, err])
    with caplog.at_level(logging.WARNING):
        assert n.send("hello") is False
    assert "ConnectionError" in caplog.text
    assert SECRET not in caplog.text


def test_make_notifier_falls_back_to_log_only():
    assert isinstance(make_notifier(OptionsSettings(TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="")), LogNotifier)
    assert isinstance(make_notifier(OptionsSettings(TELEGRAM_BOT_TOKEN=SECRET, TELEGRAM_CHAT_ID="42")),
                      TelegramNotifier)

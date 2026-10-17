"""Telegram Bot API notifier (free; no templates or messaging windows)."""

import time

import requests

from options.notify.base import Buttons, Delivery, logger

MAX_LEN = 4096          # Telegram's limit per message


class TelegramNotifier:
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, session: requests.Session | None = None,
                 timeout: float = 10.0, retries: int = 3, sleep=time.sleep):
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._session = session or requests.Session()
        self._timeout = timeout
        self._retries = retries
        self._sleep = sleep

    def payload(self, text: str, buttons: Buttons | None = None) -> dict:
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN - 1] + "…"
        body = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML",
                "disable_web_page_preview": True}
        if buttons:
            body["reply_markup"] = {"inline_keyboard": [[{"text": label, "url": url}] for label, url in buttons]}
        return body

    def deliver(self, text: str, buttons: Buttons | None = None) -> Delivery:
        """One attempt, no sleeping: the outbox decides when to retry."""
        try:
            resp = self._session.post(self._url, json=self.payload(text, buttons), timeout=self._timeout)
        except requests.RequestException as e:
            # Never log the exception text: requests puts the URL, and so the bot token, in it
            return Delivery(False, error=f"network: {type(e).__name__}")
        if resp.status_code == 200:
            return Delivery(True)
        if resp.status_code == 429 or resp.status_code >= 500:
            try:
                wait = float(resp.json().get("parameters", {}).get("retry_after", 0)) or None
            except ValueError:
                wait = None
            return Delivery(False, retry_after=wait, error=f"Telegram busy ({resp.status_code})")
        # 400 (bad chat id, bad HTML), 401 (bad token), 403 (bot blocked): retrying can't help
        return Delivery(False, permanent=True, error=f"Telegram rejected it: {resp.status_code} {resp.text[:160]}")

    def send(self, text: str, buttons: Buttons | None = None) -> bool:
        """Deliver now, retrying a few times (blocking). The session uses the outbox instead."""
        for attempt in range(1, self._retries + 1):
            result = self.deliver(text, buttons)
            if result.ok:
                return True
            if result.permanent:
                logger.warning("%s", result.error)
                return False
            logger.warning("Telegram send failed (attempt %d): %s", attempt, result.error)
            if attempt < self._retries:
                self._sleep(min(result.retry_after or 2 ** attempt, 30))
        return False

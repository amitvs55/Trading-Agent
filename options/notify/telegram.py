"""Telegram Bot API notifier (free; no templates or messaging windows)."""

import time

import requests

from options.notify.base import Buttons, logger

MAX_LEN = 4096          # Telegram's limit per message


class TelegramNotifier:
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

    def send(self, text: str, buttons: Buttons | None = None) -> bool:
        body = self.payload(text, buttons)
        for attempt in range(1, self._retries + 1):
            try:
                resp = self._session.post(self._url, json=body, timeout=self._timeout)
            except requests.RequestException as e:
                # Never log the exception text: requests puts the URL, and so the bot token, in it
                logger.warning("Telegram send failed (attempt %d): %s", attempt, type(e).__name__)
                self._sleep(2 ** attempt)
                continue
            if resp.status_code == 200:
                return True
            if resp.status_code == 429 or resp.status_code >= 500:
                try:
                    wait = float(resp.json().get("parameters", {}).get("retry_after", 2 ** attempt))
                except ValueError:
                    wait = 2 ** attempt
                logger.warning("Telegram busy (%d), retrying in %.0fs", resp.status_code, wait)
                self._sleep(min(wait, 30))
                continue
            logger.warning("Telegram rejected message: %d %s", resp.status_code, resp.text[:200])
            return False
        return False

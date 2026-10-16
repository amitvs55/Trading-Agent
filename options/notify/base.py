"""Notifier interface. Messages use Telegram-style HTML: <b>, <i>, <code>, <pre>."""

from typing import Protocol

from utils.logger import setup_logger

logger = setup_logger("options.notify")

Buttons = list[tuple[str, str]]   # (label, url)


class Notifier(Protocol):
    def send(self, text: str, buttons: Buttons | None = None) -> bool:
        """Deliver a message; never raises. Returns False if it could not be delivered."""
        ...


class LogNotifier:
    """Fallback when no alert channel is configured: messages only go to the log."""

    def send(self, text: str, buttons: Buttons | None = None) -> bool:
        logger.info("[notify] %s", text)
        return True

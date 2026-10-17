"""Notifier interface. Messages use Telegram-style HTML: <b>, <i>, <code>, <pre>."""

from dataclasses import dataclass
from typing import Protocol

from utils.logger import setup_logger

logger = setup_logger("options.notify")

Buttons = list[tuple[str, str]]   # (label, url)


@dataclass(frozen=True)
class Delivery:
    """Outcome of one delivery attempt on a channel."""
    ok: bool
    permanent: bool = False             # retrying can't help (bad token, bad chat id, …)
    retry_after: float | None = None    # seconds the channel asked us to wait
    error: str | None = None


class Notifier(Protocol):
    def send(self, text: str, buttons: Buttons | None = None) -> bool:
        """Deliver a message; never raises. Returns False if it could not be delivered."""
        ...


class Channel(Protocol):
    """A delivery channel the outbox can drive one attempt at a time."""
    name: str

    def deliver(self, text: str, buttons: Buttons | None = None) -> Delivery: ...


class LogNotifier:
    """Fallback when no alert channel is configured: messages only go to the log."""
    name = "log"

    def send(self, text: str, buttons: Buttons | None = None) -> bool:
        logger.info("[notify] %s", text)
        return True

    def deliver(self, text: str, buttons: Buttons | None = None) -> Delivery:
        self.send(text, buttons)
        return Delivery(True)

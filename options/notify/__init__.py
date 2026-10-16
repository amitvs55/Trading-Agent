"""Alert channels. Telegram now; WhatsApp can be added behind the same Notifier interface."""

from options.notify.base import LogNotifier, Notifier
from options.notify.telegram import TelegramNotifier


def make_notifier(settings) -> Notifier:
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
        return TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
    return LogNotifier()


__all__ = ["LogNotifier", "Notifier", "TelegramNotifier", "make_notifier"]

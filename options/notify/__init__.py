"""Alert channels: Telegram first, e-mail as the fallback, both behind the Notifier interface.

The recording session sends through the outbox (durable, non-blocking); short-lived callers
(API requests, the supervisor) send directly.
"""

from options.notify.base import Channel, Delivery, LogNotifier, Notifier
from options.notify.email import EmailNotifier
from options.notify.outbox import OutboxNotifier
from options.notify.telegram import TelegramNotifier


def make_notifier(settings) -> Notifier:
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
        return TelegramNotifier(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID)
    if email := make_email(settings):
        return email
    return LogNotifier()


def make_email(settings) -> EmailNotifier | None:
    if settings.SMTP_HOST and settings.ALERT_EMAIL_TO:
        return EmailNotifier(settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USERNAME,
                             settings.SMTP_PASSWORD, settings.ALERT_EMAIL_TO,
                             sender=settings.SMTP_USERNAME or settings.ALERT_EMAIL_TO)
    return None


def make_outbox(settings, store, **kwargs) -> OutboxNotifier:
    """Primary channel Telegram (or e-mail, or the log), with e-mail as the fallback when both exist."""
    primary = make_notifier(settings)
    fallback = make_email(settings) if isinstance(primary, TelegramNotifier) else None
    return OutboxNotifier(store, primary, fallback, **kwargs)


__all__ = ["Channel", "Delivery", "EmailNotifier", "LogNotifier", "Notifier", "OutboxNotifier",
           "TelegramNotifier", "make_email", "make_notifier", "make_outbox"]

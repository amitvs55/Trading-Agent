"""E-mail alerts over SMTP: the fallback when Telegram can't deliver (or the only channel).

Works with any SMTP account, e.g. Gmail with an app password (smtp.gmail.com, port 587).
Messages are written in Telegram's small HTML subset, so they go out as HTML with a
plain-text part for clients that don't render it.
"""

import re
import smtplib
import ssl
from email.message import EmailMessage
from html import escape, unescape

from options.notify.base import Buttons, Delivery, logger

_TAGS = re.compile(r"<[^>]+>")


def plain(text: str) -> str:
    return unescape(_TAGS.sub("", text))


class EmailNotifier:
    name = "email"

    def __init__(self, host: str, port: int, username: str, password: str, to: str, sender: str | None = None,
                 timeout: float = 15.0, smtp_factory=None):
        self.host, self.port = host, int(port or 587)
        self.username, self.password = username, password
        self.to = [a.strip() for a in to.split(",") if a.strip()]
        self.sender = sender or username or self.to[0]
        self.timeout = timeout
        self._smtp = smtp_factory

    def message(self, text: str, buttons: Buttons | None = None) -> EmailMessage:
        body = plain(text)
        first = body.strip().splitlines()[0] if body.strip() else "Alert"
        msg = EmailMessage()
        msg["Subject"] = f"[TradingAgents] {first[:120]}"
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.to)
        links = "\n".join(f"{label}: {url}" for label, url in buttons or [])
        msg.set_content(body + (f"\n\n{links}" if links else ""))
        html = text.replace("\n", "<br>")
        if buttons:
            html += "<br><br>" + "<br>".join(f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'
                                             for label, url in buttons)
        msg.add_alternative(f"<div style=\"font-family:system-ui,sans-serif\">{html}</div>", subtype="html")
        return msg

    def _connect(self):
        if self._smtp:
            return self._smtp(self.host, self.port)
        if self.port == 465:
            return smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ssl.create_default_context())
        smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        smtp.starttls(context=ssl.create_default_context())
        return smtp

    def verify(self) -> None:
        """Connect and log in without sending anything (the Connectors page's health check)."""
        with self._connect() as smtp:
            if self.username:
                smtp.login(self.username, self.password)

    def deliver(self, text: str, buttons: Buttons | None = None) -> Delivery:
        try:
            with self._connect() as smtp:
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(self.message(text, buttons))
            return Delivery(True)
        except smtplib.SMTPAuthenticationError:
            return Delivery(False, permanent=True, error="e-mail login rejected (check the app password)")
        except smtplib.SMTPRecipientsRefused:
            return Delivery(False, permanent=True, error="e-mail recipient refused")
        except (smtplib.SMTPException, OSError) as e:
            return Delivery(False, error=f"e-mail: {type(e).__name__}")

    def send(self, text: str, buttons: Buttons | None = None) -> bool:
        result = self.deliver(text, buttons)
        if not result.ok:
            logger.warning("E-mail alert failed: %s", result.error)
        return result.ok

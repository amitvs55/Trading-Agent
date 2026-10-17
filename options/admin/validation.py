"""Format checks for connector values, so only well-formed keys reach the database.

`clean(key, raw)` tidies a pasted value (trims it, upper-cases client codes, drops the spaces
an authenticator app puts in a TOTP secret) and returns it with a plain-language problem, or
None when it looks right. The Connectors page runs it on every save; the health checks run it
again before calling a service, so a typo is reported as a typo, not as a failed login.
"""

import base64
import binascii
import re
from typing import Callable
from urllib.parse import parse_qs, urlparse

Check = Callable[[str], str | None]

UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _angel_key(v: str) -> str | None:
    if UUID.fullmatch(v):
        return "That's the app's secret key. Use the API key shown next to it on smartapi.angelone.in → My APIs."
    if not re.fullmatch(r"[A-Za-z0-9]{6,64}", v):
        return "An Angel One API key is letters and digits only, like AbC12xYz. Copy it from smartapi.angelone.in → My APIs."
    return None


def _angel_client(v: str) -> str | None:
    if not re.fullmatch(r"[A-Z0-9]{4,15}", v) or not re.search(r"[A-Z]", v):
        return "Client code is your Angel One client ID, like A123456 (letters and digits only)."
    return None


def _angel_pin(v: str) -> str | None:
    return None if re.fullmatch(r"\d{4}", v) else "MPIN is the 4-digit PIN you use to log in to the Angel One app."


def _totp_normalize(v: str) -> str:
    if v.lower().startswith("otpauth://"):                        # a pasted QR-code link carries the secret
        v = parse_qs(urlparse(v).query).get("secret", [""])[0]
    return re.sub(r"\s+", "", v).upper().rstrip("=")


def _totp(v: str) -> str | None:
    if re.fullmatch(r"\d{6}", v):
        return ("That's a 6-digit one-time code, which changes every 30 seconds. Enter the secret text shown "
                "under the QR code instead.")
    bad = "The TOTP secret is the long text shown under the QR code (letters A–Z and digits 2–7)."
    if not re.fullmatch(r"[A-Z2-7]{16,128}", v):
        return bad
    try:
        base64.b32decode(v + "=" * (-len(v) % 8))
    except (binascii.Error, ValueError):
        return bad
    return None


def _kite_key(v: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9]{6,64}", v):
        return "A Kite API key is letters and digits only. Copy it from developers.kite.trade → your app."
    return None


def _kite_secret(v: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9]{16,64}", v):
        return "A Kite API secret is 16–64 letters and digits. Copy it from developers.kite.trade → your app."
    return None


def _kite_user(v: str) -> str | None:
    if not re.fullmatch(r"[A-Z0-9]{4,10}", v) or not re.search(r"[A-Z]", v):
        return "A Zerodha client ID looks like AB1234."
    return None


def _bot_token(v: str) -> str | None:
    if re.fullmatch(r"-?\d+", v):
        return "That's a chat ID. The bot token comes from @BotFather and has a colon in it, like 123456789:AAH…"
    if not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{30,64}", v):
        return "A bot token looks like 123456789:AAH… (digits, a colon, then about 35 characters). Copy it from @BotFather."
    return None


def _chat_id(v: str) -> str | None:
    if re.fullmatch(r"-?\d{3,20}", v):
        return None
    get_id = "Send /start to @userinfobot in Telegram and copy the Id number it replies with."
    if v.startswith("@") and v.lower().endswith("bot"):
        return f"That's your bot's username. Chat ID is your own Telegram ID, a number. {get_id}"
    if ":" in v:
        return f"That looks like the bot token. Chat ID is your own Telegram ID, a number. {get_id}"
    if v.startswith("@"):
        return f"A username doesn't work here. Chat ID is your Telegram ID, a number. {get_id}"
    return f"Chat ID is a number, like 987654321 (group IDs start with -). {get_id}"


def _openai_key(v: str) -> str | None:
    if not re.fullmatch(r"sk-[A-Za-z0-9_-]{20,}", v):
        return "OpenAI API keys start with sk-. Create one at platform.openai.com/api-keys."
    return None


def _model(v: str) -> str | None:
    return None if re.fullmatch(r"[A-Za-z0-9._:/-]{2,80}", v) else "Model names look like gpt-4o-mini."


EMAIL = re.compile(r"[^@\s,]+@[^@\s,]+\.[A-Za-z]{2,}")


def _smtp_host(v: str) -> str | None:
    if "@" in v:
        return "That's an e-mail address. The SMTP host is the mail server, like smtp.gmail.com."
    if not re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", v):
        return "The SMTP host is the mail server's name, like smtp.gmail.com."
    return None


def _smtp_port(v: str) -> str | None:
    if not re.fullmatch(r"\d{1,5}", v) or not 1 <= int(v) <= 65535:
        return "The port is a number: 587 (STARTTLS, most providers) or 465 (SSL)."
    return None


def _smtp_user(v: str) -> str | None:
    return None if re.fullmatch(r"\S{1,254}", v) else "The SMTP username is usually your full e-mail address."


def _smtp_password_normalize(v: str) -> str:
    # Gmail shows app passwords as four groups of four letters; the spaces aren't part of it
    return v.replace(" ", "") if re.fullmatch(r"[a-z]{4}( [a-z]{4}){3}", v) else v


def _usd(v: str) -> str | None:
    try:
        ok = 0 <= float(v) <= 100
    except ValueError:
        ok = False
    return None if ok else "Enter a dollar amount between 0 and 100, like 2.00 (0 means no limit)."


def _email_to(v: str) -> str | None:
    parts = [a.strip() for a in v.split(",") if a.strip()]
    if not parts or not all(EMAIL.fullmatch(a) for a in parts):
        return "Enter one or more e-mail addresses, separated by commas."
    return None


NORMALIZERS: dict[str, Callable[[str], str]] = {
    "ANGEL_CLIENT_CODE": str.upper,
    "ANGEL_TOTP_SECRET": _totp_normalize,
    "KITE_USER_ID": str.upper,
    "SMTP_PASSWORD": _smtp_password_normalize,
    "SMTP_HOST": str.lower,
}

CHECKS: dict[str, Check] = {
    "ANGEL_API_KEY": _angel_key,
    "ANGEL_HISTORICAL_API_KEY": _angel_key,
    "ANGEL_CLIENT_CODE": _angel_client,
    "ANGEL_PIN": _angel_pin,
    "ANGEL_TOTP_SECRET": _totp,
    "KITE_API_KEY": _kite_key,
    "KITE_API_SECRET": _kite_secret,
    "KITE_USER_ID": _kite_user,
    "TELEGRAM_BOT_TOKEN": _bot_token,
    "TELEGRAM_CHAT_ID": _chat_id,
    "OPENAI_API_KEY": _openai_key,
    "MODEL_NAME": _model,
    "SMTP_HOST": _smtp_host,
    "SMTP_PORT": _smtp_port,
    "SMTP_USERNAME": _smtp_user,
    "ALERT_EMAIL_TO": _email_to,
    "RESEARCH_DAILY_BUDGET_USD": _usd,
}


def normalize(key: str, value: str) -> str:
    value = value.strip()
    fn = NORMALIZERS.get(key)
    return fn(value) if fn else value


def clean(key: str, raw: str) -> tuple[str, str | None]:
    """(tidied value, problem or None)."""
    value = normalize(key, raw)
    if "•" in value:
        return value, "That's the masked placeholder, not the value. Paste the real one."
    check = CHECKS.get(key)
    return value, check(value) if check else None


def problem(key: str, value: str) -> str | None:
    return clean(key, value)[1] if value else None


def first_problem(values: dict[str, str]) -> str | None:
    """The first format problem among already-set values (used by the health checks)."""
    for key, value in values.items():
        if p := problem(key, value or ""):
            return p
    return None

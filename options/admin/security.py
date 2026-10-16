"""Password hashing, session tokens and at-rest encryption of connector secrets."""

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken

PBKDF2_ITERATIONS = 600_000          # OWASP 2023 guidance for PBKDF2-HMAC-SHA256
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or PBKDF2_ITERATIONS
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt, digest = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def password_problem(password: str, username: str = "") -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if username and password.lower() == username.lower():
        return "The password can't be the same as the username."
    return None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Only digests of session tokens are stored, so a database leak can't be replayed."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_setup_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"            # no 0/O, 1/I lookalikes
    raw = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


def normalize_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").upper()


class Cipher:
    """Fernet (AES-128-CBC + HMAC) keyed from any secret string."""

    def __init__(self, secret: str):
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as e:
            raise ValueError("stored secret can't be decrypted with the current key") from e


def new_secret_key() -> str:
    return secrets.token_urlsafe(48)

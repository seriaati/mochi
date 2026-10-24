"""Encrypts secrets stored in the database, the Discord webhook URL and bot token, with
ENCRYPTION_KEY (Fernet: AES-128-CBC with an HMAC). The key never touches the database, so a
leaked dump alone doesn't reveal them."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class NoKey(Exception):
    """ENCRYPTION_KEY isn't set."""


def _fernet() -> Fernet:
    if settings.encryption_key is None:
        raise NoKey("ENCRYPTION_KEY is not set")
    # Fernet wants 32 random-looking bytes; any long string is hashed into them.
    digest = hashlib.sha256(settings.encryption_key.get_secret_value().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def can_encrypt() -> bool:
    return settings.encryption_key is not None


def encrypt(secret: str) -> str:
    """Raises NoKey without ENCRYPTION_KEY."""
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str | None:
    """None when there's no key, or the secret was encrypted with a different one."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except NoKey, InvalidToken:
        return None

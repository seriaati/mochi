"""The dashboard password, stored only as a scrypt hash in AUTH_PASSWORD_HASH.

Hashes are self-describing, `scrypt$n$r$p$salt$hash` (salt and hash in unpadded URL-safe
base64), so the cost can be raised later without breaking hashes made earlier.

Make a hash for backend/.env with:

    uv run python -m app.passwords hash-password

This module imports nothing from the app, so the command works even while .env is invalid.
"""

import argparse
import base64
import hashlib
import hmac
import secrets
import sys
from getpass import getpass

# scrypt cost: 32 MiB of memory and roughly 50-100 ms per check.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    # OpenSSL's default memory cap (32 MiB) is just under what n=2**15, r=8 needs.
    maxmem = 128 * r * (n + p + 2) + 2**20
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=length)


def hash_password(password: str, *, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = _scrypt(password, salt, n, r, p, KEY_BYTES)
    return f"scrypt${n}${r}${p}${_b64encode(salt)}${_b64encode(key)}"


def verify_password(password: str, encoded: str) -> bool:
    """Whether `password` matches a hash from hash_password, compared in constant time."""
    scheme, n, r, p, salt, key = encoded.split("$")
    if scheme != "scrypt":
        raise ValueError(f"unknown password hash scheme {scheme!r}")
    expected = _b64decode(key)
    actual = _scrypt(password, _b64decode(salt), int(n), int(r), int(p), len(expected))
    return hmac.compare_digest(actual, expected)


def fingerprint(encoded: str) -> str:
    """Identifies a password hash, so sessions can end when it changes."""
    return hashlib.sha256(encoded.encode()).hexdigest()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.passwords")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hash-password", help="prompt for a password and print its hash")
    parser.parse_args(argv)

    password = getpass("New dashboard password: ")
    if not password:
        sys.exit("The password can't be empty.")
    if getpass("Repeat it: ") != password:
        sys.exit("The passwords don't match.")
    print(hash_password(password))
    print(
        "Put it in backend/.env as AUTH_PASSWORD_HASH='...' (single quotes keep the $ signs "
        "literal), then restart the API. Existing sessions end.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

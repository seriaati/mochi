"""Talking to Discord: posting to the reminder webhook, and looking users up with the bot token.
Tests replace `post` and `fetch_user` so nothing leaves the machine."""

import logging
from dataclasses import dataclass

import httpx2 as httpx
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app import crypto
from app.config import settings
from app.models import AppSettings

log = logging.getLogger(__name__)

CDN = "https://cdn.discordapp.com"


@dataclass(frozen=True)
class Config:
    """The Discord setup saved in Settings. Held here so everything reads it without a query:
    loaded at startup and replaced whenever settings are saved, which works because the API
    runs as one process."""

    webhook_url: str | None = None  # None: reminders are off
    mention_user_id: str | None = None  # the user's own ID, @mentioned in reminders
    bot_token: SecretStr | None = None  # None: profile sync is off


config = Config()


def load(session: Session) -> None:
    """Reads the saved setup into `config`. A webhook URL or token that can't be decrypted (no
    ENCRYPTION_KEY, or a different one) counts as unset."""
    global config
    row = session.get_one(AppSettings, 1)
    token = None
    if row.discord_bot_token_encrypted is not None:
        token = crypto.decrypt(row.discord_bot_token_encrypted)
        if token is None:
            log.warning("Can't decrypt the Discord bot token: check ENCRYPTION_KEY")
    webhook_url = row.discord_webhook_url
    if webhook_url is None and row.discord_webhook_url_encrypted is not None:
        log.warning("Can't decrypt the Discord webhook URL: check ENCRYPTION_KEY")
    mention = row.discord_mention_user_id
    config = Config(
        webhook_url=webhook_url,
        mention_user_id=str(mention) if mention is not None else None,
        bot_token=SecretStr(token) if token is not None else None,
    )


def post(content: str) -> None:
    """Post a message to the configured webhook, pinging only the configured user."""
    if config.webhook_url is None:
        raise RuntimeError("No Discord webhook URL is set")
    mention = config.mention_user_id
    response = httpx.post(
        config.webhook_url,
        json={"content": content, "allowed_mentions": {"users": [mention] if mention else []}},
        timeout=10,
    )
    response.raise_for_status()


@dataclass(frozen=True)
class User:
    username: str
    global_name: str | None  # the display name, if they set one
    avatar_url: str


class RateLimited(Exception):
    """Discord answered 429. Nothing should be looked up for `retry_after` seconds."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited for {retry_after:g}s")
        self.retry_after = retry_after


def avatar_url(user_id: int, avatar: str | None, discriminator: str | None = None) -> str:
    """The user's avatar at 128px (animated WebP for an "a_" hash), or Discord's default avatar
    when they have none."""
    if avatar is None:
        legacy = discriminator not in (None, "0")  # accounts still on name#1234
        index = int(discriminator) % 5 if legacy else (user_id >> 22) % 6
        return f"{CDN}/embed/avatars/{index}.png"
    if avatar.startswith("a_"):
        return f"{CDN}/avatars/{user_id}/{avatar}.webp?size=128&animated=true"
    return f"{CDN}/avatars/{user_id}/{avatar}.png?size=128"


def parse_user(data: dict) -> User:
    """A user object from GET /users/{id}."""
    return User(
        username=data["username"],
        global_name=data.get("global_name") or None,
        avatar_url=avatar_url(int(data["id"]), data.get("avatar"), data.get("discriminator")),
    )


def _retry_after(response: httpx.Response) -> float:
    try:
        return float(response.json()["retry_after"])
    except ValueError, KeyError, TypeError:
        return float(response.headers.get("Retry-After", 1))


def fetch_user(user_id: int, timeout: float) -> User | None:
    """Look a user up by ID with the bot token. None when Discord has no such user. Raises
    RateLimited on 429 and httpx.HTTPError when the lookup fails otherwise."""
    if config.bot_token is None:
        raise RuntimeError("No Discord bot token is set")
    response = httpx.get(
        f"{settings.discord_api_base}/users/{user_id}",
        headers={"Authorization": f"Bot {config.bot_token.get_secret_value()}"},
        timeout=timeout,
    )
    if response.status_code == 404:
        return None
    if response.status_code == 429:
        raise RateLimited(_retry_after(response))
    response.raise_for_status()
    return parse_user(response.json())

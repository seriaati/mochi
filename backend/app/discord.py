"""Talking to Discord: posting to the reminder webhook, and looking users up with the bot token.
Tests replace `post` and `fetch_user` so nothing leaves the machine."""

from dataclasses import dataclass

import httpx2 as httpx

from app.config import settings

CDN = "https://cdn.discordapp.com"


def post(content: str) -> None:
    """Post a message to the configured webhook, pinging only the configured user."""
    if settings.discord_webhook_url is None:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set")
    mention = settings.discord_mention_user_id
    response = httpx.post(
        settings.discord_webhook_url,
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
    if settings.discord_bot_token is None:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set")
    response = httpx.get(
        f"{settings.discord_api_base}/users/{user_id}",
        headers={"Authorization": f"Bot {settings.discord_bot_token.get_secret_value()}"},
        timeout=timeout,
    )
    if response.status_code == 404:
        return None
    if response.status_code == 429:
        raise RateLimited(_retry_after(response))
    response.raise_for_status()
    return parse_user(response.json())

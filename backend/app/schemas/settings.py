import re
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, BeforeValidator, StringConstraints
from pydantic_core import PydanticCustomError

from app.schemas.clients import Snowflake
from app.schemas.common import blank_to_none


def _known_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        raise PydanticCustomError(
            "unknown_timezone",
            "Unknown timezone “{name}”. Use an IANA name like Asia/Taipei.",
            {"name": name},
        ) from None
    return name


# An IANA timezone name, e.g. Asia/Taipei or Asia/Tokyo.
TimeZoneName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    AfterValidator(_known_timezone),
]


# A short name; blank means none.
OptionalName = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None,
    BeforeValidator(blank_to_none),
]

# A small PNG, JPEG or WebP image as a base64 data: URL. The frontend shrinks uploads to fit.
LogoDataUrl = Annotated[
    str,
    StringConstraints(
        max_length=200_000, pattern=r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/]+=*$"
    ),
]


class SettingsText(BaseModel):
    """The settings without the logo, which is too big to be worth sending to MCP clients."""

    timezone: TimeZoneName  # due dates, "today" and the 09:00 reminders follow it
    user_name: OptionalName = None  # what the dashboard calls the user; None uses their Discord name
    studio_name: OptionalName = None  # shown in the top bar; None shows "Studio"


# Only Discord's own webhooks: the API posts to this URL.
_WEBHOOK = re.compile(r"https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+")


def _discord_webhook(url: str) -> str:
    if not _WEBHOOK.fullmatch(url):
        raise PydanticCustomError(
            "discord_webhook",
            "Use a Discord webhook URL, like https://discord.com/api/webhooks/…",
        )
    return url


# Discord: channel settings > Integrations > Webhooks > New Webhook > Copy Webhook URL.
WebhookUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=500),
    AfterValidator(_discord_webhook),
]


class SettingsIn(SettingsText):
    studio_logo: LogoDataUrl | None = None  # shown in the top bar; None shows a plain mark
    # Maintenance reminders post here; None turns them off.
    discord_webhook_url: Annotated[WebhookUrl | None, BeforeValidator(blank_to_none)] = None
    # The user's own Discord ID, @mentioned in each reminder.
    discord_mention_user_id: Annotated[Snowflake | None, BeforeValidator(blank_to_none)] = None


class SettingsOut(SettingsIn):
    # The bot token is write-only (PUT /api/settings/discord-bot-token): only whether one is set.
    discord_bot_token_set: bool
    encryption_key_set: bool  # without ENCRYPTION_KEY, no webhook URL or bot token can be saved


class BotTokenIn(BaseModel):
    # Discord's bot tokens are three dot-separated base64url parts.
    token: Annotated[
        str, StringConstraints(strip_whitespace=True, pattern=r"^[\w-]+\.[\w-]+\.[\w-]+$")
    ]

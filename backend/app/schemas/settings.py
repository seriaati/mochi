from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, BeforeValidator, StringConstraints
from pydantic_core import PydanticCustomError

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


class SettingsIn(SettingsText):
    studio_logo: LogoDataUrl | None = None  # shown in the top bar; None shows a plain mark


class SettingsOut(SettingsIn):
    pass

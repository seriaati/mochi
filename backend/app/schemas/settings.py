from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, StringConstraints
from pydantic_core import PydanticCustomError


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


class SettingsIn(BaseModel):
    timezone: TimeZoneName  # due dates, "today" and the 09:00 reminders follow it


class SettingsOut(SettingsIn):
    pass

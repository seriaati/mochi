import enum
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, model_validator

from app.maintenance import ClientFlag
from app.models import ContactKind
from app.schemas.common import Name, OptionalName, OptionalText, blank_to_none

# Discord user IDs are 64-bit snowflakes. They travel as strings because
# JavaScript numbers can't hold them exactly.
Snowflake = Annotated[int, Field(ge=10**16, lt=2**63), PlainSerializer(str, return_type=str)]


class ContactIn(BaseModel):
    kind: ContactKind
    value: Name
    discord_user_id: Annotated[Snowflake | None, BeforeValidator(blank_to_none)] = None

    @model_validator(mode="after")
    def _discord_id_only_for_discord(self) -> Self:
        if self.discord_user_id is not None and self.kind != ContactKind.DISCORD:
            raise ValueError("discord_user_id is only allowed on Discord contacts")
        return self


class ProfileStatus(enum.StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"  # Discord has no user with this ID
    ERROR = "error"  # the last lookup failed; profile fields are from the last good one, if any
    PENDING = "pending"  # not looked up yet
    OFF = "off"  # sync is off: no bot token in Settings


class DiscordProfileOut(BaseModel):
    """A Discord user's profile as last synced. Profile fields are null until a lookup works."""

    status: ProfileStatus
    synced_at: datetime | None  # the last lookup, whatever its result
    username: str | None
    display_name: str | None  # their display name, else the username
    avatar_url: str | None  # their avatar, or Discord's default one


class ContactOut(ContactIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Discord contacts with a user ID; otherwise null.
    discord_profile: DiscordProfileOut | None = None


class ClientIn(BaseModel):
    name: Name
    contact_person: OptionalName = None
    notes: OptionalText = None


class ClientCreate(ClientIn):
    """A new client. A Discord user ID also adds them as a Discord contact; the name may then be
    left out to use their Discord display name."""

    name: OptionalName = None
    discord_user_id: Annotated[Snowflake | None, BeforeValidator(blank_to_none)] = None

    @model_validator(mode="after")
    def _name_or_discord_id(self) -> Self:
        if self.name is None and self.discord_user_id is None:
            raise ValueError("Enter a name or a Discord user ID")
        return self


class ClientUpdate(ClientIn):
    """Edits a client. A Discord user ID, when sent, goes on their first Discord contact (one is
    added if they have none); null takes it off. Left out, their contacts stay as they are."""

    discord_user_id: Annotated[Snowflake | None, BeforeValidator(blank_to_none)] = None


class ClientOut(ClientIn):
    id: int
    created_at: datetime
    contacts: list[ContactOut]
    # From the primary Discord contact: the first one synced. Null without one.
    avatar_url: str | None
    discord_name: str | None
    project_count: int
    lifetime_billed: int  # project prices plus their additions, NTD
    monthly_maintenance: int  # active retainers, NTD
    maintenance_flag: ClientFlag | None  # the card's small flag: overdue, due or auto-pay
    maintenance_due_on: date | None  # with the "due" flag

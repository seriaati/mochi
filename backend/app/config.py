from typing import Annotated

from pydantic import BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.common import blank_to_none


class Settings(BaseSettings):
    """Deployment config from the environment or .env. User preferences such as the
    timezone live in the database instead (see AppSettings)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://freelance:freelance@localhost:5433/freelance"

    # Maintenance reminders. Without a webhook URL, reminders are off.
    discord_webhook_url: Annotated[str | None, BeforeValidator(blank_to_none)] = None
    # Your own Discord user ID, @mentioned in each reminder.
    discord_mention_user_id: Annotated[
        Annotated[str, Field(pattern=r"^\d{17,20}$")] | None, BeforeValidator(blank_to_none)
    ] = None

    # Discord profile sync: names and avatars of clients' Discord contacts and of the mention
    # user. Without a bot token, sync is off. The token never leaves the backend.
    discord_bot_token: Annotated[SecretStr | None, BeforeValidator(blank_to_none)] = None
    # Only changed to point the lookups at a local mock API while testing.
    discord_api_base: str = "https://discord.com/api/v10"


settings = Settings()

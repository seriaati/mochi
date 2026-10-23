import re
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.common import blank_to_none


def _password_hash(value: SecretStr) -> SecretStr:
    if not re.fullmatch(r"scrypt\$\d+\$\d+\$\d+\$[\w-]+\$[\w-]+", value.get_secret_value()):
        raise ValueError(
            "expected scrypt$n$r$p$salt$hash from `python -m app.passwords hash-password`"
        )
    return value


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

    # Login. The scrypt hash of the dashboard password, from `python -m app.passwords hash-password`.
    # Without it, nobody can log in.
    auth_password_hash: Annotated[
        Annotated[SecretStr, AfterValidator(_password_hash)] | None, BeforeValidator(blank_to_none)
    ] = None
    # The session cookie's Domain, e.g. ".example.com" when the API and the frontend are on
    # sibling subdomains. Unset means host-only, which suits development through the Vite proxy.
    cookie_domain: Annotated[str | None, BeforeValidator(blank_to_none)] = None
    # Send the session cookie over HTTPS only. Turn off for development over plain HTTP.
    cookie_secure: bool = True
    # Frontend origins allowed to call the API cross-site with the cookie, comma-separated, e.g.
    # "https://dash.example.com". Unset means same origin only (development through the proxy).
    frontend_origin: str = ""

    @property
    def frontend_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.frontend_origin.split(",") if o.strip()]


settings = Settings()

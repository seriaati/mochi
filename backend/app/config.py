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
    timezone and the Discord setup live in the database instead (see AppSettings)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://freelance:freelance@localhost:5433/freelance"

    # The Discord webhook, mention user and bot token are set in the app (see AppSettings).
    # Only changed to point the lookups at a local mock API while testing.
    discord_api_base: str = "https://discord.com/api/v10"

    # Encrypts the Discord webhook URL, bot token and Keni API token in the database: any random
    # string of 32+ characters. Without it, none can be saved. A new key makes them unreadable,
    # so they need entering again.
    encryption_key: Annotated[
        Annotated[SecretStr, Field(min_length=32)] | None, BeforeValidator(blank_to_none)
    ] = None

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

    # The API's public URL, e.g. "https://api.example.com". MCP clients connect to /mcp under it,
    # and it is the issuer of their OAuth tokens.
    public_url: str = "http://localhost:8000"

    # This deployment is the public demo, whose data `python -m app.demo reset` wipes and fills
    # with made-up records. Never set it where the data matters.
    demo: bool = False

    @property
    def frontend_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.frontend_origin.split(",") if o.strip()]

    @property
    def app_url(self) -> str:
        """Where the frontend is: the first FRONTEND_ORIGIN, else the Vite dev server."""
        return self.frontend_origins[0] if self.frontend_origins else "http://localhost:5173"


settings = Settings()

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import Session

from app import crypto, discord
from app.db import SessionDep
from app.models import AppSettings
from app.schemas.settings import BotTokenIn, SettingsIn, SettingsOut

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _row(session: Session) -> AppSettings:
    # The migration creates this single row.
    return session.get_one(AppSettings, 1)


def _out(row: AppSettings) -> SettingsOut:
    return SettingsOut(
        **dict(SettingsIn.model_validate(row, from_attributes=True)),
        discord_bot_token_set=row.discord_bot_token_set,
        encryption_key_set=crypto.can_encrypt(),
    )


def _save(session: Session, row: AppSettings) -> SettingsOut:
    session.commit()
    discord.load(session)  # the Discord setup is read from memory (see discord.Config)
    return _out(row)


@router.get("")
def get_settings(session: SessionDep) -> SettingsOut:
    return _out(_row(session))


@router.put("")
def update_settings(body: SettingsIn, session: SessionDep) -> SettingsOut:
    """Replaces every setting but the bot token, which has its own route."""
    row = _row(session)
    try:
        for field, value in body.model_dump().items():
            setattr(row, field, value)  # discord_webhook_url encrypts (see AppSettings)
    except crypto.NoKey:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Set ENCRYPTION_KEY on the API before saving a webhook URL"
        ) from None
    return _save(session, row)


@router.put("/discord-bot-token")
def set_bot_token(body: BotTokenIn, session: SessionDep) -> SettingsOut:
    """Stores the bot token encrypted, which turns profile sync on."""
    if not crypto.can_encrypt():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Set ENCRYPTION_KEY on the API before saving a bot token"
        )
    row = _row(session)
    row.discord_bot_token_encrypted = crypto.encrypt(body.token)
    return _save(session, row)


@router.delete("/discord-bot-token")
def delete_bot_token(session: SessionDep) -> SettingsOut:
    """Forgets the bot token, which turns profile sync off."""
    row = _row(session)
    row.discord_bot_token_encrypted = None
    return _save(session, row)

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.db import SessionDep
from app.models import AppSettings
from app.schemas.settings import SettingsIn, SettingsOut

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _row(session: Session) -> AppSettings:
    # The migration creates this single row.
    return session.get_one(AppSettings, 1)


@router.get("")
def get_settings(session: SessionDep) -> SettingsOut:
    return SettingsOut.model_validate(_row(session), from_attributes=True)


@router.put("")
def update_settings(body: SettingsIn, session: SessionDep) -> SettingsOut:
    row = _row(session)
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    session.commit()
    return SettingsOut.model_validate(row, from_attributes=True)

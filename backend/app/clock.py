"""The one place "now", "today" and the user's timezone come from.

The timezone is read from the database each time, so a change in Settings applies to the
next request and the reminder loop's next tick. Tests pin the time by overriding `get_now`.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionDep
from app.models import AppSettings


@dataclass(frozen=True)
class Clock:
    now: datetime  # timezone-aware
    tz: ZoneInfo

    @property
    def local(self) -> datetime:
        return self.now.astimezone(self.tz)

    @property
    def today(self) -> date:
        return self.local.date()


def utc_now() -> datetime:
    return datetime.now(UTC)


def timezone(session: Session) -> ZoneInfo:
    """The timezone saved in Settings (a single row the migration creates)."""
    return ZoneInfo(session.scalars(select(AppSettings.timezone)).one())


def clock_for(session: Session, now: datetime) -> Clock:
    return Clock(now, timezone(session))


def get_now() -> datetime:
    return utc_now()


def get_clock(session: SessionDep, now: Annotated[datetime, Depends(get_now)]) -> Clock:
    return clock_for(session, now)


ClockDep = Annotated[Clock, Depends(get_clock)]


def get_today(clock: ClockDep) -> date:
    return clock.today


TodayDep = Annotated[date, Depends(get_today)]

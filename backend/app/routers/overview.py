from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app import income
from app.clock import TodayDep
from app.db import SessionDep
from app.schemas.overview import EarningsOut

router = APIRouter(prefix="/api/overview", tags=["overview"])


def _received(session: Session, first: date, last: date) -> Iterator[tuple[date, int]]:
    """Money received between two local dates (inclusive), as (date, amount)."""
    return ((r.paid_on, r.amount) for r in income.received(session, first, last))


def _year_before(day: date) -> date:
    """The same date a year earlier; 29 February becomes the 28th."""
    if day.month == 2 and day.day == 29:
        day = day.replace(day=28)
    return day.replace(year=day.year - 1)


@router.get("/earnings")
def earnings(
    session: SessionDep,
    today: TodayDep,
    year: Annotated[int | None, Query(ge=2, le=9999)] = None,
) -> EarningsOut:
    """Money received in `year` (default: this year) by month, up to today, and the year before
    up to the same date."""
    year = year or today.year
    last = min(today, date(year, 12, 31))
    months = [0] * 12
    for day, amount in _received(session, date(year, 1, 1), last):
        months[day.month - 1] += amount
    total = sum(months)
    previous = sum(
        amount for _, amount in _received(session, date(year - 1, 1, 1), _year_before(last))
    )
    return EarningsOut(
        year=year,
        months=months,
        total=total,
        previous_total=previous,
        change_percent=round((total - previous) * 100 / previous) if previous else None,
    )

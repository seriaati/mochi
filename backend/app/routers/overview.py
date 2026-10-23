from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import maintenance
from app.clock import TodayDep
from app.db import SessionDep
from app.models import Collection, Payment, Retainer, RetainerPayment
from app.schemas.overview import EarningsOut

router = APIRouter(prefix="/api/overview", tags=["overview"])


def _auto_transfers(retainer: Retainer, first: date, last: date) -> Iterator[tuple[date, int]]:
    """Auto-transfer months that fell due between `first` and `last`, on their due dates."""
    for period in maintenance.billed_periods(retainer, maintenance.month_start(last)):
        due = maintenance.due_on(period, retainer.due_day)
        if first <= due <= last:
            yield due, retainer.amount


def _received(session: Session, first: date, last: date) -> Iterator[tuple[date, int]]:
    """Money received between two local dates (inclusive), as (date, amount): project and
    addition payments and "ask" retainer payments by the day paid, auto transfers by due date."""
    yield from session.execute(
        select(Payment.paid_on, Payment.amount).where(Payment.paid_on.between(first, last))
    )
    yield from session.execute(
        select(RetainerPayment.paid_on, RetainerPayment.amount)
        .join(RetainerPayment.retainer)
        .where(
            Retainer.collection == Collection.ASK,
            RetainerPayment.period >= Retainer.tracked_from,  # earlier months count as settled
            RetainerPayment.paid_on.between(first, last),
        )
    )
    auto = session.scalars(select(Retainer).where(Retainer.collection == Collection.AUTO_TRANSFER))
    for retainer in auto:
        yield from _auto_transfers(retainer, first, last)


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

from datetime import date
from typing import Annotated

import httpx2 as httpx
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import discord, discord_sync, maintenance, reminders
from app.clock import Clock, ClockDep
from app.db import SessionDep
from app.maintenance import REMINDER_TIME, REPEAT_DAYS, MonthStatus, slot_at
from app.models import Collection, Retainer
from app.routers.retainers import (
    client_out,
    retainer_client,
    retainer_out,
    sort_key,
    with_children,
)
from app.schemas.maintenance import (
    AutomaticOut,
    CalendarDay,
    CalendarEntry,
    CollectedOut,
    MaintenanceOut,
    NextReminderOut,
    OverdueOut,
    ReminderConfigOut,
    SentOut,
)

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])

# Calendar day colour when retainers with different statuses fall due the same day.
_DAY_STATUS_ORDER = [MonthStatus.OVERDUE, MonthStatus.DUE, MonthStatus.UPCOMING, MonthStatus.PAID]


def _calendar(retainers: list[Retainer], period: date, today: date) -> list[CalendarDay]:
    days: dict[date, list[CalendarEntry]] = {}
    for retainer in retainers:
        if maintenance.is_billed(retainer, period):
            month = maintenance.month(retainer, period, today)
            days.setdefault(month.due_on, []).append(
                CalendarEntry(
                    retainer_id=retainer.id,
                    client=retainer_client(retainer),
                    amount=month.amount,
                    status=month.status,
                )
            )
    return [
        CalendarDay(
            day=day,
            status=min((e.status for e in entries), key=_DAY_STATUS_ORDER.index),
            entries=entries,
        )
        for day, entries in sorted(days.items())
    ]


def _overdue(session: Session, retainers: list[Retainer], clock: Clock) -> list[OverdueOut]:
    reminded = reminders.last_reminded(session)
    items = [
        OverdueOut(
            retainer_id=retainer.id,
            client=retainer_client(retainer),
            period=month.period,
            due_on=month.due_on,
            amount=month.amount,
            days=month.days_late,
            last_reminded_on=(
                sent_at.astimezone(clock.tz).date()
                if (sent_at := reminded.get(retainer.client_id))
                else None
            ),
        )
        for retainer in retainers
        for month in maintenance.overdue(retainer, clock.today)
    ]
    return sorted(items, key=lambda o: (o.due_on, o.client.name.lower()))


def _next_reminder(session: Session, clock: Clock) -> NextReminderOut | None:
    reminder = reminders.next_reminder(session, clock)
    if reminder is None:
        return None
    at = slot_at(reminder.slot_on, clock.tz)
    sent_at = reminders.last_reminded(session).get(reminder.client.id)
    return NextReminderOut(
        client=client_out(reminder.client),
        periods=[m.period for m in reminder.months],
        due_on=reminder.months[0].due_on,
        amount=reminder.amount,
        at=at,
        pending=at <= clock.now,
        last_reminded_on=sent_at.astimezone(clock.tz).date() if sent_at else None,
    )


def _check_enabled() -> None:
    if discord.config.webhook_url is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Reminders are off: add a webhook URL in Settings first"
        )


def _discord_error(error: httpx.HTTPError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, f"Discord didn't take the message: {error}")


@router.get("")
def overview(
    session: SessionDep,
    clock: ClockDep,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> MaintenanceOut:
    """Everything the Maintenance page shows. `month` (YYYY-MM) picks the calendar's month."""
    today = clock.today
    this_period = maintenance.month_start(today)
    period = date.fromisoformat(f"{month}-01") if month else this_period
    retainers = list(session.scalars(with_children()))
    active = [r for r in retainers if maintenance.is_active(r, today)]

    current = [m for r in retainers if (m := maintenance.this_month(r, today))]
    paid = [m for m in current if m.status == MonthStatus.PAID]
    automatic = [r for r in active if r.collection == Collection.AUTO_TRANSFER]

    return MaintenanceOut(
        today=today,
        month=period,
        active_count=len(active),
        monthly_total=sum(r.amount for r in active),
        retainers=sorted((retainer_out(r, today) for r in retainers), key=sort_key),
        overdue=_overdue(session, retainers, clock),
        next_reminder=_next_reminder(session, clock),
        collected=CollectedOut(
            period=this_period,
            received=sum(m.amount for m in paid),
            expected=sum(r.amount for r in retainers if maintenance.is_billed(r, this_period)),
            paid=len(paid),
            count=len(current),
        ),
        automatic=AutomaticOut(
            amount=sum(r.amount for r in automatic),
            clients=len({r.client_id for r in automatic}),
        ),
        calendar=_calendar(retainers, period, today),
        reminders=ReminderConfigOut(
            enabled=discord.config.webhook_url is not None,
            mention_user_id=discord.config.mention_user_id,
            mention=discord_sync.mention_out(session),
            timezone=clock.tz.key,
            time=REMINDER_TIME.strftime("%H:%M"),
            repeat_days=REPEAT_DAYS,
        ),
    )


@router.post("/reminders/test")
def send_test() -> SentOut:
    """Posts a test message to the webhook."""
    _check_enabled()
    try:
        return SentOut(content=reminders.send_test())
    except httpx.HTTPError as error:
        raise _discord_error(error) from error

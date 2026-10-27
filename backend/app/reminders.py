"""Maintenance reminders, one per client: when they're due, sending them, and the loop.

A client with unpaid "ask" months gets one combined reminder listing everything they owe. Its
rhythm is anchored on the oldest unpaid month's due date: 09:00 (saved timezone) on that day,
then every REPEAT_DAYS days while anything is unpaid. Months that fall due in between join the
next ping. Paying the oldest month moves the anchor to the next oldest.

Every send is written to reminder_log under the local day it counts for. The scheduler sends
the latest slot that has come, once: never a slot that is already logged, and never on a day
the client was already reminded (by date of sending, in the saved timezone). So restarts and
timezone changes don't repeat a day, and a missed slot goes out late once.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import discord, discord_sync, keni_sync
from app.clock import Clock, clock_for, utc_now
from app.config import settings
from app.db import SessionLocal
from app.maintenance import (
    REPEAT_DAYS,
    Month,
    latest_slot,
    message,
    reminder_line,
    unpaid_ask_months,
)
from app.models import Client, Collection, ContactMethod, ReminderLog, Retainer

log = logging.getLogger(__name__)

TICK_SECONDS = 60
TEST_LINE = "Test from Mochi: maintenance reminders will post here."


@dataclass(frozen=True)
class Reminder:
    """One client's combined reminder."""

    client: Client
    months: list[Month]  # unpaid "ask" months it covers, oldest first
    contact: ContactMethod | None  # where to ask: the oldest covered month's retainer contact
    slot_on: date  # the local day it counts for
    retainer_id: int  # the oldest covered month's, which the message's Record payment opens
    projects: list[str]  # what the covered retainers are for, oldest first; some have none

    @property
    def amount(self) -> int:
        return sum(m.amount for m in self.months)


@dataclass(frozen=True)
class _Owed:
    """A client's unpaid "ask" months (due, overdue, and the next one coming up per retainer)
    with the retainer each belongs to, oldest due date first."""

    client: Client
    items: list[tuple[Retainer, Month]]

    @property
    def anchor(self) -> date:
        return self.items[0][1].due_on

    def reminder(self, slot_on: date, cover: date) -> Reminder:
        """The reminder for a slot, covering every month due by `cover`."""
        covered = [(r, m) for r, m in self.items if m.due_on <= cover]
        contact = next((r.ask_via for r, _ in covered if r.ask_via is not None), None)
        months = [m for _, m in covered]
        projects = [r.project.name for r, _ in covered if r.project is not None]
        return Reminder(self.client, months, contact, slot_on, covered[0][0].id, projects)


def _owed(session: Session, today: date) -> list[_Owed]:
    query = (
        select(Retainer)
        .where(Retainer.collection == Collection.ASK)
        .options(
            selectinload(Retainer.client),
            selectinload(Retainer.project),
            selectinload(Retainer.ask_via),
            selectinload(Retainer.payments),
            selectinload(Retainer.pauses),
            selectinload(Retainer.waivers),
        )
        .execution_options(populate_existing=True)
    )
    by_client: dict[int, list[tuple[Retainer, Month]]] = defaultdict(list)
    for retainer in session.scalars(query):
        for month in unpaid_ask_months(retainer, today):
            by_client[retainer.client_id].append((retainer, month))
    return [
        _Owed(items[0][0].client, sorted(items, key=lambda i: (i[1].due_on, i[0].id)))
        for items in by_client.values()
    ]


@dataclass(frozen=True)
class _History:
    slots: set[date]  # days already reminded for
    sent_today: bool  # reminded today, by local date of sending


def _history(session: Session, clock: Clock) -> dict[int, _History]:
    slots: dict[int, set[date]] = defaultdict(set)
    sent_today: set[int] = set()
    for client_id, slot_on, sent_at in session.execute(
        select(ReminderLog.client_id, ReminderLog.slot_on, ReminderLog.sent_at)
    ):
        slots[client_id].add(slot_on)
        if sent_at.astimezone(clock.tz).date() == clock.today:
            sent_today.add(client_id)
    return defaultdict(
        lambda: _History(set(), False),
        {c: _History(slots[c], c in sent_today) for c in slots},
    )


def last_reminded(session: Session) -> dict[int, datetime]:
    """When each client was last reminded."""
    query = select(ReminderLog.client_id, func.max(ReminderLog.sent_at))
    rows = session.execute(query.group_by(ReminderLog.client_id))
    # Not dict(rows): a Result has keys(), so dict() would read it as a mapping.
    return {client_id: sent_at for client_id, sent_at in rows}  # noqa: C416


def due_now(session: Session, clock: Clock) -> list[Reminder]:
    """Clients whose latest slot has come and hasn't been sent, covering all they owe today."""
    history = _history(session, clock)
    due = []
    for owed in _owed(session, clock.today):
        slot = latest_slot(owed.anchor, clock.now, clock.tz)
        seen = history[owed.client.id]
        if slot is not None and slot not in seen.slots and not seen.sent_today:
            due.append(owed.reminder(slot, clock.today))
    return sorted(due, key=lambda r: (r.client.name.lower(), r.client.id))


def _next_for(owed: _Owed, seen: _History, clock: Clock) -> Reminder:
    slot = latest_slot(owed.anchor, clock.now, clock.tz)
    if slot is not None and slot not in seen.slots and not seen.sent_today:
        return owed.reminder(slot, clock.today)  # its time has come; the next tick sends it
    day = owed.anchor if slot is None else slot + timedelta(days=REPEAT_DAYS)
    while day in seen.slots or (day == clock.today and seen.sent_today):
        day += timedelta(days=REPEAT_DAYS)
    return owed.reminder(day, max(day, clock.today))


def next_reminder(session: Session, clock: Clock) -> Reminder | None:
    """The next reminder to go out."""
    history = _history(session, clock)
    candidates = [
        _next_for(owed, history[owed.client.id], clock) for owed in _owed(session, clock.today)
    ]
    return min(
        candidates, key=lambda r: (r.slot_on, r.client.name.lower(), r.client.id), default=None
    )


def record_url(reminder: Reminder) -> str:
    """The Retainers page with Record payment open for the reminder's oldest month."""
    month = f"{reminder.months[0].period:%Y-%m}"
    return f"{settings.app_url}/maintenance?record={reminder.retainer_id}&month={month}"


def content(reminders: list[Reminder], clock: Clock) -> str:
    lines = [
        reminder_line(r.client.name, r.months, r.contact, clock.today, record_url(r), r.projects)
        for r in reminders
    ]
    return message(lines, discord.config.mention_user_id)


def send(session: Session, reminders: list[Reminder], clock: Clock) -> str:
    """Post one message for the reminders and record them. If Discord fails, nothing is
    recorded and the error propagates."""
    text = content(reminders, clock)
    session.add_all(
        ReminderLog(client_id=r.client.id, slot_on=r.slot_on, sent_at=clock.now) for r in reminders
    )
    try:
        session.flush()
        discord.post(text)
    except Exception:
        session.rollback()
        raise
    session.commit()
    return text


def send_due(session: Session, now: datetime) -> int:
    """Send whatever is due, in one post. Does nothing while no webhook is configured."""
    if discord.config.webhook_url is None:
        return 0
    clock = clock_for(session, now)  # the timezone as saved right now
    due = due_now(session, clock)
    if due:
        send(session, due, clock)
    return len(due)


def send_test() -> str:
    text = message([TEST_LINE], discord.config.mention_user_id)
    discord.post(text)
    return text


def _tick() -> None:
    with SessionLocal() as session:
        sent = send_due(session, utc_now())
    if sent:
        log.info("Sent maintenance reminders for %d client(s)", sent)


async def run_forever() -> None:
    """Started from the app lifespan. Each tick sends due reminders, refreshes stale Discord
    profiles, then catches Keni up. Errors are logged and retried on the next tick."""
    while True:
        try:
            await asyncio.to_thread(_tick)
        except Exception:
            log.exception("Sending maintenance reminders failed")
        try:
            await asyncio.to_thread(discord_sync.tick)
        except Exception:
            log.exception("Syncing Discord profiles failed")
        try:
            await asyncio.to_thread(keni_sync.tick)
        except Exception:
            log.exception("Syncing to Keni failed")
        await asyncio.sleep(TICK_SECONDS)

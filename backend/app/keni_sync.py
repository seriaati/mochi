"""Mirrors money received into Keni, a personal finance tracker, as income.

What counts as received: project and addition payments, recorded "ask" maintenance payments,
and auto transfer months once their due date is reached. Each becomes one Keni transaction in
the wallet and category chosen in Settings, linked to it by a KeniLink row. Choosing another
wallet or category applies to transactions sent from then on; the rest stay where they are.

Every reminder-loop tick compares what should be in Keni with the links and catches up: it
creates transactions for new money, updates them when the amount, date or description changes
here, and deletes them when the money is gone, including through a deleted project, client or
retainer. Only that loop talks to Keni, so a failed request just stops the tick: the error shows
in Settings and the next tick retries.

Money already received when connecting stays out of Keni: connecting adds a link without a
transaction for every recorded payment, and auto transfers count only when due after that day.
A transaction deleted in Keni is kept out from then on too.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app import crypto, keni
from app.clock import clock_for, utc_now
from app.db import SessionLocal
from app.maintenance import billed_periods, due_on, month_start
from app.models import Addition, AppSettings, Collection, KeniLink, Project, Retainer

log = logging.getLogger(__name__)

UNREADABLE_TOKEN = "Can't decrypt the API key: check ENCRYPTION_KEY, or connect again"


@dataclass(frozen=True)
class Entry:
    """Money received, as it should appear in Keni."""

    amount: int
    paid_on: date
    description: str


def _describe(*parts: str, note: str | None = None) -> str:
    text = " · ".join(parts) + (f" ({note})" if note else "")
    return text[:500]  # Keni's limit


def _retainers(session: Session, collection: Collection) -> list[Retainer]:
    query = select(Retainer).where(Retainer.collection == collection)
    return list(
        session.scalars(
            query.options(selectinload(Retainer.client), selectinload(Retainer.payments))
        )
    )


def _recorded(session: Session) -> dict[str, Entry]:
    """Recorded payments: on projects, their additions and "ask" retainers."""
    entries = {}
    projects = session.scalars(
        select(Project).options(
            selectinload(Project.client),
            selectinload(Project.payments),
            selectinload(Project.additions).selectinload(Addition.payments),
        )
    )
    for project in projects:
        for payment in project.payments:
            description = _describe(project.client.name, project.name, note=payment.note)
            entries[f"payment:{payment.id}"] = Entry(payment.amount, payment.paid_on, description)
        for addition in project.additions:
            for payment in addition.payments:
                description = _describe(
                    project.client.name, project.name, addition.name, note=payment.note
                )
                entries[f"payment:{payment.id}"] = Entry(
                    payment.amount, payment.paid_on, description
                )
    for retainer in _retainers(session, Collection.ASK):
        for payment in retainer.payments:
            description = _describe(retainer.client.name, "Maintenance")
            entries[f"retainer_payment:{payment.id}"] = Entry(
                payment.amount, payment.paid_on, description
            )
    return entries


def _auto_transfers(session: Session, after: date, today: date) -> dict[str, Entry]:
    """Auto transfer months due after `after`, up to today."""
    entries = {}
    for retainer in _retainers(session, Collection.AUTO_TRANSFER):
        for period in billed_periods(retainer, month_start(today)):
            due = due_on(period, retainer.due_day)
            if after < due <= today:
                description = _describe(retainer.client.name, "Maintenance")
                entries[f"retainer:{retainer.id}:{period:%Y-%m}"] = Entry(
                    retainer.amount, due, description
                )
    return entries


@dataclass(frozen=True)
class Plan:
    """What a sync does to catch Keni up."""

    create: list[tuple[str, Entry]]
    update: list[tuple[KeniLink, Entry]]
    delete: list[KeniLink]  # in Keni, while the money is gone here
    forget: list[KeniLink]  # kept out of Keni, and gone here too: just the row goes

    @property
    def pending(self) -> int:
        return len(self.create) + len(self.update) + len(self.delete)


def plan(session: Session, row: AppSettings, today: date) -> Plan:
    assert row.keni_connected_on is not None
    wanted = _recorded(session) | _auto_transfers(session, row.keni_connected_on, today)
    links = {link.source: link for link in session.scalars(select(KeniLink))}
    create, update, delete_, forget = [], [], [], []
    for source, entry in sorted(wanted.items(), key=lambda item: item[1].paid_on):
        link = links.get(source)
        if link is None:
            create.append((source, entry))
        elif link.keni_id is not None and entry != Entry(
            link.amount, link.paid_on, link.description
        ):
            update.append((link, entry))
    for source, link in links.items():
        if source not in wanted:
            (forget if link.keni_id is None else delete_).append(link)
    return Plan(create, update, delete_, forget)


def connect(session: Session, row: AppSettings, today: date) -> None:
    """Starts syncing from today: the payments recorded by now stay out of Keni."""
    session.execute(delete(KeniLink))
    session.add_all(KeniLink(source=source) for source in _recorded(session))
    row.keni_connected_on = today
    row.keni_error = None


def disconnect(session: Session, row: AppSettings) -> None:
    session.execute(delete(KeniLink))
    row.keni_url = None
    row.keni_token_encrypted = None
    row.keni_wallet_id = None
    row.keni_wallet_name = None
    row.keni_wallet_currency = None
    row.keni_category_id = None
    row.keni_category_name = None
    row.keni_connected_on = None
    row.keni_error = None


def saved_account(row: AppSettings) -> keni.Account | None:
    """The connected account, or None when its token can't be decrypted (no ENCRYPTION_KEY, or
    a new one)."""
    assert row.keni_url is not None and row.keni_token_encrypted is not None
    token = crypto.decrypt(row.keni_token_encrypted)
    return keni.Account(row.keni_url, token) if token is not None else None


def _at(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(), tz)  # Keni records a time; midnight in the timezone


def sync(session: Session, now: datetime) -> int:
    """Catches Keni up and returns how many changes it sent. Does nothing while not connected.
    On a failure, keeps what got through, saves the error for Settings and raises keni.Error."""
    row = session.get_one(AppSettings, 1)
    if row.keni_token_encrypted is None:
        return 0
    account = saved_account(row)
    if account is None:
        row.keni_error = UNREADABLE_TOKEN
        session.commit()
        raise keni.Error(row.keni_error)
    assert row.keni_wallet_id is not None and row.keni_category_id is not None
    clock = clock_for(session, now)
    todo = plan(session, row, clock.today)
    for link in todo.forget:
        session.delete(link)
    session.commit()
    try:
        for link in todo.delete:
            keni.delete(account, link.wallet_id, link.keni_id)
            session.delete(link)
            session.commit()
        for link, entry in todo.update:
            when = _at(entry.paid_on, clock.tz)
            args = (account, link.wallet_id, link.keni_id, entry.amount, when, entry.description)
            if keni.update(*args):
                link.amount, link.paid_on, link.description = (
                    entry.amount,
                    entry.paid_on,
                    entry.description,
                )
            else:  # deleted in Keni: keep it out
                link.keni_id = link.wallet_id = None
                link.amount = link.paid_on = link.description = None
            session.commit()
        for source, entry in todo.create:
            when = _at(entry.paid_on, clock.tz)
            wallet, category = row.keni_wallet_id, row.keni_category_id
            keni_id = keni.create(
                account, wallet, category, entry.amount, when, entry.description
            )
            session.add(KeniLink(source=source, keni_id=keni_id, wallet_id=wallet, **asdict(entry)))
            session.commit()
    except keni.Error as error:
        row.keni_error = str(error)
        session.commit()
        raise
    row.keni_error = None
    session.commit()
    return todo.pending


def tick() -> None:
    with SessionLocal() as session:
        try:
            sent = sync(session, utc_now())
        except keni.Error as error:
            log.warning("Syncing to Keni stopped: %s", error)
            return
    if sent:
        log.info("Sent %d change(s) to Keni", sent)

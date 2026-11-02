"""Money received: what the Overview's earnings and the Stats page count.

Project and addition payments count on the day paid, "ask" retainer payments on the day paid
(for tracked months only; earlier ones count as settled), and auto transfers on each billed
month's due date, once it is reached.
"""

import enum
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import maintenance
from app.models import Addition, Client, Collection, Payment, Project, Retainer, RetainerPayment


class Source(enum.StrEnum):
    PROJECT = "project"
    ADDITION = "addition"
    RETAINER = "retainer"


@dataclass(frozen=True)
class Received:
    paid_on: date
    amount: int
    source: Source
    client: Client  # who paid
    project: Project | None  # what for: the project, the addition's, or the retainer's if any
    addition: Addition | None = None
    collection: Collection | None = None  # retainers only
    # Retainers only: days paid after the (first) month's due date, 0 when on time or ahead.
    days_late: int | None = None
    late: bool | None = None  # retainers only: paid more than the grace days after it


def received(session: Session, first: date, last: date) -> Iterator[Received]:
    """Money received between two local dates (inclusive), in no particular order."""
    payments = session.scalars(
        select(Payment)
        .where(Payment.paid_on.between(first, last))
        .options(
            selectinload(Payment.project).selectinload(Project.client),
            selectinload(Payment.addition)
            .selectinload(Addition.project)
            .selectinload(Project.client),
        )
    )
    for payment in payments:
        addition = payment.addition
        project = addition.project if addition is not None else payment.project
        assert project is not None  # a payment is for a project or an addition
        source = Source.ADDITION if addition is not None else Source.PROJECT
        yield Received(payment.paid_on, payment.amount, source, project.client, project, addition)

    asked = session.scalars(
        select(RetainerPayment)
        .join(RetainerPayment.retainer)
        .where(
            Retainer.collection == Collection.ASK,
            RetainerPayment.period >= Retainer.tracked_from,  # earlier months count as settled
            RetainerPayment.paid_on.between(first, last),
        )
        .options(
            selectinload(RetainerPayment.retainer).options(
                selectinload(Retainer.client), selectinload(Retainer.project)
            )
        )
    )
    for payment in asked:
        retainer = payment.retainer
        due = maintenance.due_on(payment.period, retainer.due_day)
        days = max((payment.paid_on - due).days, 0)
        yield Received(
            payment.paid_on,
            payment.amount,
            Source.RETAINER,
            retainer.client,
            retainer.project,
            collection=Collection.ASK,
            days_late=days,
            late=days > maintenance.GRACE_DAYS,
        )

    auto = session.scalars(
        select(Retainer)
        .where(Retainer.collection == Collection.AUTO_TRANSFER)
        .options(selectinload(Retainer.client), selectinload(Retainer.project))
    )
    for retainer in auto:
        for period in maintenance.billed_periods(retainer, maintenance.month_start(last)):
            due = maintenance.due_on(period, retainer.due_day)
            if first <= due <= last:
                yield Received(
                    due,
                    retainer.amount,
                    Source.RETAINER,
                    retainer.client,
                    retainer.project,
                    collection=Collection.AUTO_TRANSFER,
                    days_late=0,
                    late=False,
                )

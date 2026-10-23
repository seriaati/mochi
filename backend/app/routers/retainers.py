from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app import discord_sync, maintenance
from app.clock import TodayDep
from app.db import SessionDep
from app.models import Client, Collection, ContactMethod, Retainer, RetainerPayment
from app.routers.clients import contact_out
from app.schemas.maintenance import (
    MonthOut,
    RetainerClient,
    RetainerIn,
    RetainerOut,
    RetainerPaymentIn,
    RetainerPaymentOut,
)

router = APIRouter(prefix="/api/retainers", tags=["maintenance"])


def month_out(month: maintenance.Month) -> MonthOut:
    return MonthOut(
        period=month.period,
        due_on=month.due_on,
        amount=month.amount,
        status=month.status,
        paid_on=month.paid_on,
        payment_id=month.payment_id,
        days_late=month.days_late,
        late=month.late,
    )


def client_out(client: Client) -> RetainerClient:
    avatar = discord_sync.primary_avatar(client.contacts)
    return RetainerClient(id=client.id, name=client.name, avatar_url=avatar)


def retainer_client(retainer: Retainer) -> RetainerClient:
    return client_out(retainer.client)


def retainer_out(retainer: Retainer, today: date) -> RetainerOut:
    this_month = maintenance.this_month(retainer, today)
    return RetainerOut(
        id=retainer.id,
        **RetainerIn.model_validate(retainer, from_attributes=True).model_dump(),
        client=retainer_client(retainer),
        ask_via=contact_out(retainer.ask_via) if retainer.ask_via else None,
        active=maintenance.is_active(retainer, today),
        this_month=month_out(this_month) if this_month else None,
        next_due_on=(
            maintenance.due_on(period, retainer.due_day)
            if (period := maintenance.next_period(retainer, today))
            else None
        ),
        months=[month_out(m) for m in maintenance.recent(retainer, today)],
        overdue=[month_out(m) for m in maintenance.overdue(retainer, today)],
        received=maintenance.received(retainer, today),
    )


def sort_key(retainer: RetainerOut) -> tuple:
    return (not retainer.active, retainer.client.name.lower(), retainer.id)


def with_children() -> Select[tuple[Retainer]]:
    return (
        select(Retainer)
        .options(
            selectinload(Retainer.client).selectinload(Client.contacts),
            selectinload(Retainer.ask_via),
            selectinload(Retainer.payments),
        )
        .execution_options(populate_existing=True)
    )


def _read(session: Session, retainer_id: int, today: date) -> RetainerOut:
    retainer = session.scalars(with_children().where(Retainer.id == retainer_id)).one_or_none()
    if retainer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Retainer not found")
    return retainer_out(retainer, today)


def _get_retainer_or_404(session: Session, retainer_id: int) -> Retainer:
    retainer = session.get(Retainer, retainer_id)
    if retainer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Retainer not found")
    return retainer


def _get_payment_or_404(session: Session, retainer_id: int, payment_id: int) -> RetainerPayment:
    payment = session.get(RetainerPayment, payment_id)
    if payment is None or payment.retainer_id != retainer_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return payment


def _check_refs(session: Session, body: RetainerIn) -> None:
    if session.get(Client, body.client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    if body.ask_via_id is not None:
        contact = session.get(ContactMethod, body.ask_via_id)
        if contact is None or contact.client_id != body.client_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick one of this client's contacts"
            )


def _check_payments_still_fit(retainer: Retainer, body: RetainerIn) -> None:
    """After an edit, recorded payments must still be for "ask" months the retainer bills."""
    if not retainer.payments:
        return
    if body.collection != Collection.ASK:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This retainer has recorded payments; remove them before switching to auto transfer",
        )
    edited = Retainer(**body.model_dump())  # transient, never added to the session
    outside = [p for p in retainer.payments if not maintenance.is_billed(edited, p.period)]
    if outside:
        month = outside[0].period.strftime("%B %Y")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A payment is recorded for {month}, which these dates no longer cover",
        )


@router.get("")
def list_retainers(
    session: SessionDep, today: TodayDep, client_id: int | None = None
) -> list[RetainerOut]:
    query = with_children()
    if client_id is not None:
        query = query.where(Retainer.client_id == client_id)
    return sorted((retainer_out(r, today) for r in session.scalars(query)), key=sort_key)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_retainer(body: RetainerIn, session: SessionDep, today: TodayDep) -> RetainerOut:
    _check_refs(session, body)
    retainer = Retainer(**body.model_dump())
    session.add(retainer)
    session.commit()
    return _read(session, retainer.id, today)


@router.get("/{retainer_id}")
def get_retainer(retainer_id: int, session: SessionDep, today: TodayDep) -> RetainerOut:
    return _read(session, retainer_id, today)


@router.put("/{retainer_id}")
def update_retainer(
    retainer_id: int, body: RetainerIn, session: SessionDep, today: TodayDep
) -> RetainerOut:
    retainer = _get_retainer_or_404(session, retainer_id)
    _check_refs(session, body)
    _check_payments_still_fit(retainer, body)
    for field, value in body.model_dump().items():
        setattr(retainer, field, value)
    session.commit()
    return _read(session, retainer_id, today)


@router.delete("/{retainer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_retainer(retainer_id: int, session: SessionDep) -> None:
    """Also deletes its recorded payments and reminder history."""
    session.delete(_get_retainer_or_404(session, retainer_id))
    session.commit()


@router.post("/{retainer_id}/payments", status_code=status.HTTP_201_CREATED)
def record_payment(
    retainer_id: int, body: RetainerPaymentIn, session: SessionDep
) -> RetainerPaymentOut:
    """Marks one month of an "ask" retainer as paid."""
    retainer = _get_retainer_or_404(session, retainer_id)
    month = body.period.strftime("%B %Y")
    if retainer.collection != Collection.ASK:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Auto transfers count as paid on the due date by themselves"
        )
    if not maintenance.is_billed(retainer, body.period):
        if maintenance.month_start(retainer.started_on) <= body.period < retainer.tracked_from:
            detail = f"{month} is before tracking starts, so it counts as settled"
        else:
            detail = f"This retainer doesn't bill {month}"
        raise HTTPException(status.HTTP_409_CONFLICT, detail)
    taken = session.scalar(
        select(func.count(RetainerPayment.id)).where(
            RetainerPayment.retainer_id == retainer_id, RetainerPayment.period == body.period
        )
    )
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{month} is already recorded as paid")
    payment = RetainerPayment(retainer_id=retainer_id, **body.model_dump())
    session.add(payment)
    session.commit()
    return RetainerPaymentOut.model_validate(payment, from_attributes=True)


@router.delete("/{retainer_id}/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(retainer_id: int, payment_id: int, session: SessionDep) -> None:
    session.delete(_get_payment_or_404(session, retainer_id, payment_id))
    session.commit()

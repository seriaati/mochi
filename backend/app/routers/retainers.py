from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app import discord_sync, maintenance
from app.clock import TodayDep
from app.db import SessionDep
from app.models import (
    Client,
    Collection,
    ContactMethod,
    Project,
    Retainer,
    RetainerPause,
    RetainerPayment,
)
from app.routers.clients import contact_out
from app.schemas.maintenance import (
    MonthOut,
    RetainerClient,
    RetainerIn,
    RetainerOut,
    RetainerPauseIn,
    RetainerPauseOut,
    RetainerPaymentIn,
    RetainerPaymentOut,
    RetainerProject,
)

router = APIRouter(prefix="/api/retainers", tags=["maintenance"])


def month_out(month: maintenance.Month) -> MonthOut:
    return MonthOut(
        period=month.period,
        due_on=month.due_on,
        amount=month.amount,
        status=month.status,
        paid_on=month.paid_on,
        payment=(
            RetainerPaymentOut.model_validate(month.payment, from_attributes=True)
            if month.payment
            else None
        ),
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
        project=(
            RetainerProject(id=retainer.project.id, name=retainer.project.name)
            if retainer.project
            else None
        ),
        ask_via=contact_out(retainer.ask_via) if retainer.ask_via else None,
        active=maintenance.is_active(retainer, today),
        paused_on=pause.paused_on if (pause := maintenance.current_pause(retainer)) else None,
        this_month=month_out(this_month) if this_month else None,
        next_due_on=(
            maintenance.due_on(period, retainer.due_day)
            if (period := maintenance.next_period(retainer, today))
            else None
        ),
        months=[month_out(m) for m in maintenance.recent(retainer, today)],
        overdue=[month_out(m) for m in maintenance.overdue(retainer, today)],
        received=maintenance.received(retainer, today),
        pauses=[RetainerPauseOut.model_validate(p, from_attributes=True) for p in retainer.pauses],
    )


def sort_key(retainer: RetainerOut) -> tuple:
    return (not retainer.active, retainer.client.name.lower(), retainer.id)


def with_children() -> Select[Retainer]:
    return (
        select(Retainer)
        .options(
            selectinload(Retainer.client).selectinload(Client.contacts),
            selectinload(Retainer.project),
            selectinload(Retainer.ask_via),
            selectinload(Retainer.payments),
            selectinload(Retainer.pauses),
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


def _get_pause_or_404(session: Session, retainer_id: int, pause_id: int) -> RetainerPause:
    pause = session.get(RetainerPause, pause_id)
    if pause is None or pause.retainer_id != retainer_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pause not found")
    return pause


def _check_refs(session: Session, body: RetainerIn) -> None:
    if session.get(Client, body.client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    if body.project_id is not None and session.get(Project, body.project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if body.ask_via_id is not None:
        contact = session.get(ContactMethod, body.ask_via_id)
        if contact is None or contact.client_id != body.client_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick one of this client's contacts"
            )


def _check_payments_still_fit(retainer: Retainer, body: RetainerIn) -> None:
    """After an edit, recorded payments must still cover only "ask" months the retainer bills."""
    if not retainer.payments:
        return
    if body.collection != Collection.ASK:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This retainer has recorded payments; remove them before switching to auto transfer",
        )
    edited = Retainer(**body.model_dump())  # transient, never added to the session
    outside = [
        period
        for p in retainer.payments
        for period in maintenance.covered(p)
        if not maintenance.is_billed(edited, period)
    ]
    if outside:
        month = min(outside).strftime("%B %Y")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A payment is recorded for {month}, which these dates no longer cover",
        )


def _check_unpaid_while_paused(retainer: Retainer, pause: RetainerPauseIn) -> None:
    """Months falling due in a pause aren't billed, so none of them may have a payment."""
    end = pause.resumed_on or date.max
    paid = [
        period
        for p in retainer.payments
        for period in maintenance.covered(p)
        if pause.paused_on <= maintenance.due_on(period, retainer.due_day) < end
    ]
    if paid:
        month = min(paid).strftime("%B %Y")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A payment covers {month}; remove it before pausing",
        )


@router.get("")
def list_retainers(
    session: SessionDep,
    today: TodayDep,
    client_id: int | None = None,
    project_id: int | None = None,
) -> list[RetainerOut]:
    query = with_children()
    if client_id is not None:
        query = query.where(Retainer.client_id == client_id)
    if project_id is not None:
        query = query.where(Retainer.project_id == project_id)
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


@router.post("/{retainer_id}/pause")
def pause_retainer(retainer_id: int, session: SessionDep, today: TodayDep) -> RetainerOut:
    """Stops billing from today, and reminders for what's left unpaid, until resumed. For a
    client who stopped paying."""
    retainer = _get_retainer_or_404(session, retainer_id)
    if maintenance.current_pause(retainer) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This retainer is already paused")
    if retainer.ended_on is not None and retainer.ended_on < today:
        raise HTTPException(status.HTTP_409_CONFLICT, "This retainer has already ended")
    _check_unpaid_while_paused(retainer, RetainerPauseIn(paused_on=today))
    session.add(RetainerPause(retainer_id=retainer_id, paused_on=today))
    session.commit()
    return _read(session, retainer_id, today)


@router.post("/{retainer_id}/resume")
def resume_retainer(retainer_id: int, session: SessionDep, today: TodayDep) -> RetainerOut:
    """Bills again from today. Months due while it was paused stay unbilled."""
    pause = maintenance.current_pause(_get_retainer_or_404(session, retainer_id))
    if pause is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This retainer isn't paused")
    if pause.paused_on >= today:
        session.delete(pause)  # paused and resumed the same day: as if never paused
    else:
        pause.resumed_on = today
    session.commit()
    return _read(session, retainer_id, today)


@router.post("/{retainer_id}/pauses", status_code=status.HTTP_201_CREATED)
def add_pause(
    retainer_id: int, body: RetainerPauseIn, session: SessionDep, today: TodayDep
) -> RetainerOut:
    """Records a pause from a past day, e.g. a bot that was offline for a while: months falling
    due in it aren't billed, as with pausing from today. Without resumed_on it is still paused."""
    retainer = _get_retainer_or_404(session, retainer_id)
    if body.paused_on > today or (body.resumed_on is not None and body.resumed_on > today):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A pause can't start or end after today"
        )
    end = body.resumed_on or date.max
    if any(
        p.paused_on < end and body.paused_on < (p.resumed_on or date.max) for p in retainer.pauses
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "This overlaps another pause")
    _check_unpaid_while_paused(retainer, body)
    session.add(RetainerPause(retainer_id=retainer_id, **body.model_dump()))
    session.commit()
    return _read(session, retainer_id, today)


@router.delete("/{retainer_id}/pauses/{pause_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pause(retainer_id: int, pause_id: int, session: SessionDep) -> None:
    """As if it was never paused then: the months that fell due in it are billed again."""
    session.delete(_get_pause_or_404(session, retainer_id, pause_id))
    session.commit()


@router.post("/{retainer_id}/payments", status_code=status.HTTP_201_CREATED)
def record_payment(
    retainer_id: int, body: RetainerPaymentIn, session: SessionDep
) -> RetainerPaymentOut:
    """Marks one month of an "ask" retainer as paid, or several in a row paid ahead."""
    retainer = _get_retainer_or_404(session, retainer_id)
    if retainer.collection != Collection.ASK:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Auto transfers count as paid on the due date by themselves"
        )
    payment = RetainerPayment(retainer_id=retainer_id, **body.model_dump())
    for period in maintenance.covered(payment):
        month = period.strftime("%B %Y")
        if not maintenance.is_billed(retainer, period):
            if maintenance.month_start(retainer.started_on) <= period < retainer.tracked_from:
                detail = f"{month} is before tracking starts, so it counts as settled"
            else:
                detail = f"This retainer doesn't bill {month}"
            raise HTTPException(status.HTTP_409_CONFLICT, detail)
        if maintenance.payment_for(retainer, period) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{month} is already recorded as paid")
    session.add(payment)
    session.commit()
    return RetainerPaymentOut.model_validate(payment, from_attributes=True)


@router.delete("/{retainer_id}/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(retainer_id: int, payment_id: int, session: SessionDep) -> None:
    session.delete(_get_payment_or_404(session, retainer_id, payment_id))
    session.commit()

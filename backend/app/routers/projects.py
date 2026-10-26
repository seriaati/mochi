from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app import discord_sync
from app.db import SessionDep
from app.models import Addition, Client, Payment, Project
from app.schemas.projects import (
    AdditionIn,
    AdditionOut,
    Billing,
    PaymentIn,
    PaymentKind,
    PaymentOut,
    ProjectClient,
    ProjectIn,
    ProjectOut,
    Status,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def expected_deposit(price: int, deposit_percent: int) -> int:
    """round(price * pct / 100) with halves rounded up, in integer maths."""
    return (price * deposit_percent + 50) // 100


def _billing(price: int, deposit_percent: int, delivered_on: date | None, paid: int) -> Billing:
    deposit = expected_deposit(price, deposit_percent)
    outstanding = price - paid
    deposit_due = max(deposit - paid, 0)
    if delivered_on is None:
        state = Status.IN_PROGRESS
    elif outstanding > 0:
        state = Status.FINAL_PAYMENT_DUE
    else:
        state = Status.DONE
    return Billing(
        expected_deposit=deposit,
        expected_final=price - deposit,
        paid=paid,
        outstanding=outstanding,
        deposit_due=deposit_due,
        final_due=outstanding - deposit_due,
        status=state,
    )


def _payments_out(payments: list[Payment], price: int, deposit_percent: int) -> list[PaymentOut]:
    """Label each payment by where it falls against the expected deposit, oldest first."""
    deposit = expected_deposit(price, deposit_percent)
    split = 0 < deposit < price
    out, before = [], 0
    for payment in sorted(payments, key=lambda p: (p.paid_on, p.id)):
        after = before + payment.amount
        if split and after <= deposit:
            kind = PaymentKind.DEPOSIT
        elif split and before >= deposit:
            kind = PaymentKind.FINAL
        else:
            kind = PaymentKind.PAYMENT
        out.append(
            PaymentOut(
                id=payment.id,
                addition_id=payment.addition_id,
                amount=payment.amount,
                paid_on=payment.paid_on,
                note=payment.note,
                kind=kind,
            )
        )
        before = after
    return out


def _addition_out(addition: Addition) -> AdditionOut:
    paid = sum(p.amount for p in addition.payments)
    return AdditionOut(
        id=addition.id,
        project_id=addition.project_id,
        **AdditionIn.model_validate(addition, from_attributes=True).model_dump(),
        **_billing(
            addition.price, addition.deposit_percent, addition.delivered_on, paid
        ).model_dump(),
    )


def _out(project: Project) -> ProjectOut:
    paid = sum(p.amount for p in project.payments)
    additions = sorted(project.additions, key=lambda a: (a.agreed_on, a.id), reverse=True)
    additions_out = [_addition_out(a) for a in additions]
    payments = _payments_out(project.payments, project.price, project.deposit_percent)
    for addition in additions:
        payments += _payments_out(addition.payments, addition.price, addition.deposit_percent)
    payments.sort(key=lambda p: (p.paid_on, p.id))

    additions_total = sum(a.price for a in additions_out)
    total_paid = paid + sum(a.paid for a in additions_out)
    total = project.price + additions_total
    return ProjectOut(
        id=project.id,
        created_at=project.created_at,
        client=ProjectClient(
            id=project.client.id,
            name=project.client.name,
            contact_person=project.client.contact_person,
            avatar_url=discord_sync.primary_avatar(project.client.contacts),
        ),
        **ProjectIn.model_validate(project, from_attributes=True).model_dump(),
        **_billing(project.price, project.deposit_percent, project.delivered_on, paid).model_dump(),
        additions=additions_out,
        payments=payments,
        additions_total=additions_total,
        total=total,
        total_paid=total_paid,
        total_outstanding=total - total_paid,
    )


# Unfinished first (awaiting payment, then in progress), soonest due first, newest started first.
_STATUS_ORDER = {Status.FINAL_PAYMENT_DUE: 0, Status.IN_PROGRESS: 1, Status.DONE: 2}


def _sort_key(project: ProjectOut) -> tuple:
    return (
        _STATUS_ORDER[project.status],
        project.due_on is None,
        project.due_on or date.min,
        -project.started_on.toordinal(),
        -project.id,
    )


def _with_children() -> Select[Project]:
    # populate_existing refreshes rows already in the session, including their collections.
    return (
        select(Project)
        .options(
            selectinload(Project.client).selectinload(Client.contacts),
            selectinload(Project.payments),
            selectinload(Project.additions).selectinload(Addition.payments),
        )
        .execution_options(populate_existing=True)
    )


def _read(session: Session, project_id: int) -> ProjectOut:
    project = session.scalars(_with_children().where(Project.id == project_id)).one_or_none()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return _out(project)


def _get_project_or_404(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


def _get_addition_or_404(session: Session, project_id: int, addition_id: int) -> Addition:
    addition = session.get(Addition, addition_id)
    if addition is None or addition.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Addition not found")
    return addition


def _get_payment_or_404(session: Session, project_id: int, payment_id: int) -> Payment:
    payment = session.get(Payment, payment_id)
    if payment is not None:
        owner = payment.addition.project_id if payment.addition else payment.project_id
        if owner == project_id:
            return payment
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")


def _check_client_exists(session: Session, client_id: int) -> None:
    if session.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")


def _check_price_covers_payments(price: int, payments: list[Payment]) -> None:
    paid = sum(p.amount for p in payments)
    if price < paid:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"NT${paid:,} has already been paid, so the price can't be lower than that",
        )


@router.get("")
def list_projects(session: SessionDep, client_id: int | None = None) -> list[ProjectOut]:
    query = _with_children()
    if client_id is not None:
        query = query.where(Project.client_id == client_id)
    return sorted((_out(p) for p in session.scalars(query)), key=_sort_key)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, session: SessionDep) -> ProjectOut:
    _check_client_exists(session, body.client_id)
    project = Project(**body.model_dump())
    session.add(project)
    session.commit()
    return _read(session, project.id)


@router.get("/{project_id}")
def get_project(project_id: int, session: SessionDep) -> ProjectOut:
    return _read(session, project_id)


@router.put("/{project_id}")
def update_project(project_id: int, body: ProjectIn, session: SessionDep) -> ProjectOut:
    project = _get_project_or_404(session, project_id)
    _check_client_exists(session, body.client_id)
    _check_price_covers_payments(body.price, project.payments)
    for field, value in body.model_dump().items():
        setattr(project, field, value)
    session.commit()
    return _read(session, project_id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, session: SessionDep) -> None:
    """Also deletes the project's additions and every payment for either."""
    session.delete(_get_project_or_404(session, project_id))
    session.commit()


@router.post("/{project_id}/additions", status_code=status.HTTP_201_CREATED)
def create_addition(project_id: int, body: AdditionIn, session: SessionDep) -> AdditionOut:
    _get_project_or_404(session, project_id)
    addition = Addition(project_id=project_id, **body.model_dump())
    session.add(addition)
    session.commit()
    return _addition_out(addition)


@router.put("/{project_id}/additions/{addition_id}")
def update_addition(
    project_id: int, addition_id: int, body: AdditionIn, session: SessionDep
) -> AdditionOut:
    addition = _get_addition_or_404(session, project_id, addition_id)
    _check_price_covers_payments(body.price, addition.payments)
    for field, value in body.model_dump().items():
        setattr(addition, field, value)
    session.commit()
    return _addition_out(addition)


@router.delete("/{project_id}/additions/{addition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_addition(project_id: int, addition_id: int, session: SessionDep) -> None:
    session.delete(_get_addition_or_404(session, project_id, addition_id))
    session.commit()


def _payment_target(
    session: Session, project_id: int, body: PaymentIn, editing: Payment | None = None
) -> Project | Addition:
    """The project or addition a payment is for, checked so it isn't overpaid.

    When editing, the payment's current amount doesn't count towards what's already paid.
    """
    project = _get_project_or_404(session, project_id)
    if body.addition_id is None:
        target: Project | Addition = project
        name = "this project"
    else:
        target = _get_addition_or_404(session, project_id, body.addition_id)
        name = target.name
    owed = target.price - sum(p.amount for p in target.payments if p is not editing)
    if body.amount > owed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"That's more than the NT${owed:,} still owed on {name}",
        )
    return target


def _payment_out(target: Project | Addition, payment: Payment) -> PaymentOut:
    labelled = _payments_out(target.payments, target.price, target.deposit_percent)
    return next(p for p in labelled if p.id == payment.id)


@router.post("/{project_id}/payments", status_code=status.HTTP_201_CREATED)
def record_payment(project_id: int, body: PaymentIn, session: SessionDep) -> PaymentOut:
    """Pays the project itself, or one of its additions when addition_id is set."""
    target = _payment_target(session, project_id, body)
    payment = Payment(amount=body.amount, paid_on=body.paid_on, note=body.note)
    target.payments.append(payment)
    session.commit()
    return _payment_out(target, payment)


@router.put("/{project_id}/payments/{payment_id}")
def update_payment(
    project_id: int, payment_id: int, body: PaymentIn, session: SessionDep
) -> PaymentOut:
    """Full replace. Changing addition_id moves the payment within the same project."""
    payment = _get_payment_or_404(session, project_id, payment_id)
    target = _payment_target(session, project_id, body, editing=payment)
    payment.project = None
    payment.addition = None
    target.payments.append(payment)
    payment.amount, payment.paid_on, payment.note = body.amount, body.paid_on, body.note
    session.commit()
    return _payment_out(target, payment)


@router.delete("/{project_id}/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(project_id: int, payment_id: int, session: SessionDep) -> None:
    session.delete(_get_payment_or_404(session, project_id, payment_id))
    session.commit()

import enum
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, model_validator

from app.schemas.common import NTD, Name, OptionalName, OptionalText, Percent, PositiveNTD


class Status(enum.StrEnum):
    IN_PROGRESS = "in_progress"  # not delivered yet
    FINAL_PAYMENT_DUE = "final_payment_due"  # delivered, not fully paid
    DONE = "done"  # delivered and fully paid


class PaymentKind(enum.StrEnum):
    DEPOSIT = "deposit"  # falls entirely within the expected deposit
    FINAL = "final"  # falls entirely after the expected deposit
    PAYMENT = "payment"  # single-payment terms, or spans both parts


class Billing(BaseModel):
    """Money figures derived for a project (its own price only) or an addition. All NTD."""

    expected_deposit: int  # round(price * deposit_percent / 100), halves round up
    expected_final: int  # price - expected_deposit
    paid: int
    outstanding: int  # price - paid
    deposit_due: int  # what's left of the deposit
    final_due: int  # what's left of the final payment; deposit_due + final_due == outstanding
    status: Status


class ProjectIn(BaseModel):
    client_id: int
    name: Name
    description: OptionalText = None
    price: NTD
    deposit_percent: Percent = 50
    started_on: date
    due_on: date | None = None
    delivered_on: date | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.due_on is not None and self.due_on < self.started_on:
            raise ValueError("The due date can't be before the start date")
        if self.delivered_on is not None and self.delivered_on < self.started_on:
            raise ValueError("The delivery date can't be before the start date")
        return self


class AdditionIn(BaseModel):
    name: Name
    description: OptionalText = None
    price: NTD
    deposit_percent: Percent = 0  # 0 means a single payment
    agreed_on: date
    delivered_on: date | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> Self:
        if self.delivered_on is not None and self.delivered_on < self.agreed_on:
            raise ValueError("The delivery date can't be before the agreed date")
        return self


class PaymentIn(BaseModel):
    addition_id: int | None = None  # None pays the project itself
    amount: PositiveNTD
    paid_on: date
    note: OptionalName = None


class PaymentOut(PaymentIn):
    id: int
    kind: PaymentKind


class AdditionOut(AdditionIn, Billing):
    id: int
    project_id: int


class ProjectClient(BaseModel):
    id: int
    name: str
    contact_person: str | None
    avatar_url: str | None  # the client's primary Discord contact, if synced


class ProjectOut(ProjectIn, Billing):
    """Billing fields cover the project price alone; the total_* fields add the additions."""

    id: int
    created_at: datetime
    client: ProjectClient
    additions: list[AdditionOut]  # newest agreed first
    payments: list[PaymentOut]  # for the project and its additions, oldest first
    additions_total: int
    total: int  # price + additions_total
    total_paid: int
    total_outstanding: int

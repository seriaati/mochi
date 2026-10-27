from datetime import date, datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.maintenance import MonthStatus
from app.models import Collection, WaiverKind
from app.schemas.clients import ContactOut, DiscordProfileOut
from app.schemas.common import OptionalName, PositiveNTD

# A month is sent as any date in it and stored as its first day.
Period = Annotated[date, AfterValidator(lambda d: d.replace(day=1))]


class RetainerIn(BaseModel):
    client_id: int
    project_id: int | None = None  # the project it's for; may be another client's
    amount: PositiveNTD  # per month
    due_day: Annotated[int, Field(ge=1, le=31)]  # shorter months fall due on their last day
    collection: Collection
    ask_via_id: int | None = None  # the client contact to ask on; "ask" retainers only
    started_on: date
    ended_on: date | None = None
    # First tracked month; earlier ones count as settled. Defaults to the start month.
    tracked_from: Period | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.ended_on is not None and self.ended_on < self.started_on:
            raise ValueError("The end date can't be before the start date")
        first = self.started_on.replace(day=1)
        if self.tracked_from is None:
            self.tracked_from = first
        if self.tracked_from < first:
            raise ValueError("Tracking can't start before the retainer's first month")
        if self.ended_on is not None and self.tracked_from > self.ended_on:
            raise ValueError("Tracking can't start after the retainer ends")
        if self.ask_via_id is not None and self.collection != Collection.ASK:
            raise ValueError("Only retainers you ask for have a contact to ask on")
        return self


class RetainerSwitchIn(BaseModel):
    period: Period  # the first month paid by auto transfer


class RetainerPaymentIn(BaseModel):
    period: Period  # the first month paid for
    months: Annotated[int, Field(ge=1, le=12)] = 1  # in a row from period, when paid ahead
    amount: PositiveNTD  # for all the months together
    paid_on: date


class RetainerPaymentOut(RetainerPaymentIn):
    id: int
    retainer_id: int


class RetainerPauseIn(BaseModel):
    paused_on: date
    resumed_on: date | None = None  # None: still paused

    @model_validator(mode="after")
    def _resumed_after(self) -> Self:
        if self.resumed_on is not None and self.resumed_on <= self.paused_on:
            raise ValueError("It must resume after the day it was paused")
        return self


class RetainerPauseOut(RetainerPauseIn):
    id: int


class RetainerWaiverIn(BaseModel):
    period: Period  # the month let off
    kind: WaiverKind = WaiverKind.WAIVED  # given_up: owed, but written off
    note: OptionalName = None


class RetainerWaiverOut(RetainerWaiverIn):
    id: int
    retainer_id: int


class MonthOut(BaseModel):
    period: date  # first day of the month
    due_on: date
    amount: int  # the fee, or this month's share of the payment for a paid "ask" month
    status: MonthStatus
    paid_on: date | None  # auto transfers count as paid on the due date
    payment: RetainerPaymentOut | None  # the recorded payment covering it, "ask" retainers only
    # Due, overdue or unpaid: days since the due date. Paid "ask" month: days paid after it,
    # or 0.
    days_late: int
    late: bool  # overdue, or paid more than the grace days after the due date


class RetainerClient(BaseModel):
    id: int
    name: str
    avatar_url: str | None  # the client's primary Discord contact, if synced


class RetainerProject(BaseModel):
    id: int
    name: str


class RetainerOut(RetainerIn):
    id: int
    client: RetainerClient
    project: RetainerProject | None
    ask_via: ContactOut | None
    active: bool  # started, not ended and not paused, as of today
    paused_on: date | None  # when it was paused, while it is
    this_month: MonthOut | None  # None when this month isn't billed
    # The next month due today or later, past any "ask" months paid ahead; None once ended
    # or while paused.
    next_due_on: date | None
    months: list[MonthOut]  # the last few billed months up to the next one due, oldest first
    overdue: list[MonthOut]  # oldest first
    received: int  # all time, NTD
    pauses: list[RetainerPauseOut]  # oldest first
    waivers: list[RetainerWaiverOut]  # months let off the fee, oldest first


class OverdueOut(BaseModel):
    retainer_id: int
    client: RetainerClient
    period: date
    due_on: date
    amount: int
    days: int  # since the due date
    last_reminded_on: date | None  # the client, by any reminder


class NextReminderOut(BaseModel):
    """A client's next combined reminder."""

    client: RetainerClient
    periods: list[date]  # the months it asks for, oldest first
    due_on: date  # the oldest of those months' due dates
    amount: int  # all of them together
    at: datetime  # 09:00 local on the slot's date
    pending: bool  # its time has passed; the scheduler sends it within a minute once enabled
    last_reminded_on: date | None


class CollectedOut(BaseModel):
    """This month's fees by the month they're for, not the date they arrived."""

    period: date
    received: int
    expected: int
    paid: int  # retainers paid
    count: int  # retainers billed this month


class AutomaticOut(BaseModel):
    amount: int  # per month, active auto-transfer retainers
    clients: int


class CalendarEntry(BaseModel):
    retainer_id: int
    client: RetainerClient
    amount: int
    status: MonthStatus


class CalendarDay(BaseModel):
    day: date
    # The most pressing: overdue, then due, then upcoming, then unpaid, then paid.
    status: MonthStatus
    entries: list[CalendarEntry]


class ReminderConfigOut(BaseModel):
    enabled: bool  # a webhook URL is configured
    mention_user_id: str | None
    mention: DiscordProfileOut | None  # your synced profile, with mention_user_id
    timezone: str
    time: str  # "09:00", on the due date
    repeat_days: int  # while overdue


class MaintenanceOut(BaseModel):
    today: date
    month: date  # the calendar's month
    active_count: int
    monthly_total: int  # active retainers, NTD
    # Overdue in the calendar's month first, then active ones, then by client name.
    retainers: list[RetainerOut]
    months: dict[int, MonthOut]  # each retainer's calendar month, by ID; only those billed then
    overdue: list[OverdueOut]  # oldest first
    next_reminder: NextReminderOut | None
    collected: CollectedOut
    automatic: AutomaticOut
    calendar: list[CalendarDay]  # only days with something due
    reminders: ReminderConfigOut


class SentOut(BaseModel):
    content: str  # the message posted to Discord

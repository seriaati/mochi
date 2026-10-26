"""Monthly maintenance: due dates, each month's status and the reminder text.

A retainer bills one fee per calendar month (its "period", stored as the month's first day).
The fee falls due on `due_day`, or on the month's last day when the month is shorter. A month
is billed when its due date falls between `started_on` and `ended_on` (inclusive), outside
any pause, and it is not before `tracked_from`. Earlier months count as settled and appear
nowhere.

Status of a billed month, as of `today` (a date in the saved timezone):
- auto transfer: paid once the due date is reached, upcoming before that;
- ask: paid once a recorded payment covers it. A payment covers one month, or several in a
  row when the client pays ahead, each counting for an even share of it. Unpaid, a month is
  upcoming before the due date, due from the due date through GRACE_DAYS after it, and
  overdue after that. A payment is late for a month only when made more than GRACE_DAYS
  after that month's due date. A month still unpaid when the retainer was paused is just
  unpaid: never overdue or reminded, though a payment can still be recorded for it.

Reminders (see app/reminders.py) go out per client at 09:00, every REPEAT_DAYS days. Each of
those times is a "slot", named by its local date.
"""

import calendar
import enum
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import (
    Collection,
    ContactKind,
    ContactMethod,
    Retainer,
    RetainerPause,
    RetainerPayment,
)

REMINDER_TIME = time(9)
REPEAT_DAYS = 2
GRACE_DAYS = 2  # an unpaid "ask" month turns overdue, and a payment late, after this many days
RECENT_MONTHS = 6


class MonthStatus(enum.StrEnum):
    PAID = "paid"
    UPCOMING = "upcoming"  # due date still ahead
    DUE = "due"  # "ask" only: unpaid, due date reached, still within the grace days
    OVERDUE = "overdue"  # "ask" only: unpaid past the grace days
    UNPAID = "unpaid"  # "ask" only: left unpaid when the retainer was paused


@dataclass(frozen=True)
class Month:
    period: date
    due_on: date
    amount: int  # the fee, or this month's share of the payment for a paid "ask" month
    status: MonthStatus
    paid_on: date | None = None
    payment: RetainerPayment | None = None  # the recorded payment covering it
    # Due, overdue or unpaid: days since the due date. Paid "ask" month: days paid after it,
    # or 0.
    days_late: int = 0
    late: bool = False  # overdue, or paid more than GRACE_DAYS after the due date


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(period: date, count: int) -> date:
    years, month = divmod(period.month - 1 + count, 12)
    return date(period.year + years, month + 1, 1)


def months_between(first: date, period: date) -> int:
    return (period.year - first.year) * 12 + period.month - first.month


def covered(payment: RetainerPayment) -> list[date]:
    """The months a payment is for, oldest first."""
    return [add_months(payment.period, i) for i in range(payment.months)]


def share(payment: RetainerPayment, period: date) -> int:
    """A covered month's part of the payment: an even split, the earliest months taking any
    remainder (NT$1,000 over three months is 334, 333, 333)."""
    base, extra = divmod(payment.amount, payment.months)
    return base + (1 if months_between(payment.period, period) < extra else 0)


def month_range(payment: RetainerPayment) -> str:
    """The months a payment covers, e.g. "Jan 2027", "Jan–Mar 2027" or "Dec 2026–Feb 2027"."""
    first, last = payment.period, add_months(payment.period, payment.months - 1)
    if first == last:
        return f"{first:%b %Y}"
    if first.year == last.year:
        return f"{first:%b}–{last:%b %Y}"
    return f"{first:%b %Y}–{last:%b %Y}"


def payment_for(retainer: Retainer, period: date) -> RetainerPayment | None:
    return next((p for p in retainer.payments if period in covered(p)), None)


def due_on(period: date, due_day: int) -> date:
    """The due date in a month, clamped to the month's last day (31 -> 30 Apr, 28/29 Feb)."""
    last = calendar.monthrange(period.year, period.month)[1]
    return period.replace(day=min(due_day, last))


def current_pause(retainer: Retainer) -> RetainerPause | None:
    return next((p for p in retainer.pauses if p.resumed_on is None), None)


def is_paused(retainer: Retainer, day: date) -> bool:
    return any(
        p.paused_on <= day and (p.resumed_on is None or day < p.resumed_on) for p in retainer.pauses
    )


def is_billed(retainer: Retainer, period: date) -> bool:
    """Whether a month counts: due between the start and end dates, outside any pause, and
    tracked."""
    if period < retainer.tracked_from:
        return False
    due = due_on(period, retainer.due_day)
    return (
        retainer.started_on <= due
        and (retainer.ended_on is None or due <= retainer.ended_on)
        and not is_paused(retainer, due)
    )


def is_active(retainer: Retainer, today: date) -> bool:
    return (
        retainer.started_on <= today
        and (retainer.ended_on is None or today <= retainer.ended_on)
        and not is_paused(retainer, today)
    )


def billed_periods(retainer: Retainer, through: date) -> Iterator[date]:
    """Billed months from the first tracked one up to the period `through`, oldest first."""
    period = max(month_start(retainer.started_on), retainer.tracked_from)
    last = through if retainer.ended_on is None else min(through, month_start(retainer.ended_on))
    while period <= last:
        if is_billed(retainer, period):
            yield period
        period = add_months(period, 1)


def next_period(retainer: Retainer, today: date) -> date | None:
    """The first billed month due today or later, skipping "ask" months already paid ahead,
    or None once the retainer has ended or while it's paused."""
    period = max(month_start(today), month_start(retainer.started_on), retainer.tracked_from)
    # This month's due date may have passed or precede the start, and months may be paid.
    paid_until = max((add_months(p.period, p.months) for p in retainer.payments), default=period)
    last = max(add_months(period, 2), paid_until)
    while period <= last:
        if (
            is_billed(retainer, period)
            and due_on(period, retainer.due_day) >= today
            and payment_for(retainer, period) is None
        ):
            return period
        period = add_months(period, 1)
    return None


def month(retainer: Retainer, period: date, today: date) -> Month:
    due = due_on(period, retainer.due_day)
    if retainer.collection == Collection.AUTO_TRANSFER:
        if due <= today:
            return Month(period, due, retainer.amount, MonthStatus.PAID, paid_on=due)
        return Month(period, due, retainer.amount, MonthStatus.UPCOMING)
    payment = payment_for(retainer, period)
    if payment is not None:
        days = max((payment.paid_on - due).days, 0)
        return Month(
            period,
            due,
            share(payment, period),
            MonthStatus.PAID,
            paid_on=payment.paid_on,
            payment=payment,
            days_late=days,
            late=days > GRACE_DAYS,
        )
    days = (today - due).days
    if any(p.paused_on > due for p in retainer.pauses):
        return Month(period, due, retainer.amount, MonthStatus.UNPAID, days_late=days)
    if days < 0:
        return Month(period, due, retainer.amount, MonthStatus.UPCOMING)
    if days <= GRACE_DAYS:
        return Month(period, due, retainer.amount, MonthStatus.DUE, days_late=days)
    return Month(period, due, retainer.amount, MonthStatus.OVERDUE, days_late=days, late=True)


def this_month(retainer: Retainer, today: date) -> Month | None:
    period = month_start(today)
    return month(retainer, period, today) if is_billed(retainer, period) else None


def overdue(retainer: Retainer, today: date) -> list[Month]:
    if retainer.collection != Collection.ASK:
        return []
    months = (month(retainer, p, today) for p in billed_periods(retainer, month_start(today)))
    return [m for m in months if m.status == MonthStatus.OVERDUE]


def recent(retainer: Retainer, today: date) -> list[Month]:
    """The last few billed months, up to and including the next one due. Oldest first."""
    through = next_period(retainer, today) or month_start(today)
    periods = list(billed_periods(retainer, through))[-RECENT_MONTHS:]
    return [month(retainer, p, today) for p in periods]


def received(retainer: Retainer, today: date) -> int:
    """All maintenance received for tracked months: recorded payments, or auto transfers due
    by today."""
    if retainer.collection == Collection.ASK:
        return sum(p.amount for p in retainer.payments if p.period >= retainer.tracked_from)
    reached = [
        p
        for p in billed_periods(retainer, month_start(today))
        if due_on(p, retainer.due_day) <= today
    ]
    return retainer.amount * len(reached)


class ClientFlag(enum.StrEnum):
    """The small flag on a client card."""

    OVERDUE = "overdue"  # an "ask" month is overdue
    DUE = "due"  # an "ask" fee is due (in its grace days), or this month's is still to come
    AUTO = "auto"  # pays by automatic transfer


@dataclass(frozen=True)
class ClientMaintenance:
    monthly: int  # retainers active today
    flag: ClientFlag | None
    due_on: date | None  # with the DUE flag


def client_maintenance(retainers: Iterable[Retainer], today: date) -> ClientMaintenance:
    retainers = list(retainers)
    monthly = sum(r.amount for r in retainers if is_active(r, today))
    if any(overdue(r, today) for r in retainers):
        return ClientMaintenance(monthly, ClientFlag.OVERDUE, None)
    due = [
        m.due_on
        for r in retainers
        for m in unpaid_ask_months(r, today)
        if m.status == MonthStatus.DUE
    ]
    due += [
        m.due_on
        for r in retainers
        if r.collection == Collection.ASK
        and (m := this_month(r, today)) is not None
        and m.status == MonthStatus.UPCOMING
    ]
    if due:
        return ClientMaintenance(monthly, ClientFlag.DUE, min(due))
    if any(r.collection == Collection.AUTO_TRANSFER and is_active(r, today) for r in retainers):
        return ClientMaintenance(monthly, ClientFlag.AUTO, None)
    return ClientMaintenance(monthly, None, None)


# Reminder slots


def slot_at(slot_on: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(slot_on, REMINDER_TIME, tz)


def latest_slot(due: date, now: datetime, tz: ZoneInfo) -> date | None:
    """The latest reminder slot at or before `now`, or None before 09:00 on the due date."""
    local = now.astimezone(tz)
    days = (local.date() - due).days
    if local.time() < REMINDER_TIME:
        days -= 1
    if days < 0:
        return None
    return due + timedelta(days=days - days % REPEAT_DAYS)


def unpaid_ask_months(retainer: Retainer, today: date) -> list[Month]:
    """Unpaid months that are or will be reminded about: due and overdue ones, and the next
    one coming up. Not those left unpaid by a pause."""
    if retainer.collection != Collection.ASK:
        return []
    through = next_period(retainer, today) or month_start(today)
    months = (month(retainer, p, today) for p in billed_periods(retainer, through))
    return [m for m in months if m.status not in (MonthStatus.PAID, MonthStatus.UNPAID)]


# Reminder text

_CONTACT_PHRASES = {
    ContactKind.DISCORD: "on Discord {}",
    ContactKind.LINE: "on LINE {}",
    ContactKind.EMAIL: "by email at {}",
    ContactKind.OTHER: "via {}",
}


def month_name(period: date, today: date) -> str:
    name = calendar.month_name[period.month]
    return name if period.year == today.year else f"{name} {period.year}"


def reminder_line(
    client_name: str,
    months: list[Month],
    contact: ContactMethod | None,
    today: date,
    record_url: str | None = None,
) -> str:
    """Everything a client owes in one line, oldest month first, e.g.
    "Ask Northwind Coffee for NT$750 (August, September, October) on Discord @danpark".
    A Discord handle with a user ID links to their profile, one click from your DM, and
    `record_url` adds a link that opens Record payment. Links are in <> so Discord doesn't
    embed them."""
    names = list(dict.fromkeys(month_name(m.period, today) for m in months))
    line = f"Ask {client_name} for NT${sum(m.amount for m in months):,} ({', '.join(names)})"
    if contact is not None:
        handle = contact.value
        if contact.kind == ContactKind.DISCORD and contact.discord_user_id is not None:
            handle = f"[{handle}](<https://discord.com/users/{contact.discord_user_id}>)"
        line += " " + _CONTACT_PHRASES[contact.kind].format(handle)
    if record_url is not None:
        line += f" · [Record payment](<{record_url}>)"
    return line


def message(lines: list[str], mention_user_id: str | None) -> str:
    mention = f"<@{mention_user_id}> " if mention_user_id else ""
    if len(lines) == 1:
        return mention + lines[0]
    return mention + "Maintenance reminders:\n" + "\n".join(f"- {line}" for line in lines)

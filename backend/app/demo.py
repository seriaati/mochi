"""The public demo's daily reset: wipes every record and fills in made-up clients, projects and
maintenance fees, dated around today so each page has something to show.

    python -m app.demo reset

Refuses to run unless DEMO is set, as it deletes everything.
"""

import argparse
import sys
from datetime import date, timedelta

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.clock import clock_for, utc_now
from app.config import settings
from app.db import SessionLocal
from app.maintenance import add_months, billed_periods, due_on, month_start
from app.models import (
    Addition,
    AppSettings,
    Base,
    Client,
    Collection,
    ContactKind,
    ContactMethod,
    Payment,
    Project,
    Retainer,
    RetainerPayment,
)


def wipe(session: Session) -> None:
    """Deletes every record, sessions and MCP access included, and puts Settings back to their
    defaults."""
    tables = [t.name for t in Base.metadata.sorted_tables if t is not AppSettings.__table__]
    session.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    session.expunge_all()  # what was loaded is gone
    session.execute(delete(AppSettings))
    session.add(AppSettings(id=1, user_name="Alex"))
    session.flush()


def _pay_months(retainer: Retainer, through: date, skip_last: bool = False) -> None:
    """Records an on-time payment for each billed month due before `through`, but the latest
    one when `skip_last`."""
    periods = [
        p for p in billed_periods(retainer, through) if due_on(p, retainer.due_day) < through
    ]
    if skip_last:
        periods = periods[:-1]
    for period in periods:
        paid = due_on(period, retainer.due_day)
        retainer.payments.append(
            RetainerPayment(period=period, amount=retainer.amount, paid_on=paid)
        )


def seed(session: Session, today: date) -> None:
    def ago(days: int) -> date:
        return today - timedelta(days=days)

    cafe = Client(name="Lantern Café", contact_person="Mei Lin", notes="Prefers LINE.")
    cafe_line = ContactMethod(kind=ContactKind.LINE, value="@lanterncafe")
    cafe.contacts = [cafe_line, ContactMethod(kind=ContactKind.EMAIL, value="mei@lantern.example")]
    guild = Client(name="Pixel Guild", contact_person="Kai")
    guild_discord = ContactMethod(kind=ContactKind.DISCORD, value="kai.dev")
    guild.contacts = [guild_discord]
    studio = Client(name="Northwind Studio", contact_person="Jordan Wu")
    studio.contacts = [ContactMethod(kind=ContactKind.EMAIL, value="jordan@northwind.example")]
    bakery = Client(name="Hoshi Bakery", contact_person="Aiko")
    bakery_line = ContactMethod(kind=ContactKind.LINE, value="@hoshibakery")
    bakery.contacts = [bakery_line]

    website = Project(
        client=cafe,
        name="Ordering website",
        description="Menu, online orders and pickup times.",
        price=48000,
        started_on=ago(75),
        due_on=ago(20),
        delivered_on=ago(25),
        payments=[
            Payment(amount=24000, paid_on=ago(74), note="Deposit"),
            Payment(amount=24000, paid_on=ago(24)),
        ],
    )
    website.additions = [
        Addition(
            name="Table reservations",
            price=8000,
            agreed_on=ago(10),
            delivered_on=ago(2),
        )
    ]
    bot = Project(
        client=guild,
        name="Community Discord bot",
        description="Roles, events and a leveling system.",
        price=15000,
        started_on=ago(40),
        due_on=ago(5),
        delivered_on=ago(6),
        payments=[Payment(amount=7500, paid_on=ago(39), note="Deposit")],
    )
    Project(
        client=studio,
        name="Portfolio redesign",
        price=32000,
        deposit_percent=30,
        started_on=ago(12),
        due_on=today + timedelta(days=25),
        payments=[Payment(amount=9600, paid_on=ago(11), note="Deposit")],
    )
    line_bot = Project(
        client=bakery,
        name="LINE ordering bot",
        price=22000,
        started_on=ago(220),
        due_on=ago(170),
        delivered_on=ago(172),
        payments=[
            Payment(amount=11000, paid_on=ago(219), note="Deposit"),
            Payment(amount=11000, paid_on=ago(170)),
        ],
    )

    Retainer(
        client=cafe,
        project=website,
        amount=800,
        due_day=1,
        collection=Collection.AUTO_TRANSFER,
        started_on=ago(24),
    )
    # Due five days ago and left unpaid, so it shows as overdue.
    bot_upkeep = Retainer(
        client=guild,
        project=bot,
        amount=1500,
        due_day=ago(5).day,
        collection=Collection.ASK,
        ask_via=guild_discord,
        started_on=ago(130),
    )
    bot_upkeep.tracked_from = month_start(bot_upkeep.started_on)
    _pay_months(bot_upkeep, today, skip_last=True)
    line_upkeep = Retainer(
        client=bakery,
        project=line_bot,
        amount=1000,
        due_day=15,
        collection=Collection.ASK,
        ask_via=bakery_line,
        started_on=ago(170),
    )
    line_upkeep.tracked_from = month_start(line_upkeep.started_on)
    _pay_months(line_upkeep, today)
    # Then two months paid ahead.
    ahead = add_months(line_upkeep.payments[-1].period, 1)
    line_upkeep.payments.append(
        RetainerPayment(period=ahead, months=2, amount=2000, paid_on=ago(3))
    )

    session.add_all([cafe, guild, studio, bakery])  # projects and retainers come along
    session.flush()


def reset(session: Session) -> None:
    wipe(session)
    seed(session, clock_for(session, utc_now()).today)
    session.commit()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.demo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("reset", help="delete all data and fill in the demo's sample data")
    parser.parse_args(argv)

    if not settings.demo:
        sys.exit("Refusing to reset: DEMO isn't set, and this deletes all data.")
    with SessionLocal() as session:
        reset(session)


if __name__ == "__main__":
    main()

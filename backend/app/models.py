"""Domain models. All money is stored as whole NTD integers."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _enum(cls: type[enum.Enum]) -> Enum:
    # Store enum values ("discord") rather than SQLAlchemy's default of member names ("DISCORD").
    return Enum(cls, values_callable=lambda members: [m.value for m in members])


class ContactKind(enum.StrEnum):
    DISCORD = "discord"
    LINE = "line"
    EMAIL = "email"
    OTHER = "other"


class Collection(enum.StrEnum):
    AUTO_TRANSFER = "auto_transfer"  # assumed paid on the due date
    ASK = "ask"  # needs a reminder and a recorded payment


class SyncStatus(enum.StrEnum):
    """How the last Discord profile lookup went."""

    OK = "ok"
    NOT_FOUND = "not_found"  # Discord has no user with this ID
    ERROR = "error"  # the lookup failed; retried sooner than a fresh profile


class DiscordProfile:
    """A Discord user's profile as last synced (see app/discord_sync.py), mixed into the tables
    that hold a Discord user ID. Profile fields are cleared when the user isn't found and kept
    when a lookup fails."""

    discord_username: Mapped[str | None] = mapped_column(String(100))
    discord_global_name: Mapped[str | None] = mapped_column(String(100))  # the display name
    discord_avatar_url: Mapped[str | None] = mapped_column(String(255))
    discord_sync_status: Mapped[SyncStatus | None] = mapped_column(_enum(SyncStatus))
    discord_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    contacts: Mapped[list[ContactMethod]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(back_populates="client")
    retainers: Mapped[list[Retainer]] = relationship(back_populates="client")


class ContactMethod(DiscordProfile, Base):
    __tablename__ = "contact_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    kind: Mapped[ContactKind] = mapped_column(_enum(ContactKind))
    value: Mapped[str] = mapped_column(
        String(200)
    )  # handle, LINE ID or address as shown to the user
    discord_user_id: Mapped[int | None] = mapped_column(BigInteger)  # for live name/avatar lookup

    client: Mapped[Client] = relationship(back_populates="contacts")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("deposit_percent BETWEEN 0 AND 100", name="deposit_percent_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int]
    deposit_percent: Mapped[int] = mapped_column(default=50)
    started_on: Mapped[date]
    due_on: Mapped[date | None]
    delivered_on: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    client: Mapped[Client] = relationship(back_populates="projects")
    additions: Mapped[list[Addition]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    # Deleted along with the project. No delete-orphan: a payment has two possible parents.
    payments: Mapped[list[Payment]] = relationship(
        back_populates="project", cascade="all", passive_deletes=True
    )


class Addition(Base):
    """An extra feature billed on top of a project, often requested after it is done."""

    __tablename__ = "additions"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("deposit_percent BETWEEN 0 AND 100", name="deposit_percent_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int]
    # 0 means a single payment; otherwise split into deposit and rest like a project.
    deposit_percent: Mapped[int] = mapped_column(default=0)
    agreed_on: Mapped[date]
    delivered_on: Mapped[date | None]

    project: Mapped[Project] = relationship(back_populates="additions")
    payments: Mapped[list[Payment]] = relationship(
        back_populates="addition", cascade="all", passive_deletes=True
    )


class Payment(Base):
    """Money received for a project or for one of its additions."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("(project_id IS NULL) <> (addition_id IS NULL)", name="one_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    addition_id: Mapped[int | None] = mapped_column(ForeignKey("additions.id", ondelete="CASCADE"))
    amount: Mapped[int]
    paid_on: Mapped[date]
    note: Mapped[str | None] = mapped_column(String(200))

    project: Mapped[Project | None] = relationship(back_populates="payments")
    addition: Mapped[Addition | None] = relationship(back_populates="payments")


class Retainer(Base):
    """A client's monthly maintenance fee, which may cover several projects."""

    __tablename__ = "retainers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # Months shorter than due_day fall due on their last day.
        CheckConstraint("due_day BETWEEN 1 AND 31", name="due_day_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    amount: Mapped[int]
    due_day: Mapped[int]
    collection: Mapped[Collection] = mapped_column(_enum(Collection))
    ask_via_id: Mapped[int | None] = mapped_column(
        ForeignKey("contact_methods.id", ondelete="SET NULL")
    )
    started_on: Mapped[date]
    ended_on: Mapped[date | None]
    # First month (its first day) that is tracked. Earlier months count as settled: never
    # overdue or reminded, and left out of all totals. started_on stays the true start date.
    tracked_from: Mapped[date] = mapped_column(
        default=lambda ctx: ctx.get_current_parameters()["started_on"].replace(day=1)
    )

    client: Mapped[Client] = relationship(back_populates="retainers")
    ask_via: Mapped[ContactMethod | None] = relationship()
    payments: Mapped[list[RetainerPayment]] = relationship(
        back_populates="retainer", cascade="all, delete-orphan"
    )


class RetainerPayment(Base):
    """A recorded monthly payment. Only needed for ASK retainers."""

    __tablename__ = "retainer_payments"
    __table_args__ = (UniqueConstraint("retainer_id", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    retainer_id: Mapped[int] = mapped_column(ForeignKey("retainers.id", ondelete="CASCADE"))
    period: Mapped[date]  # first day of the month being paid for
    amount: Mapped[int]
    paid_on: Mapped[date]

    retainer: Mapped[Retainer] = relationship(back_populates="payments")


class ReminderLog(Base):
    """A maintenance reminder posted to Discord for a client, so none is sent twice.

    `slot_on` is the local day the reminder counts for: the scheduled 09:00 slot it stands for
    (even when sent late), or the day of a manual send. The scheduler skips a slot that is
    already logged, and any day the client was already reminded on.
    """

    __tablename__ = "reminder_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    slot_on: Mapped[date]
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppSettings(DiscordProfile, Base):
    """The user's in-app settings: a single row with id 1."""

    __tablename__ = "app_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False, default=1)
    # IANA name. Due dates, "today" and the 09:00 reminder time are counted in it.
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Taipei")
    # Whose profile is cached here: DISCORD_MENTION_USER_ID when it was last synced.
    discord_user_id: Mapped[int | None] = mapped_column(BigInteger)

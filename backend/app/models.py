"""Domain models. All money is stored as whole NTD integers."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app import crypto


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
    # The project the fee is for. It may belong to another client, e.g. a bot several pay for.
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
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
    project: Mapped[Project | None] = relationship()
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
    # What the dashboard calls the user, e.g. in the Overview greeting. None falls back to their
    # Discord name.
    user_name: Mapped[str | None] = mapped_column(String(60))
    # Shown in the top bar. None shows "Studio" and a plain mark.
    studio_name: Mapped[str | None] = mapped_column(String(60))
    studio_logo: Mapped[str | None] = mapped_column(Text)  # a small image as a data: URL
    # Where maintenance reminders post, encrypted like the bot token: anyone with the URL can
    # post to the channel. Read and set it through discord_webhook_url. None turns reminders off.
    discord_webhook_url_encrypted: Mapped[str | None] = mapped_column(Text)
    # The user's own Discord ID, @mentioned in each reminder.
    discord_mention_user_id: Mapped[int | None] = mapped_column(BigInteger)
    # The bot token for profile sync, encrypted with ENCRYPTION_KEY (see app/crypto.py). None
    # turns sync off.
    discord_bot_token_encrypted: Mapped[str | None] = mapped_column(Text)
    # Whose profile is cached here: discord_mention_user_id when it was last synced.
    discord_user_id: Mapped[int | None] = mapped_column(BigInteger)
    # Keni, where money received is mirrored as income (see app/keni_sync.py). Its base URL,
    # e.g. https://app.keni.seria.moe. None: not connected.
    keni_url: Mapped[str | None] = mapped_column(String(255))
    # A Keni personal API token, encrypted like the bot token.
    keni_token_encrypted: Mapped[str | None] = mapped_column(Text)
    # Where new income is recorded, changeable while connected. Names as shown in Settings.
    keni_wallet_id: Mapped[str | None] = mapped_column(String(36))
    keni_wallet_name: Mapped[str | None] = mapped_column(String(100))
    keni_wallet_currency: Mapped[str | None] = mapped_column(String(10))
    keni_category_id: Mapped[str | None] = mapped_column(String(36))
    keni_category_name: Mapped[str | None] = mapped_column(String(100))
    # The local day it was connected. Money already received by then stays out of Keni.
    keni_connected_on: Mapped[date | None]
    # Why the last sync stopped, until a sync gets everything through.
    keni_error: Mapped[str | None] = mapped_column(Text)

    @property
    def discord_bot_token_set(self) -> bool:
        return self.discord_bot_token_encrypted is not None

    @property
    def discord_webhook_url(self) -> str | None:
        """None when unset, or when it can't be decrypted (no ENCRYPTION_KEY, or a new one)."""
        encrypted = self.discord_webhook_url_encrypted
        return crypto.decrypt(encrypted) if encrypted is not None else None

    @discord_webhook_url.setter
    def discord_webhook_url(self, url: str | None) -> None:
        """Raises crypto.NoKey for a URL without ENCRYPTION_KEY."""
        self.discord_webhook_url_encrypted = crypto.encrypt(url) if url is not None else None


class KeniLink(Base):
    """Money received here and its Keni transaction (see app/keni_sync.py)."""

    __tablename__ = "keni_links"

    # What it mirrors: "payment:<id>", "retainer_payment:<id>", or "retainer:<id>:<YYYY-MM>" for
    # an auto transfer month. No foreign key: once the source is gone, the next sync deletes its
    # Keni transaction, then this row.
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    # None: kept out of Keni, as it was received before connecting or was deleted in Keni.
    keni_id: Mapped[str | None] = mapped_column(String(36))
    # The wallet it is in, which Keni addresses it through: the one chosen when it was sent.
    wallet_id: Mapped[str | None] = mapped_column(String(36))
    # As last sent, to tell when the source changes. None while kept out.
    amount: Mapped[int | None]
    paid_on: Mapped[date | None]
    description: Mapped[str | None] = mapped_column(String(500))


class AuthSession(Base):
    """A login session (see app/auth.py). The cookie holds a random token; only its SHA-256 is
    stored here, so a leaked database can't be replayed as a cookie."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # hex SHA-256 of the token
    # SHA-256 of the AUTH_PASSWORD_HASH it logged in under: setting a new password ends it.
    password_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthClient(Base):
    """An MCP client that registered itself for OAuth (see app/oauth.py)."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # The registration as the MCP SDK's OAuthClientInformationFull, client secret included.
    info: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthCode(Base):
    """An authorization code, issued when the user approves a client and exchanged once for
    tokens. Stored as the code's SHA-256, like the tokens."""

    __tablename__ = "oauth_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE")
    )
    # The SDK's AuthorizationCode without the code itself: PKCE challenge, redirect URI, scopes.
    params: Mapped[dict] = mapped_column(JSON)
    # Of the AUTH_PASSWORD_HASH it was approved under, as on AuthSession.
    password_fingerprint: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthToken(Base):
    """An MCP client's access or refresh token, stored as its SHA-256. Each grant (one approval,
    then each refresh of it) issues one of each; refreshing or revoking ends the pair."""

    __tablename__ = "oauth_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # "access" or "refresh"
    grant_id: Mapped[str] = mapped_column(String(64), index=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE")
    )
    scopes: Mapped[list[str]] = mapped_column(JSON)
    resource: Mapped[str | None] = mapped_column(String(255))
    # Setting a new password ends MCP access too, as it does browser sessions.
    password_fingerprint: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

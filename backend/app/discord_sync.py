"""Discord profile sync: display names, usernames and avatars of clients' Discord contacts and
of you (DISCORD_MENTION_USER_ID), looked up by user ID with the bot token.

A profile is looked up when a contact's Discord user ID is saved (inline, with a short timeout),
when you press Sync now, and by the background loop in app/reminders.py: each tick refreshes
up to BATCH profiles that are older than TTL, or whose last lookup failed more than RETRY_ERROR
ago, oldest first and with a pause between lookups. A 429 pauses every lookup until Discord's
retry_after has passed.

Without a bot token nothing is looked up and the API shows no synced data, so the UI falls back
to the typed handle and initials. Times come from the caller, so tests pin them.
"""

import logging
import time
from collections.abc import Iterable
from datetime import datetime, timedelta

import httpx2 as httpx
from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from app import discord
from app.clock import utc_now
from app.config import settings
from app.db import SessionLocal
from app.models import AppSettings, ContactMethod, DiscordProfile, SyncStatus
from app.schemas.clients import DiscordProfileOut, ProfileStatus

log = logging.getLogger(__name__)

TTL = timedelta(hours=1)
RETRY_ERROR = timedelta(minutes=5)
BATCH = 10  # lookups per tick
PAUSE_SECONDS = 1.0  # between lookups in a tick
TIMEOUT = 10  # seconds
SAVE_TIMEOUT = 3  # seconds, so saving a contact stays quick

# Set by a 429: no lookups before this time.
_paused_until: datetime | None = None


def enabled() -> bool:
    return settings.discord_bot_token is not None


def _mention_id() -> int | None:
    mention = settings.discord_mention_user_id
    return int(mention) if mention else None


def clear(row: DiscordProfile) -> None:
    """Forget the synced profile, e.g. when the user ID changes."""
    row.discord_username = None
    row.discord_global_name = None
    row.discord_avatar_url = None
    row.discord_sync_status = None
    row.discord_synced_at = None


def _lookup(row: DiscordProfile, user_id: int, now: datetime, timeout: float) -> None:
    """Look the user up and store the result on the row. Raises discord.RateLimited while
    lookups are paused, and pauses them when Discord answers 429."""
    global _paused_until
    if _paused_until is not None and now < _paused_until:
        raise discord.RateLimited((_paused_until - now).total_seconds())
    try:
        user = discord.fetch_user(user_id, timeout)
    except discord.RateLimited as limited:
        _paused_until = now + timedelta(seconds=limited.retry_after)
        raise
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as error:
        log.warning("Discord lookup of user %s failed: %s", user_id, error)
        row.discord_sync_status = SyncStatus.ERROR  # keeps the last good profile
    else:
        if user is None:
            clear(row)
            row.discord_sync_status = SyncStatus.NOT_FOUND
        else:
            row.discord_username = user.username
            row.discord_global_name = user.global_name
            row.discord_avatar_url = user.avatar_url
            row.discord_sync_status = SyncStatus.OK
    row.discord_synced_at = now


def on_save(contact: ContactMethod, user_id: int | None, now: datetime) -> None:
    """After a contact's Discord user ID is set or changed: drop the old profile and look the
    new one up straight away. While rate limited, the loop picks it up later."""
    clear(contact)
    if enabled() and user_id is not None:
        try:
            _lookup(contact, user_id, now, SAVE_TIMEOUT)
        except discord.RateLimited:
            pass


def sync_now(contacts: Iterable[ContactMethod], now: datetime) -> None:
    """Look these contacts up whatever their age. Raises discord.RateLimited."""
    for contact in sorted(contacts, key=lambda c: c.id):
        if contact.discord_user_id is not None:
            _lookup(contact, contact.discord_user_id, now, TIMEOUT)


def _stale(model: type[ContactMethod | AppSettings], now: datetime) -> ColumnElement[bool]:
    return or_(
        model.discord_synced_at.is_(None),
        model.discord_synced_at <= now - TTL,
        and_(
            model.discord_sync_status == SyncStatus.ERROR,
            model.discord_synced_at <= now - RETRY_ERROR,
        ),
    )


def due(session: Session, now: datetime) -> list[ContactMethod | AppSettings]:
    """Profiles to refresh on this tick: yours first, then contacts, least recent first."""
    rows: list[ContactMethod | AppSettings] = []
    mention = _mention_id()
    if mention is not None:
        me = session.get_one(AppSettings, 1)
        if me.discord_user_id != mention:  # DISCORD_MENTION_USER_ID changed
            clear(me)
            me.discord_user_id = mention
        rows += session.scalars(select(AppSettings).where(_stale(AppSettings, now)))
    query = (
        select(ContactMethod)
        .where(ContactMethod.discord_user_id.is_not(None), _stale(ContactMethod, now))
        .order_by(ContactMethod.discord_synced_at.asc().nulls_first(), ContactMethod.id)
        .limit(BATCH - len(rows))
    )
    return rows + list(session.scalars(query))


def refresh_due(session: Session, now: datetime, pause: float = 0) -> int:
    """Refresh what is due, committing after each lookup. Stops early when rate limited.
    Returns how many were looked up."""
    if not enabled():
        return 0
    rows = due(session, now)
    done = 0
    try:
        for row in rows:
            if done and pause:
                time.sleep(pause)
            _lookup(row, row.discord_user_id, now, TIMEOUT)
            session.commit()
            done += 1
    except discord.RateLimited as limited:
        log.info("Discord asked to wait %gs before more lookups", limited.retry_after)
    session.commit()
    return done


def tick() -> None:
    """One run of the background loop."""
    with SessionLocal() as session:
        count = refresh_due(session, utc_now(), pause=PAUSE_SECONDS)
    if count:
        log.info("Refreshed %d Discord profile(s)", count)


# Output


def profile_out(row: DiscordProfile, user_id: int | None) -> DiscordProfileOut | None:
    """What the API shows for a row's profile; None without a user ID."""
    if user_id is None:
        return None
    if not enabled():
        return DiscordProfileOut(
            status=ProfileStatus.OFF,
            synced_at=None,
            username=None,
            display_name=None,
            avatar_url=None,
        )
    return DiscordProfileOut(
        status=row.discord_sync_status or ProfileStatus.PENDING,
        synced_at=row.discord_synced_at,
        username=row.discord_username,
        display_name=row.discord_global_name or row.discord_username,
        avatar_url=row.discord_avatar_url,
    )


def primary(contacts: Iterable[ContactMethod]) -> DiscordProfileOut | None:
    """The client's first Discord contact with a synced profile, for its avatar and name."""
    for contact in sorted(contacts, key=lambda c: c.id):
        profile = profile_out(contact, contact.discord_user_id)
        if profile is not None and profile.status == ProfileStatus.OK:
            return profile
    return None


def primary_avatar(contacts: Iterable[ContactMethod]) -> str | None:
    profile = primary(contacts)
    return profile.avatar_url if profile else None


def mention_out(session: Session) -> DiscordProfileOut | None:
    """Your profile, for DISCORD_MENTION_USER_ID; pending until synced for that ID."""
    mention = _mention_id()
    if mention is None:
        return None
    me = session.get_one(AppSettings, 1)
    if me.discord_user_id != mention:  # what's cached is for another ID
        return profile_out(AppSettings(), mention)
    return profile_out(me, mention)

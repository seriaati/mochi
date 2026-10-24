import math
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app import discord, discord_sync
from app.clock import ClockDep, TodayDep
from app.db import SessionDep
from app.maintenance import client_maintenance
from app.models import (
    Addition,
    Client,
    ContactKind,
    ContactMethod,
    Project,
    Retainer,
    SyncStatus,
)
from app.schemas.clients import ClientCreate, ClientIn, ClientOut, ContactIn, ContactOut

router = APIRouter(prefix="/api/clients", tags=["clients"])


def _with_stats() -> Select[tuple[Client, int, int, int]]:
    """Clients with their contacts, retainers and the project figures the cards show."""
    project_count = select(func.count(Project.id)).where(Project.client_id == Client.id)
    project_total = select(func.coalesce(func.sum(Project.price), 0)).where(
        Project.client_id == Client.id
    )
    addition_total = (
        select(func.coalesce(func.sum(Addition.price), 0))
        .join(Addition.project)
        .where(Project.client_id == Client.id)
    )
    return (
        select(
            Client,
            project_count.scalar_subquery(),
            project_total.scalar_subquery(),
            addition_total.scalar_subquery(),
        )
        .options(
            selectinload(Client.contacts),
            selectinload(Client.retainers).selectinload(Retainer.payments),
        )
        .execution_options(populate_existing=True)
    )


def contact_out(contact: ContactMethod) -> ContactOut:
    profile = discord_sync.profile_out(contact, contact.discord_user_id)
    return ContactOut.model_validate(contact).model_copy(update={"discord_profile": profile})


def _out(
    client: Client, project_count: int, projects: int, additions: int, today: date
) -> ClientOut:
    maintenance = client_maintenance(client.retainers, today)
    primary = discord_sync.primary(client.contacts)
    return ClientOut(
        id=client.id,
        name=client.name,
        contact_person=client.contact_person,
        notes=client.notes,
        created_at=client.created_at,
        contacts=[contact_out(c) for c in client.contacts],
        avatar_url=primary.avatar_url if primary else None,
        discord_name=primary.display_name if primary else None,
        project_count=project_count,
        lifetime_billed=projects + additions,
        monthly_maintenance=maintenance.monthly,
        maintenance_flag=maintenance.flag,
        maintenance_due_on=maintenance.due_on,
    )


def _read(session: Session, client_id: int, today: date) -> ClientOut:
    row = session.execute(_with_stats().where(Client.id == client_id)).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return _out(*row, today)


def _get_client(session: Session, client_id: int) -> Client:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client


def _get_contact(session: Session, client_id: int, contact_id: int) -> ContactMethod:
    contact = session.get(ContactMethod, contact_id)
    if contact is None or contact.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found")
    return contact


@router.get("")
def list_clients(session: SessionDep, today: TodayDep) -> list[ClientOut]:
    rows = session.execute(_with_stats().order_by(func.lower(Client.name), Client.id))
    return [_out(*row, today) for row in rows]


def _discord_contact(user_id: int, now: datetime) -> ContactMethod:
    """A Discord contact for a new client, looked up straight away. Its handle is their username,
    or the ID until a lookup works. Raises 422 for an ID Discord doesn't know."""
    contact = ContactMethod(kind=ContactKind.DISCORD, value=str(user_id), discord_user_id=user_id)
    discord_sync.on_save(contact, user_id, now)
    if contact.discord_sync_status == SyncStatus.NOT_FOUND:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No Discord user has that ID")
    if contact.discord_username is not None:
        contact.value = contact.discord_username
    return contact


def _discord_name(contact: ContactMethod) -> str:
    """The contact's Discord display name, for a client added without a name."""
    if contact.discord_sync_status == SyncStatus.OK:
        return contact.discord_global_name or contact.discord_username or contact.value
    reason = (
        "Discord sync is off: add a bot token in Settings"
        if not discord_sync.enabled()
        else "Couldn't look that Discord user up. Try again"
    )
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{reason}, or enter a name")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(body: ClientCreate, session: SessionDep, clock: ClockDep) -> ClientOut:
    """A Discord user ID also adds them as a Discord contact, and names the client after them
    when no name is given."""
    client = Client(**body.model_dump(exclude={"discord_user_id"}))
    if body.discord_user_id is not None:
        contact = _discord_contact(body.discord_user_id, clock.now)
        client.contacts.append(contact)
        if client.name is None:
            client.name = _discord_name(contact)
    session.add(client)
    session.commit()
    return _read(session, client.id, clock.today)


@router.get("/{client_id}")
def get_client(client_id: int, session: SessionDep, today: TodayDep) -> ClientOut:
    return _read(session, client_id, today)


@router.put("/{client_id}")
def update_client(
    client_id: int, body: ClientIn, session: SessionDep, today: TodayDep
) -> ClientOut:
    client = _get_client(session, client_id)
    for field, value in body.model_dump().items():
        setattr(client, field, value)
    session.commit()
    return _read(session, client_id, today)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: int, session: SessionDep) -> None:
    client = _get_client(session, client_id)
    if client.projects or client.retainers:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Client has projects or retainers; remove those first"
        )
    session.delete(client)
    session.commit()


@router.post("/{client_id}/discord/sync")
def sync_discord(client_id: int, session: SessionDep, clock: ClockDep) -> ClientOut:
    """Looks up the client's Discord profiles now, however recently they were synced."""
    if not discord_sync.enabled():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Discord sync is off: add a bot token in Settings first"
        )
    client = _get_client(session, client_id)
    try:
        discord_sync.sync_now(client.contacts, clock.now)
    except discord.RateLimited as limited:
        session.commit()  # keep the ones looked up before Discord said to wait
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Discord asked to slow down. Try again in {math.ceil(limited.retry_after)} s",
        ) from None
    session.commit()
    return _read(session, client_id, clock.today)


@router.post("/{client_id}/contacts", status_code=status.HTTP_201_CREATED)
def create_contact(
    client_id: int, body: ContactIn, session: SessionDep, clock: ClockDep
) -> ContactOut:
    """A Discord contact with a user ID gets its profile looked up straight away."""
    _get_client(session, client_id)
    contact = ContactMethod(client_id=client_id, **body.model_dump())
    discord_sync.on_save(contact, body.discord_user_id, clock.now)
    session.add(contact)
    session.commit()
    return contact_out(contact)


@router.put("/{client_id}/contacts/{contact_id}")
def update_contact(
    client_id: int, contact_id: int, body: ContactIn, session: SessionDep, clock: ClockDep
) -> ContactOut:
    """A changed Discord user ID drops the old profile and looks the new one up."""
    contact = _get_contact(session, client_id, contact_id)
    id_changed = contact.discord_user_id != body.discord_user_id
    for field, value in body.model_dump().items():
        setattr(contact, field, value)
    if id_changed:
        discord_sync.on_save(contact, body.discord_user_id, clock.now)
    session.commit()
    return contact_out(contact)


@router.delete("/{client_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(client_id: int, contact_id: int, session: SessionDep) -> None:
    session.delete(_get_contact(session, client_id, contact_id))
    session.commit()

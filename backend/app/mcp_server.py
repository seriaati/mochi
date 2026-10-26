"""The dashboard as an MCP server, for AI assistants such as Claude, at /mcp.

Clients sign in with OAuth (see app/oauth.py). The tools call the API's route functions, so they
share its validation, errors and output; an error such as a 404 comes back as a tool error.
"""

import asyncio
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl, BaseModel, Field, create_model
from sqlalchemy.orm import Session

from app import oauth
from app.clock import Clock, clock_for, utc_now
from app.config import settings as config
from app.db import SessionLocal
from app.routers import clients, maintenance, overview, projects, retainers, settings
from app.schemas.clients import (
    ClientCreate,
    ClientIn,
    ClientOut,
    ClientUpdate,
    ContactIn,
    ContactOut,
)
from app.schemas.maintenance import (
    MaintenanceOut,
    RetainerIn,
    RetainerOut,
    RetainerPaymentIn,
    RetainerPaymentOut,
)
from app.schemas.overview import EarningsOut
from app.schemas.projects import (
    AdditionIn,
    AdditionOut,
    PaymentIn,
    PaymentOut,
    ProjectIn,
    ProjectOut,
)
from app.schemas.settings import SettingsIn, SettingsText

mcp = FastMCP(
    name="Freelance Dashboard",
    instructions=(
        "A freelancer's dashboard: clients and their contact methods, projects with their paid "
        "additions and payments, and clients' monthly maintenance fees (retainers). Money is "
        "whole NTD. Dates are YYYY-MM-DD, and 'today' is in the user's timezone (get_settings)."
    ),
    auth_server_provider=oauth.Provider(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(config.public_url),
        resource_server_url=AnyHttpUrl(f"{config.public_url.rstrip('/')}/mcp"),
        required_scopes=[oauth.SCOPE],
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=[oauth.SCOPE], default_scopes=[oauth.SCOPE]
        ),
        revocation_options=RevocationOptions(enabled=True),
        # Tokens only ever come from this server, for /mcp, and not every client names the
        # resource it wants a token for.
        validate_token_resource=False,
    ),
    # DNS rebinding protection guards servers on localhost that take requests without auth.
    # Every /mcp request here needs a token, and checking Host would need the public hostname
    # configured twice.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


async def _run[T](work: Callable[[Session, Clock], T]) -> T:
    """Runs work(session, clock) off the event loop, as FastAPI runs the sync routes."""

    def call() -> T:
        with SessionLocal() as session:
            return work(session, clock_for(session, utc_now()))

    return await asyncio.to_thread(call)


def _ann(
    title: str, *, read_only: bool = False, destructive: bool = False, open_world: bool = False
) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=read_only or destructive,
        openWorldHint=open_world,
    )


def _changes(model: type[BaseModel]) -> type[BaseModel]:
    """`model` with every field optional, for updates that send only the fields they change."""
    fields: dict[str, Any] = {
        name: (field.annotation | None, None) for name, field in model.model_fields.items()
    }
    return create_model(f"{model.__name__.removesuffix('In')}Changes", **fields)


def _merge[M: BaseModel](model: type[M], current: object, changes: BaseModel) -> M:
    """`current` with `changes` applied, validated as `model`. Fields left out of `changes` keep
    their values; null clears an optional one."""
    values = model.model_validate(current, from_attributes=True).model_dump()
    return model.model_validate(values | changes.model_dump(exclude_unset=True))


ClientChanges = _changes(ClientUpdate)
ContactChanges = _changes(ContactIn)
ProjectChanges = _changes(ProjectIn)
AdditionChanges = _changes(AdditionIn)
PaymentChanges = _changes(PaymentIn)
RetainerChanges = _changes(RetainerIn)


# Clients


@mcp.tool(annotations=_ann("List clients", read_only=True))
async def list_clients() -> list[ClientOut]:
    """All clients, with contacts, project count, lifetime billed and maintenance status."""
    return await _run(lambda s, c: clients.list_clients(session=s, today=c.today))


@mcp.tool(annotations=_ann("Get client", read_only=True))
async def get_client(client_id: int) -> ClientOut:
    """One client, with contacts, project count, lifetime billed and maintenance status."""
    return await _run(lambda s, c: clients.get_client(client_id, session=s, today=c.today))


@mcp.tool(annotations=_ann("Create client"))
async def create_client(client: ClientCreate) -> ClientOut:
    """Adds a client. A discord_user_id also adds them as a Discord contact, and names the client
    after their Discord display name when name is left out. Add other contact methods with
    add_contact."""
    return await _run(lambda s, c: clients.create_client(client, session=s, clock=c))


@mcp.tool(annotations=_ann("Update client", destructive=True))
async def update_client(client_id: int, changes: ClientChanges) -> ClientOut:
    """Edits a client. Changes only the fields in `changes`; null clears an optional one. A
    discord_user_id goes on their first Discord contact (one is added if they have none); null
    takes it off."""

    def work(s: Session, c: Clock) -> ClientOut:
        body = _merge(ClientIn, clients._get_client(s, client_id), changes)
        # discord_user_id only when sent, so otherwise the client's contacts stay as they are.
        discord = changes.model_dump(include={"discord_user_id"}, exclude_unset=True)
        update = ClientUpdate.model_validate(body.model_dump() | discord)
        return clients.update_client(client_id, update, session=s, clock=c)

    return await _run(work)


@mcp.tool(annotations=_ann("Delete client", destructive=True))
async def delete_client(client_id: int) -> str:
    """Deletes a client and their contacts. Only clients without projects or retainers."""
    await _run(lambda s, c: clients.delete_client(client_id, session=s))
    return f"Deleted client {client_id}"


@mcp.tool(annotations=_ann("Add contact"))
async def add_contact(client_id: int, contact: ContactIn) -> ContactOut:
    """Adds a contact method to a client. discord_user_id (Discord contacts only) lets the
    dashboard show their Discord name and avatar."""
    return await _run(lambda s, c: clients.create_contact(client_id, contact, session=s, clock=c))


@mcp.tool(annotations=_ann("Update contact", destructive=True))
async def update_contact(client_id: int, contact_id: int, changes: ContactChanges) -> ContactOut:
    """Edits a client's contact method. Changes only the fields in `changes`; null clears an
    optional one."""

    def work(s: Session, c: Clock) -> ContactOut:
        body = _merge(ContactIn, clients._get_contact(s, client_id, contact_id), changes)
        return clients.update_contact(client_id, contact_id, body, session=s, clock=c)

    return await _run(work)


@mcp.tool(annotations=_ann("Delete contact", destructive=True))
async def delete_contact(client_id: int, contact_id: int) -> str:
    """Deletes a client's contact method."""
    await _run(lambda s, c: clients.delete_contact(client_id, contact_id, session=s))
    return f"Deleted contact {contact_id}"


# Projects, their additions and payments


@mcp.tool(annotations=_ann("List projects", read_only=True))
async def list_projects(client_id: int | None = None) -> list[ProjectOut]:
    """All projects, or one client's, with additions, payments and what is still owed.
    Unfinished first."""
    return await _run(lambda s, c: projects.list_projects(session=s, client_id=client_id))


@mcp.tool(annotations=_ann("Get project", read_only=True))
async def get_project(project_id: int) -> ProjectOut:
    """One project, with additions, payments and what is still owed."""
    return await _run(lambda s, c: projects.get_project(project_id, session=s))


@mcp.tool(annotations=_ann("Create project"))
async def create_project(project: ProjectIn) -> ProjectOut:
    """Adds a project for an existing client. deposit_percent (default 50) is paid up front and
    the rest on delivery."""
    return await _run(lambda s, c: projects.create_project(project, session=s))


@mcp.tool(annotations=_ann("Update project", destructive=True))
async def update_project(project_id: int, changes: ProjectChanges) -> ProjectOut:
    """Edits a project; set delivered_on when it is delivered. Changes only the fields in
    `changes`; null clears an optional one."""

    def work(s: Session, c: Clock) -> ProjectOut:
        body = _merge(ProjectIn, projects._get_project_or_404(s, project_id), changes)
        return projects.update_project(project_id, body, session=s)

    return await _run(work)


@mcp.tool(annotations=_ann("Delete project", destructive=True))
async def delete_project(project_id: int) -> str:
    """Deletes a project with its additions and every payment for either."""
    await _run(lambda s, c: projects.delete_project(project_id, session=s))
    return f"Deleted project {project_id}"


@mcp.tool(annotations=_ann("Add addition"))
async def add_addition(project_id: int, addition: AdditionIn) -> AdditionOut:
    """Adds an extra paid feature to a project. deposit_percent 0 (the default) means one
    payment; otherwise it splits into deposit and rest like a project."""
    return await _run(lambda s, c: projects.create_addition(project_id, addition, session=s))


@mcp.tool(annotations=_ann("Update addition", destructive=True))
async def update_addition(
    project_id: int, addition_id: int, changes: AdditionChanges
) -> AdditionOut:
    """Edits a project's addition. Changes only the fields in `changes`; null clears an
    optional one."""

    def work(s: Session, c: Clock) -> AdditionOut:
        current = projects._get_addition_or_404(s, project_id, addition_id)
        body = _merge(AdditionIn, current, changes)
        return projects.update_addition(project_id, addition_id, body, session=s)

    return await _run(work)


@mcp.tool(annotations=_ann("Delete addition", destructive=True))
async def delete_addition(project_id: int, addition_id: int) -> str:
    """Deletes a project's addition and its payments."""
    await _run(lambda s, c: projects.delete_addition(project_id, addition_id, session=s))
    return f"Deleted addition {addition_id}"


@mcp.tool(annotations=_ann("Record project payment"))
async def record_project_payment(project_id: int, payment: PaymentIn) -> PaymentOut:
    """Records money received for a project, or for one of its additions when addition_id is
    set. It can't be more than is still owed."""
    return await _run(lambda s, c: projects.record_payment(project_id, payment, session=s))


@mcp.tool(annotations=_ann("Update project payment", destructive=True))
async def update_project_payment(
    project_id: int, payment_id: int, changes: PaymentChanges
) -> PaymentOut:
    """Edits a payment on a project or its additions; addition_id moves it. Changes only the
    fields in `changes`; null clears an optional one."""

    def work(s: Session, c: Clock) -> PaymentOut:
        current = projects._get_payment_or_404(s, project_id, payment_id)
        body = _merge(PaymentIn, current, changes)
        return projects.update_payment(project_id, payment_id, body, session=s)

    return await _run(work)


@mcp.tool(annotations=_ann("Delete project payment", destructive=True))
async def delete_project_payment(project_id: int, payment_id: int) -> str:
    """Deletes a payment on a project or one of its additions."""
    await _run(lambda s, c: projects.delete_payment(project_id, payment_id, session=s))
    return f"Deleted payment {payment_id}"


# Maintenance: retainers and their payments


@mcp.tool(annotations=_ann("List retainers", read_only=True))
async def list_retainers(
    client_id: int | None = None, project_id: int | None = None
) -> list[RetainerOut]:
    """All monthly maintenance fees (retainers), or one client's or project's, with recent
    months and what is overdue. Active first."""
    return await _run(
        lambda s, c: retainers.list_retainers(
            session=s, today=c.today, client_id=client_id, project_id=project_id
        )
    )


@mcp.tool(annotations=_ann("Get retainer", read_only=True))
async def get_retainer(retainer_id: int) -> RetainerOut:
    """One monthly maintenance fee, with recent months and what is overdue."""
    return await _run(lambda s, c: retainers.get_retainer(retainer_id, session=s, today=c.today))


@mcp.tool(annotations=_ann("Create retainer"))
async def create_retainer(retainer: RetainerIn) -> RetainerOut:
    """Adds a client's monthly maintenance fee. "auto_transfer" fees count as paid on the due
    date; "ask" fees need reminders and recorded payments. Months before tracked_from count as
    settled."""
    return await _run(lambda s, c: retainers.create_retainer(retainer, session=s, today=c.today))


@mcp.tool(annotations=_ann("Update retainer", destructive=True))
async def update_retainer(retainer_id: int, changes: RetainerChanges) -> RetainerOut:
    """Edits a monthly maintenance fee; set ended_on to end it. Changes only the fields in
    `changes`; null clears an optional one."""

    def work(s: Session, c: Clock) -> RetainerOut:
        body = _merge(RetainerIn, retainers._get_retainer_or_404(s, retainer_id), changes)
        return retainers.update_retainer(retainer_id, body, session=s, today=c.today)

    return await _run(work)


@mcp.tool(annotations=_ann("Delete retainer", destructive=True))
async def delete_retainer(retainer_id: int) -> str:
    """Deletes a monthly maintenance fee with its payments and reminder history. To stop one
    but keep its history, set ended_on instead."""
    await _run(lambda s, c: retainers.delete_retainer(retainer_id, session=s))
    return f"Deleted retainer {retainer_id}"


@mcp.tool(annotations=_ann("Record retainer payment"))
async def record_retainer_payment(
    retainer_id: int, payment: RetainerPaymentIn
) -> RetainerPaymentOut:
    """Marks one month of an "ask" retainer as paid. period is any date in that month. When the
    client pays several months ahead in one go, period is the first of them, months how many,
    and amount the total."""
    return await _run(lambda s, c: retainers.record_payment(retainer_id, payment, session=s))


@mcp.tool(annotations=_ann("Delete retainer payment", destructive=True))
async def delete_retainer_payment(retainer_id: int, payment_id: int) -> str:
    """Deletes a recorded retainer payment, so the months it covered are unpaid again."""
    await _run(lambda s, c: retainers.delete_payment(retainer_id, payment_id, session=s))
    return f"Deleted payment {payment_id}"


@mcp.tool(annotations=_ann("Get maintenance overview", read_only=True))
async def get_maintenance(
    month: Annotated[str | None, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> MaintenanceOut:
    """Everything on the Maintenance page: retainers, overdue months, the next reminder, this
    month's collection and a calendar of `month` (YYYY-MM, default this month)."""
    return await _run(lambda s, c: maintenance.overview(session=s, clock=c, month=month))


# Overview and settings


@mcp.tool(annotations=_ann("Get earnings", read_only=True))
async def get_earnings(year: int | None = None) -> EarningsOut:
    """Money received in `year` (default this year) by month, up to today, compared with the
    year before up to the same date."""
    return await _run(lambda s, c: overview.earnings(session=s, today=c.today, year=year))


@mcp.tool(annotations=_ann("Get settings", read_only=True))
async def get_settings() -> SettingsText:
    """The user's settings: the timezone that due dates, 'today' and reminders follow, the name
    the dashboard calls them (null: their Discord name), and their studio's name."""
    out = await _run(lambda s, c: settings.get_settings(session=s))
    return SettingsText(**out.model_dump(exclude={"studio_logo"}))


@mcp.tool(annotations=_ann("Update settings", destructive=True))
async def update_settings(
    timezone: str | None = None, user_name: str | None = None, studio_name: str | None = None
) -> SettingsText:
    """Changes the settings given; the rest stay as they are. timezone is an IANA name such as
    Asia/Taipei or Asia/Tokyo. An empty user_name or studio_name clears it."""
    changes = {"timezone": timezone, "user_name": user_name, "studio_name": studio_name}

    def work(s: Session, c: Clock) -> SettingsText:
        current = settings.get_settings(session=s).model_dump()
        body = SettingsIn.model_validate(
            current | {k: v for k, v in changes.items() if v is not None}
        )
        out = settings.update_settings(body, session=s)
        return SettingsText(**out.model_dump(exclude={"studio_logo"}))

    return await _run(work)


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Replaces `$ref` pointers with their `$defs`, so every property carries a `type`: some
    MCP clients don't follow references."""
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = defs[node["$ref"].removeprefix("#/$defs/")]
                return walk({**target, **{k: v for k, v in node.items() if k != "$ref"}})
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


for _tool in mcp._tool_manager.list_tools():
    _tool.parameters = _inline_refs(_tool.parameters)

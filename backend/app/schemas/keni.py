from datetime import date
from typing import Annotated

from pydantic import AfterValidator, AnyHttpUrl, BaseModel, StringConstraints


def _base_url(url: AnyHttpUrl) -> str:
    return str(url).rstrip("/")


# Where Keni runs, e.g. https://app.keni.seria.moe. The API is under /api.
KeniUrl = Annotated[AnyHttpUrl, AfterValidator(_base_url)]

KeniId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=36)]


class KeniLogin(BaseModel):
    url: KeniUrl
    # A personal API token: Keni's Settings > API tokens.
    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class KeniDestinationIn(BaseModel):
    """Where new income is recorded."""

    wallet_id: KeniId
    category_id: KeniId


class KeniConnectIn(KeniLogin, KeniDestinationIn):
    pass


class KeniWalletOut(BaseModel):
    id: str
    name: str
    currency: str


class KeniCategoryOut(BaseModel):
    id: str
    name: str


class KeniOptionsOut(BaseModel):
    """What the Keni account offers to record in."""

    wallets: list[KeniWalletOut]
    categories: list[KeniCategoryOut]


class KeniOut(BaseModel):
    """The Keni connection. Everything but `pending` is None while not connected."""

    url: str | None = None
    wallet_id: str | None = None
    wallet_name: str | None = None
    wallet_currency: str | None = None
    category_id: str | None = None
    category_name: str | None = None
    connected_on: date | None = None  # money already received by then stays out of Keni
    pending: int = 0  # changes still to send
    error: str | None = None  # why the last sync stopped

"""Talking to Keni's API with a personal API token: listing wallets and categories, and creating,
updating and deleting income transactions. Tests replace `_request` so nothing leaves the
machine."""

from dataclasses import dataclass
from datetime import datetime

import httpx2 as httpx


class Error(Exception):
    """Keni couldn't be reached or refused the request. The message is shown in Settings."""


@dataclass(frozen=True)
class Account:
    url: str  # the base URL; the API is under /api
    token: str


@dataclass(frozen=True)
class Wallet:
    id: str
    name: str
    currency: str


@dataclass(frozen=True)
class Category:
    id: str
    name: str


def _request(method: str, url: str, token: str, json: object = None) -> httpx.Response:
    return httpx.request(
        method, url, headers={"Authorization": f"Bearer {token}"}, json=json, timeout=10
    )


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError, AttributeError:
        detail = None
    return detail if isinstance(detail, str) else f"HTTP {response.status_code}"


def _refused(response: httpx.Response) -> Error:
    return Error(f"Keni refused the request: {_detail(response)}")


def _call(account: Account, method: str, path: str, json: object = None) -> httpx.Response:
    """Raises Error unless Keni answers 2xx, or 404 (which callers tell apart by its detail)."""
    try:
        response = _request(method, f"{account.url}/api{path}", account.token, json)
    except httpx.HTTPError as error:
        raise Error(f"Couldn't reach Keni: {error}") from error
    if response.status_code == 401:
        raise Error("Keni didn't accept the API key")
    if response.is_success or response.status_code == 404:
        return response
    raise _refused(response)


def _wallet(data: dict) -> Wallet:
    return Wallet(id=data["id"], name=data["name"], currency=data["currency"])


def wallets(account: Account) -> list[Wallet]:
    response = _call(account, "GET", "/wallets")
    if not response.is_success:
        raise Error("No Keni API at that URL")
    return [_wallet(w) for w in response.json()]


def wallet(account: Account, wallet_id: str) -> Wallet:
    response = _call(account, "GET", f"/wallets/{wallet_id}")
    if not response.is_success:
        raise Error("That wallet isn't in your Keni account")
    return _wallet(response.json())


def categories(account: Account) -> list[Category]:
    response = _call(account, "GET", "/categories")
    if not response.is_success:
        raise Error("No Keni API at that URL")
    return [Category(id=c["id"], name=c["name"]) for c in response.json()]


def _body(amount: int, when: datetime, description: str) -> dict:
    return {"amount": amount, "date": when.isoformat(), "description": description}


def create(
    account: Account,
    wallet_id: str,
    category_id: str,
    amount: int,
    when: datetime,
    description: str,
) -> str:
    """Records income in the wallet and returns its transaction ID."""
    body = _body(amount, when, description) | {"type": "income", "category_id": category_id}
    response = _call(account, "POST", f"/wallets/{wallet_id}/transactions", body)
    if not response.is_success:
        raise _refused(response)
    return response.json()["id"]


def update(
    account: Account,
    wallet_id: str,
    transaction_id: str,
    amount: int,
    when: datetime,
    description: str,
) -> bool:
    """False when the transaction is gone from Keni. Its category and tags stay as they are."""
    path = f"/wallets/{wallet_id}/transactions/{transaction_id}"
    response = _call(account, "PATCH", path, _body(amount, when, description))
    if response.status_code == 404 and _detail(response) == "Transaction not found":
        return False
    if not response.is_success:
        raise _refused(response)
    return True


def delete(account: Account, wallet_id: str, transaction_id: str) -> None:
    """Also fine when it's already gone."""
    response = _call(account, "DELETE", f"/wallets/{wallet_id}/transactions/{transaction_id}")
    if response.status_code == 404 and _detail(response) != "Transaction not found":
        raise _refused(response)

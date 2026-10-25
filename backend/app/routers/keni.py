from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import Session

from app import crypto, keni, keni_sync
from app.clock import TodayDep
from app.db import SessionDep
from app.models import AppSettings
from app.schemas.keni import (
    KeniCategoryOut,
    KeniConnectIn,
    KeniDestinationIn,
    KeniLogin,
    KeniOptionsOut,
    KeniOut,
    KeniWalletOut,
)

router = APIRouter(prefix="/api/settings/keni", tags=["settings"])


def _row(session: Session) -> AppSettings:
    return session.get_one(AppSettings, 1)


def _out(session: Session, row: AppSettings, today: date) -> KeniOut:
    if row.keni_connected_on is None:
        return KeniOut()
    return KeniOut(
        url=row.keni_url,
        wallet_id=row.keni_wallet_id,
        wallet_name=row.keni_wallet_name,
        wallet_currency=row.keni_wallet_currency,
        category_id=row.keni_category_id,
        category_name=row.keni_category_name,
        connected_on=row.keni_connected_on,
        pending=keni_sync.plan(session, row, today).pending,
        error=row.keni_error,
    )


def _keni_error(error: keni.Error) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(error))


def _saved_account(row: AppSettings) -> keni.Account:
    if row.keni_connected_on is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Keni isn't connected")
    account = keni_sync.saved_account(row)
    if account is None:
        raise HTTPException(status.HTTP_409_CONFLICT, keni_sync.UNREADABLE_TOKEN)
    return account


def _options(account: keni.Account) -> KeniOptionsOut:
    try:
        wallets, categories = keni.wallets(account), keni.categories(account)
    except keni.Error as error:
        raise _keni_error(error) from None
    return KeniOptionsOut(
        wallets=[KeniWalletOut(id=w.id, name=w.name, currency=w.currency) for w in wallets],
        categories=[KeniCategoryOut(id=c.id, name=c.name) for c in categories],
    )


def _choose(row: AppSettings, account: keni.Account, body: KeniDestinationIn) -> None:
    """Checks the wallet and category are in the account, and records new income there."""
    try:
        wallet = keni.wallet(account, body.wallet_id)
        category = next((c for c in keni.categories(account) if c.id == body.category_id), None)
    except keni.Error as error:
        raise _keni_error(error) from None
    if category is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "That category isn't in your Keni account"
        )
    row.keni_wallet_id, row.keni_wallet_name = wallet.id, wallet.name
    row.keni_wallet_currency = wallet.currency
    row.keni_category_id, row.keni_category_name = category.id, category.name


@router.get("")
def get_keni(session: SessionDep, today: TodayDep) -> KeniOut:
    return _out(session, _row(session), today)


@router.post("/options")
def find_options(body: KeniLogin) -> KeniOptionsOut:
    """The wallets and categories a token can record in, to pick from before connecting."""
    return _options(keni.Account(body.url, body.token))


@router.get("/options")
def get_options(session: SessionDep) -> KeniOptionsOut:
    """The wallets and categories of the connected account, to change where income goes."""
    return _options(_saved_account(_row(session)))


@router.put("")
def connect(body: KeniConnectIn, session: SessionDep, today: TodayDep) -> KeniOut:
    """Connects (again) with the token stored encrypted. Money received from now on is sent to
    the wallet and category; what is already recorded stays out of Keni."""
    if not crypto.can_encrypt():
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Set ENCRYPTION_KEY on the API before connecting Keni"
        )
    row = _row(session)
    _choose(row, keni.Account(body.url, body.token), body)
    row.keni_url = body.url
    row.keni_token_encrypted = crypto.encrypt(body.token)
    keni_sync.connect(session, row, today)
    session.commit()
    return _out(session, row, today)


@router.put("/destination")
def change_destination(body: KeniDestinationIn, session: SessionDep, today: TodayDep) -> KeniOut:
    """Records income sent from now on in another wallet or category. Transactions already in
    Keni stay where they are, and edits and deletes still reach them."""
    row = _row(session)
    _choose(row, _saved_account(row), body)
    session.commit()
    return _out(session, row, today)


@router.delete("")
def disconnect(session: SessionDep, today: TodayDep) -> KeniOut:
    """Stops syncing. Transactions already in Keni stay there."""
    row = _row(session)
    keni_sync.disconnect(session, row)
    session.commit()
    return _out(session, row, today)

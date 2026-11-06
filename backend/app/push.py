"""Notifications in the Android app, through Firebase Cloud Messaging's HTTP v1 API.

Mochi sends as the service account in FIREBASE_SERVICE_ACCOUNT, with an OAuth access token it
gets by signing a JWT with the account's key. Messages carry data only (strings): the app
builds each notification itself. Every device that turned notifications on has its token in
fcm_tokens; a token FCM no longer knows (the app was uninstalled, or Firebase replaced the
token) is deleted. Tests replace `send` so nothing leaves the machine."""

import base64
import json
import logging
import time
from dataclasses import dataclass
from functools import cache

import httpx2 as httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FcmToken

log = logging.getLogger(__name__)

FCM_API = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
# How long FCM keeps a message for a device that's offline.
TTL_SECONDS = 24 * 3600
# An access token lasts an hour; a new one is fetched 5 minutes before it runs out.
RENEW_EARLY_SECONDS = 300


class Error(Exception):
    """FIREBASE_SERVICE_ACCOUNT isn't a usable service account key."""


class NoDevice(Exception):
    """No app is registered to send to, or FCM said each one is gone."""


@dataclass(frozen=True)
class Account:
    project_id: str
    client_email: str
    key_id: str | None
    key: rsa.RSAPrivateKey


@cache
def _account(encoded: str) -> Account:
    try:
        info = json.loads(base64.b64decode(encoded))
        key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise TypeError("not an RSA key")
        return Account(info["project_id"], info["client_email"], info.get("private_key_id"), key)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise Error(
            f"FIREBASE_SERVICE_ACCOUNT isn't a base64 service account key: {error!r}"
        ) from None


def account() -> Account:
    if settings.firebase_service_account is None:
        raise Error("No FIREBASE_SERVICE_ACCOUNT is set")
    return _account(settings.firebase_service_account.get_secret_value())


def enabled() -> bool:
    """Whether this server is set up to notify the app. Never on the public demo."""
    return (
        settings.firebase_service_account is not None
        and settings.firebase_android_config is not None
        and not settings.demo
    )


def ready(session: Session) -> bool:
    """Set up, with at least one app to notify."""
    return enabled() and session.scalar(select(FcmToken.id).limit(1)) is not None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def assertion(sender: Account, now: int) -> str:
    """The JWT (RS256, signed with the service account's key) that Google's token endpoint
    exchanges for an access token to FCM."""
    header = {"alg": "RS256", "typ": "JWT"}
    if sender.key_id is not None:
        header["kid"] = sender.key_id
    claims = {
        "iss": sender.client_email,
        "scope": FCM_SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    signature = sender.key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(signature)}"


_token: tuple[str, float] = ("", 0.0)  # the access token, and when to fetch a new one


def access_token(sender: Account) -> str:
    """An access token to FCM, reused until shortly before it expires."""
    global _token
    token, renew_at = _token
    if time.time() < renew_at:
        return token
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion(sender, int(time.time())),
        },
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()
    _token = (body["access_token"], time.time() + body["expires_in"] - RENEW_EARLY_SECONDS)
    return body["access_token"]


def send(token: str, data: dict[str, str]) -> bool:
    """Send a data message to one app. False when FCM no longer knows the token, so it can be
    deleted. Raises Error for an unusable service account, and httpx.HTTPError when FCM refuses
    the message otherwise."""
    global _token
    sender = account()
    response = httpx.post(
        FCM_API.format(project=sender.project_id),
        json={
            "message": {
                "token": token,
                "data": data,
                "android": {"priority": "high", "ttl": f"{TTL_SECONDS}s"},
            }
        },
        headers={"Authorization": f"Bearer {access_token(sender)}"},
        timeout=10,
    )
    if response.status_code == 404 or "UNREGISTERED" in response.text:
        return False
    if response.status_code == 401:
        _token = ("", 0.0)  # fetch a new one next time
    response.raise_for_status()
    return True


def broadcast(session: Session, messages: list[dict[str, str]]) -> int:
    """Send the messages to every registered app and delete the tokens FCM no longer knows,
    without committing. Returns how many apps got them all. When none did, raises NoDevice if
    there was no app (left), else the first app's error; an app that fails while another gets
    them is only logged. Raises Error at once for an unusable service account."""
    reached, gone, errors = 0, [], []
    for token in session.scalars(select(FcmToken.token).order_by(FcmToken.id)):
        try:
            if all(send(token, message) for message in messages):
                reached += 1
            else:
                gone.append(token)
        except httpx.HTTPError as error:
            log.warning("FCM didn't take a message: %s", error)
            errors.append(error)
    if gone:
        session.execute(delete(FcmToken).where(FcmToken.token.in_(gone)))
        log.info("Forgot %d app(s) that FCM no longer knows", len(gone))
    if reached:
        return reached
    if errors:
        raise errors[0]
    raise NoDevice

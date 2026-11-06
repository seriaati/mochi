"""Notifications in the Android app: the FCM access token, sending and forgetting gone apps,
and the /api/notifications routes. FCM and Google's token endpoint are faked."""

import base64
import json
from types import SimpleNamespace
from typing import Any

import httpx2 as httpx
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import push
from app.config import settings
from app.models import FcmToken
from app.routers.notifications import NOT_SET_UP, TEST_MESSAGE

REAL_SEND = push.send  # before conftest swaps it out
PROJECT = "mochi-test"
EMAIL = "mochi-fcm@mochi-test.iam.gserviceaccount.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
T0 = 1_800_000_000.0  # the wall clock push sees, in seconds


def service_account(key: rsa.RSAPrivateKey = KEY) -> str:
    """FIREBASE_SERVICE_ACCOUNT: a service account's JSON key, base64-encoded."""
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    info = {
        "type": "service_account",
        "project_id": PROJECT,
        "private_key_id": "key-1",
        "private_key": pem.decode(),
        "client_email": EMAIL,
        "token_uri": push.TOKEN_URL,
    }
    return base64.b64encode(json.dumps(info).encode()).decode()


def google_services(*packages: str) -> str:
    """FIREBASE_ANDROID_CONFIG: a google-services.json with an app for each package, base64."""
    clients = [
        {
            "client_info": {
                "mobilesdk_app_id": f"1:123456789012:android:{i}abc",
                "android_client_info": {"package_name": package},
            },
            "oauth_client": [],
            "api_key": [{"current_key": f"AIza-key-{i}"}],
            "services": {"appinvite_service": {"other_platform_oauth_client": []}},
        }
        for i, package in enumerate(packages)
    ]
    config = {
        "project_info": {"project_number": "123456789012", "project_id": PROJECT},
        "client": clients,
        "configuration_version": "1",
    }
    return base64.b64encode(json.dumps(config).encode()).decode()


@pytest.fixture
def firebase(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server is set up for notifications in the app."""
    monkeypatch.setattr(settings, "firebase_service_account", SecretStr(service_account()))
    monkeypatch.setattr(settings, "firebase_android_config", google_services("moe.seria.mochi"))
    monkeypatch.setattr(settings, "demo", False)


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Google:
    """Google's token endpoint and FCM. `answers` maps an app's token to the FCM status it
    gets (200 by default)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.now = T0
        self.token_requests = 0
        self.received: list[tuple[str, dict[str, str]]] = []
        self.answers: dict[str, int] = {}
        monkeypatch.setattr(push, "send", REAL_SEND)
        monkeypatch.setattr(push.httpx, "post", self.post)
        monkeypatch.setattr(push, "time", SimpleNamespace(time=lambda: self.now))

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        if url == push.TOKEN_URL:
            return httpx.Response(200, json=self.grant(kwargs["data"]), request=request)
        assert url == f"https://fcm.googleapis.com/v1/projects/{PROJECT}/messages:send"
        assert kwargs["headers"] == {"Authorization": f"Bearer access-{self.token_requests}"}
        message = kwargs["json"]["message"]
        assert message["android"] == {"priority": "high", "ttl": "86400s"}
        assert all(isinstance(value, str) for value in message["data"].values())
        status = self.answers.get(message["token"], 200)
        if status == 404:
            error = {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}
            return httpx.Response(404, json={"error": error}, request=request)
        if status != 200:
            return httpx.Response(status, json={"error": {"status": "ERROR"}}, request=request)
        self.received.append((message["token"], message["data"]))
        return httpx.Response(200, json={"name": f"projects/{PROJECT}/messages/1"}, request=request)

    def grant(self, form: dict[str, str]) -> dict:
        assert form["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
        header, claims, signature = form["assertion"].split(".")
        # Signed with the service account's key: verify() raises otherwise.
        KEY.public_key().verify(
            b64url_decode(signature),
            f"{header}.{claims}".encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        assert json.loads(b64url_decode(header)) == {"alg": "RS256", "typ": "JWT", "kid": "key-1"}
        assert json.loads(b64url_decode(claims)) == {
            "iss": EMAIL,
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": int(self.now),
            "exp": int(self.now) + 3600,
        }
        self.token_requests += 1
        return {"access_token": f"access-{self.token_requests}", "expires_in": 3599}


@pytest.fixture
def google(firebase: None, monkeypatch: pytest.MonkeyPatch) -> Google:
    return Google(monkeypatch)


def add_tokens(session: Session, *tokens: str) -> None:
    session.add_all(FcmToken(token=t) for t in tokens)
    session.flush()


def tokens(session: Session) -> list[str]:
    session.expire_all()
    return list(session.scalars(select(FcmToken.token).order_by(FcmToken.id)))


# The access token


def test_the_access_token_is_signed_and_reused_for_55_minutes(google: Google) -> None:
    data = {"type": "test", "title": "Hi"}
    assert push.send("phone", data) is True
    assert push.send("phone", data) is True
    assert google.token_requests == 1

    google.now = T0 + 54 * 60
    assert push.send("phone", data)
    assert google.token_requests == 1
    google.now = T0 + 55 * 60  # 3599 seconds, renewed 5 minutes early
    assert push.send("phone", data)
    assert google.token_requests == 2
    assert google.received == [("phone", data)] * 4


def test_a_forged_assertion_fails_verification(google: Google) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = push._account(service_account(other))
    form = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": push.assertion(forged, int(T0)),
    }
    with pytest.raises(InvalidSignature):
        google.grant(form)


def test_a_rejected_access_token_is_fetched_again(google: Google) -> None:
    google.answers["phone"] = 401
    with pytest.raises(httpx.HTTPStatusError):
        push.send("phone", {"type": "test"})
    google.answers["phone"] = 200
    assert push.send("phone", {"type": "test"})
    assert google.token_requests == 2


def test_an_unusable_service_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(push, "send", REAL_SEND)
    with pytest.raises(push.Error, match="No FIREBASE_SERVICE_ACCOUNT"):
        push.send("phone", {})
    monkeypatch.setattr(settings, "firebase_service_account", SecretStr("not base64 json"))
    with pytest.raises(push.Error, match="isn't a base64 service account key"):
        push.send("phone", {})


# Sending to every app


def test_gone_apps_are_forgotten_and_failing_ones_kept(google: Google, session: Session) -> None:
    add_tokens(session, "gone", "ok", "down")
    google.answers |= {"gone": 404, "down": 503}
    assert push.broadcast(session, [{"type": "test"}]) == 1
    assert google.received == [("ok", {"type": "test"})]
    assert tokens(session) == ["ok", "down"]


def test_unregistered_in_the_body_is_gone_too(
    google: Google, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_tokens(session, "old")

    def unregistered(url: str, **kwargs: Any) -> httpx.Response:
        if url == push.TOKEN_URL:
            return google.post(url, **kwargs)
        body = {"error": {"status": "INVALID_ARGUMENT", "details": [{"errorCode": "UNREGISTERED"}]}}
        return httpx.Response(400, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(push.httpx, "post", unregistered)
    with pytest.raises(push.NoDevice):
        push.broadcast(session, [{"type": "test"}])
    assert tokens(session) == []


def test_no_app_got_them(google: Google, session: Session) -> None:
    with pytest.raises(push.NoDevice):
        push.broadcast(session, [{"type": "test"}])
    add_tokens(session, "down")
    google.answers["down"] = 500
    with pytest.raises(httpx.HTTPStatusError):
        push.broadcast(session, [{"type": "test"}])
    assert tokens(session) == ["down"]


# The routes


def test_firebase_settings_for_the_app(
    client: TestClient, firebase: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = google_services("x.other", "moe.seria.mochi")
    monkeypatch.setattr(settings, "firebase_android_config", config)
    response = client.get("/api/notifications/firebase")
    assert response.status_code == 200
    assert response.json() == {
        "project_id": PROJECT,
        "app_id": "1:123456789012:android:1abc",
        "api_key": "AIza-key-1",
        "sender_id": "123456789012",
    }


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"firebase_android_config": None}, "isn't set up"),
        ({"firebase_service_account": None}, "isn't set up"),
        ({"demo": True}, "isn't set up"),
        ({"firebase_android_config": google_services("x.other")}, "FIREBASE_ANDROID_CONFIG"),
        ({"firebase_android_config": "not base64 json"}, "FIREBASE_ANDROID_CONFIG"),
        ({"firebase_service_account": SecretStr("e30=")}, "FIREBASE_SERVICE_ACCOUNT"),  # {}
    ],
)
def test_no_firebase_settings_for_the_app(
    client: TestClient, firebase: None, monkeypatch: pytest.MonkeyPatch, changes: dict, detail: str
) -> None:
    for name, value in changes.items():
        monkeypatch.setattr(settings, name, value)
    response = client.get("/api/notifications/firebase")
    assert response.status_code == 404
    assert detail in response.json()["detail"]


def test_register_and_unregister_the_app(client: TestClient, session: Session) -> None:
    for _ in range(2):  # registering again changes nothing
        response = client.put("/api/notifications/fcm", json={"token": "phone-1"})
        assert response.status_code == 204
    assert client.put("/api/notifications/fcm", json={"token": "phone-2"}).status_code == 204
    assert tokens(session) == ["phone-1", "phone-2"]
    assert client.put("/api/notifications/fcm", json={"token": " "}).status_code == 422

    response = client.request("DELETE", "/api/notifications/fcm", json={"token": "phone-1"})
    assert response.status_code == 204
    assert tokens(session) == ["phone-2"]
    response = client.request("DELETE", "/api/notifications/fcm", json={"token": "unknown"})
    assert response.status_code == 204


def test_send_test(client: TestClient, session: Session, google: Google) -> None:
    add_tokens(session, "phone", "gone")
    google.answers["gone"] = 404
    response = client.post("/api/notifications/test")
    assert response.status_code == 200
    assert response.json() == {"devices": 1}
    assert google.received == [("phone", TEST_MESSAGE)]
    assert tokens(session) == ["phone"]


def test_send_test_errors(
    client: TestClient, session: Session, google: Google, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.post("/api/notifications/test")
    assert response.status_code == 409
    assert response.json()["detail"].startswith("No device is registered")

    add_tokens(session, "down")
    google.answers["down"] = 500
    response = client.post("/api/notifications/test")
    assert response.status_code == 502
    assert response.json()["detail"].startswith("FCM didn't take the message")

    # Unset on the server, or the public demo.
    monkeypatch.setattr(settings, "demo", True)
    response = client.post("/api/notifications/test")
    assert response.status_code == 409
    assert response.json()["detail"] == NOT_SET_UP
    assert google.received == []

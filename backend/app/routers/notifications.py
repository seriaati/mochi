import base64
import json
import logging

import httpx2 as httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app import push
from app.config import settings
from app.db import SessionDep
from app.models import FcmToken
from app.schemas.notifications import FcmTokenIn, FirebaseOut, PushTestOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
log = logging.getLogger(__name__)

ANDROID_PACKAGE = "moe.seria.mochi"
NOT_SET_UP = "This Mochi server isn't set up for notifications in the app"
TEST_MESSAGE = {
    "type": "test",
    "title": "Test from Mochi",
    "body": "Maintenance reminders will show up here.",
    "path": "/settings",
}


@router.get("/firebase")
def firebase() -> FirebaseOut:
    """What the Android app starts Firebase with, from FIREBASE_ANDROID_CONFIG (its
    google-services.json). 404 when Mochi can't notify the app: a variable unset or unusable,
    or the public demo."""
    if not push.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_SET_UP)
    try:
        push.account()
    except push.Error as error:
        log.warning("%s", error)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "FIREBASE_SERVICE_ACCOUNT isn't usable: see the API's log"
        ) from None
    try:
        config = json.loads(base64.b64decode(settings.firebase_android_config or ""))
        project = config["project_info"]
        app = next(
            client
            for client in config["client"]
            if client["client_info"]["android_client_info"]["package_name"] == ANDROID_PACKAGE
        )
        return FirebaseOut(
            project_id=project["project_id"],
            app_id=app["client_info"]["mobilesdk_app_id"],
            api_key=app["api_key"][0]["current_key"],
            sender_id=project["project_number"],
        )
    except ValueError, KeyError, IndexError, TypeError, StopIteration:
        log.warning(
            "FIREBASE_ANDROID_CONFIG isn't a base64 google-services.json for %s", ANDROID_PACKAGE
        )
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "FIREBASE_ANDROID_CONFIG isn't usable: see the API's log"
        ) from None


@router.put("/fcm", status_code=status.HTTP_204_NO_CONTENT)
def register_app(body: FcmTokenIn, session: SessionDep) -> None:
    """Notifies this device from now on. Registering again changes nothing."""
    session.execute(insert(FcmToken).values(token=body.token).on_conflict_do_nothing())
    session.commit()


@router.delete("/fcm", status_code=status.HTTP_204_NO_CONTENT)
def unregister_app(body: FcmTokenIn, session: SessionDep) -> None:
    session.execute(delete(FcmToken).where(FcmToken.token == body.token))
    session.commit()


@router.post("/test")
def send_test(session: SessionDep) -> PushTestOut:
    """Sends a test notification to every registered app."""
    if not push.enabled():
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_SET_UP)
    try:
        return PushTestOut(devices=push.broadcast(session, [TEST_MESSAGE]))
    except push.NoDevice:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No device is registered: turn notifications on in the app"
        ) from None
    except push.Error as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    except httpx.HTTPError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"FCM didn't take the message: {error}"
        ) from error
    finally:
        session.commit()  # forgets the devices FCM no longer knows

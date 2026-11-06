from typing import Annotated

from pydantic import BaseModel, StringConstraints


class FirebaseOut(BaseModel):
    """What the Android app starts Firebase with: its entry in google-services.json."""

    project_id: str
    app_id: str  # mobilesdk_app_id
    api_key: str
    sender_id: str  # the project number


class FcmTokenIn(BaseModel):
    """The Android app's FCM registration token."""

    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)]


class PushTestOut(BaseModel):
    devices: int  # how many apps got the test notification

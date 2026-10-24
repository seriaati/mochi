"""The consent step of MCP clients' OAuth sign-in (see app/oauth.py)."""

from fastapi import APIRouter, HTTPException, status

from app import oauth
from app.auth import NowDep
from app.db import SessionDep
from app.schemas.oauth import AccessRequestOut, AnswerIn, AnswerOut

router = APIRouter(prefix="/api/oauth", tags=["oauth"])

GONE = "This request has expired or was already answered. Connect again from the app."


@router.get("/requests/{request_id}")
def get_request(request_id: str, now: NowDep) -> AccessRequestOut:
    request = oauth.pending(request_id, now)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    return AccessRequestOut(
        client_name=request.client.client_name, redirect_uri=str(request.params.redirect_uri)
    )


@router.post("/requests/{request_id}")
def answer_request(request_id: str, body: AnswerIn, session: SessionDep, now: NowDep) -> AnswerOut:
    redirect_uri = oauth.answer(session, now, request_id, body.approve)
    if redirect_uri is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    return AnswerOut(redirect_uri=redirect_uri)

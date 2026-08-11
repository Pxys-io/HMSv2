"""Chat routes (Plan/08 §5): staff inbox + SSE stream, public widget with
cookie-guarded guest identity."""

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.audit import service as audit
from app.core.config import get_settings
from app.core.deps import (
    AuditDbDep,
    DbDep,
    get_current_patient,
    get_current_staff,
    get_request_id,
    verify_csrf,
)
from app.core.errors import AppError
from app.core.security import sha256_hex
from app.models.comms import ChatConversation
from app.models.identity import PatientAccount, StaffUser
from app.services import chat as chat_service
from app.services.broadcast import Broadcaster
from app.services.idempotency import claim, complete, get_key_from_request

chat_broadcaster = Broadcaster()
CHAT_KEY = ("chat", "global")


class SendBody(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class StartBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    guest_name: str | None = Field(default=None, max_length=200)
    guest_contact: str | None = Field(default=None, max_length=200)


def _publish(conversation_id: int) -> None:
    chat_broadcaster.publish(CHAT_KEY, {"event": "message", "conversation_id": conversation_id})


# ------------------------------------------------------------------ staff


staff_router = APIRouter(prefix="/api/chat", tags=["chat-staff"])


@staff_router.get("/conversations")
def list_conversations(
    current: Annotated[StaffUser, Depends(get_current_staff)],
    db: DbDep,
    status: str = Query(default="open", pattern="^(open|closed|all)$"),
):
    stmt = select(ChatConversation).order_by(
        ChatConversation.last_message_at.desc()
    )
    if status != "all":
        stmt = stmt.where(ChatConversation.status == status)
    rows = db.scalars(stmt.limit(100)).all()
    return [chat_service.conversation_payload(db, c) for c in rows]


@staff_router.get("/conversations/{conversation_id}/messages")
def staff_messages(
    conversation_id: int,
    current: Annotated[StaffUser, Depends(get_current_staff)],
    db: DbDep,
):
    conversation = chat_service.get_conversation(db, conversation_id)
    payload = chat_service.messages_payload(db, conversation)
    chat_service.mark_staff_read(db, conversation)
    return {
        "conversation": chat_service.conversation_payload(db, conversation),
        "messages": payload,
    }


@staff_router.post("/conversations/{conversation_id}/messages")
def staff_send(
    conversation_id: int,
    body: SendBody,
    current: Annotated[StaffUser, Depends(get_current_staff)],
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    key = get_key_from_request(request)
    if key:
        replay = claim(db, owner_type="staff", owner_id=current.id, key=key,
                       payload={"conversation_id": conversation_id, **body.model_dump()})
        if replay:
            response.status_code = replay["status"]
            response.body = json.dumps(replay["body"], ensure_ascii=False).encode()
            response.headers["Content-Type"] = "application/json"
            return response
    conversation = chat_service.get_conversation(db, conversation_id)
    message = chat_service.staff_send(db, conversation, body.body, current.id)
    _publish(conversation.id)
    payload = {
        "id": message.id, "sender_type": message.sender_type, "body": message.body,
        "conversation_id": conversation.id,
    }
    if key:
        complete(db, owner_type="staff", owner_id=current.id, key=key, status=200, body=payload)
    return payload


@staff_router.post("/conversations/{conversation_id}/close")
def close_conversation(
    conversation_id: int,
    current: Annotated[StaffUser, Depends(get_current_staff)],
    db: DbDep,
):
    conversation = chat_service.get_conversation(db, conversation_id)
    chat_service.set_status(db, conversation, "closed")
    return {"id": conversation.id, "status": "closed"}


@staff_router.post("/conversations/{conversation_id}/reopen")
def reopen_conversation(
    conversation_id: int,
    current: Annotated[StaffUser, Depends(get_current_staff)],
    db: DbDep,
):
    conversation = chat_service.get_conversation(db, conversation_id)
    chat_service.set_status(db, conversation, "open")
    return {"id": conversation.id, "status": "open"}


@staff_router.get("/stream")
async def chat_stream(
    current: Annotated[StaffUser, Depends(get_current_staff)],
):
    subscription = chat_broadcaster.subscribe(CHAT_KEY)

    async def gen():
        try:
            while True:
                try:
                    message = await asyncio.wait_for(subscription.get(), timeout=15)
                except TimeoutError:
                    yield ": ping"
                    continue
                yield message
        finally:
            chat_broadcaster.unsubscribe(CHAT_KEY, subscription)

    return EventSourceResponse(gen())


# ------------------------------------------------------------------ public


public_router = APIRouter(
    prefix="/api/public/chat", tags=["chat-public"], dependencies=[Depends(verify_csrf)]
)
Patient = Annotated[PatientAccount, Depends(get_current_patient)]


def _guest_conversation(db: DbDep, request: Request) -> ChatConversation:
    raw = request.cookies.get("hmsv2_guest_key")
    if not raw:
        raise AppError("UNAUTHORIZED", "no guest chat session")
    conversation = db.scalar(
        select(ChatConversation).where(
            ChatConversation.guest_key_hash == sha256_hex(raw),
            ChatConversation.status == "open",
        )
    )
    if conversation is None:
        raise AppError("UNAUTHORIZED", "guest session expired or closed")
    return conversation


@public_router.post("/start")
def public_start(
    body: StartBody,
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    """C1: authenticated patients reuse their open conversation; guests get a
    fresh HttpOnly cookie with a hashed key."""
    token = request.headers.get("Authorization", "")
    account = None
    if token.startswith("Bearer "):
        account = _bearer_account(token[7:], db)
    conversation, guest_key = chat_service.start_conversation(
        db,
        account=account,
        guest_name=body.guest_name,
        guest_contact=body.guest_contact,
        first_message=body.message,
    )
    if guest_key is not None:
        response.set_cookie(
            "hmsv2_guest_key",
            guest_key,
            httponly=True,
            secure=get_settings().COOKIE_SECURE,
            samesite=get_settings().COOKIE_SAMESITE,
            path="/",
        )
    _publish(conversation.id)
    audit.access(
        audit_db,
        actor_type="patient", actor_id=account.id if account else None,
        actor_label=account.full_name if account else (body.guest_name or "guest"),
        action="chat.start", entity_type="chat_conversation", entity_id=str(conversation.id),
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return {"conversation_id": conversation.id, "guest": guest_key is not None}


@public_router.get("/messages")
def public_messages(
    request: Request,
    db: DbDep,
    since_id: int | None = Query(default=None, ge=0),
):
    token = request.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        account = _bearer_account(token[7:], db)
        conversation = db.scalar(
            select(ChatConversation).where(
                ChatConversation.patient_account_id == account.id,
                ChatConversation.status == "open",
            )
        )
        if conversation is None:
            return {"messages": []}
    else:
        conversation = _guest_conversation(db, request)
    return {"messages": chat_service.messages_payload(db, conversation, since_id)}


@public_router.post("/messages")
def public_send(
    body: SendBody,
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    token = request.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        account = _bearer_account(token[7:], db)
        conversation = db.scalar(
            select(ChatConversation).where(
                ChatConversation.patient_account_id == account.id,
                ChatConversation.status == "open",
            )
        )
        if conversation is None:
            raise AppError("NOT_FOUND", "no open conversation; start one first")
    else:
        conversation = _guest_conversation(db, request)
        account = None
    message = chat_service.patient_send(db, conversation, body.body, account)
    _publish(conversation.id)
    return {"id": message.id, "sender_type": "patient", "body": message.body}


def _bearer_account(token: str, db: DbDep) -> PatientAccount:
    from app.core.deps import decode_access_token

    try:
        claims = decode_access_token(token)
    except Exception:  # noqa: BLE001
        raise AppError("UNAUTHORIZED", "invalid token") from None
    account = db.get(PatientAccount, int(claims["sub"]))
    if account is None or not account.is_active:
        raise AppError("UNAUTHORIZED", "account not found")
    return account

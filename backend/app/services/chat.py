"""Chat service (Plan/08 C1–C4): conversations, messages, unread counters,
assignment, close/reopen. AI-ready (`sender_type=ai` reserved, unused in v1)."""

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import sha256_hex
from app.models.comms import ChatConversation, ChatMessage
from app.models.identity import PatientAccount

MAX_MESSAGE_LENGTH = 2000


def _now() -> datetime:
    return datetime.now(UTC)


def generate_guest_key() -> str:
    return secrets.token_urlsafe(32)


def start_conversation(
    db: Session,
    *,
    account: PatientAccount | None,
    guest_name: str | None,
    guest_contact: str | None,
    first_message: str,
) -> tuple[ChatConversation, str | None]:
    """C1: one open conversation per account; guests always get a new one
    with a fresh opaque key (hash stored, cookie-only)."""
    conversation = None
    guest_key = None
    if account is not None:
        conversation = db.scalar(
            select(ChatConversation).where(
                ChatConversation.patient_account_id == account.id,
                ChatConversation.status == "open",
            )
        )
        if conversation is None:
            conversation = ChatConversation(
                patient_account_id=account.id, status="open", last_message_at=_now()
            )
            db.add(conversation)
            db.flush()
    else:
        if not guest_name or not guest_contact:
            raise AppError("VALIDATION", "guest name and contact are required")
        guest_key = generate_guest_key()
        conversation = ChatConversation(
            guest_key_hash=sha256_hex(guest_key),
            guest_name=guest_name,
            guest_contact=guest_contact,
            status="open",
            last_message_at=_now(),
        )
        db.add(conversation)
        db.flush()

    _add_message(db, conversation, "patient", first_message)
    if conversation.subject is None:
        conversation.subject = first_message[:60]
    conversation.last_message_at = _now()
    conversation.unread_staff += 1
    db.commit()
    return conversation, guest_key


def _add_message(
    db: Session,
    conversation: ChatConversation,
    sender_type: str,
    body: str,
    sender_id: int | None = None,
) -> ChatMessage:
    if not body.strip():
        raise AppError("VALIDATION", "empty message")
    if len(body) > MAX_MESSAGE_LENGTH:
        raise AppError("VALIDATION", "message too long")
    message = ChatMessage(
        conversation_id=conversation.id,
        sender_type=sender_type,
        sender_id=sender_id,
        body=body[:MAX_MESSAGE_LENGTH],
    )
    db.add(message)
    db.flush()
    return message


def patient_send(
    db: Session, conversation: ChatConversation, body: str, account: PatientAccount | None
) -> ChatMessage:
    if conversation.status != "open":
        raise AppError("CONFLICT", "conversation is closed")
    if account is not None and conversation.patient_account_id != account.id:
        raise AppError("FORBIDDEN", "not your conversation")
    message = _add_message(db, conversation, "patient", body)
    conversation.last_message_at = _now()
    conversation.unread_staff += 1
    db.commit()
    return message


def staff_send(
    db: Session, conversation: ChatConversation, body: str, staff_id: int
) -> ChatMessage:
    if conversation.status != "open":
        raise AppError("CONFLICT", "conversation is closed")
    message = _add_message(db, conversation, "secretary", body, sender_id=staff_id)
    conversation.last_message_at = _now()
    conversation.unread_patient += 1
    if conversation.assigned_to is None:
        conversation.assigned_to = staff_id  # first reply auto-assigns (C3)
    db.commit()
    return message


def mark_staff_read(db: Session, conversation: ChatConversation) -> None:
    conversation.unread_staff = 0
    messages = db.scalars(
        select(ChatMessage).where(
            ChatMessage.conversation_id == conversation.id,
            ChatMessage.sender_type == "patient",
            ChatMessage.read_at.is_(None),
        )
    ).all()
    for message in messages:
        message.read_at = _now()
    db.commit()


def set_status(db: Session, conversation: ChatConversation, status: str) -> None:
    if status not in ("open", "closed"):
        raise AppError("VALIDATION", "status must be open or closed")
    conversation.status = status
    db.commit()


def get_conversation(db: Session, conversation_id: int) -> ChatConversation:
    conversation = db.get(ChatConversation, conversation_id)
    if conversation is None:
        raise AppError("NOT_FOUND", "conversation not found")
    return conversation


def conversation_payload(db: Session, conversation: ChatConversation) -> dict:
    last = db.scalar(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    return {
        "id": conversation.id,
        "status": conversation.status,
        "subject": conversation.subject,
        "patient_account_id": conversation.patient_account_id,
        "guest_name": conversation.guest_name,
        "guest_contact": conversation.guest_contact,
        "assigned_to": conversation.assigned_to,
        "last_message_at": conversation.last_message_at.isoformat(),
        "last_message_preview": last.body[:80] if last else None,
        "unread_staff": conversation.unread_staff,
        "unread_patient": conversation.unread_patient,
    }


def messages_payload(
    db: Session, conversation: ChatConversation, since_id: int | None = None
) -> list[dict]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.id)
    )
    if since_id:
        stmt = stmt.where(ChatMessage.id > since_id)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": m.id,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "body": m.body,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]

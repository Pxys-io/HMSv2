"""Comms/config models: chat, notifications, print templates, outbox."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ChatConversation(TimestampMixin, Base):
    __tablename__ = "chat_conversation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_account_id: Mapped[int | None] = mapped_column(ForeignKey("patient_account.id"),
        nullable=True)
    guest_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    guest_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(Enum("open", "closed", name="chat_status"), default="open")
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"), nullable=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    unread_staff: Mapped[int] = mapped_column(Integer, default=0)
    unread_patient: Mapped[int] = mapped_column(Integer, default=0)


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("chat_conversation.id"), index=True)
    sender_type: Mapped[str] = mapped_column(
        Enum("patient", "secretary", "system", "ai", name="chat_sender_type")
    )  # ai reserved, unused in v1
    sender_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(TimestampMixin, Base):
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(String(500), nullable=True)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PrintTemplate(TimestampMixin, Base):
    __tablename__ = "print_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40))  # rx | report | sick_leave | referral | invoice
    locale: Mapped[str] = mapped_column(Enum("ar", "en", name="locale"))
    title: Mapped[str] = mapped_column(String(120))
    body_html: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    sanitized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("uq_print_template_key_locale", "key", "locale", unique=True),)


class OutboxEvent(TimestampMixin, Base):
    __tablename__ = "outbox_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(
        Enum("email_booking_confirmation", "attachment_scan", name="outbox_kind")
    )
    aggregate_type: Mapped[str] = mapped_column(String(60))
    aggregate_id: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "processing", "sent", "failed", name="outbox_status"), default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)

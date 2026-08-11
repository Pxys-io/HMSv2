"""Audit database models (Phase 02 surface, defined now so the audit Alembic
environment can boot).

Tamper-evident, not tamper-proof-by-magic: rows are append-only, hash-chained,
and covered by signed external checkpoints. See Plan/02 §2.7 & §4.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuditBase


class AuditEvent(AuditBase):
    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), index=True
    )
    actor_type: Mapped[str] = mapped_column(
        Enum("staff", "patient", "system", name="audit_actor_type")
    )
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_label: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    outcome: Mapped[str] = mapped_column(
        Enum("intent", "committed", "aborted", "access", name="audit_outcome")
    )
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class AuditMeta(AuditBase):
    __tablename__ = "audit_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    genesis_hash: Mapped[str] = mapped_column(String(64))
    last_hash: Mapped[str] = mapped_column(String(64))
    last_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )


class AuditCheckpoint(AuditBase):
    __tablename__ = "audit_checkpoint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )
    first_event_id: Mapped[int] = mapped_column()
    last_event_id: Mapped[int] = mapped_column()
    chain_head_hash: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str] = mapped_column(String(256))
    public_key_id: Mapped[str] = mapped_column(String(64))
    export_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (Index("ix_audit_checkpoint_last_event", "last_event_id"),)

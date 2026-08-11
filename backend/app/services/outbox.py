"""Persisted outbox worker (Plan/02 §2.6, Plan/08 N3).

Jobs are claimed with a `lease_until` so a crash mid-job cannot lose them;
after restart the loop resumes pending/processing jobs. Phase 05 implements
`attachment_scan`; `email_booking_confirmation` lands in Phase 08 (logged
here as a stub).
"""

import asyncio
import logging
import os
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.comms import OutboxEvent

logger = logging.getLogger("hmsv2.outbox")

WORKER_ID = os.urandom(8).hex()
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 10


def enqueue(
    db: Session,
    *,
    kind: str,
    aggregate_type: str,
    aggregate_id: int,
    payload: dict | None = None,
    dedupe_key: str,
) -> OutboxEvent:
    event = OutboxEvent(
        kind=kind,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        status="pending",
        next_attempt_at=datetime.now(UTC),
        dedupe_key=dedupe_key,
    )
    db.add(event)
    db.commit()
    return event


def _claim(db: Session) -> OutboxEvent | None:
    now = datetime.now(UTC)
    event = db.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_(("pending", "processing")),
            OutboxEvent.attempts < MAX_ATTEMPTS,
            (OutboxEvent.next_attempt_at.is_(None)) | (OutboxEvent.next_attempt_at <= now),
        )
        .order_by(OutboxEvent.id)
        .limit(1)
        .with_for_update()
    )
    if event is None:
        return None
    event.status = "processing"
    event.lease_until = now + timedelta(minutes=1)
    event.worker_id = WORKER_ID
    db.commit()
    return event


def _retry_or_fail(db: Session, event: OutboxEvent, error: str) -> None:
    event.attempts += 1
    event.last_error = error[:500]
    if event.attempts >= MAX_ATTEMPTS:
        event.status = "failed"
        logger.error("outbox job %s failed permanently: %s", event.id, error)
    else:
        event.status = "pending"
        event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=BACKOFF_SECONDS)
    db.commit()


def _process(db: Session, event: OutboxEvent) -> None:
    if event.kind == "attachment_scan":
        from app.services.attachments import scan_attachment

        scan_attachment(db, event.aggregate_id)
    elif event.kind == "email_booking_confirmation":
        # Phase 08 wires the SMTP sender here; until then the job is a stub.
        logger.info("outbox email stub for booking %s", event.aggregate_id)
    else:
        raise ValueError(f"unknown outbox kind {event.kind}")


def drain_once() -> int:
    """Processes a batch of ready jobs; returns how many completed."""
    completed = 0
    with SessionLocal() as db:
        while True:
            event = _claim(db)
            if event is None:
                break
            try:
                _process(db, event)
                event.status = "sent"
                db.commit()
                completed += 1
            except Exception as exc:  # noqa: BLE001 - outbox must never crash the loop
                logger.warning(
                    "outbox job %s failed (attempt %s): %s",
                    event.id, event.attempts + 1, exc,
                )
                _retry_or_fail(db, event, str(exc))
    return completed


async def outbox_loop(stop: asyncio.Event) -> None:
    """Background worker loop (single-process v1)."""
    while not stop.is_set():
        try:
            drain_once()
        except Exception:  # noqa: BLE001
            logger.exception("outbox drain crashed; continuing")
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=2.0)

"""Idempotency service (Plan/02 §2.6, D22).

Resource mutations require an `Idempotency-Key` header. Replaying a completed
key returns the original response; reuse with a different request body is 409.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import ensure_aware
from app.models.config import IdempotencyKey


def request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=get_settings().IDEMPOTENCY_TTL_DAYS)


def get_key_from_request(request: Request) -> str | None:
    """Accepts the key from the header (mobile/native) or the `_idem` query
    param (browser fetch streaming, where custom headers are awkward)."""
    key = request.headers.get("Idempotency-Key")
    if key:
        return key
    return request.query_params.get("_idem")


def claim(
    db: Session,
    *,
    owner_type: str,
    owner_id: int | None,
    key: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Returns a replay payload `{status, body}` if the key was already
    completed; raises 409 on key reuse with a different request hash."""
    now = datetime.now(UTC)
    row = db.query(IdempotencyKey).filter(
        IdempotencyKey.owner_type == owner_type,
        IdempotencyKey.owner_id == owner_id,
        IdempotencyKey.key == key,
    ).first()
    if row is None:
        db.add(
            IdempotencyKey(
                owner_type=owner_type,
                owner_id=owner_id,
                key=key,
                request_hash=request_hash(payload),
                status="processing",
                expires_at=_expiry(),
            )
        )
        db.commit()
        return None

    if ensure_aware(row.expires_at) < now or row.status == "processing":
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": "idempotency key in progress"},
        )
    if row.request_hash != request_hash(payload):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT",
                "message": "idempotency key reused with a different request body",
            },
        )
    return {"status": row.response_status or 200, "body": row.response_json or {}}


def complete(
    db: Session,
    *,
    owner_type: str,
    owner_id: int | None,
    key: str,
    status: int,
    body: dict[str, Any],
) -> None:
    row = db.query(IdempotencyKey).filter(
        IdempotencyKey.owner_type == owner_type,
        IdempotencyKey.owner_id == owner_id,
        IdempotencyKey.key == key,
    ).first()
    if row is None:
        return
    row.status = "succeeded"
    row.response_status = status
    row.response_json = body
    db.commit()

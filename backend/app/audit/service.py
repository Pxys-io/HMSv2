"""Audit service: hash-chained append, intent/commit protocol, verification.

Design (Plan/02 §4):

- Events are appended to the SEPARATE audit database in their own transaction.
- A mutation writes an `intent` event before touching the main DB, then a
  `committed` or `aborted` outcome after the main transaction finishes.
  If the process dies in between, `reconcile()` flags the unresolved intent.
- Every event hash-chains to the previous one (sha256 over the canonical
  payload plus `prev_hash`), so any modification is detectable.
- Signed checkpoints (Ed25519) bind the chain head to an external key, so a
  copy of the checkpoint plus public key survives even DB-level tampering.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditCheckpoint, AuditEvent, AuditMeta
from app.core.config import get_settings
from app.core.security import GENESIS_HASH
from app.core.timeutil import ensure_aware

GENESIS = GENESIS_HASH


def _canonical(payload: dict) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _iso(dt: datetime) -> str:
    """Stable ISO string for hashing — SQLite round-trips datetimes as naive."""
    return ensure_aware(dt).isoformat()


def _now() -> datetime:
    return datetime.now(UTC)


def ensure_meta(audit_db: Session) -> None:
    meta = audit_db.scalar(select(AuditMeta).limit(1))
    if meta is None:
        meta = AuditMeta(genesis_hash=GENESIS, last_hash=GENESIS, last_id=None)
        audit_db.add(meta)
        audit_db.commit()


def append(
    audit_db: Session,
    *,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    action: str,
    outcome: str,
    correlation_id: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ctx: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    ensure_meta(audit_db)
    meta = audit_db.scalar(select(AuditMeta).limit(1).with_for_update())
    assert meta is not None

    now = _now()
    next_id = (meta.last_id or 0) + 1
    prev_hash = meta.last_hash or GENESIS

    payload = {
        "id": next_id,
        "occurred_at": _iso(now),
        "actor_type": actor_type,
        "actor_id": actor_id,
        "actor_label": actor_label,
        "action": action,
        "outcome": outcome,
        "correlation_id": correlation_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before_json": before,
        "after_json": after,
        "context_json": ctx,
        "ip": ip,
        "user_agent": user_agent,
    }
    event_hash = hashlib.sha256(prev_hash.encode() + _canonical(payload)).hexdigest()

    event = AuditEvent(
        occurred_at=now,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        outcome=outcome,
        correlation_id=correlation_id,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=before,
        after_json=after,
        context_json=ctx,
        ip=ip,
        user_agent=user_agent,
        prev_hash=prev_hash,
        hash=event_hash,
    )
    audit_db.add(event)
    meta.last_hash = event_hash
    meta.last_id = next_id
    audit_db.commit()
    return event


def intent(
    audit_db: Session,
    *,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    action: str,
    correlation_id: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ctx: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    return append(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        outcome="intent",
        correlation_id=correlation_id,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        ctx=ctx,
        ip=ip,
        user_agent=user_agent,
    )


def outcome(
    audit_db: Session,
    *,
    outcome: str,
    correlation_id: str,
    action: str,
    actor_type: str = "system",
    actor_id: int | None = None,
    actor_label: str = "system",
    ctx: dict | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> AuditEvent:
    return append(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        outcome=outcome,
        correlation_id=correlation_id,
        entity_type=entity_type,
        entity_id=entity_id,
        ctx=ctx,
    )


def access(
    audit_db: Session,
    *,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    action: str,
    entity_type: str,
    entity_id: str,
    correlation_id: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    return append(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        outcome="access",
        correlation_id=correlation_id,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=ip,
        user_agent=user_agent,
    )


@contextmanager
def audited_action(
    audit_db: Session,
    *,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    action: str,
    correlation_id: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Generator[None, None, None]:
    """Wraps a main-DB mutation: intent -> fn -> committed|aborted.

    If the intent cannot be written, the mutation never starts (the wrapped
    block is not executed). Outcome failures raise so reconciliation can pick
    up the unresolved intent.
    """
    intent(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        correlation_id=correlation_id,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        ip=ip,
        user_agent=user_agent,
    )
    _outcome_kwargs = {"ctx": {"ip": ip}, "entity_type": entity_type, "entity_id": entity_id}
    try:
        yield
    except Exception:
        with suppress(Exception):  # pragma: no cover - audit DB down
            outcome(
                audit_db,
                outcome="aborted",
                correlation_id=correlation_id,
                action=action,
                **_outcome_kwargs,
            )
        raise
    else:
        try:
            outcome(
                audit_db,
                outcome="committed",
                correlation_id=correlation_id,
                action=action,
                **_outcome_kwargs,
            )
        except Exception:
            # The main transaction already committed; surface this loudly.
            raise RuntimeError(f"audit outcome write failed for {correlation_id}") from None


# ------------------------------------------------------------------ verify


def verify(audit_db: Session) -> dict:
    """Walks the chain by id; recomputes hashes; checks intent/outcome pairs."""
    events = audit_db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    meta = audit_db.scalar(select(AuditMeta).limit(1))

    prev = GENESIS
    broken_at = None
    for ev in events:
        payload = {
            "id": ev.id,
            "occurred_at": _iso(ev.occurred_at),
            "actor_type": ev.actor_type,
            "actor_id": ev.actor_id,
            "actor_label": ev.actor_label,
            "action": ev.action,
            "outcome": ev.outcome,
            "correlation_id": ev.correlation_id,
            "entity_type": ev.entity_type,
            "entity_id": ev.entity_id,
            "before_json": ev.before_json,
            "after_json": ev.after_json,
            "context_json": ev.context_json,
            "ip": ev.ip,
            "user_agent": ev.user_agent,
        }
        recomputed = hashlib.sha256(prev.encode() + _canonical(payload)).hexdigest()
        if ev.prev_hash != prev or recomputed != ev.hash:
            broken_at = ev.id
            break
        prev = ev.hash

    # unresolved intents: intent without committed/aborted for same correlation
    unresolved = 0
    if broken_at is None:
        correlations = {e.correlation_id: e for e in events if e.outcome == "intent"}
        for cid in correlations:
            has_terminal = any(
                e.correlation_id == cid and e.outcome in ("committed", "aborted") for e in events
            )
            if not has_terminal:
                unresolved += 1

    return {
        "ok": broken_at is None and (meta is None or meta.last_hash == prev),
        "broken_at_id": broken_at,
        "unresolved_count": unresolved,
        "checked": len(events),
    }


def reconcile(audit_db: Session) -> int:
    """Closes stale unresolved intents with an `aborted` outcome (action
    `reconcile`), preserving the original correlation id; returns the count."""
    ensure_meta(audit_db)
    events = audit_db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    count = 0
    for ev in events:
        if ev.outcome != "intent":
            continue
        has_terminal = any(
            e.correlation_id == ev.correlation_id and e.outcome in ("committed", "aborted")
            for e in events
        )
        if not has_terminal:
            outcome(
                audit_db,
                outcome="aborted",
                correlation_id=ev.correlation_id,
                action="reconcile",
                ctx={"note": "unresolved intent reconciled"},
            )
            count += 1
    return count


# ------------------------------------------------------------- checkpoints


def _checkpoint_key_paths() -> tuple[Path, Path]:
    settings = get_settings()
    key_path = Path(settings.AUDIT_CHECKPOINT_PRIVATE_KEY_PATH or "")
    if key_path.is_file():
        return key_path, Path(str(key_path) + ".pub")
    # dev fallback: generate a keypair under AUDIT_CHECKPOINT_DIR
    d = Path(settings.AUDIT_CHECKPOINT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    private = d / "checkpoint_ed25519.key"
    if not private.exists():
        key = ed25519.Ed25519PrivateKey.generate()
        private.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        public = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        (d / "checkpoint_ed25519.pub").write_bytes(public)
    return private, d / "checkpoint_ed25519.pub"


def create_checkpoint(audit_db: Session) -> AuditCheckpoint:
    """Signs the current chain head and stores the checkpoint row."""
    ensure_meta(audit_db)
    meta = audit_db.scalar(select(AuditMeta).limit(1))
    assert meta is not None
    last_id = meta.last_id or 0
    digest = hashlib.sha256(meta.last_hash.encode()).hexdigest()

    private_path, _ = _checkpoint_key_paths()
    key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    assert isinstance(key, ed25519.Ed25519PrivateKey)
    signature = key.sign(digest.encode("utf-8")).hex()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    public_key_id = hashlib.sha256(public_pem).hexdigest()[:16]

    cp = AuditCheckpoint(
        first_event_id=1,
        last_event_id=last_id,
        chain_head_hash=meta.last_hash,
        signature=signature,
        public_key_id=public_key_id,
    )
    audit_db.add(cp)
    audit_db.commit()
    return cp


def verify_checkpoint(audit_db: Session, checkpoint_id: int) -> dict:
    cp = audit_db.get(AuditCheckpoint, checkpoint_id)
    if cp is None:
        return {"ok": False, "reason": "not_found"}
    digest = hashlib.sha256(cp.chain_head_hash.encode()).hexdigest()
    _, public_path = _checkpoint_key_paths()
    public_pem = public_path.read_bytes()
    key = serialization.load_pem_public_key(public_pem)
    assert isinstance(key, ed25519.Ed25519PublicKey)
    try:
        key.verify(bytes.fromhex(cp.signature), digest.encode("utf-8"))
        return {"ok": True, "checkpoint_id": checkpoint_id, "last_event_id": cp.last_event_id}
    except Exception:
        return {"ok": False, "checkpoint_id": checkpoint_id, "reason": "bad_signature"}


def correlation_for_audit() -> str:
    """Correlation id used by routes; wired to the request id elsewhere."""
    stamp = _now().isoformat(timespec="milliseconds").replace(":", "").replace("-", "")
    return stamp + os.urandom(2).hex()

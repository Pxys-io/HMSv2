"""Audit chain tests: intent/commit protocol, tamper detection, checkpoints."""

from sqlalchemy import select, text

from app.audit import service as audit
from app.audit.models import AuditEvent
from app.db.session import AuditSessionLocal


def _admin_token(client):
    resp = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"}
    )
    return resp.json()["access_token"]


def test_intent_commit_pairs_and_verify_ok(client, admin_user):
    import secrets

    email = f"audit-{secrets.token_hex(4)}@example.com"
    token = _admin_token(client)
    resp = client.post(
        "/api/users",
        json={"email": email, "password": "passw0rd", "full_name": "A1", "role": "secretary"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    user_id = str(resp.json()["id"])
    with AuditSessionLocal() as audit_db:
        events = audit_db.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "user.create", AuditEvent.entity_id == user_id
            )
        ).all()
        outcomes = {e.outcome for e in events}
        assert outcomes == {"intent", "committed"}
        status = audit.verify(audit_db)
        assert status["ok"] is True
        assert status["unresolved_count"] == 0
        assert status["broken_at_id"] is None


def test_reconcile_closes_unresolved_intent():
    with AuditSessionLocal() as audit_db:
        audit.intent(
            audit_db,
            actor_type="system",
            actor_id=None,
            actor_label="test",
            action="test.unresolved",
            correlation_id="orphan-correlation",
        )
        status = audit.verify(audit_db)
        assert status["unresolved_count"] >= 1

        reconciled = audit.reconcile(audit_db)
        assert reconciled >= 1
        status = audit.verify(audit_db)
        assert status["ok"] is True
        assert status["unresolved_count"] == 0

def test_tamper_detected(client, admin_user):
    with AuditSessionLocal() as audit_db:
        audit_db.execute(
            text(
                "UPDATE audit_event SET after_json = '{\"tampered\": true}' "
                "WHERE id = (SELECT MIN(id) FROM audit_event)"
            )
        )
        audit_db.commit()
        status = audit.verify(audit_db)
        assert status["ok"] is False
        assert status["broken_at_id"] is not None

def test_checkpoint_sign_and_verify():
    with AuditSessionLocal() as audit_db:
        cp = audit.create_checkpoint(audit_db)
        result = audit.verify_checkpoint(audit_db, cp.id)
        assert result["ok"] is True
        assert result["last_event_id"] == cp.last_event_id


def test_audit_write_failure_fails_request(client, admin_user, monkeypatch):
    import app.audit.service as audit_service

    def boom(*args, **kwargs):
        raise RuntimeError("audit db unavailable")

    monkeypatch.setattr(audit_service, "append", boom)

    from fastapi.testclient import TestClient

    client_raising = TestClient(client.app, raise_server_exceptions=False)
    resp = client_raising.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"}
    )
    assert resp.status_code == 500

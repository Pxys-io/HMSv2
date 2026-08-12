"""Bulk actions tests (Plan/14 C9)."""

import secrets

from tests.test_financial import admin_headers


def _patient(client, admin, name, phone):
    resp = client.post(
        "/api/patients", json={"full_name": name, "phone": phone},
        headers={**admin, "Idempotency-Key": f"b-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _tag(client, admin, name):
    resp = client.post(
        "/api/tags", json={"name": name},
        headers={**admin, "Idempotency-Key": f"bt-{secrets.token_hex(4)}"},
    )
    return resp.json()


def test_bulk_tag_and_untag(client):
    admin = admin_headers(client)
    p1 = _patient(client, admin, "Bulk One", "01011110001")
    p2 = _patient(client, admin, "Bulk Two", "01011110002")
    tag = _tag(client, admin, "batch")

    resp = client.post("/api/patients/bulk/tag",
                       json={"profile_ids": [p1["id"], p2["id"], 999999], "tag_id": tag["id"]},
                       headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] == [p1["id"], p2["id"]]
    assert resp.json()["failed"] == [999999]

    for pid in (p1["id"], p2["id"]):
        detail = client.get(f"/api/patients/{pid}", headers=admin).json()
        assert any(t["name"] == "batch" for t in detail["tags"])

    resp = client.post("/api/patients/bulk/untag",
                       json={"profile_ids": [p1["id"], p2["id"]], "tag_id": tag["id"]},
                       headers=admin)
    assert resp.json()["success"] == [p1["id"], p2["id"]]
    detail = client.get(f"/api/patients/{p1['id']}", headers=admin).json()
    assert detail["tags"] == []


def test_bulk_delete_archives(client):
    admin = admin_headers(client)
    p1 = _patient(client, admin, "Bulk Del One", "01011110003")
    p2 = _patient(client, admin, "Bulk Del Two", "01011110004")
    resp = client.post("/api/patients/bulk/delete",
                       json={"profile_ids": [p1["id"], p2["id"]]}, headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] == [p1["id"], p2["id"]]
    for pid in (p1["id"], p2["id"]):
        detail = client.get(f"/api/patients/{pid}", headers=admin).json()
        assert detail["is_archived"] is True


def test_bulk_validation(client):
    admin = admin_headers(client)
    tag = _tag(client, admin, "bv")
    resp = client.post("/api/patients/bulk/tag", json={"profile_ids": [], "tag_id": tag["id"]},
                       headers=admin)
    assert resp.status_code == 422
    resp = client.post("/api/patients/bulk/tag",
                       json={"profile_ids": [1, 2], "tag_id": 999999}, headers=admin)
    assert resp.status_code == 404

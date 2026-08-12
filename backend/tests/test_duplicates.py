"""Duplicate detection, merge, archive tests (Plan/14 C8)."""

import secrets
from datetime import date

from tests.test_financial import _complete_visit, admin_headers


def _create_patient(client, admin, name, phone, birth=None):
    body = {"full_name": name, "phone": phone}
    if birth:
        body["birth_date"] = birth
    resp = client.post(
        "/api/patients", json=body,
        headers={**admin, "Idempotency-Key": f"dup-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_detection_by_phone(client):
    admin = admin_headers(client)
    _create_patient(client, admin, "Same Person", "01012345678")
    _create_patient(client, admin, "Same Person Copy", "01012345678")
    resp = client.post("/api/duplicates/refresh", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["groups"] >= 1
    items = client.get("/api/duplicates", headers=admin).json()["items"]
    assert any(g["match_reason"].startswith("phone:") for g in items)


def test_detection_by_name_and_birth(client):
    admin = admin_headers(client)
    _create_patient(client, admin, "Twin Name", "01077770001", "1990-05-05")
    _create_patient(client, admin, "Twin Name", "01077770002", "1990-05-05")
    client.post("/api/duplicates/refresh", headers=admin)
    items = client.get("/api/duplicates", headers=admin).json()["items"]
    assert any(g["match_reason"].startswith("name:") for g in items)


def test_merge_absorbs_records(client, clinic):
    admin = admin_headers(client)
    # primary goes through a full visit so it has appointments/visits/invoices
    _complete_visit(client, clinic)
    dup = _create_patient(client, admin, "Merge Me", "01055557777")
    _create_patient(client, admin, "Merge Me Copy", "01055557777")
    client.post("/api/duplicates/refresh", headers=admin)
    items = client.get("/api/duplicates", headers=admin).json()["items"]
    group = next(g for g in items if dup["id"] in g["profile_ids"])
    other_id = next(pid for pid in group["profile_ids"] if pid != group["primary_profile_id"])

    # give the duplicate an appointment too
    client.post(
        "/api/appointments",
        json={"patient_profile_id": other_id, "doctor_id": clinic["doctor_id"],
              "visit_type_id": clinic["visit_type_id"], "date": date.today().isoformat(),
              "start_time": "17:40"},
        headers={**admin, "Idempotency-Key": f"bk-{secrets.token_hex(4)}"},
    )

    resp = client.post(f"/api/duplicates/{group['id']}/accept", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "merged"

    # absorbed profile is archived; its appointment moved to primary
    dup_detail = client.get(f"/api/patients/{other_id}", headers=admin).json()
    assert dup_detail["is_archived"] is True
    appts = client.get(
        f"/api/patients/{group['primary_profile_id']}/appointments", headers=admin
    ).json()
    assert len(appts) >= 1
    # activity logged on both sides
    events = client.get(f"/api/patients/{other_id}/activity", headers=admin).json()["items"]
    assert any(e["type"] == "patient.merged" for e in events)


def test_reject_group(client):
    admin = admin_headers(client)
    a = _create_patient(client, admin, "Reject A", "01066668888")
    _create_patient(client, admin, "Reject B", "01066668888")
    client.post("/api/duplicates/refresh", headers=admin)
    group = next(
        g for g in client.get("/api/duplicates", headers=admin).json()["items"]
        if a["id"] in g["profile_ids"]
    )
    resp = client.post(f"/api/duplicates/{group['id']}/reject", headers=admin)
    assert resp.status_code == 200
    open_items = client.get("/api/duplicates", headers=admin).json()["items"]
    assert all(g["id"] != group["id"] for g in open_items)
    rejected = client.get("/api/duplicates?status=rejected", headers=admin).json()["items"]
    assert any(g["id"] == group["id"] for g in rejected)


def test_archive_unarchive(client, clinic):
    admin = admin_headers(client)
    pid = clinic["profile_id"]
    resp = client.post(f"/api/patients/{pid}/archive", headers=admin)
    assert resp.status_code == 200, resp.text
    detail = client.get(f"/api/patients/{pid}", headers=admin).json()
    assert detail["is_archived"] is True
    resp = client.post(f"/api/patients/{pid}/unarchive", headers=admin)
    assert resp.status_code == 200, resp.text
    detail = client.get(f"/api/patients/{pid}", headers=admin).json()
    assert detail["is_archived"] is False
    # double archive -> 422
    client.post(f"/api/patients/{pid}/archive", headers=admin)
    resp = client.post(f"/api/patients/{pid}/archive", headers=admin)
    assert resp.status_code == 422

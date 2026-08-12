"""Visit form customizability tests (high-grade form config)."""

import secrets

from tests.test_financial import admin_headers


def test_visit_form_defaults_and_round_trip(client):
    admin = admin_headers(client)
    body = client.get("/api/visit-form/sections", headers=admin).json()
    assert len(body["sections"]) == 8
    assert body["builtin_keys"] == [
        "chief_complaint", "history", "clinical_exam", "findings",
        "labs", "imaging", "plan", "notes_next_visit",
    ]

    sections = body["sections"]
    sections[0]["label_en"] = "Reason for visit"
    sections[0]["label_ar"] = "سبب الزيارة"
    sections[1]["enabled"] = False
    sections[2]["required"] = True
    sections.append({"key": "smoking_status", "label_en": "Smoking", "label_ar": "التدخين",
                     "type": "select", "required": False, "enabled": True,
                     "options": ["Never", "Former", "Current"]})
    resp = client.put("/api/visit-form/sections", json={"sections": sections}, headers=admin)
    assert resp.status_code == 200, resp.text
    saved = resp.json()["sections"]
    assert saved[0]["label_en"] == "Reason for visit"
    assert saved[1]["enabled"] is False
    assert saved[2]["required"] is True
    assert saved[-1]["options"] == ["Never", "Former", "Current"]

    # bad type rejected
    sections[0]["type"] = "hologram"
    resp = client.put("/api/visit-form/sections", json={"sections": sections}, headers=admin)
    assert resp.status_code == 422


def test_required_section_blocks_completion(client, clinic):
    admin = admin_headers(client)
    body = client.get("/api/visit-form/sections", headers=admin).json()
    sections = body["sections"]
    for section in sections:
        section["required"] = False
        section["enabled"] = True
    sections[0]["required"] = True  # chief_complaint
    client.put("/api/visit-form/sections", json={"sections": sections}, headers=admin)

    # run the queue flow but STOP before completing
    from tests.test_financial import _book_and_check_in

    entry = _book_and_check_in(client, clinic, admin)
    client.post(
        f"/api/queue/{entry['id']}/start",
        headers={**admin, "Idempotency-Key": f"st-{secrets.token_hex(4)}"},
    )
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=admin
    ).json()[0]["id"]
    # completing without chief complaint -> 422
    resp = client.post(
        f"/api/visits/{visit_id}/complete",
        headers={**admin, "Idempotency-Key": f"cp-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 422, resp.text

    # fill it in, completion succeeds
    version = client.get(f"/api/visits/{visit_id}", headers=admin).json()["record_version"]
    client.patch(
        f"/api/visits/{visit_id}",
        json={"record_version": version, "chief_complaint": "Fever and cough"},
        headers=admin,
    )
    resp = client.post(
        f"/api/visits/{visit_id}/complete",
        headers={**admin, "Idempotency-Key": f"cp-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text


def test_reset_form_config(client):
    admin = admin_headers(client)
    body = client.get("/api/visit-form/sections", headers=admin).json()
    sections = body["sections"]
    sections[0]["label_en"] = "X"
    client.put("/api/visit-form/sections", json={"sections": sections}, headers=admin)
    # restoring defaults: empty list -> defaults
    resp = client.put("/api/visit-form/sections", json={"sections": []}, headers=admin)
    assert resp.status_code == 200
    assert resp.json()["sections"][0]["label_en"] == "Chief complaint"

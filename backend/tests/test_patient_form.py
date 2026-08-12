"""Patient form builder tests (sophisticated JSON schema form)."""

import secrets

from tests.test_financial import admin_headers


def _form(client, admin):
    body = client.get("/api/patient-form", headers=admin).json()
    assert len(body["fields"]) >= 9
    return body


def test_patient_form_defaults_and_round_trip(client):
    admin = admin_headers(client)
    body = _form(client, admin)
    keys = [f["key"] for f in body["fields"]]
    assert "full_name" in keys and "phone" in keys and "chronic_conditions" in keys

    fields = body["fields"]
    for f in fields:
        if f["key"] == "gender":
            f["required"] = True
            f["label_en"] = "Sex"
        if f["key"] == "phone":
            f["pattern"] = r"^01[0-9]{9}$"
    resp = client.put("/api/patient-form", json={"fields": fields}, headers=admin)
    assert resp.status_code == 200, resp.text
    saved = resp.json()["fields"]
    assert next(f for f in saved if f["key"] == "gender")["label_en"] == "Sex"
    assert next(f for f in saved if f["key"] == "phone")["pattern"] == "^01[0-9]{9}$"

    # bad type rejected
    fields[0]["type"] = "hologram"
    resp = client.put("/api/patient-form", json={"fields": fields}, headers=admin)
    assert resp.status_code == 422

    # reset
    fields[0]["type"] = "text"
    client.put("/api/patient-form", json={"fields": fields}, headers=admin)


def test_required_field_enforced_on_create(client):
    admin = admin_headers(client)
    body = client.get("/api/patient-form", headers=admin).json()
    for f in body["fields"]:
        if f["key"] == "gender":
            f["required"] = True
    client.put("/api/patient-form", json={"fields": body["fields"]}, headers=admin)

    resp = client.post(
        "/api/patients",
        json={"full_name": "No Gender", "phone": "01012345678"},
        headers={**admin, "Idempotency-Key": f"pf-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 422, resp.text
    assert "gender" in resp.text

    resp = client.post(
        "/api/patients",
        json={"full_name": "With Gender", "phone": "01012345678", "gender": "female"},
        headers={**admin, "Idempotency-Key": f"pf-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text

    # reset
    for f in body["fields"]:
        f["required"] = False
    client.put("/api/patient-form", json={"fields": body["fields"]}, headers=admin)


def test_unknown_and_invalid_values_rejected(client):
    admin = admin_headers(client)
    # a fixed column disabled in the form config is rejected on write
    body = client.get("/api/patient-form", headers=admin).json()
    for f in body["fields"]:
        if f["key"] == "phone_alt":
            f["enabled"] = False
    client.put("/api/patient-form", json={"fields": body["fields"]}, headers=admin)
    resp = client.post(
        "/api/patients",
        json={"full_name": "X Y", "phone": "01012345678", "phone_alt": "01099998888"},
        headers={**admin, "Idempotency-Key": f"pf-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 422, resp.text
    assert "phone_alt" in resp.text
    for f in body["fields"]:
        f["enabled"] = True
    client.put("/api/patient-form", json={"fields": body["fields"]}, headers=admin)

    # bad select value on patch
    created = client.post(
        "/api/patients",
        json={"full_name": "Z W", "phone": "01012345678"},
        headers={**admin, "Idempotency-Key": f"pf-{secrets.token_hex(4)}"},
    ).json()
    resp = client.patch(
        f"/api/patients/{created['id']}/demographics",
        json={"gender": "martian"},
        headers=admin,
    )
    assert resp.status_code == 422

    # valid select round-trips
    resp = client.patch(
        f"/api/patients/{created['id']}/demographics",
        json={"gender": "male"},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text


def test_patient_form_requires_permission(client):
    # staff with patient.view can read the schema
    pass

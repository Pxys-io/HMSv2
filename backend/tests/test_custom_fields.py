"""Custom fields tests (Plan/14 A2 done-when)."""

import secrets

from tests.conftest import csrf_headers


def admin_headers(client):
    client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    token = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_custom_field_crud_and_roundtrip(client):
    headers = admin_headers(client)

    # create "Blood group" select on patient
    created = client.post(
        "/api/custom-fields",
        json={
            "entity": "patient",
            "label": "Blood group",
            "label_ar": "فصيلة الدم",
            "type": "select",
            "options": ["A+", "A-", "B+", "O+"],
            "is_required": True,
        },
        headers=headers,
    )
    assert created.status_code == 200
    field = created.json()
    assert field["key"] == "blood_group"  # F1 auto slug key
    assert field["is_required"] is True

    # visit field "Smoker" boolean
    smoker = client.post(
        "/api/custom-fields",
        json={"entity": "visit", "label": "Smoker", "type": "boolean"},
        headers=headers,
    )
    assert smoker.status_code == 200
    assert smoker.json()["key"] == "smoker"

    # create a patient, set custom_data (required blood group)
    patient = client.post(
        "/api/patients",
        json={"full_name": "Custom P", "phone": "01000000001",
              "custom_data": {"blood_group": "A+"}},
        headers=headers,
    )
    assert patient.status_code == 200, patient.text
    assert patient.json()["custom_data"] == {"blood_group": "A+"}

    # missing required -> 422
    bad = client.post(
        "/api/patients",
        json={"full_name": "Custom P2", "phone": "01000000002", "custom_data": {}},
        headers=headers,
    )
    assert bad.status_code == 422

    # bogus option -> 422
    bogus = client.patch(
        f"/api/patients/{patient.json()['id']}/demographics",
        json={"custom_data": {"blood_group": "AB-unknown"}},
        headers=headers,
    )
    assert bogus.status_code == 422

    # unknown key -> 422
    unknown = client.patch(
        f"/api/patients/{patient.json()['id']}/demographics",
        json={"custom_data": {"not_a_field": 1}},
        headers=headers,
    )
    assert unknown.status_code == 422

    # deactivate hides from schema but value still readable (F4)
    deactivated = client.post(
        f"/api/custom-fields/{field['id']}/deactivate", headers=headers
    )
    assert deactivated.status_code == 200
    schema = client.get("/api/custom-fields/schema?entity=patient", headers=headers).json()
    assert all(f["key"] != "blood_group" for f in schema["fields"])
    profile = client.get(f"/api/patients/{patient.json()['id']}", headers=headers).json()
    assert profile["custom_data"] == {"blood_group": "A+"}


def test_visit_custom_data_roundtrip(client):
    headers = admin_headers(client)
    client.post(
        "/api/custom-fields",
        json={"entity": "visit", "label": "Smoker", "type": "boolean"},
        headers=headers,
    )

    # create doctor + patient + adhoc visit
    doctor = client.post(
        "/api/doctors",
        json={"email": f"cf-{secrets.token_hex(4)}@example.com", "password": "passw0rd",
              "full_name": "CF Doc", "specialty": "General"},
        headers=headers,
    )
    assert doctor.status_code == 200
    doc_token = client.post(
        "/api/auth/login",
        json={"email": doctor.json()["email"], "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    doc = {"Authorization": f"Bearer {doc_token}"}

    patient = client.post(
        "/api/patients", json={"full_name": "Visit CF", "phone": "01000000003"}, headers=headers
    ).json()

    from app.db.session import SessionLocal
    from app.models.scheduling import VisitType

    db = SessionLocal()
    vt = VisitType(name="Consultation", name_ar="كشف", duration_minutes=20, default_price=300)
    db.add(vt)
    db.commit()
    vts = [{"id": vt.id}]
    db.close()
    visit = client.post(
        "/api/visits",
        json={"patient_profile_id": patient["id"], "visit_type_id": vts[0]["id"]},
        headers=doc,
    )
    assert visit.status_code == 200
    visit_id = visit.json()["id"]

    saved = client.patch(
        f"/api/visits/{visit_id}",
        json={"custom_data": {"smoker": True}, "record_version": 1},
        headers=doc,
    )
    assert saved.status_code == 200
    assert saved.json()["custom_data"] == {"smoker": True}

    # boolean type validation
    bad = client.patch(
        f"/api/visits/{visit_id}",
        json={"custom_data": {"smoker": "yes"}, "record_version": 2},
        headers=doc,
    )
    assert bad.status_code == 422


def test_key_unique_and_type_validation(client):
    headers = admin_headers(client)
    first = client.post(
        "/api/custom-fields",
        json={"entity": "patient", "label": "Height", "type": "number"},
        headers=headers,
    )
    assert first.status_code == 200
    dup = client.post(
        "/api/custom-fields",
        json={"entity": "patient", "label": "Height", "type": "number"},
        headers=headers,
    )
    assert dup.status_code == 200
    assert dup.json()["key"] == "height_2"

    # select without options -> 422
    noopts = client.post(
        "/api/custom-fields",
        json={"entity": "visit", "label": "Severity", "type": "select"},
        headers=headers,
    )
    assert noopts.status_code == 422

    # schema endpoint requires staff but not admin
    sec_token = client.post(
        "/api/auth/login", json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    schema = client.get(
        "/api/custom-fields/schema?entity=visit",
        headers={"Authorization": f"Bearer {sec_token}"},
    )
    assert schema.status_code == 200

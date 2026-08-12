"""Form asset tests: templates, uploads, annotation/audio field values."""

import io
import secrets

from PIL import Image

from tests.test_financial import admin_headers


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), color=(30, 60, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _png_upload(client, headers, url):
    return client.post(url, files={"file": ("tpl.png", _png(), "image/png")}, headers=headers)


def test_template_upload_and_serve(client):
    admin = admin_headers(client)
    resp = _png_upload(client, admin, "/api/form-assets/template")
    assert resp.status_code == 200, resp.text
    template_id = resp.json()["template_file_id"]

    served = client.get(f"/api/form-assets/template/{template_id}", headers=admin)
    assert served.status_code == 200
    assert served.content.startswith(b"\x89PNG")


def test_form_asset_upload_for_patient_and_visit(client, clinic):
    admin = admin_headers(client)
    resp = _png_upload(
        client, admin, f"/api/form-assets/patient/{clinic['profile_id']}"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_id"] and body["mime"] in ("image/png", "image/jpeg")


def test_asset_custom_field_round_trip(client, clinic):
    admin = admin_headers(client)
    field = client.post(
        "/api/custom-fields",
        json={"entity": "patient", "label": "Chest X-ray", "type": "photo"},
        headers={**admin, "Idempotency-Key": f"cf-{secrets.token_hex(4)}"},
    ).json()
    field_key = field["key"]
    asset = _png_upload(
        client, admin, f"/api/form-assets/patient/{clinic['profile_id']}"
    ).json()

    resp = client.post(
        "/api/patients",
        json={"full_name": "Asset Pat", "phone": "01012345678",
              "custom_data": {field_key: {"file_id": asset["file_id"], "mime": "image/png"}}},
        headers={**admin, "Idempotency-Key": f"as-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["custom_data"][field_key]["file_id"] == asset["file_id"]

    # bad value shape rejected
    bad = client.post(
        "/api/patients",
        json={"full_name": "Bad Asset", "phone": "01012345678",
              "custom_data": {field_key: "not-a-file"}},
        headers={**admin, "Idempotency-Key": f"as-{secrets.token_hex(4)}"},
    )
    assert bad.status_code == 422


def test_annotation_field_requires_template(client):
    admin = admin_headers(client)
    resp = client.post(
        "/api/custom-fields",
        json={"entity": "patient", "label": "Body diagram", "type": "annotation"},
        headers=admin,
    )
    assert resp.status_code == 422
    resp = client.post(
        "/api/custom-fields",
        json={"entity": "patient", "label": "Body diagram", "type": "annotation",
              "template_file_id": 1},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text

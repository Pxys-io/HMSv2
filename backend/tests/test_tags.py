"""Patient tags tests (Plan/14 C4)."""

import secrets

from tests.test_financial import admin_headers


def _make_tag(client, admin, name):
    resp = client.post(
        "/api/tags", json={"name": name, "name_ar": f"وسم {name}"},
        headers={**admin, "Idempotency-Key": f"tg-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_tag_crud_and_patient_assignment(client, clinic):
    admin = admin_headers(client)
    tag = _make_tag(client, admin, "vip")
    assert tag["name"] == "vip"

    pid = clinic["profile_id"]
    resp = client.put(f"/api/patients/{pid}/tags", json={"tag_ids": [tag["id"]]}, headers=admin)
    assert resp.status_code == 200, resp.text
    detail = client.get(f"/api/patients/{pid}", headers=admin).json()
    assert any(t["name"] == "vip" for t in detail["tags"])

    tags = client.get("/api/tags", headers=admin).json()["items"]
    assert any(t["name"] == "vip" for t in tags)

    # deactivate hides from list, keeps assignment intact
    client.patch(f"/api/tags/{tag['id']}", json={"is_active": False}, headers=admin)
    tags = client.get("/api/tags", headers=admin).json()["items"]
    assert all(t["name"] != "vip" for t in tags)


def test_tag_delete_removes_assignments(client, clinic):
    admin = admin_headers(client)
    tag = _make_tag(client, admin, "temp")
    pid = clinic["profile_id"]
    client.put(f"/api/patients/{pid}/tags", json={"tag_ids": [tag["id"]]}, headers=admin)
    resp = client.delete(f"/api/tags/{tag['id']}", headers=admin)
    assert resp.status_code == 200
    detail = client.get(f"/api/patients/{pid}", headers=admin).json()
    assert detail["tags"] == []


def test_search_filters_by_tag(client, clinic):
    admin = admin_headers(client)
    tag = _make_tag(client, admin, "diabetic")
    pid = clinic["profile_id"]
    client.put(f"/api/patients/{pid}/tags", json={"tag_ids": [tag["id"]]}, headers=admin)

    with_tag = client.get(
        f"/api/search/patients?q=Fin&tag_id={tag['id']}", headers=admin
    ).json()["results"]
    assert any(r["id"] == pid for r in with_tag)
    assert with_tag[0]["tags"][0]["name"] == "diabetic"


def test_duplicate_tag_rejected(client, clinic):
    admin = admin_headers(client)
    _make_tag(client, admin, "unique")
    resp = client.post("/api/tags", json={"name": "unique"}, headers=admin)
    assert resp.status_code == 422

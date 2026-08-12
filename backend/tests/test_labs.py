"""Structured labs + trends tests (Plan/14 D2)."""

import secrets
from datetime import date

from tests.test_financial import _complete_visit, admin_headers

TODAY = date.today()


def test_add_and_list_visit_labs(client, clinic):
    admin = admin_headers(client)
    _complete_visit(client, clinic)
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=admin
    ).json()[0]["id"]
    resp = client.post(
        f"/api/visits/{visit_id}/lab-results",
        json={"results": [
            {"name": "HbA1c", "value": 7.2, "unit": "%", "ref_min": 4, "ref_max": 5.6},
            {"name": "CBC - WBC", "value": 8.5, "unit": "x10^3/uL", "ref_min": 4, "ref_max": 11},
        ]},
        headers={**admin, "Idempotency-Key": f"lab-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 2

    rows = client.get(f"/api/visits/{visit_id}/lab-results", headers=admin).json()["items"]
    assert len(rows) == 2
    assert any(r["name"] == "HbA1c" and r["value"] == 7.2 for r in rows)


def test_lab_trend_endpoint(client, clinic):
    admin = admin_headers(client)
    _complete_visit(client, clinic)
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=admin
    ).json()[0]["id"]
    for value in (6.5, 7.0, 7.4):
        client.post(
            f"/api/visits/{visit_id}/lab-results",
            json={"results": [{"name": "HbA1c", "value": value, "unit": "%"}]},
            headers=admin,
        )
    trend = client.get(
        f"/api/patients/{clinic['profile_id']}/lab-trends?name=HbA1c", headers=admin
    ).json()
    assert trend["name"] == "HbA1c"
    assert [p["value"] for p in trend["points"]] == [6.5, 7.0, 7.4]
    assert trend["unit"] == "%"


def test_lab_validation(client, clinic):
    admin = admin_headers(client)
    _complete_visit(client, clinic)
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=admin
    ).json()[0]["id"]
    resp = client.post(
        f"/api/visits/{visit_id}/lab-results",
        json={"results": [{"name": "", "value": 1}]},
        headers=admin,
    )
    assert resp.status_code == 422
    resp = client.post(
        f"/api/visits/{visit_id}/lab-results",
        json={"results": [{"name": "X", "value": "abc"}]},
        headers=admin,
    )
    assert resp.status_code == 422

"""Vitals reference range tests (Plan/14 D3)."""


from tests.test_financial import _complete_visit, admin_headers


def test_vitals_flagged_at_save(client, clinic):
    admin = admin_headers(client)
    _complete_visit(client, clinic)
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=admin
    ).json()[0]["id"]
    version = client.get(f"/api/visits/{visit_id}", headers=admin).json()["record_version"]
    resp = client.patch(
        f"/api/visits/{visit_id}",
        json={"record_version": version, "vitals": {
            "bp_sys": 150, "bp_dia": 85, "hr": 55, "temp": 37.0, "spo2": 94,
        }},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    vitals = resp.json()["vitals"]
    assert vitals["bp_sys_flag"] == "high"
    assert vitals["bp_dia_flag"] == "normal"
    assert vitals["hr_flag"] == "low"
    assert vitals["spo2_flag"] == "low"
    assert vitals["temp_flag"] == "normal"


def test_custom_ranges_respected(client, clinic):
    admin = admin_headers(client)
    client.put("/api/settings", json={
        "vitals.reference_ranges": {
            "hr": {"min": 50, "max": 90, "unit": "bpm"},
            "temp": {"min": 36.0, "max": 37.5, "unit": "°C"},
        }
    }, headers=admin)
    _complete_visit(client, clinic)
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=admin
    ).json()[0]["id"]
    version = client.get(f"/api/visits/{visit_id}", headers=admin).json()["record_version"]
    resp = client.patch(
        f"/api/visits/{visit_id}",
        json={"record_version": version, "vitals": {"hr": 55}},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["vitals"]["hr_flag"] == "normal"

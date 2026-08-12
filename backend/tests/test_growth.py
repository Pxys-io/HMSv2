"""Growth chart tests (Plan/14 D4)."""

import secrets
from datetime import date, timedelta

from tests.test_financial import admin_headers

TODAY = date.today()


def _make_boy(client, admin, birth):
    resp = client.post(
        "/api/patients",
        json={"full_name": "Baby Boy", "phone": "01022223333", "gender": "male",
              "birth_date": birth.isoformat()},
        headers={**admin, "Idempotency-Key": f"gr-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_growth_curves_and_measurements(client, clinic):
    admin = admin_headers(client)
    boy = _make_boy(client, admin, TODAY - timedelta(days=365))

    # book + run a visit for the boy
    client.post(
        "/api/appointments",
        json={"patient_profile_id": boy["id"], "doctor_id": clinic["doctor_id"],
              "visit_type_id": clinic["visit_type_id"], "date": TODAY.isoformat(),
              "start_time": "17:30"},
        headers={**admin, "Idempotency-Key": f"bk-{secrets.token_hex(4)}"},
    )
    appts = client.get(f"/api/patients/{boy['id']}/appointments", headers=admin).json()["items"]
    appt = appts[0]
    client.post("/api/queue/check-in", json={"appointment_id": appt["id"]}, headers=admin)
    entry = client.get(f"/api/queue?doctor_id={clinic['doctor_id']}&date={TODAY.isoformat()}",
                       headers=admin).json()["entries"][-1]
    client.post(f"/api/queue/{entry['id']}/start", headers=admin)
    visit_id = client.get(f"/api/patients/{boy['id']}/timeline", headers=admin).json()[0]["id"]
    version = client.get(f"/api/visits/{visit_id}", headers=admin).json()["record_version"]
    client.patch(f"/api/visits/{visit_id}",
                 json={"record_version": version, "vitals": {"weight": 9.5, "height": 74.0}},
                 headers=admin)

    report = client.get(f"/api/patients/{boy['id']}/growth?metric=weight", headers=admin).json()
    assert report["metric"] == "weight"
    assert report["sex"] == "boy"
    assert report["unit"] == "kg"
    assert len(report["curves"]["ages"]) >= 10
    assert len(report["curves"]["median"]) == len(report["curves"]["ages"])
    assert len(report["measurements"]) == 1
    assert report["measurements"][0]["value"] == 9.5
    # median at ~12 months ≈ 9.6 kg (WHO)
    ages = report["curves"]["ages"]
    median_12m = report["curves"]["median"][ages.index(12)]
    assert 9.0 < median_12m < 10.5
    # z-curves are ordered low < median < high everywhere
    for low, med, high in zip(
        report["curves"]["low"],
        report["curves"]["median"],
        report["curves"]["high"],
        strict=False,
    ):
        assert low < med < high


def test_growth_bad_metric(client):
    admin = admin_headers(client)
    resp = client.get("/api/patients/1/growth?metric=blood", headers=admin)
    assert resp.status_code == 422

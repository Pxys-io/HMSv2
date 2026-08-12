"""Communication log tests (Plan/14 C3)."""

from tests.test_financial import _complete_visit, admin_headers


def test_manual_log_and_list(client, clinic):
    admin = admin_headers(client)
    pid = clinic["profile_id"]
    resp = client.post(
        f"/api/patients/{pid}/communications",
        json={"channel": "call", "summary": "Called to confirm appointment"},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["channel"] == "call"
    rows = client.get(f"/api/patients/{pid}/communications", headers=admin).json()["items"]
    assert any(r["summary"] == "Called to confirm appointment" for r in rows)


def test_bad_channel_rejected(client, clinic):
    admin = admin_headers(client)
    pid = clinic["profile_id"]
    resp = client.post(
        f"/api/patients/{pid}/communications",
        json={"channel": "fax", "summary": "x"},
        headers=admin,
    )
    assert resp.status_code == 422


def test_reminder_link_hook_logs_whatsapp(client, clinic):
    admin = admin_headers(client)
    pid = clinic["profile_id"]
    client.patch(f"/api/patients/{pid}/demographics", json={"phone": "01012345678"}, headers=admin)
    appt_id = clinic["appointment_id"]
    resp = client.get(
        f"/api/appointments/{appt_id}/reminder-link?locale=ar", headers=admin
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["url"] and resp.json()["url"].startswith("https://wa.me/")
    rows = client.get(f"/api/patients/{pid}/communications", headers=admin).json()["items"]
    assert any(r["channel"] == "whatsapp" for r in rows)


def test_staff_booking_logs_no_communications(client, clinic):
    """Staff bookings don't email the patient -> no automatic log entries."""
    admin = admin_headers(client)
    _complete_visit(client, clinic)
    pid = clinic["profile_id"]
    rows = client.get(f"/api/patients/{pid}/communications", headers=admin).json()["items"]
    assert rows == []

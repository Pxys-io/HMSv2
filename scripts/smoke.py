#!/usr/bin/env python3
"""HMSv2 live end-to-end smoke test (Plan/13 launch checklist).

Brings up nothing itself — expects the API on $HMSV2_API (default
http://localhost:8000) with a freshly seeded dev database. Walks the whole
patient journey through the real HTTP API and asserts each step.

Exit code 0 = everything works; non-zero = a step failed.
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "http://localhost:8000"

PASS, FAIL = 0, 1
failures: list[str] = []


def req(method, path, body=None, token=None, idem=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if idem:
        r.add_header("Idempotency-Key", idem)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def step(name, fn):
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as exc:  # noqa: BLE001 - any failure fails the smoke
        print(f"  ✗ {name}: {exc}")
        failures.append(name)


def expect(cond, message):
    if not cond:
        raise AssertionError(message)


def main():
    print("== HMSv2 live smoke ==")
    s, _ = req("GET", "/api/health")
    expect(s == 200, "API not reachable — start it with scripts/dev.sh or run.py")
    print("  ✓ API reachable")

    # ---- staff flow: admin, demo doctor, book, queue, exam, invoice
    s, login = req("POST", "/api/auth/login", {"email": "admin@example.com", "password": "admin12345"})
    expect(s == 200, "admin login failed")
    admin = login["access_token"]

    s, docs = req("GET", "/api/doctors", token=admin)
    expect(s == 200 and docs["items"], "no doctors seeded")
    doc_id = docs["items"][0]["id"]

    today = date.today()
    req("POST", f"/api/doctors/{doc_id}/schedules",
        {"weekday": today.weekday(), "start_time": "17:00", "end_time": "21:00"}, token=admin)

    s, vts = req("GET", "/api/visit-types", token=admin)
    expect(s == 200 and vts, "no visit types seeded")
    vt_id = vts[0]["id"]

    s, prof = req("POST", "/api/patients", {"full_name": "Smoke Patient", "phone": "01055556666"}, token=admin)
    expect(s == 200, "patient create failed")

    s, appt = req("POST", "/api/appointments",
                  {"patient_profile_id": prof["id"], "doctor_id": doc_id, "visit_type_id": vt_id,
                   "date": today.isoformat(), "start_time": "17:00"}, token=admin, idem="smoke-appt")
    expect(s == 200 and appt["booking_ref"].startswith("BK-"), "booking failed")

    s, checked = req("POST", "/api/queue/check-in", {"appointment_id": appt["id"]}, token=admin, idem="smoke-ci")
    expect(s == 200 and checked["status"] == "waiting", "check-in failed")

    s, entry = req("GET", f"/api/queue?doctor_id={doc_id}&date={today.isoformat()}", token=admin)
    expect(s == 200 and entry["entries"], "queue board empty")
    entry_id = entry["entries"][0]["id"]

    s, started = req("POST", f"/api/queue/{entry_id}/start", token=admin, idem="smoke-start")
    expect(s == 200 and started["status"] == "in_room", "visit start failed")

    s, dlogin = req("POST", "/api/auth/login", {"email": "demo@example.com", "password": "demo12345"})
    expect(s == 200, "demo doctor login failed")
    doc = dlogin["access_token"]

    s, timeline = req("GET", f"/api/patients/{prof['id']}/timeline", token=doc)
    expect(s == 200 and timeline, "timeline empty after visit start")
    visit_id = timeline[0]["id"]

    s, _ = req("PATCH", f"/api/visits/{visit_id}",
               {"chief_complaint": "headache", "plan": "rest", "record_version": 1}, token=doc)
    expect(s == 200, "visit autosave failed")

    s, done = req("POST", f"/api/visits/{visit_id}/complete", token=doc, idem="smoke-complete")
    expect(s == 200 and done["status"] == "completed", "visit completion failed")

    # No auto-invoice: the completed visit appears in the cashier list.
    s, uninvoiced = req("GET", "/api/cashier/uninvoiced", token=admin)
    expect(s == 200, "uninvoiced list failed")
    expect(any(r["visit_id"] == visit_id for r in uninvoiced), "completed visit not in cashier list")
    row = next(r for r in uninvoiced if r["visit_id"] == visit_id)
    expect(row["price_preview"] == 300, "price preview mismatch")

    # Cashier creates the invoice manually.
    s, inv = req("POST", f"/api/invoices/from-visit/{visit_id}", token=admin, idem="smoke-inv")
    expect(s == 200 and inv["number"].startswith("INV-"), "manual invoice failed")
    expect(float(inv["total"]) == 300, "invoice total mismatch")

    s, paid = req("POST", f"/api/invoices/{inv['id']}/payments",
                  {"amount": 300, "method": "fawry"}, token=admin, idem="smoke-pay")
    expect(s == 200 and paid["status"] == "paid", "payment failed")

    s, pt = req("POST", f"/api/print/token?key=invoice&entity_id={inv['id']}", token=admin)
    expect(s == 200, "print token failed")
    r = urllib.request.Request(BASE + f"/api/print/invoice/{inv['id']}?token={pt['token']}&locale=en")
    with urllib.request.urlopen(r, timeout=20) as resp:
        html = resp.read().decode()
    expect(inv["number"] in html, "printed invoice missing number")

    # ---- public flow: register, family profile, book, notification fan-out
    s, reg = req("POST", "/api/public/auth/register",
                 {"full_name": "Smoke Public", "email": f"smoke-{date.today().isoformat()}@example.com",
                  "password": "smokepass"})
    expect(s == 200, "patient register failed")
    ptoken = reg["access_token"]

    s, pprof = req("POST", "/api/public/profiles", {"full_name": "Smoke Public", "phone": "01011112222"}, token=ptoken)
    expect(s == 200, "public profile create failed")

    days_ahead = (0 - today.weekday()) % 7 or 7
    monday = (today + timedelta(days=days_ahead)).isoformat()
    s, pub = req("POST", "/api/public/appointments",
                 {"profile_id": pprof["id"], "doctor_id": doc_id, "visit_type_id": vt_id,
                  "date": monday, "start_time": "17:00"}, token=ptoken, idem="smoke-pub")
    expect(s == 200 and pub["booking_ref"].startswith("BK-"), "public booking failed")

    s, notifs = req("GET", "/api/notifications?unread_only=true", token=admin)
    expect(any(n["type"] == "booking_new" for n in notifs), "secretaries not notified of public booking")

    # ---- audit chain must verify
    s, verify = req("POST", "/api/audit/verify", token=admin)
    expect(s == 200 and verify["ok"], f"audit chain broken: {verify}")

    if failures:
        print(f"\nFAILED: {len(failures)} step(s): {', '.join(failures)}")
        return FAIL
    print("\nAll smoke steps passed ✓")
    return PASS


if __name__ == "__main__":
    sys.exit(main())

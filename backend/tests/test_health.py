from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_health_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["env"] in ("dev", "test")


def test_root_message():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["message"] == "HMSv2 API is running"


def test_request_id_header_present():
    resp = client.get("/api/health")
    assert "X-Request-ID" in resp.headers

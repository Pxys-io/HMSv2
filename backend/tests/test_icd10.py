"""ICD-10 catalog tests (Plan/14 D1)."""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.icd10 import Icd10Code
from tests.test_financial import admin_headers


def _seed_codes():
    from app.data.icd10 import ICD10_SEED

    db = SessionLocal()
    for code, label_en, label_ar in ICD10_SEED[:20]:
        if db.scalar(select(Icd10Code).where(Icd10Code.code == code)) is None:
            db.add(Icd10Code(code=code, label_en=label_en, label_ar=label_ar))
    db.commit()
    db.close()


def test_icd10_search(client):
    _seed_codes()
    admin = admin_headers(client)
    resp = client.get("/api/icd10?q=diabet", headers=admin)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert any(i["code"] == "E11" for i in items)

    resp = client.get("/api/icd10?q=E11", headers=admin)
    assert resp.json()["items"][0]["label_en"] == "Type 2 diabetes"

    resp = client.get("/api/icd10?q=سكري", headers=admin)
    assert any(i["code"] in ("E10", "E11", "E14") for i in resp.json()["items"])


def test_icd10_requires_emr_write(client, clinic):
    token = clinic["token"]
    resp = client.get("/api/icd10?q=diabet", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200  # doctor has emr.write

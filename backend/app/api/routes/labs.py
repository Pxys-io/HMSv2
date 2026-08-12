"""Structured lab results endpoints (Plan/14 D2)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import DbDep, require_perm
from app.core.errors import AppError
from app.models.emr import Visit
from app.models.identity import PatientProfile, StaffUser
from app.models.labs import LabResult

router = APIRouter(prefix="/api", tags=["labs"])
writer = Annotated[StaffUser, Depends(require_perm("emr.write"))]
viewer = Annotated[StaffUser, Depends(require_perm("emr.view"))]


def _payload(r: LabResult) -> dict:
    return {
        "id": r.id, "visit_id": r.visit_id, "patient_profile_id": r.patient_profile_id,
        "name": r.name, "value": float(r.value), "unit": r.unit,
        "ref_min": float(r.ref_min) if r.ref_min is not None else None,
        "ref_max": float(r.ref_max) if r.ref_max is not None else None,
        "result_date": r.result_date.isoformat(),
    }


@router.post("/visits/{visit_id}/lab-results")
def add_lab_results(body: dict, visit_id: int, current: writer, db: DbDep):
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise AppError("NOT_FOUND", "visit not found")
    items = body.get("results") or []
    if not isinstance(items, list) or not items:
        raise AppError("VALIDATION", "results must be a non-empty list")
    created = []
    for item in items:
        name = str(item.get("name", "")).strip()
        if not name:
            raise AppError("VALIDATION", "each result needs a name")
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError) as exc:
            raise AppError("VALIDATION", f"{name}: value must be a number") from exc
        result = LabResult(
            visit_id=visit_id,
            patient_profile_id=visit.patient_profile_id,
            name=name,
            value=value,
            unit=item.get("unit"),
            ref_min=float(item["ref_min"]) if item.get("ref_min") is not None else None,
            ref_max=float(item["ref_max"]) if item.get("ref_max") is not None else None,
            result_date=date.fromisoformat(str(item.get("result_date", date.today().isoformat()))),
        )
        db.add(result)
        created.append(result)
    db.commit()
    return {"items": [_payload(r) for r in created]}


@router.get("/visits/{visit_id}/lab-results")
def list_visit_labs(visit_id: int, current: viewer, db: DbDep):
    rows = db.scalars(
        select(LabResult).where(LabResult.visit_id == visit_id).order_by(LabResult.id)
    ).all()
    return {"items": [_payload(r) for r in rows]}


@router.get("/patients/{profile_id}/growth")
def growth_report_route(
    profile_id: int, current: viewer, db: DbDep,
    metric: str = Query(default="weight", pattern="^(weight|height)$"),
):
    from app.services.growth import growth_report

    return growth_report(db, profile_id, metric)


@router.get("/patients/{profile_id}/lab-trends")
def lab_trends(
    profile_id: int, current: viewer, db: DbDep,
    name: str = Query(min_length=2),
    limit: int = Query(default=30, ge=2, le=200),
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    rows = db.scalars(
        select(LabResult)
        .where(LabResult.patient_profile_id == profile_id, LabResult.name == name)
        .order_by(LabResult.result_date.desc(), LabResult.id.desc())
        .limit(limit)
    ).all()
    series = list(reversed([_payload(r) for r in rows]))
    ref_min = next((r["ref_min"] for r in series if r["ref_min"] is not None), None)
    ref_max = next((r["ref_max"] for r in series if r["ref_max"] is not None), None)
    unit = next((r["unit"] for r in series if r["unit"]), None)
    return {
        "name": name,
        "unit": unit,
        "ref_min": ref_min,
        "ref_max": ref_max,
        "points": [
            {"date": r["result_date"], "value": r["value"], "visit_id": r["visit_id"]}
            for r in series
        ],
    }

"""WHO growth-curve service (Plan/14 D4).

Produces -2SD / median / +2SD reference curves by month (LMS interpolation
between anchor ages) plus the patient's own weight/height measurements taken
from visit vitals.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.data.who_growth import GROWTH
from app.models.emr import Visit
from app.models.identity import PatientProfile


def _interp(anchor: list[tuple[int, float, float, float]], month: int) -> dict:
    anchor = sorted(anchor)
    lo, hi = anchor[0], anchor[-1]
    for i in range(len(anchor) - 1):
        if anchor[i][0] <= month <= anchor[i + 1][0]:
            lo, hi = anchor[i], anchor[i + 1]
            break
    t = (month - lo[0]) / max(hi[0] - lo[0], 1)

    def lerp(a, b):
        return a + (b - a) * t

    return {"M": lerp(lo[1], hi[1]), "L": lerp(lo[2], hi[2]), "S": lerp(lo[3], hi[3])}


def _percentile(lms: dict, z: float) -> float:
    if abs(lms["L"]) < 1e-6:
        return lms["M"] * (1 + lms["S"] * z)
    return lms["M"] * (1 + lms["L"] * lms["S"] * z) ** (1 / lms["L"])


def growth_curves(sex: str, metric: str) -> dict:
    table = GROWTH.get(metric, {}).get(sex)
    if table is None:
        raise AppError("VALIDATION", "metric must be weight or height")
    ages = [m for m, *_ in table]
    return {
        "low": [round(_percentile(_interp(table, m), -2), 2) for m in ages],
        "median": [round(_percentile(_interp(table, m), 0), 2) for m in ages],
        "high": [round(_percentile(_interp(table, m), 2), 2) for m in ages],
        "ages": ages,
    }


def growth_report(db: Session, profile_id: int, metric: str) -> dict:
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    if metric not in ("weight", "height"):
        raise AppError("VALIDATION", "metric must be weight or height")
    sex = "boy" if profile.gender == "male" else "girl"
    visits = db.scalars(
        select(Visit).where(Visit.patient_profile_id == profile_id)
        .order_by(Visit.started_at)
    ).all()
    measurements = []
    for visit in visits:
        vitals = visit.vitals or {}
        value = vitals.get(metric)
        if not isinstance(value, int | float) or visit.started_at is None:
            continue
        measurements.append({
            "date": visit.started_at.date().isoformat(),
            "value": float(value),
            "visit_id": visit.id,
        })
    curves = growth_curves(sex, metric)
    # project the patient's age at each measurement against the curves
    for m in measurements:
        age_months = max(
            ((date.fromisoformat(m["date"]) - profile.birth_date).days / 30.44)
            if profile.birth_date else 0, 0
        )
        m["age_months"] = round(min(age_months, 60), 1)
    return {
        "metric": metric,
        "sex": sex,
        "unit": "kg" if metric == "weight" else "cm",
        "curves": curves,
        "measurements": measurements,
        "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
    }

"""ICD-10 search endpoint (Plan/14 D1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.core.deps import DbDep, require_perm
from app.models.icd10 import Icd10Code
from app.models.identity import StaffUser

router = APIRouter(prefix="/api/icd10", tags=["icd10"])
viewer = Annotated[StaffUser, Depends(require_perm("emr.write"))]


@router.get("")
def search_icd10(
    current: viewer, db: DbDep,
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
):
    needle = q.strip()
    like = f"%{needle}%"
    rows = db.scalars(
        select(Icd10Code).where(
            or_(
                Icd10Code.code.ilike(like),
                Icd10Code.label_en.ilike(like),
                Icd10Code.label_ar.ilike(like),
            )
        )
        .order_by(Icd10Code.code)
        .limit(limit)
    ).all()
    return {
        "items": [
            {"code": r.code, "label_en": r.label_en, "label_ar": r.label_ar}
            for r in rows
        ]
    }

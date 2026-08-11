"""Patient quick search (Plan/07 S1): code prefix, name substring, phone
substring. Ranked, access-audited, and clinical fields are never returned."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.billing import Syndicate
from app.models.identity import PatientProfile


def search_patients(db: Session, query: str, limit: int = 8) -> list[dict]:
    q = query.strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    rows = db.scalars(
        select(PatientProfile).where(
            PatientProfile.is_archived.is_(False),
            or_(
                PatientProfile.code.ilike(like),
                PatientProfile.full_name.ilike(like),
                PatientProfile.full_name_ar.ilike(like),
                PatientProfile.phone.ilike(like),
            ),
        ).order_by(PatientProfile.id)
    ).all()

    def rank(profile: PatientProfile) -> int:
        if profile.code.lower().startswith(q.lower()):
            return 0
        if q in profile.phone:
            return 1
        if profile.full_name.lower().startswith(q.lower()):
            return 2
        return 3

    rows.sort(key=rank)
    out = []
    for profile in rows[:limit]:
        syndicate_name = None
        if profile.syndicate_id:
            syndicate = db.get(Syndicate, profile.syndicate_id)
            syndicate_name = syndicate.name if syndicate else None
        from datetime import date

        age = (date.today() - profile.birth_date).days // 365 if profile.birth_date else None
        out.append(
            {
                "id": profile.id,
                "code": profile.code,
                "full_name": profile.full_name,
                "full_name_ar": profile.full_name_ar,
                "phone": profile.phone,
                "age": age,
                "gender": profile.gender,
                "no_show_count": profile.no_show_count,
                "syndicate_name": syndicate_name,
            }
        )
    return out

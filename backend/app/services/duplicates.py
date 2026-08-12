"""Duplicate detection + merge (Plan/14 C8)."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.activity import ActivityEvent
from app.models.billing import Invoice
from app.models.comms_log import CommunicationLogEntry
from app.models.duplicates import DuplicateGroup
from app.models.emr import Visit
from app.models.identity import PatientProfile
from app.models.ops import LabOrder, Referral
from app.models.queueing import QueueEntry
from app.models.scheduling import Appointment
from app.models.tags import patient_tag

REASSIGNABLE = (
    (Appointment, "patient_profile_id"),
    (QueueEntry, "patient_profile_id"),
    (Visit, "patient_profile_id"),
    (Invoice, "patient_profile_id"),
    (ActivityEvent, "patient_profile_id"),
    (CommunicationLogEntry, "patient_profile_id"),
    (Referral, "patient_profile_id"),
    (LabOrder, "patient_profile_id"),
)


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 8:
        return None
    return digits[-10:]


def refresh_detection(db: Session) -> int:
    """Group profiles sharing a phone (or name + birth date) into duplicate
    candidates. Idempotent: open groups are replaced each refresh."""
    rows = db.scalars(
        select(PatientProfile).where(PatientProfile.is_archived.is_(False))
    ).all()
    phones: dict[str, list[PatientProfile]] = {}
    identities: dict[tuple[str, str], list[PatientProfile]] = {}
    for p in rows:
        phone = _normalize_phone(p.phone)
        if phone:
            phones.setdefault(phone, []).append(p)
        if p.full_name and p.birth_date:
            key = (p.full_name.strip().lower(), p.birth_date.isoformat())
            identities.setdefault(key, []).append(p)

    candidates: dict[tuple[int, int], str] = {}
    for phone, members in phones.items():
        for a in members:
            for b in members:
                if a.id < b.id:
                    candidates[(a.id, b.id)] = f"phone:{phone}"
    for key, members in identities.items():
        for a in members:
            for b in members:
                if a.id < b.id and (a.id, b.id) not in candidates:
                    candidates[(a.id, b.id)] = f"name:{key[0]} birth:{key[1]}"

    db.execute(update(DuplicateGroup).where(DuplicateGroup.status == "open")
               .values(status="rejected", resolved_by=None))

    def _make_group(member_ids: list[int], reason: str) -> None:
        group = DuplicateGroup(
            primary_profile_id=member_ids[0],
            profile_ids=member_ids,
            match_reason=reason,
            status="open",
        )
        db.add(group)

    seen: set[int] = set()
    for (a, b), reason in sorted(candidates.items()):
        if a in seen or b in seen:
            continue
        seen.update({a, b})
        _make_group([a, b], reason)
    db.commit()
    return len(seen) // 2


def list_groups(db: Session, status: str = "open") -> list[dict]:
    rows = db.scalars(
        select(DuplicateGroup).where(DuplicateGroup.status == status)
        .order_by(DuplicateGroup.id)
    ).all()
    out = []
    for g in rows:
        profiles = [
            db.get(PatientProfile, pid) for pid in g.profile_ids
        ]
        out.append({
            "id": g.id,
            "primary_profile_id": g.primary_profile_id,
            "profile_ids": g.profile_ids,
            "match_reason": g.match_reason,
            "status": g.status,
            "profiles": [
                {"id": p.id, "code": p.code, "full_name": p.full_name,
                 "phone": p.phone, "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                 "is_archived": p.is_archived}
                for p in profiles if p is not None
            ],
        })
    return out


def merge_group(db: Session, group: DuplicateGroup, actor_id: int) -> None:
    """Merge all duplicates into the primary; the absorbed profiles are
    archived and activity is logged on both sides."""
    primary = db.get(PatientProfile, group.primary_profile_id)
    if primary is None or primary.is_archived:
        raise AppError("CONFLICT", "primary profile is archived or missing")
    others = [db.get(PatientProfile, pid) for pid in group.profile_ids
              if pid != group.primary_profile_id]
    for model, col in REASSIGNABLE:
        for other in others:
            if other is None:
                continue
            db.execute(
                update(model).where(getattr(model, col) == other.id)
                .values(**{col: primary.id})
            )
    db.execute(
        update(patient_tag).where(patient_tag.c.patient_profile_id.in_(
            [o.id for o in others if o is not None]
        )).values(patient_profile_id=primary.id)
    )
    group.status = "merged"
    group.resolved_by = actor_id
    for other in others:
        if other is None:
            continue
        other.is_archived = True
        from app.services.activity import log_activity

        log_activity(db, patient_profile_id=other.id, type="patient.merged",
                     actor_id=actor_id, actor_label="merge", merged_into=primary.id)
    from app.services.activity import log_activity

    log_activity(db, patient_profile_id=primary.id, type="patient.merged",
                 actor_id=actor_id, actor_label="merge", absorbed=[o.id for o in others if o])
    db.commit()

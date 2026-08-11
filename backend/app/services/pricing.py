"""Price resolution (Plan/06 M1).

Chain: syndicate contract (coverage + patient share) -> doctor override ->
clinic default -> visit_type.default_price. Per-hour doctors bill from the
completed visit's started_at/ended_at, rounded up to 15-minute units, with the
visit type price as a minimum charge when set.
"""

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.billing import PriceListItem, SyndicatePrice
from app.models.emr import Visit
from app.models.identity import Doctor
from app.models.scheduling import VisitType

QUARTER_HOUR = 15


@dataclass
class ResolvedPrice:
    price: float
    syndicate_coverage: float | None
    patient_share: float | None
    source: str


def resolve_for_visit(
    db: Session, visit: Visit, doctor: Doctor, visit_type: VisitType
) -> ResolvedPrice:
    """Resolves the price for a completed visit (M1 + per-hour logic)."""
    if doctor.billing_mode == "per_hour":
        if visit.started_at is None or visit.ended_at is None:
            raise AppError("CONFLICT", "per-hour billing needs visit timings")
        minutes = (visit.ended_at - visit.started_at).total_seconds() / 60
        units = max(1, math.ceil(minutes / QUARTER_HOUR))
        hours = units * (QUARTER_HOUR / 60)
        computed = hours * float(doctor.hourly_rate or 0)
        minimum = float(visit_type.default_price or 0)
        return ResolvedPrice(price=max(computed, minimum), syndicate_coverage=None,
                             patient_share=None, source="per_hour")

    from app.models.identity import PatientProfile

    if visit.patient_profile_id:
        profile = db.get(PatientProfile, visit.patient_profile_id)
        if profile is not None and profile.syndicate_id is not None:
            row = db.scalar(
                select(SyndicatePrice).where(
                    SyndicatePrice.syndicate_id == profile.syndicate_id,
                    SyndicatePrice.visit_type_id == visit_type.id,
                    (SyndicatePrice.doctor_id == doctor.id) | (SyndicatePrice.doctor_id.is_(None)),
                ).order_by(SyndicatePrice.doctor_id.is_(None))
            )
            if row is not None:
                return ResolvedPrice(
                    price=float(row.syndicate_coverage) + float(row.patient_share),
                    syndicate_coverage=float(row.syndicate_coverage),
                    patient_share=float(row.patient_share),
                    source="syndicate",
                )

    item = db.scalar(
        select(PriceListItem).where(
            PriceListItem.visit_type_id == visit_type.id,
            (PriceListItem.doctor_id == doctor.id) | (PriceListItem.doctor_id.is_(None)),
        ).order_by(PriceListItem.doctor_id.is_(None))
    )
    if item is not None:
        return ResolvedPrice(price=float(item.price), syndicate_coverage=None,
                             patient_share=None,
                             source="doctor" if item.doctor_id else "clinic_default")
    return ResolvedPrice(price=float(visit_type.default_price), syndicate_coverage=None,
                         patient_share=None, source="visit_type_default")

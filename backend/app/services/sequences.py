"""Human-readable code generation (Plan/02 §2.1 number_sequence).

Patient codes `P-000001`, booking refs `BK-XXXXXXXX`; invoice numbering
(`INV-YYYY-NNNNNN`) will use the same helper in Phase 06.
"""

import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import NumberSequence


def next_sequence(db: Session, scope: str, year: int | None = None) -> int:
    row = db.scalar(
        select(NumberSequence).where(
            NumberSequence.scope == scope, NumberSequence.year == year
        )
    )
    if row is None:
        row = NumberSequence(scope=scope, year=year, value=0)
        db.add(row)
        db.flush()
    row.value += 1
    db.flush()
    return row.value


def next_patient_code(db: Session) -> str:
    return f"P-{next_sequence(db, 'patient_code'):06d}"


_ALNUM = string.ascii_uppercase + string.digits


def next_booking_ref(db: Session) -> str:
    # Randomized, collision-retried: no per-year sequence needed for refs.
    for _ in range(5):
        ref = "BK-" + "".join(secrets.choice(_ALNUM) for _ in range(8))
        from app.models.scheduling import Appointment

        if db.scalar(select(Appointment).where(Appointment.booking_ref == ref)) is None:
            return ref
    raise RuntimeError("could not generate a unique booking ref")

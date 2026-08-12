"""Seed command: `python -m app.seed`.

Development: creates admin with a known password and a demo doctor.
Production: requires `INITIAL_ADMIN_PASSWORD` env var, or prints a one-time
random bootstrap password and marks the account for immediate change. Never
commit or document a production password.
"""

import os
import secrets
from datetime import time

from sqlalchemy import select

from app.core.security import hash_password
from app.data.icd10 import ICD10_SEED
from app.db.session import SessionLocal
from app.models.comms import PrintTemplate
from app.models.config import Setting
from app.models.emr import Medication
from app.models.identity import Doctor, NumberSequence, StaffUser
from app.models.scheduling import DoctorSchedule, VisitType
from app.services.print_templates import PRINT_TEMPLATES
from app.services.settings import DEFAULT_SETTINGS

SEED_MEDICATIONS = [
    ("Augmentin", "أوجمنتين", "tab", "1g"),
    ("Panadol Extra", "بنادول إكسترا", "tab", "500mg"),
    ("Cataflam", "كاتافلام", "tab", "50mg"),
    ("Flagyl", "فلاجيل", "tab", "500mg"),
    ("Nexium", "نيكسيوم", "cap", "40mg"),
    ("Zithromax", "زيثرون", "tab", "500mg"),
    ("Brufen", "بروفين", "tab", "400mg"),
    ("Ventolin", "فينتولين", "inh", "100mcg"),
    ("Insulin Mixtard", "أنسولين ميكستارد", "inj", "30"),
    ("Glucophage", "جلوكوفاج", "tab", "850mg"),
    ("Concor", "كونكور", "tab", "5mg"),
    ("Amaryl", "أماريل", "tab", "2mg"),
    ("Plavix", "بلافيكس", "tab", "75mg"),
    ("Aspirin", "أسبرين", "tab", "81mg"),
    ("Ciprocin", "سيبروسين", "tab", "500mg"),
    ("Vibramycin", "فيبراميسين", "cap", "100mg"),
    ("Histop", "هيستوب", "tab", "10mg"),
    ("Zyrtec", "زيرتك", "tab", "10mg"),
    ("Diclac", "ديكلاك", "gel", "75mg"),
    ("Voltaren", "فولتارين", "inj", "75mg"),
    ("Dexamethasone", "ديكساميثازون", "amp", "8mg"),
    ("Rocephin", "روسفين", "inj", "1g"),
    ("Flagyl gel", "فلاجيل جيل", "gel", "1%"),
    ("Canesten", "كانستين", "cream", "1%"),
    ("Fucidin", "فيوسيدين", "cream", "2%"),
    ("Betnovate", "بيتاموفيت", "cream", "0.1%"),
    ("E-Mox", "إي-موكس", "cap", "500mg"),
    ("Maalox Plus", "مالوكس بلس", "susp", "500mg"),
    ("Spasmocan", "سبازموكان", "tab", "20mg"),
    ("Cetal Drops", "سيتال نقط", "drops", "100mg/ml"),
]

DEMO_VISIT_TYPES = [
    {"name": "Consultation", "name_ar": "كشف", "category": "new_visit",
     "duration_minutes": 20, "default_price": 300, "color": "#0D9488"},
    {"name": "Follow-up", "name_ar": "متابعة", "category": "follow_up",
     "duration_minutes": 10, "default_price": 150, "color": "#2563EB"},
    {"name": "Procedure", "name_ar": "إجراء", "category": "procedure",
     "duration_minutes": 60, "default_price": 800, "color": "#D97706"},
]


def seed() -> None:
    db = SessionLocal()
    try:
        is_prod = os.environ.get("APP_ENV") == "prod"

        # --- settings
        for key, value in DEFAULT_SETTINGS.items():
            if db.scalar(select(Setting).where(Setting.key == key)) is None:
                db.add(Setting(key=key, value=value))

        # --- number sequences
        for scope, year in (("patient_code", None), ("invoice", None), ("booking", None)):
            if db.scalar(
                select(NumberSequence).where(
                    NumberSequence.scope == scope, NumberSequence.year == year
                )
            ) is None:
                db.add(NumberSequence(scope=scope, year=year, value=0))

        # --- admin
        if db.scalar(select(StaffUser).where(StaffUser.role == "admin")) is None:
            if is_prod:
                env_password = os.environ.get("INITIAL_ADMIN_PASSWORD")
                password = env_password or secrets.token_urlsafe(12)
                if not env_password:
                    print(f"BOOTSTRAP ADMIN PASSWORD: {password} (change immediately)")
                must_change = True
            else:
                password = "admin12345"
                must_change = False
            from app.services.roles import role_id as _rid

            db.add(
                StaffUser(
                    email="admin@example.com",
                    password_hash=hash_password(password),
                    full_name="System Admin",
                    role_id=_rid(db, "admin"),
                    is_active=True,
                    must_change_password=must_change,
                )
            )

        # --- demo doctor + visit types (development only)
        if not is_prod and db.scalar(select(Doctor)) is None:
            exists = db.scalar(
                select(StaffUser).where(StaffUser.email == "demo@example.com")
            )
            if exists is None:
                from app.services.roles import role_id as _rid

                demo_user = StaffUser(
                    email="demo@example.com",
                    password_hash=hash_password("demo12345"),
                    full_name="Demo Doctor",
                    full_name_ar="دكتور تجريبي",
                    role_id=_rid(db, "doctor"),
                    is_active=True,
                )
                db.add(demo_user)
                db.flush()
                doctor = Doctor(
                    staff_user_id=demo_user.id,
                    specialty="Internal Medicine",
                    title="Consultant",
                    booking_mode="slots",
                    default_slot_minutes=20,
                    buffer_minutes=0,
                    slot_capacity=1,
                    billing_mode="per_visit",
                    is_bookable_online=True,
                )
                db.add(doctor)
                db.flush()
                for weekday, start, end in (
                    (0, time(17, 0), time(21, 0)),
                    (2, time(17, 0), time(21, 0)),
                ):
                    db.add(
                        DoctorSchedule(
                            doctor_id=doctor.id,
                            weekday=weekday,
                            start_time=start,
                            end_time=end,
                        )
                    )
                for vt in DEMO_VISIT_TYPES:
                    db.add(VisitType(**vt))
                for name, name_ar, form, strength in SEED_MEDICATIONS:
                    db.add(
                        Medication(
                            name=name, name_ar=name_ar, form=form, strength=strength
                        )
                    )

        from app.models.icd10 import Icd10Code

        for code, label_en, label_ar in ICD10_SEED:
            if db.scalar(select(Icd10Code).where(Icd10Code.code == code)) is None:
                db.add(Icd10Code(code=code, label_en=label_en, label_ar=label_ar))

        for key, locales in PRINT_TEMPLATES.items():
            for locale, (title, body) in locales.items():
                exists = db.scalar(
                    select(PrintTemplate).where(
                        PrintTemplate.key == key, PrintTemplate.locale == locale
                    )
                )
                if exists is None:
                    db.add(
                        PrintTemplate(key=key, locale=locale, title=title, body_html=body)
                    )

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

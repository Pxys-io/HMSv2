"""EMR schemas (Plan/05)."""

from datetime import date

from pydantic import BaseModel, Field


class VisitCreate(BaseModel):
    queue_entry_id: int | None = None
    patient_profile_id: int | None = None
    visit_type_id: int | None = None


class VisitPatch(BaseModel):
    """Any subset of clinical fields; null clears a field. `record_version`
    is required so stale autosaves never silently overwrite (E3, D22)."""

    chief_complaint: str | None = None
    history: str | None = None
    vitals: dict | None = None
    clinical_exam: str | None = None
    findings: str | None = None
    labs: str | None = None
    imaging: str | None = None
    plan: str | None = None
    notes_next_visit: str | None = None
    notes_private: str | None = None
    follow_up_weeks: int | None = Field(default=None, ge=1, le=208)
    follow_up_due: date | None = None
    record_version: int = Field(ge=1)


class DiagnosisItem(BaseModel):
    kind: str = Field(pattern="^(differential|final)$")
    label: str = Field(min_length=1, max_length=300)
    icd10_code: str | None = Field(default=None, max_length=16)
    notes: str | None = Field(default=None, max_length=300)


class DiagnosisPut(BaseModel):
    items: list[DiagnosisItem]
    record_version: int = Field(ge=1)


class MedicationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    name_ar: str | None = None
    form: str = Field(min_length=1, max_length=60)
    strength: str = Field(min_length=1, max_length=60)
    default_dose: str | None = None
    default_frequency: str | None = None
    default_duration: str | None = None


class MedicationUpdate(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    form: str | None = None
    strength: str | None = None
    default_dose: str | None = None
    default_frequency: str | None = None
    default_duration: str | None = None
    is_active: bool | None = None


class PrescriptionItemIn(BaseModel):
    medication_id: int | None = None
    free_text: str | None = Field(default=None, max_length=300)
    dose: str = Field(min_length=1, max_length=120)
    frequency: str = Field(min_length=1, max_length=120)
    duration: str = Field(min_length=1, max_length=60)
    instructions: str | None = Field(default=None, max_length=300)
    quantity: str | None = Field(default=None, max_length=60)


class PrescriptionPut(BaseModel):
    notes: str | None = None
    items: list[PrescriptionItemIn] = Field(default_factory=list, max_length=50)
    record_version: int = Field(ge=1)

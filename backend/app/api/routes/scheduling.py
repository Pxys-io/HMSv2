"""Staff scheduling routes: visit types, doctor shifts, blocks, availability
(Plan/03 §3.1)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm, require_role
from app.core.errors import AppError
from app.models.identity import Doctor, StaffUser
from app.models.scheduling import DoctorSchedule, ScheduleBlock, VisitType
from app.schemas.scheduling import (
    BlockCreate,
    ScheduleCreate,
    ScheduleUpdate,
    VisitTypeCreate,
    VisitTypeUpdate,
)
from app.services.availability import day_availability

router = APIRouter(prefix="/api", tags=["scheduling"])
admin = Annotated[StaffUser, Depends(require_role("admin"))]
staff = Annotated[StaffUser, Depends(require_perm("appointment.view"))]
doctor_self = Annotated[StaffUser, Depends(require_role("admin", "doctor"))]


# ----------------------------------------------------------------- visit types


@router.get("/visit-types")
def list_visit_types(current: staff, db: DbDep):
    rows = db.scalars(select(VisitType).order_by(VisitType.id)).all()
    return [
        {
            "id": v.id, "name": v.name, "name_ar": v.name_ar, "category": v.category,
            "duration_minutes": v.duration_minutes,
            "default_price": float(v.default_price), "color": v.color, "is_active": v.is_active,
        }
        for v in rows
    ]


@router.post("/visit-types")
def create_visit_type(
    body: VisitTypeCreate, current: admin, request: Request, db: DbDep, audit_db: AuditDbDep
):
    vt = VisitType(**body.model_dump())
    db.add(vt)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="visit_type.create", correlation_id=get_request_id(request),
        entity_type="visit_type", entity_id=str(vt.id),
        after={"name": vt.name, "price": float(vt.default_price)},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": vt.id, "name": vt.name}


@router.patch("/visit-types/{visit_type_id}")
def update_visit_type(
    visit_type_id: int,
    body: VisitTypeUpdate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    vt = db.get(VisitType, visit_type_id)
    if vt is None:
        raise AppError("NOT_FOUND", "visit type not found")
    if not body.is_active and db.scalar(
        select(VisitType).where(VisitType.id == visit_type_id)
    ):
        pass  # deactivation allowed; deletion is forbidden (service-level)
    before = {"name": vt.name, "price": float(vt.default_price), "is_active": vt.is_active}
    for field in body.model_fields_set:
        setattr(vt, field, getattr(body, field))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="visit_type.update", correlation_id=get_request_id(request),
        entity_type="visit_type", entity_id=str(vt.id),
        before=before,
        after={"name": vt.name, "price": float(vt.default_price), "is_active": vt.is_active},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": vt.id, "name": vt.name}


# -------------------------------------------------------------- doctor shifts


@router.get("/doctors/{doctor_id}/schedules")
def list_schedules(doctor_id: int, current: staff, db: DbDep):
    if db.get(Doctor, doctor_id) is None:
        raise AppError("NOT_FOUND", "doctor not found")
    rows = db.scalars(
        select(DoctorSchedule).where(DoctorSchedule.doctor_id == doctor_id).order_by(
            DoctorSchedule.weekday, DoctorSchedule.start_time
        )
    ).all()
    return [
        {
            "id": s.id, "weekday": s.weekday,
            "start_time": s.start_time.strftime("%H:%M"), "end_time": s.end_time.strftime("%H:%M"),
            "effective_from": s.effective_from.isoformat() if s.effective_from else None,
            "effective_to": s.effective_to.isoformat() if s.effective_to else None,
            "is_active": s.is_active,
        }
        for s in rows
    ]


@router.post("/doctors/{doctor_id}/schedules")
def create_schedule(
    doctor_id: int,
    body: ScheduleCreate,
    current: doctor_self,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    _check_doctor_owner(current, doctor_id, db)
    if body.start_time >= body.end_time:
        raise AppError("VALIDATION", "start_time must be before end_time")
    sched = DoctorSchedule(doctor_id=doctor_id, **body.model_dump())
    db.add(sched)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="schedule.create", correlation_id=get_request_id(request),
        entity_type="doctor_schedule", entity_id=str(sched.id),
        after={"doctor_id": doctor_id, "weekday": body.weekday},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": sched.id}


@router.patch("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    current: doctor_self,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    sched = db.get(DoctorSchedule, schedule_id)
    if sched is None:
        raise AppError("NOT_FOUND", "schedule not found")
    _check_doctor_owner(current, sched.doctor_id, db)
    for field in body.model_fields_set:
        setattr(sched, field, getattr(body, field))
    if sched.start_time >= sched.end_time:
        raise AppError("VALIDATION", "start_time must be before end_time")
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="schedule.update", correlation_id=get_request_id(request),
        entity_type="doctor_schedule", entity_id=str(schedule_id),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": schedule_id}


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: int, current: doctor_self, request: Request, db: DbDep, audit_db: AuditDbDep
):
    sched = db.get(DoctorSchedule, schedule_id)
    if sched is None:
        raise AppError("NOT_FOUND", "schedule not found")
    _check_doctor_owner(current, sched.doctor_id, db)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="schedule.delete", correlation_id=get_request_id(request),
        entity_type="doctor_schedule", entity_id=str(schedule_id),
        ip=request.client.host if request.client else None,
    ):
        db.delete(sched)
        db.commit()


# -------------------------------------------------------------- schedule blocks


@router.get("/doctors/{doctor_id}/blocks")
def list_blocks(doctor_id: int, current: staff, db: DbDep):
    rows = db.scalars(
        select(ScheduleBlock)
        .where(ScheduleBlock.doctor_id == doctor_id)
        .order_by(ScheduleBlock.date_from)
    ).all()
    return [
        {
            "id": b.id,
            "date_from": b.date_from.isoformat(),
            "date_to": b.date_to.isoformat(),
            "reason": b.reason,
        }
        for b in rows
    ]


@router.post("/doctors/{doctor_id}/blocks")
def create_block(
    doctor_id: int,
    body: BlockCreate,
    current: doctor_self,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    _check_doctor_owner(current, doctor_id, db)
    if body.date_from > body.date_to:
        raise AppError("VALIDATION", "date_from must be <= date_to")
    block = ScheduleBlock(doctor_id=doctor_id, **body.model_dump())
    db.add(block)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="schedule_block.create", correlation_id=get_request_id(request),
        entity_type="schedule_block", entity_id=str(block.id),
        after={
            "doctor_id": doctor_id,
            "from": body.date_from.isoformat(),
            "to": body.date_to.isoformat(),
        },
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": block.id}


@router.delete("/blocks/{block_id}", status_code=204)
def delete_block(
    block_id: int, current: doctor_self, request: Request, db: DbDep, audit_db: AuditDbDep
):
    block = db.get(ScheduleBlock, block_id)
    if block is None:
        raise AppError("NOT_FOUND", "block not found")
    _check_doctor_owner(current, block.doctor_id, db)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="schedule_block.delete", correlation_id=get_request_id(request),
        entity_type="schedule_block", entity_id=str(block_id),
        ip=request.client.host if request.client else None,
    ):
        db.delete(block)
        db.commit()


# ---------------------------------------------------------------- availability


@router.get("/availability/{doctor_id}")
def availability(
    doctor_id: int,
    current: staff,
    db: DbDep,
    date: Annotated[date, Query(description="clinic-local date")],
    visit_type_id: Annotated[int, Query()],
):
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise AppError("NOT_FOUND", "doctor not found")
    vt = db.get(VisitType, visit_type_id)
    if vt is None:
        raise AppError("NOT_FOUND", "visit type not found")
    return day_availability(db, doctor, date, vt)


def _check_doctor_owner(current: StaffUser, doctor_id: int, db: DbDep) -> None:
    if current.role == "admin":
        return
    doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == current.id))
    if doctor is None or doctor.id != doctor_id:
        raise AppError("FORBIDDEN", "not your schedule")

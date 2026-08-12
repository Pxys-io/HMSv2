"""Roles & permissions API (Plan/14 A1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.core.permissions import PERMISSION_GROUPS
from app.models.identity import Permission, Role, RolePermission, StaffUser
from app.services.roles import role_payload

router = APIRouter(prefix="/api", tags=["roles"])
admin = Annotated[StaffUser, Depends(require_perm("admin.roles"))]


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    name_ar: str | None = None


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    name_ar: str | None = None
    is_active: bool | None = None


class RolePermissionsPut(BaseModel):
    permission_ids: list[int] = Field(max_length=200)


@router.get("/roles")
def list_roles(current: admin, db: DbDep):
    rows = db.scalars(select(Role).order_by(Role.is_system.desc(), Role.id)).all()
    return [role_payload(db, r) for r in rows]


@router.post("/roles")
def create_role(
    body: RoleCreate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if db.scalar(select(Role).where(Role.name == body.name)):
        raise AppError("CONFLICT", "role name already exists")
    role = Role(name=body.name, name_ar=body.name_ar, is_system=False, is_active=True)
    db.add(role)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="role.create", correlation_id=get_request_id(request),
        entity_type="role", entity_id=str(role.id),
        after={"name": role.name}, ip=request.client.host if request.client else None,
    ):
        db.commit()
    return role_payload(db, role)


@router.patch("/roles/{role_id}")
def update_role(
    role_id: int,
    body: RoleUpdate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    role = db.get(Role, role_id)
    if role is None:
        raise AppError("NOT_FOUND", "role not found")
    if role.is_system and body.name is not None and body.name != role.name:
        raise AppError("CONFLICT", "system role names are fixed")
    before = {"name": role.name, "is_active": role.is_active}
    if body.name is not None and not role.is_system:
        if db.scalar(select(Role).where(Role.name == body.name, Role.id != role.id)):
            raise AppError("CONFLICT", "role name already exists")
        role.name = body.name
    if body.name_ar is not None:
        role.name_ar = body.name_ar
    if body.is_active is not None:
        role.is_active = body.is_active
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="role.update", correlation_id=get_request_id(request),
        entity_type="role", entity_id=str(role_id),
        before=before, after={"name": role.name, "is_active": role.is_active},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return role_payload(db, role)


@router.get("/permissions")
def permission_catalog(current: admin, db: DbDep):
    return {
        "groups": [
            {
                "group": group,
                "permissions": [
                    {"id": p.id, "code": p.code, "label": p.label, "label_ar": p.label_ar}
                    for p in db.scalars(
                        select(Permission)
                        .where(Permission.group == group)
                        .order_by(Permission.code)
                    ).all()
                ],
            }
            for group in PERMISSION_GROUPS
        ]
    }


@router.get("/roles/{role_id}/permissions")
def get_role_permissions(role_id: int, current: admin, db: DbDep):
    role = db.get(Role, role_id)
    if role is None:
        raise AppError("NOT_FOUND", "role not found")
    ids = [rp.permission_id for rp in role.permissions]
    return {"role_id": role_id, "permission_ids": ids}


@router.put("/roles/{role_id}/permissions")
def replace_role_permissions(
    role_id: int,
    body: RolePermissionsPut,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    role = db.get(Role, role_id)
    if role is None:
        raise AppError("NOT_FOUND", "role not found")
    found = db.scalars(
        select(Permission.id).where(Permission.id.in_(body.permission_ids))
    ).all()
    if len(found) != len(set(body.permission_ids)):
        raise AppError("VALIDATION", "unknown permission id in the set")
    before = {"permission_ids": sorted(rp.permission_id for rp in role.permissions)}
    for rp in list(role.permissions):
        db.delete(rp)
    db.flush()
    for pid in body.permission_ids:
        db.add(RolePermission(role_id=role.id, permission_id=pid))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="role.permissions", correlation_id=get_request_id(request),
        entity_type="role", entity_id=str(role_id),
        before=before, after={"permission_ids": body.permission_ids},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return get_role_permissions(role_id, current, db)

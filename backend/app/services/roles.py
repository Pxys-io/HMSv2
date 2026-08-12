"""Role helpers (Plan/14 A1)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permissions import PERMISSION_GROUPS, PERMISSION_LABELS, SYSTEM_ROLE_MATRIX
from app.models.identity import Permission, Role, RolePermission


def resolve_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name, Role.is_active.is_(True)))
    if role is None:
        raise AppError("NOT_FOUND", f"role '{name}' not found")
    return role


def role_id(db: Session, name: str) -> int:
    return resolve_role(db, name).id


def seed_system_roles(db: Session) -> None:
    """Idempotent: creates the permission catalog and the 3 system roles with
    their default matrices. Used by seed and the test bootstrap."""
    from sqlalchemy import select as _select

    permission_ids: dict[str, int] = {}
    for code, (label, label_ar) in PERMISSION_LABELS.items():
        row = db.scalar(_select(Permission).where(Permission.code == code))
        if row is None:
            group = next(
                g for g, rows in PERMISSION_GROUPS.items() if any(r[0] == code for r in rows)
            )
            row = Permission(code=code, label=label, label_ar=label_ar, group=group)
            db.add(row)
            db.flush()
        permission_ids[code] = row.id
    for name, meta in SYSTEM_ROLE_MATRIX.items():
        role = db.scalar(_select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name, name_ar=meta["name_ar"], is_system=True, is_active=True)
            db.add(role)
            db.flush()
        existing = {
            rp.permission_id
            for rp in db.scalars(
                _select(RolePermission).where(RolePermission.role_id == role.id)
            ).all()
        }
        for code in meta["permissions"]:
            if permission_ids[code] not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission_ids[code]))
    db.commit()


def role_payload(db: Session, role: Role) -> dict:
    perms = sorted({rp.permission.code for rp in role.permissions})
    return {
        "id": role.id,
        "name": role.name,
        "name_ar": role.name_ar,
        "is_system": role.is_system,
        "is_active": role.is_active,
        "permissions": perms,
    }

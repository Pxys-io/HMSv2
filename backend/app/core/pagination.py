"""Pagination helpers shared by every list endpoint.

Contract: `{items, total, page, page_size}`.
"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def paginate(db: Session, stmt, page: int = 1, page_size: int = 20) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows: Sequence = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}

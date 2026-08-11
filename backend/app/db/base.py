"""Two declarative bases: main DB and audit DB.

These never share metadata. Alembic environments import only their own base so
the main and audit migrations stay fully independent.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class AuditBase(DeclarativeBase):
    pass

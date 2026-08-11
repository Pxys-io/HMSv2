"""Timezone helpers: SQLite returns naive datetimes; normalize comparisons."""

from datetime import UTC, datetime


def ensure_aware(dt: datetime) -> datetime:
    """Attach UTC to naive datetimes (SQLite) so comparisons stay valid."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


def format_utc(value: datetime) -> str:
    return normalize_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")

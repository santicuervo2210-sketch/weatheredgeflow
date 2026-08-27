from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    clean = value.replace("Z", "+00:00")
    try:
        return ensure_utc(datetime.fromisoformat(clean))
    except ValueError:
        return None


def local_day_bounds(day: datetime, timezone_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name)
    local = day.astimezone(tz)
    start = datetime.combine(local.date(), time.min, tzinfo=tz)
    end = datetime.combine(local.date(), time.max, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


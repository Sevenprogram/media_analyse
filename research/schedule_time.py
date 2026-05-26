from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


UTC8 = timezone(timedelta(hours=8))
_REFRESH_TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


def normalize_refresh_time_utc8(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _REFRESH_TIME_PATTERN.fullmatch(text)
    if not match:
        raise ValueError("refresh_time_utc8 must use HH:mm format")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("refresh_time_utc8 must be a valid UTC+8 time")
    return f"{hour:02d}:{minute:02d}"


def next_utc8_daily_run_at(refresh_time_utc8: str | None, *, now: datetime | None = None) -> datetime | None:
    normalized = normalize_refresh_time_utc8(refresh_time_utc8)
    if normalized is None:
        return None

    hour, minute = [int(part) for part in normalized.split(":", 1)]
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    local_now = now_utc.astimezone(UTC8)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)

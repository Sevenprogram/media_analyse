from datetime import datetime, timedelta, timezone
from typing import Any


def within_recent_days(timestamp_value: Any, days: int | None) -> bool:
    if days is None:
        return True
    timestamp = unix_seconds(timestamp_value)
    if timestamp is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    return datetime.fromtimestamp(timestamp, tz=timezone.utc) >= cutoff


def unix_seconds(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 10_000_000_000:
        number = number / 1000
    return int(number)


def xhs_filter_note_time(days: int | None) -> str:
    if days is None:
        return ""
    if days <= 1:
        return "一天内"
    if days <= 7:
        return "一周内"
    return "半年内"

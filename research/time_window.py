from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    @classmethod
    def from_dates(cls, start_date: date, end_date: date) -> "TimeWindow":
        return cls(
            start=datetime.combine(start_date, time.min, tzinfo=timezone.utc),
            end=datetime.combine(end_date, time.max, tzinfo=timezone.utc),
        )

    def contains(self, value: datetime | None) -> bool:
        if value is None:
            return False
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return self.start <= value <= self.end


def filter_by_time_window(
    records: list[dict[str, Any]], *, window: TimeWindow | None
) -> tuple[list[dict[str, Any]], int, int]:
    if window is None:
        return records, 0, 0

    accepted: list[dict[str, Any]] = []
    outside = 0
    missing = 0
    for record in records:
        publish_time = record.get("publish_time")
        if publish_time is None:
            missing += 1
            continue
        if window.contains(publish_time):
            accepted.append(record)
        else:
            outside += 1
    return accepted, outside, missing


def time_window_from_job(job: dict[str, Any] | None) -> TimeWindow | None:
    if not job:
        return None
    comment_policy = job.get("comment_policy") or {}
    if comment_policy.get("disable_time_window"):
        return None
    start_date = job.get("start_date")
    end_date = job.get("end_date")
    if start_date is None or end_date is None:
        return None
    return TimeWindow.from_dates(start_date, end_date)


def timestamp_bounds(window: TimeWindow | None) -> tuple[int, int] | None:
    if window is None:
        return None
    return int(window.start.timestamp()), int(window.end.timestamp())

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from media_platform.recent_search import unix_seconds

SORT_RELEVANCE = "relevance"
SORT_LATEST = "latest"
SORT_MOST_LIKED = "most_liked"
SORT_MOST_COMMENTED = "most_commented"
SORT_MOST_COLLECTED = "most_collected"

TIME_ALL = "all"
TIME_1D = "1d"
TIME_7D = "7d"
TIME_30D = "30d"
TIME_180D = "180d"

FILL_PREFER_FILL = "prefer_fill"

VALID_SORT_MODES = {
    SORT_RELEVANCE,
    SORT_LATEST,
    SORT_MOST_LIKED,
    SORT_MOST_COMMENTED,
    SORT_MOST_COLLECTED,
}
VALID_TIME_PRESETS = {TIME_ALL, TIME_1D, TIME_7D, TIME_30D, TIME_180D}

XHS_SORT_PARAMS = {
    SORT_RELEVANCE: "general",
    SORT_LATEST: "time_descending",
    SORT_MOST_LIKED: "popularity_descending",
    SORT_MOST_COMMENTED: "comment_descending",
    SORT_MOST_COLLECTED: "collect_descending",
}
XHS_TIME_PARAMS = {
    TIME_ALL: "\u4e0d\u9650",
    TIME_1D: "\u4e00\u5929\u5185",
    TIME_7D: "\u4e00\u5468\u5185",
    TIME_180D: "\u534a\u5e74\u5185",
}

DOUYIN_SORT_PARAMS = {
    SORT_RELEVANCE: "0",
    SORT_MOST_LIKED: "1",
    SORT_LATEST: "2",
}
DOUYIN_TIME_PARAMS = {
    TIME_ALL: "0",
    TIME_1D: "1",
    TIME_7D: "7",
    TIME_180D: "180",
}

_PRESET_DAYS = {
    TIME_1D: 1,
    TIME_7D: 7,
    TIME_30D: 30,
    TIME_180D: 180,
}


@dataclass(frozen=True)
class SearchControls:
    sort_mode: str = SORT_RELEVANCE
    time_preset: str = TIME_ALL
    time_start: datetime | None = None
    time_end: datetime | None = None
    fill_strategy: str = FILL_PREFER_FILL
    max_extra_pages: int = 5

    @property
    def has_exact_range(self) -> bool:
        return self.time_start is not None and self.time_end is not None


@dataclass(frozen=True)
class EffectiveSearchControls:
    platform: str
    requested_sort_mode: str
    effective_sort_mode: str
    time_preset: str
    time_start: datetime | None
    time_end: datetime | None
    fill_strategy: str
    max_extra_pages: int
    downgraded: bool = False

    @property
    def has_exact_range(self) -> bool:
        return self.time_start is not None and self.time_end is not None


@dataclass(frozen=True)
class TimeRangeClassification:
    within_requested_time_range: bool
    outside_requested_time_range: bool
    fill_reason: str


def search_controls_from_raw(
    *,
    sort_mode: str = SORT_RELEVANCE,
    time_preset: str = TIME_ALL,
    time_start: str | datetime | None = None,
    time_end: str | datetime | None = None,
    fill_strategy: str = FILL_PREFER_FILL,
    max_extra_pages: int = 5,
) -> SearchControls:
    raw_sort = str(sort_mode or SORT_RELEVANCE).strip()
    raw_preset = str(time_preset or TIME_ALL).strip()
    normalized_sort = raw_sort if raw_sort in VALID_SORT_MODES else SORT_RELEVANCE
    normalized_preset = raw_preset if raw_preset in VALID_TIME_PRESETS else TIME_ALL
    start = _parse_datetime(time_start)
    end = _parse_datetime(time_end)
    if (start is None) != (end is None):
        raise ValueError("time_start and time_end must be provided together")
    if start is not None and end is not None and start > end:
        raise ValueError("time_start must be before or equal to time_end")
    return SearchControls(
        sort_mode=normalized_sort,
        time_preset=normalized_preset,
        time_start=start,
        time_end=end,
        fill_strategy=FILL_PREFER_FILL if fill_strategy != FILL_PREFER_FILL else fill_strategy,
        max_extra_pages=max(1, int(max_extra_pages or 1)),
    )


def effective_search_controls(
    platform: str, controls: SearchControls
) -> EffectiveSearchControls:
    requested_sort = controls.sort_mode
    if platform == "xhs":
        effective_sort = SORT_LATEST if controls.has_exact_range else requested_sort
    elif platform == "dy":
        if controls.has_exact_range:
            effective_sort = SORT_LATEST
        elif requested_sort in DOUYIN_SORT_PARAMS:
            effective_sort = requested_sort
        else:
            effective_sort = SORT_RELEVANCE
    else:
        effective_sort = requested_sort
    return EffectiveSearchControls(
        platform=platform,
        requested_sort_mode=requested_sort,
        effective_sort_mode=effective_sort,
        time_preset=controls.time_preset,
        time_start=controls.time_start,
        time_end=controls.time_end,
        fill_strategy=controls.fill_strategy,
        max_extra_pages=controls.max_extra_pages,
        downgraded=effective_sort != requested_sort,
    )


def apply_native_search_params(
    platform: str,
    params: dict[str, Any],
    controls: EffectiveSearchControls,
) -> dict[str, Any]:
    next_params = dict(params)
    if platform == "xhs":
        next_params["sort_type"] = XHS_SORT_PARAMS.get(
            controls.effective_sort_mode, XHS_SORT_PARAMS[SORT_RELEVANCE]
        )
        next_params["filter_note_time"] = XHS_TIME_PARAMS.get(
            controls.time_preset, XHS_TIME_PARAMS[TIME_ALL]
        )
    elif platform == "dy":
        next_params["sort_type"] = DOUYIN_SORT_PARAMS.get(
            controls.effective_sort_mode, DOUYIN_SORT_PARAMS[SORT_RELEVANCE]
        )
        next_params["publish_time"] = DOUYIN_TIME_PARAMS.get(
            controls.time_preset, DOUYIN_TIME_PARAMS[TIME_ALL]
        )
    return next_params


def classify_time_range(
    timestamp_value: Any,
    controls: SearchControls | EffectiveSearchControls,
    *,
    now: datetime | None = None,
) -> TimeRangeClassification:
    bounds = _requested_time_bounds(controls, now=now)
    if bounds is None:
        return TimeRangeClassification(True, False, "exact_match")

    timestamp = unix_seconds(timestamp_value)
    if timestamp is None:
        return TimeRangeClassification(False, True, "fill_to_target")

    start, end = bounds
    published = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    within = start <= published <= end
    return TimeRangeClassification(
        within,
        not within,
        "exact_match" if within else "fill_to_target",
    )


def metadata_for_item(
    controls: EffectiveSearchControls, classification: TimeRangeClassification
) -> dict[str, Any]:
    return {
        "platform": controls.platform,
        "requested_sort_mode": controls.requested_sort_mode,
        "effective_sort_mode": controls.effective_sort_mode,
        "sort_mode_downgraded": controls.downgraded,
        "requested_time_preset": controls.time_preset,
        "requested_time_start": controls.time_start.isoformat() if controls.time_start else None,
        "requested_time_end": controls.time_end.isoformat() if controls.time_end else None,
        "fill_strategy": controls.fill_strategy,
        "within_requested_time_range": classification.within_requested_time_range,
        "outside_requested_time_range": classification.outside_requested_time_range,
        "fill_reason": classification.fill_reason,
    }


def _requested_time_bounds(
    controls: SearchControls | EffectiveSearchControls,
    *,
    now: datetime | None,
) -> tuple[datetime, datetime] | None:
    if controls.has_exact_range:
        return controls.time_start, controls.time_end  # type: ignore[return-value]
    days = _PRESET_DAYS.get(controls.time_preset)
    if days is None:
        return None
    end = _normalize_datetime(now or datetime.now(timezone.utc))
    return end - timedelta(days=days), end


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _normalize_datetime(parsed)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

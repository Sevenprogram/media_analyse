from __future__ import annotations

from datetime import datetime, timezone

import pytest

from media_platform.tikhub.search_controls import (
    SearchControls,
    apply_native_search_params,
    classify_time_range,
    effective_search_controls,
    search_controls_from_raw,
)


def test_xhs_latest_seven_day_mapping() -> None:
    controls = SearchControls(sort_mode="latest", time_preset="7d")
    effective = effective_search_controls("xhs", controls)
    params = apply_native_search_params("xhs", {"keyword": "cat food"}, effective)

    assert effective.effective_sort_mode == "latest"
    assert params["sort_type"] == "time_descending"
    assert params["filter_note_time"] == "\u4e00\u5468\u5185"


def test_xhs_thirty_day_uses_local_time_filtering() -> None:
    controls = SearchControls(sort_mode="latest", time_preset="30d")
    effective = effective_search_controls("xhs", controls)
    params = apply_native_search_params("xhs", {"keyword": "cat food"}, effective)

    assert params["sort_type"] == "time_descending"
    assert params["filter_note_time"] == "\u4e0d\u9650"


def test_douyin_latest_seven_day_mapping() -> None:
    controls = SearchControls(sort_mode="latest", time_preset="7d")
    effective = effective_search_controls("dy", controls)
    params = apply_native_search_params("dy", {"keyword": "cat food"}, effective)

    assert effective.effective_sort_mode == "latest"
    assert params["sort_type"] == "2"
    assert params["publish_time"] == "7"


def test_douyin_unsupported_sort_downgrades_to_relevance() -> None:
    controls = SearchControls(sort_mode="most_collected", time_preset="all")
    effective = effective_search_controls("dy", controls)
    params = apply_native_search_params("dy", {"keyword": "cat food"}, effective)

    assert effective.requested_sort_mode == "most_collected"
    assert effective.effective_sort_mode == "relevance"
    assert effective.downgraded is True
    assert params["sort_type"] == "0"


def test_exact_range_forces_latest_sort_for_xhs_and_douyin() -> None:
    controls = search_controls_from_raw(
        sort_mode="most_liked",
        time_preset="all",
        time_start="2026-05-01T00:00:00+00:00",
        time_end="2026-05-07T23:59:59+00:00",
    )

    xhs = effective_search_controls("xhs", controls)
    dy = effective_search_controls("dy", controls)

    assert xhs.requested_sort_mode == "most_liked"
    assert xhs.effective_sort_mode == "latest"
    assert dy.requested_sort_mode == "most_liked"
    assert dy.effective_sort_mode == "latest"


def test_exact_range_classification_marks_inside_and_outside() -> None:
    controls = search_controls_from_raw(
        sort_mode="latest",
        time_preset="all",
        time_start="2026-05-01T00:00:00+00:00",
        time_end="2026-05-07T23:59:59+00:00",
    )

    inside = classify_time_range(1_778_112_000, controls)
    outside = classify_time_range(1_779_000_000, controls)

    assert inside.within_requested_time_range is True
    assert inside.outside_requested_time_range is False
    assert inside.fill_reason == "exact_match"
    assert outside.within_requested_time_range is False
    assert outside.outside_requested_time_range is True
    assert outside.fill_reason == "fill_to_target"


def test_missing_exact_range_time_is_available_for_fill() -> None:
    controls = SearchControls(
        sort_mode="latest",
        time_preset="all",
        time_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        time_end=datetime(2026, 5, 7, 23, 59, 59, tzinfo=timezone.utc),
    )

    result = classify_time_range(None, controls)

    assert result.within_requested_time_range is False
    assert result.outside_requested_time_range is True
    assert result.fill_reason == "fill_to_target"


def test_relative_preset_classification_uses_local_window() -> None:
    controls = SearchControls(sort_mode="latest", time_preset="30d")
    now = datetime(2026, 5, 24, tzinfo=timezone.utc)

    inside = classify_time_range(1_778_112_000, controls, now=now)
    outside = classify_time_range(1_775_000_000, controls, now=now)

    assert inside.within_requested_time_range is True
    assert outside.outside_requested_time_range is True


def test_rejects_partial_or_reversed_exact_range() -> None:
    with pytest.raises(ValueError, match="provided together"):
        search_controls_from_raw(time_start="2026-05-01T00:00:00+00:00")
    with pytest.raises(ValueError, match="before or equal"):
        search_controls_from_raw(
            time_start="2026-05-08T00:00:00+00:00",
            time_end="2026-05-01T00:00:00+00:00",
        )

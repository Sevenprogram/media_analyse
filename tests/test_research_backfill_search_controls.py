from datetime import datetime, timezone

from research.backfill import (
    annotate_prefer_fill_records,
    candidate_query_limit,
    controls_from_job,
    job_has_search_controls,
    should_preserve_fill_candidates,
)
from research.normalizer import normalize_douyin_aweme, normalize_xhs_note


def test_annotate_prefer_fill_records_prefers_exact_then_fill() -> None:
    job = {
        "comment_policy": {
            "sort_mode": "latest",
            "time_preset": "all",
            "time_start": "2026-05-01T00:00:00+00:00",
            "time_end": "2026-05-07T23:59:59+00:00",
            "fill_strategy": "prefer_fill",
            "max_extra_pages": 3,
        }
    }
    controls = controls_from_job(job, "xhs")
    records = [
        {"id": "outside", "time": _ts(2026, 5, 17)},
        {"id": "inside", "time": _ts(2026, 5, 7)},
        {"id": "missing", "time": None},
    ]

    selected = annotate_prefer_fill_records(
        records,
        platform="xhs",
        controls=controls,
        timestamp_key="time",
        limit=2,
    )

    assert [item["id"] for item in selected] == ["inside", "outside"]
    assert selected[0]["crawl_meta"]["within_requested_time_range"] is True
    assert selected[0]["crawl_meta"]["fill_reason"] == "exact_match"
    assert selected[1]["crawl_meta"]["outside_requested_time_range"] is True
    assert selected[1]["crawl_meta"]["fill_reason"] == "fill_to_target"


def test_exact_prefer_fill_expands_candidate_limit_for_backfill() -> None:
    job = {
        "comment_policy": {
            "time_start": "2026-05-01T00:00:00+00:00",
            "time_end": "2026-05-07T23:59:59+00:00",
            "fill_strategy": "prefer_fill",
            "max_extra_pages": 4,
        }
    }
    controls = controls_from_job(job, "dy")

    assert job_has_search_controls(job) is True
    assert should_preserve_fill_candidates(job, controls) is True
    assert candidate_query_limit(25, controls) == 100


def test_normalizers_copy_crawl_meta_to_engagement_json() -> None:
    crawl_meta = {
        "requested_sort_mode": "latest",
        "effective_sort_mode": "latest",
        "requested_time_preset": "all",
        "requested_time_start": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "requested_time_end": "2026-05-07T23:59:59+00:00",
        "within_requested_time_range": False,
        "outside_requested_time_range": True,
        "fill_reason": "fill_to_target",
        "ignored": "not copied",
    }

    xhs = normalize_xhs_note(
        {
            "note_id": "n1",
            "user_id": "u1",
            "title": "title",
            "desc": "desc",
            "time": _ts(2026, 5, 17),
            "crawl_meta": crawl_meta,
        },
        job_id=1,
        salt="salt",
    )
    dy = normalize_douyin_aweme(
        {
            "aweme_id": 123,
            "user_id": "u1",
            "title": "title",
            "desc": "desc",
            "create_time": _ts(2026, 5, 17),
            "crawl_meta": crawl_meta,
        },
        job_id=1,
        salt="salt",
    )

    assert xhs["engagement_json"]["requested_time_start"] == "2026-05-01T00:00:00+00:00"
    assert xhs["engagement_json"]["outside_requested_time_range"] is True
    assert xhs["engagement_json"]["fill_reason"] == "fill_to_target"
    assert "ignored" not in xhs["engagement_json"]
    assert dy["engagement_json"]["requested_sort_mode"] == "latest"
    assert dy["engagement_json"]["outside_requested_time_range"] is True


def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())

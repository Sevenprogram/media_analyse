from __future__ import annotations

from api.routers.research import _enrich_progress_events, _unit_counts_with_event_outcomes
from research.enums import CRAWL_UNIT_FAILED, CRAWL_UNIT_PENDING, CRAWL_UNIT_SUCCEEDED


def test_unit_counts_use_platform_outcomes_for_direct_execution() -> None:
    units = [
        {"id": 1, "platform": "xhs", "status": CRAWL_UNIT_PENDING},
        {"id": 2, "platform": "xhs", "status": CRAWL_UNIT_PENDING},
        {"id": 3, "platform": "dy", "status": CRAWL_UNIT_PENDING},
        {"id": 4, "platform": "dy", "status": CRAWL_UNIT_PENDING},
    ]
    events = [
        {
            "id": 11,
            "created_at": "2026-05-24 13:40:06",
            "platform": None,
            "event_type": "execution_completed_with_platform_failures",
            "stats_json": {
                "succeeded_platforms": ["dy"],
                "failed_platforms": [{"platform": "xhs", "message": "Crawler exited"}],
            },
        },
    ]

    counts = _unit_counts_with_event_outcomes(units, events)

    assert counts["total"] == 4
    assert counts[CRAWL_UNIT_SUCCEEDED] == 2
    assert counts[CRAWL_UNIT_FAILED] == 2
    assert counts[CRAWL_UNIT_PENDING] == 0


def test_progress_events_add_error_summary_for_legacy_platform_failure_event() -> None:
    events = [
        {
            "id": 11,
            "created_at": "2026-05-24 13:40:06",
            "platform": None,
            "event_type": "execution_completed_with_platform_failures",
            "message": "Research job completed with platform failures",
            "stats_json": {
                "succeeded_platforms": ["dy"],
                "failed_platforms": [{"platform": "xhs", "message": "Crawler exited"}],
            },
        }
    ]

    enriched = _enrich_progress_events(events)

    assert enriched[0]["stats_json"]["error"] == "xhs: Crawler exited"
    assert "error" not in events[0]["stats_json"]

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lead_attribution import (
    compute_attribution_rows,
    normalize_attribution_config,
)


def test_normalize_attribution_config_applies_defaults() -> None:
    config = normalize_attribution_config({})
    assert config["default_model"] == "last_touch"
    assert config["window_days"] == 7
    assert config["enabled_dimensions"] == ["platform", "keyword", "content", "creator"]
    assert config["dedupe_by"] == "external_lead_id"


def test_first_touch_assigns_full_credit_to_earliest_touch() -> None:
    rows = compute_attribution_rows(
        model="first_touch",
        conversion_event={
            "id": 7,
            "event_time": datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc),
        },
        touchpoints=[
            {
                "id": 1,
                "platform": "xhs",
                "source_keyword": "猫粮",
                "post_id": 101,
                "touch_time": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
                "touch_type": "content_click",
            },
            {
                "id": 2,
                "platform": "dy",
                "source_keyword": "幼猫粮",
                "post_id": 102,
                "touch_time": datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
                "touch_type": "content_click",
            },
        ],
        window_days=7,
        enabled_dimensions=["platform", "keyword", "content"],
    )
    platform_rows = [row for row in rows if row["dimension"] == "platform"]
    assert platform_rows == [
        {
            "dimension": "platform",
            "dimension_key": "xhs",
            "credit": 1.0,
            "meta_json": {"touchpoint_id": 1, "touch_type": "content_click"},
        }
    ]


def test_linear_assigns_split_credit() -> None:
    rows = compute_attribution_rows(
        model="linear",
        conversion_event={
            "id": 9,
            "event_time": datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc),
        },
        touchpoints=[
            {
                "id": 1,
                "platform": "xhs",
                "source_keyword": "猫粮",
                "post_id": 101,
                "touch_time": datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
                "touch_type": "content_click",
            },
            {
                "id": 2,
                "platform": "dy",
                "source_keyword": "幼猫粮",
                "post_id": 102,
                "touch_time": datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
                "touch_type": "content_click",
            },
        ],
        window_days=7,
        enabled_dimensions=["platform", "keyword", "content"],
    )
    platform_rows = [row for row in rows if row["dimension"] == "platform"]
    assert len(platform_rows) == 2
    assert sum(row["credit"] for row in platform_rows) == 1.0

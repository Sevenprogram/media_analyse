from research.creator_search import _apply_realtime_result_quota


def test_apply_realtime_result_quota_targets_requested_final_ratio() -> None:
    results = [
        _item("rt-1", "realtime"),
        _item("rt-2", "realtime"),
        _item("rt-3", "realtime"),
        _item("db-1", "local"),
        _item("db-2", "local"),
        _item("db-3", "local"),
    ]

    selected = _apply_realtime_result_quota(
        results,
        {"include_realtime": True, "realtime_ratio": 50, "limit": 4},
        {"enabled": True},
        4,
    )

    assert [item["creator_id"] for item in selected] == ["rt-1", "rt-2", "db-1", "db-2"]


def test_apply_realtime_result_quota_backfills_with_realtime_when_local_is_short() -> None:
    results = [
        _item("rt-1", "realtime"),
        _item("rt-2", "realtime"),
        _item("rt-3", "realtime"),
        _item("rt-4", "realtime"),
        _item("db-1", "local"),
    ]

    selected = _apply_realtime_result_quota(
        results,
        {"include_realtime": True, "realtime_ratio": 50, "limit": 4},
        {"enabled": True},
        4,
    )

    assert len(selected) == 4
    assert sum(1 for item in selected if item["source_type"] == "realtime") == 3
    assert any(item["creator_id"] == "db-1" for item in selected)


def _item(creator_id: str, source_type: str) -> dict:
    labels = ["Realtime"] if source_type == "realtime" else ["Database"]
    return {
        "platform": "xhs",
        "creator_id": creator_id,
        "display_name": creator_id,
        "match_score": 80,
        "source_type": source_type,
        "source_labels": labels,
    }

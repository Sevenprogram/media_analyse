import pytest
from pydantic import ValidationError

from research.schemas import (
    ContentTrackerCreate,
    MonitorPoolCreate,
    ScenePackCreate,
    ScenePackKeywordCreate,
)


def test_scene_pack_keyword_type_validation():
    item = ScenePackKeywordCreate(
        scene_pack_id=1,
        keyword="K12 education",
        keyword_type="secondary",
        platform="xhs",
        weight=1.2,
        usage_flags=["creator_discovery", "keyword_heat"],
    )

    assert item.keyword == "K12 education"
    assert item.keyword_type == "secondary"


def test_scene_pack_keyword_rejects_bad_type():
    with pytest.raises(ValidationError):
        ScenePackKeywordCreate(
            scene_pack_id=1,
            keyword="ads",
            keyword_type="bad",
        )


def test_monitor_pool_defaults_to_twelve_hours():
    pool = MonitorPoolCreate(name="K12 creator pool")

    assert pool.schedule_interval_minutes == 720
    assert pool.comment_policy == {
        "enable_comments": True,
        "enable_sub_comments": False,
    }


def test_content_tracker_requires_keywords_or_seed_refs():
    with pytest.raises(ValidationError):
        ContentTrackerCreate(name="empty", platforms=["xhs"])


def test_repository_exposes_growth_methods():
    from research.repository import ResearchRepository

    repository = ResearchRepository()

    assert hasattr(repository, "create_scene_pack")
    assert hasattr(repository, "list_scene_packs")
    assert hasattr(repository, "create_monitor_pool")
    assert hasattr(repository, "create_content_tracker")
    assert hasattr(repository, "upsert_keyword_heat_snapshot")

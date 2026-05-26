from datetime import datetime

from research.competitors import build_competitor_composition, build_competitor_composition_snapshot


def test_build_competitor_composition_falls_back_to_keyword_extraction() -> None:
    composition = build_competitor_composition(
        posts=[
            {
                "platform": "xhs",
                "title": "K12 家长必看 数学思维规划",
                "content": "K12 家长都在关注数学思维和学习规划",
                "publish_time": datetime(2026, 5, 24, 9, 30),
                "engagement_json": {},
            }
        ],
        entity_tags=[],
        keywords=[],
    )

    assert composition["keyword_distribution"]
    assert any(key in composition["keyword_distribution"] for key in ("K12", "家长", "数学", "思维"))


def test_build_competitor_composition_infers_content_type_from_platform() -> None:
    composition = build_competitor_composition(
        posts=[
            {
                "platform": "xhs",
                "title": "图文帖子",
                "content": "这是一条小红书图文",
                "publish_time": datetime(2026, 5, 24, 9, 30),
                "engagement_json": {},
            },
            {
                "platform": "dy",
                "title": "短视频帖子",
                "content": "这是一条抖音短视频",
                "publish_time": datetime(2026, 5, 24, 20, 10),
                "engagement_json": {},
            },
        ],
        entity_tags=[],
        keywords=["帖子"],
    )

    assert composition["content_type_distribution"]["note"] == 1
    assert composition["content_type_distribution"]["video"] == 1


def test_build_competitor_composition_snapshot_preserves_top_post_engagement() -> None:
    snapshot = build_competitor_composition_snapshot(
        competitor_account_id=1,
        snapshot_date=datetime(2026, 5, 24).date(),
        platform="xhs",
        posts=[
            {
                "platform": "xhs",
                "platform_post_id": "note-1",
                "title": "High engagement note",
                "content": "sample",
                "url": "https://example.com/note-1",
                "publish_time": datetime(2026, 5, 24, 9, 30),
                "engagement_json": {
                    "liked_count": "21",
                    "comment_count": "5",
                    "collected_count": "4",
                    "share_count": "2",
                },
            }
        ],
        entity_tags=[],
        keywords=[],
    )

    top_post = snapshot["evidence"]["top_posts"][0]
    assert top_post["engagement"]["liked_count"] == "21"
    assert top_post["engagement"]["comment_count"] == "5"
    assert top_post["engagement"]["collected_count"] == "4"
    assert top_post["engagement_total"] == 32

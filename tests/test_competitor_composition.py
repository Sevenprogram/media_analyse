from datetime import datetime

from research.competitors import build_competitor_composition


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

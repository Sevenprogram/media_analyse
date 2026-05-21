from datetime import datetime

from research.competitors import (
    build_competitor_composition,
    build_competitor_composition_snapshot,
)


def test_competitor_composition_splits_keywords_tags_types_and_time():
    snapshot = build_competitor_composition_snapshot(
        competitor_account_id=1,
        snapshot_date=datetime(2026, 5, 20).date(),
        platform="xhs",
        posts=[
            {
                "platform_post_id": "p1",
                "title": "K12 tutoring",
                "content": "single parent mothers",
                "content_type": "video",
                "publish_time": datetime(2026, 5, 20, 9),
                "engagement_json": {"liked_count": 200},
            }
        ],
        entity_tags=[{"tag_id": 2}],
        keywords=["K12", "single parent mothers"],
    )

    assert snapshot["keyword_distribution"]["K12"] == 1
    assert snapshot["tag_distribution"]["2"] == 1
    assert snapshot["content_type_distribution"]["video"] == 1
    assert snapshot["publish_time_distribution"]["morning"] == 1
    assert snapshot["interaction_structure"]["like"] == 200
    assert snapshot["evidence"]["top_posts"][0]["platform_post_id"] == "p1"


def test_competitor_composition_outputs_structured_flow_breakdown():
    composition = build_competitor_composition(
        posts=[
            {
                "platform_post_id": "p1",
                "title": "K12 education for single moms",
                "content": "math planning",
                "content_type": "note",
                "publish_time": datetime(2026, 5, 20, 21),
                "engagement_json": {
                    "liked_count": 60,
                    "comment_count": 30,
                    "share_count": 10,
                    "collected_count": 20,
                },
            },
            {
                "platform_post_id": "p2",
                "title": "K12 education",
                "content": "low engagement",
                "content_type": "video",
                "publish_time": datetime(2026, 5, 20, 14),
                "engagement_json": {"liked_count": 1},
            },
        ],
        entity_tags=[{"tag_id": "k12"}, {"tag_id": "single_mom"}],
        keywords=["K12 education", "single moms"],
        hot_threshold=100,
    )

    assert composition["new_post_count"] == 2
    assert composition["keyword_distribution"]["K12 education"] == 2
    assert composition["content_type_distribution"]["note"] == 1
    assert composition["publish_time_distribution"]["night"] == 1
    assert composition["publish_time_distribution"]["afternoon"] == 1
    assert composition["hot_post_rate"] == 0.5
    assert composition["interaction_structure"]["comment"] == 30

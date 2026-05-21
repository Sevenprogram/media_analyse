from research.content_tracking import (
    build_tracker_analysis,
    extract_content_keywords,
    search_similar_content,
)


def test_extract_content_keywords_uses_scene_pack_primary_and_secondary_terms():
    result = extract_content_keywords(
        text="single parent mothers share K12 education tutoring experience",
        scene_keywords=[
            {
                "keyword": "K12 education",
                "keyword_type": "primary",
                "scene_pack_id": 1,
                "weight": 1,
            },
            {
                "keyword": "single parent mothers",
                "keyword_type": "secondary",
                "scene_pack_id": 1,
                "weight": 1,
            },
        ],
    )

    assert [item["keyword"] for item in result] == [
        "K12 education",
        "single parent mothers",
    ]
    assert result[0]["keyword_type"] == "primary"


def test_search_similar_content_scores_keyword_overlap():
    posts = [
        {
            "platform": "xhs",
            "platform_post_id": "p1",
            "title": "K12 education tutoring",
            "content": "single parent mothers experience",
            "engagement_json": {"liked_count": 20},
        },
        {
            "platform": "xhs",
            "platform_post_id": "p2",
            "title": "beauty review",
            "content": "lipstick test",
            "engagement_json": {"liked_count": 50},
        },
    ]

    result = search_similar_content(
        keywords=["K12 education", "single parent mothers"],
        posts=posts,
        limit=10,
    )

    assert result[0]["platform_post_id"] == "p1"
    assert result[0]["similarity_score"] > 50


def test_search_similar_content_matches_source_keyword_from_engagement():
    posts = [
        {
            "platform": "xhs",
            "platform_post_id": "p1",
            "title": "英语启蒙经验",
            "content": "陪读妈妈分享笔记",
            "engagement_json": {"liked_count": 20, "source_keyword": "单亲妈妈陪读"},
        }
    ]

    result = search_similar_content(
        keywords=["单亲妈妈"],
        posts=posts,
        limit=10,
    )

    assert result[0]["platform_post_id"] == "p1"
    assert result[0]["matched_keywords"][0]["term"] == "单亲妈妈"


def test_build_tracker_analysis_aggregates_candidates():
    analysis = build_tracker_analysis(
        tracker={"id": 1},
        candidates=[
            {
                "platform": "xhs",
                "matched_keywords": [{"term": "K12", "count": 2}],
                "evidence": {"source": "local"},
            }
        ],
    )

    assert analysis["summary"]["total_candidates"] == 1
    assert analysis["summary"]["top_keywords"][0]["name"] == "K12"

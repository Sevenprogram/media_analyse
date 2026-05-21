from datetime import datetime, timedelta, timezone

from research.keyword_heat import aggregate_keyword_heat_from_posts, calculate_keyword_heat_signal


def test_keyword_heat_returns_label_scores_and_evidence():
    signal = calculate_keyword_heat_signal(
        keyword="K12 education",
        current_24h={
            "content_count": 30,
            "engagement_total": 900,
            "hot_post_count": 6,
            "creator_count": 12,
        },
        avg_7d={
            "content_count": 10,
            "engagement_total": 200,
            "hot_post_count": 1,
            "creator_count": 5,
        },
        avg_30d={
            "content_count": 8,
            "engagement_total": 150,
            "hot_post_count": 1,
            "creator_count": 4,
        },
    )

    assert signal["label"] == "boosting"
    assert signal["heat_score"] > 70
    assert signal["push_score"] > signal["cooldown_risk"]
    assert signal["confidence"] == "medium"
    assert signal["sample_quality"]["content_7d"] == 70
    assert signal["evidence"]


def test_keyword_heat_confidence_uses_7d_sample_quality():
    now = datetime(2026, 5, 20, 12, tzinfo=timezone.utc)
    posts = []
    for index in range(120):
        posts.append(
            {
                "title": "K12 education planning",
                "content": "parent demand and education trend",
                "platform": "xhs" if index % 2 else "dy",
                "publish_time": now - timedelta(hours=index % 80),
                "author_hash": f"author-{index % 40}",
                "engagement_json": {"like_count": 10, "comment_count": 2},
            }
        )

    signal = aggregate_keyword_heat_from_posts(
        keyword="K12 education",
        posts=posts,
        now=now,
    )

    assert signal["confidence"] == "high"
    assert signal["sample_quality"]["content_7d"] == 120
    assert signal["sample_quality"]["creator_7d"] == 40
    assert signal["sample_quality"]["platform_count"] == 2


def test_keyword_heat_matches_source_keyword_for_backfilled_posts():
    now = datetime(2026, 5, 20, 12, tzinfo=timezone.utc)
    posts = [
        {
            "title": "",
            "content": "",
            "platform": "xhs",
            "publish_time": now,
            "author_hash": "author-1",
            "engagement_json": {"source_keyword": "K12 education"},
        }
    ]

    signal = aggregate_keyword_heat_from_posts(
        keyword="K12 education",
        posts=posts,
        now=now,
    )

    assert signal["sample_quality"]["content_7d"] == 1

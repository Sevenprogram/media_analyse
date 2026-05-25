from research.creator_metrics import (
    avg_engagement_rate_from_posts,
    hot_post_rate_from_posts,
)
from research.creator_search import _merge_profile_seed


def test_avg_engagement_rate_from_posts_uses_sample_average() -> None:
    posts = [
        {"engagement_json": {"liked_count": 120, "comment_count": 30}},
        {"engagement_json": {"liked_count": 40, "share_count": 10}},
    ]

    rate = avg_engagement_rate_from_posts(posts, follower_count=1000)

    assert rate == 0.1


def test_hot_post_rate_from_posts_uses_dynamic_threshold() -> None:
    posts = [
        {"engagement_json": {"liked_count": 50}},
        {"engagement_json": {"liked_count": 200}},
        {"engagement_json": {"liked_count": 500}},
    ]

    rate = hot_post_rate_from_posts(posts)

    assert rate == 0.333333


def test_hot_post_rate_from_posts_supports_realtime_engagement_field() -> None:
    posts = [
        {"engagement": {"liked_count": 60}},
        {"engagement": {"liked_count": 160}},
        {"engagement": {"liked_count": 500}},
    ]

    rate = hot_post_rate_from_posts(posts, engagement_fields=("engagement",))

    assert rate == 0.333333


def test_merge_profile_seed_preserves_existing_non_empty_fields() -> None:
    merged = _merge_profile_seed(
        {
            "display_name": "已有昵称",
            "profile_url": "https://example.com/profile",
            "follower_count": 12345,
        },
        {
            "display_name": "新昵称",
            "profile_url": "",
            "follower_count": None,
            "recent_post_count_30d": 7,
        },
    )

    assert merged["display_name"] == "新昵称"
    assert merged["profile_url"] == "https://example.com/profile"
    assert merged["follower_count"] == 12345
    assert merged["recent_post_count_30d"] == 7

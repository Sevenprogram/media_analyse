from research.competitor_recommendations import recommend_suspected_competitors


def test_recommend_suspected_competitors_scores_commercial_a_tier_candidates():
    recommendations = recommend_suspected_competitors(
        candidates=[
            {
                "platform": "xhs",
                "creator_id": "u1",
                "display_name": "K12课程官方",
                "match_score": 82,
                "matched_tags": [{"tag": "K12"}],
                "recent_post_count_30d": 12,
                "follower_count": 20000,
                "evidence": {
                    "primary_hits": ["K12"],
                    "representative_posts": [
                        {"title": "K12体验课报名"},
                        {"title": "单亲妈妈课程咨询"},
                    ],
                },
            },
            {
                "platform": "xhs",
                "creator_id": "u2",
                "display_name": "ordinary parent",
                "match_score": 40,
                "matched_tags": [],
                "evidence": {},
            },
        ],
        existing_competitors=[],
    )

    assert len(recommendations) == 1
    assert recommendations[0]["creator_id"] == "u1"
    assert recommendations[0]["recommendation_score"] >= 65
    assert "create_payload" in recommendations[0]


def test_recommend_suspected_competitors_excludes_existing_competitors():
    recommendations = recommend_suspected_competitors(
        candidates=[
            {
                "platform": "xhs",
                "creator_id": "u1",
                "display_name": "K12课程官方",
                "match_score": 90,
                "matched_tags": [{"tag": "K12"}],
                "evidence": {"primary_hits": ["K12"], "representative_posts": [{"title": "体验课报名"}]},
            }
        ],
        existing_competitors=[{"platform": "xhs", "creator_id": "u1"}],
    )

    assert recommendations == []

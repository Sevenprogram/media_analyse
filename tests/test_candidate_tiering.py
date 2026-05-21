from research.candidate_tiering import tier_creator_candidate, tier_creator_candidates


def test_tier_creator_candidate_marks_a_tier_when_score_and_evidence_are_strong():
    result = tier_creator_candidate(
        {
            "platform": "xhs",
            "creator_id": "u1",
            "match_score": 82,
            "matched_tags": [{"tag_id": 1}],
            "recent_post_count_30d": 8,
            "evidence": {"representative_posts": [{"id": "p1"}]},
        }
    )

    assert result["tier"] == "A"
    assert result["auto_pool_eligible"] is True
    assert "建议自动监控" in result["tier_reason"]


def test_tier_creator_candidate_blocks_negative_flags():
    result = tier_creator_candidate(
        {
            "platform": "xhs",
            "creator_id": "u1",
            "match_score": 95,
            "matched_tags": [{"tag_id": 1}],
            "evidence": {
                "representative_posts": [{"id": "p1"}],
                "negative_hits": [{"keyword": "情感八卦"}],
            },
        }
    )

    assert result["tier"] == "C"
    assert result["auto_pool_eligible"] is False
    assert result["negative_flags"] == ["negative_keyword:情感八卦"]


def test_tier_creator_candidates_embeds_tiering_evidence():
    result = tier_creator_candidates(
        [
            {"platform": "xhs", "creator_id": "a", "match_score": 76, "matched_tags": [{"tag_id": 1}], "evidence": {"representative_posts": [{}]}},
            {"platform": "xhs", "creator_id": "b", "match_score": 55, "evidence": {}},
        ]
    )

    assert result[0]["evidence"]["tiering"]["tier"] == "A"
    assert result[1]["evidence"]["tiering"]["tier"] == "C"


def test_tier_creator_candidates_accepts_list_evidence_from_search_results():
    result = tier_creator_candidates(
        [
            {
                "platform": "xhs",
                "creator_id": "a",
                "match_score": 76,
                "matched_tags": [{"tag_id": 1}],
                "evidence": [{"platform_post_id": "p1"}],
            }
        ]
    )

    assert result[0]["tier"] == "A"
    assert result[0]["evidence"]["evidence"] == [{"platform_post_id": "p1"}]
    assert result[0]["evidence"]["tiering"]["tier"] == "A"

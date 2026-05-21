from research.competitors import calculate_keyword_opportunities


def test_keyword_opportunities_include_explainable_scores():
    result = calculate_keyword_opportunities(
        vertical_id=1,
        platform="xhs",
        tag_definitions=[{"id": 1, "tag_name": "K12", "vertical_id": 1}],
        entity_tags=[{"tag_id": 1}, {"tag_id": 1}],
        creator_profiles=[{"tag_summary_json": {"1": {"count": 1}}}],
        snapshots=[{"platform": "xhs", "tag_distribution_json": {"1": 6}}],
    )

    assert result[0]["tag_id"] == 1
    assert result[0]["heat_score"] == 8
    assert result[0]["evidence"]["snapshot_tag_hits"] == 6

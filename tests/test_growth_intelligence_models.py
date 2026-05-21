from database.models import Base


def test_growth_intelligence_tables_registered():
    expected = {
        "research_scene_packs",
        "research_scene_pack_keywords",
        "research_ai_keyword_suggestion_sessions",
        "research_monitor_pools",
        "research_monitor_pool_creators",
        "research_content_samples",
        "research_extracted_content_keywords",
        "research_similar_content_candidates",
        "research_content_trackers",
        "research_content_tracking_snapshots",
        "research_keyword_heat_snapshots",
        "research_competitor_composition_snapshots",
    }

    assert expected.issubset(set(Base.metadata.tables))


def test_monitor_pool_creator_unique_columns_registered():
    table = Base.metadata.tables["research_monitor_pool_creators"]
    constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if hasattr(constraint, "columns")
    }

    assert ("pool_id", "platform", "creator_id") in constraints

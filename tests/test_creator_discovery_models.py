from database.models import Base


def test_creator_discovery_tables_registered():
    expected = {
        "research_platform_capabilities",
        "research_verticals",
        "research_tag_groups",
        "research_tag_definitions",
        "research_entity_tags",
        "research_creator_profiles",
        "research_creator_daily_snapshots",
        "research_search_intents",
        "research_competitor_accounts",
        "research_keyword_opportunity_snapshots",
    }

    assert expected.issubset(set(Base.metadata.tables))


def test_creator_profile_unique_columns_registered():
    table = Base.metadata.tables["research_creator_profiles"]
    constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if hasattr(constraint, "columns")
    }

    assert ("platform", "creator_id") in constraints

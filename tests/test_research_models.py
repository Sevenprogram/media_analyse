from database.models import Base


def test_research_tables_are_registered_with_base_metadata():
    expected = {
        "research_jobs",
        "crawl_checkpoints",
        "crawl_events",
        "raw_records",
        "research_authors",
        "research_posts",
        "research_comments",
        "ai_provider_configs",
        "ai_prompt_templates",
        "ai_analysis_jobs",
        "ai_analysis_results",
    }

    assert expected.issubset(set(Base.metadata.tables))


def test_research_job_collection_mode_columns_are_registered():
    columns = set(Base.metadata.tables["research_jobs"].columns.keys())

    assert {"collection_mode", "target_ids", "creator_ids"}.issubset(columns)

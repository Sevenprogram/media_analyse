from database.models import Base


def test_research_tables_are_registered_with_base_metadata():
    expected = {
        "research_jobs",
        "crawl_checkpoints",
        "crawl_events",
        "research_crawl_units",
        "research_worker_heartbeats",
        "research_platform_rate_limits",
        "research_auth_profiles",
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


def test_research_opportunity_feedback_model_columns():
    from research.models import ResearchOpportunityFeedback

    columns = set(ResearchOpportunityFeedback.__table__.columns.keys())
    assert {
        "id",
        "opportunity_id",
        "feedback",
        "note",
        "opportunity_type",
        "opportunity_name",
        "payload_json",
        "created_at",
    }.issubset(columns)

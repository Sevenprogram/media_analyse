from research.schema_migration import missing_research_job_columns


def test_missing_research_job_columns_reports_collection_mode_columns():
    missing = missing_research_job_columns(["id", "name", "keywords"])

    assert {"collection_mode", "target_ids", "creator_ids"}.issubset(missing)
    assert "schedule_enabled" in missing


def test_missing_research_job_columns_is_empty_when_columns_exist():
    missing = missing_research_job_columns(
        [
            "id",
            "collection_mode",
            "target_ids",
            "creator_ids",
            "schedule_enabled",
            "schedule_interval_minutes",
            "next_run_at",
            "last_scheduled_at",
        ]
    )

    assert missing == set()


def test_missing_research_feedback_table_is_required():
    from research.setup_status import REQUIRED_RESEARCH_TABLES

    assert "research_opportunity_feedback" in REQUIRED_RESEARCH_TABLES

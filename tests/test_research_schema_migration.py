from research.schema_migration import missing_research_job_columns


def test_missing_research_job_columns_reports_collection_mode_columns():
    missing = missing_research_job_columns(["id", "name", "keywords"])

    assert missing == {"collection_mode", "target_ids", "creator_ids"}


def test_missing_research_job_columns_is_empty_when_columns_exist():
    missing = missing_research_job_columns(
        ["id", "collection_mode", "target_ids", "creator_ids"]
    )

    assert missing == set()

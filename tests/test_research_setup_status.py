from research.setup_status import build_research_setup_status


def test_setup_status_masks_secrets_and_reports_research_tables():
    status = build_research_setup_status()

    assert status["database"]["postgres"]["password_set"] is True
    assert "password" not in status["database"]["postgres"]
    assert "research_database_ready" in status["database"]
    assert {"db", "mysql", "postgres", "sqlite"}.issubset(
        set(status["database"]["supported_research_save_options"])
    )
    assert status["database"]["research_tables_registered"] is True
    assert status["database"]["missing_research_tables"] == []

    platforms = {item["value"]: item for item in status["platforms"]}
    assert platforms["bili"]["backfill_supported"] is True
    assert "danmaku_count" in platforms["bili"]["content_types"]

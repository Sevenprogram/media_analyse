import config

from research.database_guard import (
    ResearchDatabaseNotConfigured,
    assert_research_database_enabled,
    is_research_database_enabled,
    research_database_error_message,
)


def test_research_database_enabled_accepts_sql_storage():
    assert is_research_database_enabled("sqlite") is True
    assert is_research_database_enabled("postgres") is True
    assert is_research_database_enabled("mysql") is True
    assert is_research_database_enabled("db") is True


def test_research_database_enabled_rejects_file_storage():
    assert is_research_database_enabled("jsonl") is False
    assert is_research_database_enabled("csv") is False


def test_research_database_guard_reports_current_save_option(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "jsonl", raising=False)

    try:
        assert_research_database_enabled()
    except ResearchDatabaseNotConfigured as exc:
        assert "SQL storage" in str(exc)
        assert "Current value: jsonl" in str(exc)
    else:
        raise AssertionError("Expected ResearchDatabaseNotConfigured")


def test_research_database_error_message_lists_supported_options():
    message = research_database_error_message("json")

    assert "db" in message
    assert "mysql" in message
    assert "postgres" in message
    assert "sqlite" in message

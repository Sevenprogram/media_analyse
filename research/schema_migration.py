from collections.abc import Sequence

from sqlalchemy import text


RESEARCH_JOB_REQUIRED_COLUMNS = {
    "collection_mode",
    "target_ids",
    "creator_ids",
}


async def ensure_research_schema(conn) -> None:
    existing = await _get_table_columns(conn, "research_jobs")
    if not existing:
        return

    dialect = conn.dialect.name
    for column in sorted(RESEARCH_JOB_REQUIRED_COLUMNS - existing):
        statement = _alter_research_jobs_statement(dialect, column)
        if statement:
            await conn.execute(text(statement))


async def _get_table_columns(conn, table_name: str) -> set[str]:
    dialect = conn.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        return {str(row[1]) for row in result.fetchall()}
    if dialect == "postgresql":
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
        return {str(row[0]) for row in result.fetchall()}
    if dialect in {"mysql", "mariadb"}:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
        return {str(row[0]) for row in result.fetchall()}
    return set()


def _alter_research_jobs_statement(dialect: str, column: str) -> str | None:
    statements: dict[str, dict[str, str]] = {
        "sqlite": {
            "collection_mode": "ALTER TABLE research_jobs ADD COLUMN collection_mode VARCHAR(32) NOT NULL DEFAULT 'search'",
            "target_ids": "ALTER TABLE research_jobs ADD COLUMN target_ids JSON NOT NULL DEFAULT '[]'",
            "creator_ids": "ALTER TABLE research_jobs ADD COLUMN creator_ids JSON NOT NULL DEFAULT '[]'",
        },
        "postgresql": {
            "collection_mode": "ALTER TABLE research_jobs ADD COLUMN collection_mode VARCHAR(32) NOT NULL DEFAULT 'search'",
            "target_ids": "ALTER TABLE research_jobs ADD COLUMN target_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
            "creator_ids": "ALTER TABLE research_jobs ADD COLUMN creator_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
        },
        "mysql": {
            "collection_mode": "ALTER TABLE research_jobs ADD COLUMN collection_mode VARCHAR(32) NOT NULL DEFAULT 'search'",
            "target_ids": "ALTER TABLE research_jobs ADD COLUMN target_ids JSON NULL",
            "creator_ids": "ALTER TABLE research_jobs ADD COLUMN creator_ids JSON NULL",
        },
        "mariadb": {
            "collection_mode": "ALTER TABLE research_jobs ADD COLUMN collection_mode VARCHAR(32) NOT NULL DEFAULT 'search'",
            "target_ids": "ALTER TABLE research_jobs ADD COLUMN target_ids JSON NULL",
            "creator_ids": "ALTER TABLE research_jobs ADD COLUMN creator_ids JSON NULL",
        },
    }
    return statements.get(dialect, {}).get(column)


def missing_research_job_columns(columns: Sequence[str]) -> set[str]:
    return RESEARCH_JOB_REQUIRED_COLUMNS - set(columns)

from collections.abc import Sequence

from sqlalchemy import text


RESEARCH_JOB_REQUIRED_COLUMNS = {
    "collection_mode",
    "target_ids",
    "creator_ids",
    "schedule_enabled",
    "schedule_interval_minutes",
    "next_run_at",
    "last_scheduled_at",
}

RESEARCH_CRAWL_UNIT_REQUIRED_COLUMNS = {
    "run_key",
}

RESEARCH_SCENE_PACK_REQUIRED_COLUMNS = {
    "primary_goal",
    "default_collection_depth",
    "default_ai_template",
    "source",
    "archived",
}

RESEARCH_GROWTH_PROJECT_REQUIRED_COLUMNS = {
    "comment_collection_enabled",
    "refresh_cadence",
    "custom_interval_value",
    "custom_interval_unit",
}


async def ensure_research_schema(conn) -> None:
    dialect = conn.dialect.name
    await _ensure_table(
        conn,
        table_name="research_opportunity_feedback",
        statement_builder=_create_research_opportunity_feedback_statement,
        dialect=dialect,
    )
    await _ensure_columns(
        conn,
        table_name="research_jobs",
        required=RESEARCH_JOB_REQUIRED_COLUMNS,
        statement_builder=_alter_research_jobs_statement,
        dialect=dialect,
    )
    await _ensure_columns(
        conn,
        table_name="research_crawl_units",
        required=RESEARCH_CRAWL_UNIT_REQUIRED_COLUMNS,
        statement_builder=_alter_research_crawl_units_statement,
        dialect=dialect,
    )
    await _ensure_columns(
        conn,
        table_name="research_scene_packs",
        required=RESEARCH_SCENE_PACK_REQUIRED_COLUMNS,
        statement_builder=_alter_research_scene_packs_statement,
        dialect=dialect,
    )
    await _ensure_columns(
        conn,
        table_name="research_growth_projects",
        required=RESEARCH_GROWTH_PROJECT_REQUIRED_COLUMNS,
        statement_builder=_alter_research_growth_projects_statement,
        dialect=dialect,
    )


async def _ensure_columns(conn, *, table_name, required, statement_builder, dialect) -> None:
    existing = await _get_table_columns(conn, table_name)
    if not existing:
        return
    for column in sorted(required - existing):
        statement = statement_builder(dialect, column)
        if statement:
            await conn.execute(text(statement))


async def _ensure_table(conn, *, table_name, statement_builder, dialect) -> None:
    existing = await _get_table_columns(conn, table_name)
    if existing:
        return
    statement = statement_builder(dialect)
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
            "schedule_enabled": "ALTER TABLE research_jobs ADD COLUMN schedule_enabled BOOLEAN NOT NULL DEFAULT 0",
            "schedule_interval_minutes": "ALTER TABLE research_jobs ADD COLUMN schedule_interval_minutes INTEGER NULL",
            "next_run_at": "ALTER TABLE research_jobs ADD COLUMN next_run_at DATETIME NULL",
            "last_scheduled_at": "ALTER TABLE research_jobs ADD COLUMN last_scheduled_at DATETIME NULL",
        },
        "postgresql": {
            "collection_mode": "ALTER TABLE research_jobs ADD COLUMN collection_mode VARCHAR(32) NOT NULL DEFAULT 'search'",
            "target_ids": "ALTER TABLE research_jobs ADD COLUMN target_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
            "creator_ids": "ALTER TABLE research_jobs ADD COLUMN creator_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
            "schedule_enabled": "ALTER TABLE research_jobs ADD COLUMN schedule_enabled BOOLEAN NOT NULL DEFAULT false",
            "schedule_interval_minutes": "ALTER TABLE research_jobs ADD COLUMN schedule_interval_minutes INTEGER NULL",
            "next_run_at": "ALTER TABLE research_jobs ADD COLUMN next_run_at TIMESTAMP WITH TIME ZONE NULL",
            "last_scheduled_at": "ALTER TABLE research_jobs ADD COLUMN last_scheduled_at TIMESTAMP WITH TIME ZONE NULL",
        },
        "mysql": {
            "collection_mode": "ALTER TABLE research_jobs ADD COLUMN collection_mode VARCHAR(32) NOT NULL DEFAULT 'search'",
            "target_ids": "ALTER TABLE research_jobs ADD COLUMN target_ids JSON NULL",
            "creator_ids": "ALTER TABLE research_jobs ADD COLUMN creator_ids JSON NULL",
            "schedule_enabled": "ALTER TABLE research_jobs ADD COLUMN schedule_enabled BOOLEAN NOT NULL DEFAULT false",
            "schedule_interval_minutes": "ALTER TABLE research_jobs ADD COLUMN schedule_interval_minutes INTEGER NULL",
            "next_run_at": "ALTER TABLE research_jobs ADD COLUMN next_run_at DATETIME NULL",
            "last_scheduled_at": "ALTER TABLE research_jobs ADD COLUMN last_scheduled_at DATETIME NULL",
        },
        "mariadb": {
            "collection_mode": "ALTER TABLE research_jobs ADD COLUMN collection_mode VARCHAR(32) NOT NULL DEFAULT 'search'",
            "target_ids": "ALTER TABLE research_jobs ADD COLUMN target_ids JSON NULL",
            "creator_ids": "ALTER TABLE research_jobs ADD COLUMN creator_ids JSON NULL",
            "schedule_enabled": "ALTER TABLE research_jobs ADD COLUMN schedule_enabled BOOLEAN NOT NULL DEFAULT false",
            "schedule_interval_minutes": "ALTER TABLE research_jobs ADD COLUMN schedule_interval_minutes INTEGER NULL",
            "next_run_at": "ALTER TABLE research_jobs ADD COLUMN next_run_at DATETIME NULL",
            "last_scheduled_at": "ALTER TABLE research_jobs ADD COLUMN last_scheduled_at DATETIME NULL",
        },
    }
    return statements.get(dialect, {}).get(column)


def _create_research_opportunity_feedback_statement(dialect: str) -> str | None:
    statements: dict[str, str] = {
        "sqlite": """
            CREATE TABLE IF NOT EXISTS research_opportunity_feedback (
                id INTEGER NOT NULL PRIMARY KEY,
                opportunity_id VARCHAR(255) NOT NULL,
                opportunity_type VARCHAR(32) NULL,
                opportunity_name TEXT NULL,
                feedback VARCHAR(32) NOT NULL,
                note TEXT NULL,
                payload_json JSON NOT NULL DEFAULT '{}',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "postgresql": """
            CREATE TABLE IF NOT EXISTS research_opportunity_feedback (
                id SERIAL PRIMARY KEY,
                opportunity_id VARCHAR(255) NOT NULL,
                opportunity_type VARCHAR(32) NULL,
                opportunity_name TEXT NULL,
                feedback VARCHAR(32) NOT NULL,
                note TEXT NULL,
                payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
        """,
        "mysql": """
            CREATE TABLE IF NOT EXISTS research_opportunity_feedback (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                opportunity_id VARCHAR(255) NOT NULL,
                opportunity_type VARCHAR(32) NULL,
                opportunity_name TEXT NULL,
                feedback VARCHAR(32) NOT NULL,
                note TEXT NULL,
                payload_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "mariadb": """
            CREATE TABLE IF NOT EXISTS research_opportunity_feedback (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                opportunity_id VARCHAR(255) NOT NULL,
                opportunity_type VARCHAR(32) NULL,
                opportunity_name TEXT NULL,
                feedback VARCHAR(32) NOT NULL,
                note TEXT NULL,
                payload_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """,
    }
    return statements.get(dialect)


def _alter_research_crawl_units_statement(dialect: str, column: str) -> str | None:
    statements: dict[str, dict[str, str]] = {
        "sqlite": {
            "run_key": "ALTER TABLE research_crawl_units ADD COLUMN run_key VARCHAR(64) NOT NULL DEFAULT 'default'",
        },
        "postgresql": {
            "run_key": "ALTER TABLE research_crawl_units ADD COLUMN run_key VARCHAR(64) NOT NULL DEFAULT 'default'",
        },
        "mysql": {
            "run_key": "ALTER TABLE research_crawl_units ADD COLUMN run_key VARCHAR(64) NOT NULL DEFAULT 'default'",
        },
        "mariadb": {
            "run_key": "ALTER TABLE research_crawl_units ADD COLUMN run_key VARCHAR(64) NOT NULL DEFAULT 'default'",
        },
    }
    return statements.get(dialect, {}).get(column)


def _alter_research_scene_packs_statement(dialect: str, column: str) -> str | None:
    statements: dict[str, dict[str, str]] = {
        "sqlite": {
            "primary_goal": "ALTER TABLE research_scene_packs ADD COLUMN primary_goal VARCHAR(64) NOT NULL DEFAULT 'topic_discovery'",
            "default_collection_depth": "ALTER TABLE research_scene_packs ADD COLUMN default_collection_depth VARCHAR(32) NOT NULL DEFAULT 'standard'",
            "default_ai_template": "ALTER TABLE research_scene_packs ADD COLUMN default_ai_template VARCHAR(128) NULL",
            "source": "ALTER TABLE research_scene_packs ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'custom'",
            "archived": "ALTER TABLE research_scene_packs ADD COLUMN archived BOOLEAN NOT NULL DEFAULT 0",
        },
        "postgresql": {
            "primary_goal": "ALTER TABLE research_scene_packs ADD COLUMN primary_goal VARCHAR(64) NOT NULL DEFAULT 'topic_discovery'",
            "default_collection_depth": "ALTER TABLE research_scene_packs ADD COLUMN default_collection_depth VARCHAR(32) NOT NULL DEFAULT 'standard'",
            "default_ai_template": "ALTER TABLE research_scene_packs ADD COLUMN default_ai_template VARCHAR(128) NULL",
            "source": "ALTER TABLE research_scene_packs ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'custom'",
            "archived": "ALTER TABLE research_scene_packs ADD COLUMN archived BOOLEAN NOT NULL DEFAULT false",
        },
        "mysql": {
            "primary_goal": "ALTER TABLE research_scene_packs ADD COLUMN primary_goal VARCHAR(64) NOT NULL DEFAULT 'topic_discovery'",
            "default_collection_depth": "ALTER TABLE research_scene_packs ADD COLUMN default_collection_depth VARCHAR(32) NOT NULL DEFAULT 'standard'",
            "default_ai_template": "ALTER TABLE research_scene_packs ADD COLUMN default_ai_template VARCHAR(128) NULL",
            "source": "ALTER TABLE research_scene_packs ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'custom'",
            "archived": "ALTER TABLE research_scene_packs ADD COLUMN archived BOOLEAN NOT NULL DEFAULT false",
        },
        "mariadb": {
            "primary_goal": "ALTER TABLE research_scene_packs ADD COLUMN primary_goal VARCHAR(64) NOT NULL DEFAULT 'topic_discovery'",
            "default_collection_depth": "ALTER TABLE research_scene_packs ADD COLUMN default_collection_depth VARCHAR(32) NOT NULL DEFAULT 'standard'",
            "default_ai_template": "ALTER TABLE research_scene_packs ADD COLUMN default_ai_template VARCHAR(128) NULL",
            "source": "ALTER TABLE research_scene_packs ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'custom'",
            "archived": "ALTER TABLE research_scene_packs ADD COLUMN archived BOOLEAN NOT NULL DEFAULT false",
        },
    }
    return statements.get(dialect, {}).get(column)


def _alter_research_growth_projects_statement(dialect: str, column: str) -> str | None:
    statements: dict[str, dict[str, str]] = {
        "sqlite": {
            "comment_collection_enabled": "ALTER TABLE research_growth_projects ADD COLUMN comment_collection_enabled BOOLEAN NOT NULL DEFAULT 1",
            "refresh_cadence": "ALTER TABLE research_growth_projects ADD COLUMN refresh_cadence VARCHAR(32) NOT NULL DEFAULT 'off'",
            "custom_interval_value": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_value INTEGER NULL",
            "custom_interval_unit": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_unit VARCHAR(16) NULL",
        },
        "postgresql": {
            "comment_collection_enabled": "ALTER TABLE research_growth_projects ADD COLUMN comment_collection_enabled BOOLEAN NOT NULL DEFAULT true",
            "refresh_cadence": "ALTER TABLE research_growth_projects ADD COLUMN refresh_cadence VARCHAR(32) NOT NULL DEFAULT 'off'",
            "custom_interval_value": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_value INTEGER NULL",
            "custom_interval_unit": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_unit VARCHAR(16) NULL",
        },
        "mysql": {
            "comment_collection_enabled": "ALTER TABLE research_growth_projects ADD COLUMN comment_collection_enabled BOOLEAN NOT NULL DEFAULT true",
            "refresh_cadence": "ALTER TABLE research_growth_projects ADD COLUMN refresh_cadence VARCHAR(32) NOT NULL DEFAULT 'off'",
            "custom_interval_value": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_value INTEGER NULL",
            "custom_interval_unit": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_unit VARCHAR(16) NULL",
        },
        "mariadb": {
            "comment_collection_enabled": "ALTER TABLE research_growth_projects ADD COLUMN comment_collection_enabled BOOLEAN NOT NULL DEFAULT true",
            "refresh_cadence": "ALTER TABLE research_growth_projects ADD COLUMN refresh_cadence VARCHAR(32) NOT NULL DEFAULT 'off'",
            "custom_interval_value": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_value INTEGER NULL",
            "custom_interval_unit": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_unit VARCHAR(16) NULL",
        },
    }
    return statements.get(dialect, {}).get(column)


def missing_research_job_columns(columns: Sequence[str]) -> set[str]:
    return RESEARCH_JOB_REQUIRED_COLUMNS - set(columns)

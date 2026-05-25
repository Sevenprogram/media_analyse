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
    "daily_collection_limit_per_platform",
}

RESEARCH_CONTENT_TRACKER_REQUIRED_COLUMNS = {
    "latest_analysis_run_id",
    "latest_analysis_snapshot_id",
}

RESEARCH_COMPETITOR_ACCOUNT_REQUIRED_COLUMNS = {
    "monitor_type",
}

TENANT_SCOPED_TABLES = {
    "ai_analysis_jobs",
    "ai_analysis_results",
    "crawl_checkpoints",
    "crawl_events",
    "raw_records",
    "research_account_profiles",
    "research_account_roles",
    "research_ai_hotspots",
    "research_ai_insight_runs",
    "research_ai_keyword_suggestion_sessions",
    "research_ai_topic_ideas",
    "research_authors",
    "research_backtests",
    "research_collection_runs",
    "research_comments",
    "research_competitor_accounts",
    "research_competitor_composition_snapshots",
    "research_content_samples",
    "research_content_tracker_analysis_runs",
    "research_content_tracker_analysis_snapshots",
    "research_content_tracker_candidate_samples",
    "research_content_trackers",
    "research_content_tracking_snapshots",
    "research_crawl_units",
    "research_creator_candidates",
    "research_creator_daily_snapshots",
    "research_creator_profiles",
    "research_creator_search_session_results",
    "research_creator_search_sessions",
    "research_extracted_content_keywords",
    "research_entity_tags",
    "research_growth_project_collection_plans",
    "research_growth_project_keywords",
    "research_growth_projects",
    "research_jobs",
    "research_keyword_heat_snapshots",
    "research_keyword_opportunity_snapshots",
    "research_keyword_sets",
    "research_lead_attribution_daily_snapshots",
    "research_lead_attribution_results",
    "research_lead_attribution_spend",
    "research_lead_conversion_events",
    "research_lead_touchpoints",
    "research_leads",
    "research_monitor_pool_creators",
    "research_monitor_pools",
    "research_opportunity_feedback",
    "research_posts",
    "research_search_intents",
    "research_similar_content_candidates",
    "research_auth_profiles",
}


async def ensure_research_schema(conn) -> None:
    dialect = conn.dialect.name
    await _ensure_table(
        conn,
        table_name="research_opportunity_feedback",
        statement_builder=_create_research_opportunity_feedback_statement,
        dialect=dialect,
    )
    await _ensure_table(
        conn,
        table_name="research_content_tracker_analysis_runs",
        statement_builder=_create_research_content_tracker_analysis_runs_statement,
        dialect=dialect,
    )
    await _ensure_table(
        conn,
        table_name="research_content_tracker_analysis_snapshots",
        statement_builder=_create_research_content_tracker_analysis_snapshots_statement,
        dialect=dialect,
    )
    await _ensure_table(
        conn,
        table_name="research_content_tracker_candidate_samples",
        statement_builder=_create_research_content_tracker_candidate_samples_statement,
        dialect=dialect,
    )
    await _ensure_table(
        conn,
        table_name="research_collection_runs",
        statement_builder=_create_research_collection_runs_statement,
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
    await _ensure_columns(
        conn,
        table_name="research_content_trackers",
        required=RESEARCH_CONTENT_TRACKER_REQUIRED_COLUMNS,
        statement_builder=_alter_research_content_trackers_statement,
        dialect=dialect,
    )
    await _ensure_columns(
        conn,
        table_name="research_competitor_accounts",
        required=RESEARCH_COMPETITOR_ACCOUNT_REQUIRED_COLUMNS,
        statement_builder=_alter_research_competitor_accounts_statement,
        dialect=dialect,
    )
    for table_name in sorted(TENANT_SCOPED_TABLES):
        await _ensure_columns(
            conn,
            table_name=table_name,
            required={"org_id"},
            statement_builder=lambda dialect, column, table_name=table_name: _alter_org_id_statement(
                dialect,
                table_name,
                column,
            ),
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


def _alter_research_competitor_accounts_statement(dialect: str, column: str) -> str | None:
    if column != "monitor_type":
        return None
    statements = {
        "sqlite": "ALTER TABLE research_competitor_accounts ADD COLUMN monitor_type VARCHAR(32) NOT NULL DEFAULT 'competitor'",
        "postgresql": "ALTER TABLE research_competitor_accounts ADD COLUMN monitor_type VARCHAR(32) NOT NULL DEFAULT 'competitor'",
        "mysql": "ALTER TABLE research_competitor_accounts ADD COLUMN monitor_type VARCHAR(32) NOT NULL DEFAULT 'competitor'",
        "mariadb": "ALTER TABLE research_competitor_accounts ADD COLUMN monitor_type VARCHAR(32) NOT NULL DEFAULT 'competitor'",
    }
    return statements.get(dialect)


def _alter_org_id_statement(dialect: str, table_name: str, column: str) -> str | None:
    if column != "org_id":
        return None
    if dialect in {"sqlite", "postgresql", "mysql", "mariadb"}:
        return f"ALTER TABLE {table_name} ADD COLUMN org_id INTEGER NULL"
    return None


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


def _create_research_content_tracker_analysis_runs_statement(dialect: str) -> str | None:
    statements: dict[str, str] = {
        "sqlite": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_analysis_runs (
                id INTEGER NOT NULL PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'completed',
                analysis_version VARCHAR(32) NOT NULL DEFAULT 'v1',
                window_days INTEGER NOT NULL DEFAULT 7,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                sample_quality_score FLOAT NOT NULL DEFAULT 0,
                trend_strength_score FLOAT NOT NULL DEFAULT 0,
                noise_rate FLOAT NOT NULL DEFAULT 0,
                decision_confidence FLOAT NOT NULL DEFAULT 0,
                input_summary_json JSON NOT NULL DEFAULT '{}',
                summary_json JSON NOT NULL DEFAULT '{}',
                error_message TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id)
            )
        """,
        "postgresql": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_analysis_runs (
                id SERIAL PRIMARY KEY,
                tracker_id INTEGER NOT NULL REFERENCES research_content_trackers(id),
                status VARCHAR(32) NOT NULL DEFAULT 'completed',
                analysis_version VARCHAR(32) NOT NULL DEFAULT 'v1',
                window_days INTEGER NOT NULL DEFAULT 7,
                started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                completed_at TIMESTAMP WITH TIME ZONE NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                sample_quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                trend_strength_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                noise_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
                decision_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                input_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                error_message TEXT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
        """,
        "mysql": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_analysis_runs (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'completed',
                analysis_version VARCHAR(32) NOT NULL DEFAULT 'v1',
                window_days INTEGER NOT NULL DEFAULT 7,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                sample_quality_score DOUBLE NOT NULL DEFAULT 0,
                trend_strength_score DOUBLE NOT NULL DEFAULT 0,
                noise_rate DOUBLE NOT NULL DEFAULT 0,
                decision_confidence DOUBLE NOT NULL DEFAULT 0,
                input_summary_json JSON NOT NULL,
                summary_json JSON NOT NULL,
                error_message TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id)
            )
        """,
        "mariadb": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_analysis_runs (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'completed',
                analysis_version VARCHAR(32) NOT NULL DEFAULT 'v1',
                window_days INTEGER NOT NULL DEFAULT 7,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                candidate_count INTEGER NOT NULL DEFAULT 0,
                sample_quality_score DOUBLE NOT NULL DEFAULT 0,
                trend_strength_score DOUBLE NOT NULL DEFAULT 0,
                noise_rate DOUBLE NOT NULL DEFAULT 0,
                decision_confidence DOUBLE NOT NULL DEFAULT 0,
                input_summary_json JSON NOT NULL,
                summary_json JSON NOT NULL,
                error_message TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id)
            )
        """,
    }
    return statements.get(dialect)


def _create_research_content_tracker_analysis_snapshots_statement(dialect: str) -> str | None:
    statements: dict[str, str] = {
        "sqlite": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_analysis_snapshots (
                id INTEGER NOT NULL PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                snapshot_date DATE NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'ready',
                overview_json JSON NOT NULL DEFAULT '{}',
                trends_json JSON NOT NULL DEFAULT '{}',
                keywords_json JSON NOT NULL DEFAULT '{}',
                patterns_json JSON NOT NULL DEFAULT '{}',
                creators_json JSON NOT NULL DEFAULT '{}',
                samples_json JSON NOT NULL DEFAULT '{}',
                risks_json JSON NOT NULL DEFAULT '{}',
                decisions_json JSON NOT NULL DEFAULT '{}',
                meta_json JSON NOT NULL DEFAULT '{}',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id),
                FOREIGN KEY(run_id) REFERENCES research_content_tracker_analysis_runs(id)
            )
        """,
        "postgresql": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_analysis_snapshots (
                id SERIAL PRIMARY KEY,
                tracker_id INTEGER NOT NULL REFERENCES research_content_trackers(id),
                run_id INTEGER NOT NULL REFERENCES research_content_tracker_analysis_runs(id),
                snapshot_date DATE NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'ready',
                overview_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                trends_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                keywords_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                patterns_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                creators_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                samples_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                risks_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                decisions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
        """,
        "mysql": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_analysis_snapshots (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                snapshot_date DATE NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'ready',
                overview_json JSON NOT NULL,
                trends_json JSON NOT NULL,
                keywords_json JSON NOT NULL,
                patterns_json JSON NOT NULL,
                creators_json JSON NOT NULL,
                samples_json JSON NOT NULL,
                risks_json JSON NOT NULL,
                decisions_json JSON NOT NULL,
                meta_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id),
                FOREIGN KEY(run_id) REFERENCES research_content_tracker_analysis_runs(id)
            )
        """,
        "mariadb": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_analysis_snapshots (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                snapshot_date DATE NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'ready',
                overview_json JSON NOT NULL,
                trends_json JSON NOT NULL,
                keywords_json JSON NOT NULL,
                patterns_json JSON NOT NULL,
                creators_json JSON NOT NULL,
                samples_json JSON NOT NULL,
                risks_json JSON NOT NULL,
                decisions_json JSON NOT NULL,
                meta_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id),
                FOREIGN KEY(run_id) REFERENCES research_content_tracker_analysis_runs(id)
            )
        """,
    }
    return statements.get(dialect)


def _create_research_content_tracker_candidate_samples_statement(dialect: str) -> str | None:
    statements: dict[str, str] = {
        "sqlite": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_candidate_samples (
                id INTEGER NOT NULL PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                platform VARCHAR(32) NOT NULL,
                platform_post_id VARCHAR(255) NOT NULL,
                author_id VARCHAR(255) NULL,
                title TEXT NULL,
                url TEXT NULL,
                publish_time DATETIME NULL,
                candidate_level VARCHAR(8) NOT NULL DEFAULT 'L2',
                similarity_score FLOAT NOT NULL DEFAULT 0,
                engagement_total INTEGER NOT NULL DEFAULT 0,
                is_hot BOOLEAN NOT NULL DEFAULT 0,
                matched_keywords_json JSON NOT NULL DEFAULT '[]',
                fingerprint_json JSON NOT NULL DEFAULT '{}',
                engagement_json JSON NOT NULL DEFAULT '{}',
                evidence_json JSON NOT NULL DEFAULT '{}',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id),
                FOREIGN KEY(run_id) REFERENCES research_content_tracker_analysis_runs(id),
                CONSTRAINT uq_research_content_tracker_candidate_sample UNIQUE (run_id, platform, platform_post_id)
            )
        """,
        "postgresql": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_candidate_samples (
                id SERIAL PRIMARY KEY,
                tracker_id INTEGER NOT NULL REFERENCES research_content_trackers(id),
                run_id INTEGER NOT NULL REFERENCES research_content_tracker_analysis_runs(id),
                platform VARCHAR(32) NOT NULL,
                platform_post_id VARCHAR(255) NOT NULL,
                author_id VARCHAR(255) NULL,
                title TEXT NULL,
                url TEXT NULL,
                publish_time TIMESTAMP WITH TIME ZONE NULL,
                candidate_level VARCHAR(8) NOT NULL DEFAULT 'L2',
                similarity_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                engagement_total INTEGER NOT NULL DEFAULT 0,
                is_hot BOOLEAN NOT NULL DEFAULT false,
                matched_keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                fingerprint_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                engagement_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT uq_research_content_tracker_candidate_sample UNIQUE (run_id, platform, platform_post_id)
            )
        """,
        "mysql": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_candidate_samples (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                platform VARCHAR(32) NOT NULL,
                platform_post_id VARCHAR(255) NOT NULL,
                author_id VARCHAR(255) NULL,
                title TEXT NULL,
                url TEXT NULL,
                publish_time DATETIME NULL,
                candidate_level VARCHAR(8) NOT NULL DEFAULT 'L2',
                similarity_score DOUBLE NOT NULL DEFAULT 0,
                engagement_total INTEGER NOT NULL DEFAULT 0,
                is_hot BOOLEAN NOT NULL DEFAULT false,
                matched_keywords_json JSON NOT NULL,
                fingerprint_json JSON NOT NULL,
                engagement_json JSON NOT NULL,
                evidence_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_research_content_tracker_candidate_sample UNIQUE (run_id, platform, platform_post_id),
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id),
                FOREIGN KEY(run_id) REFERENCES research_content_tracker_analysis_runs(id)
            )
        """,
        "mariadb": """
            CREATE TABLE IF NOT EXISTS research_content_tracker_candidate_samples (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                tracker_id INTEGER NOT NULL,
                run_id INTEGER NOT NULL,
                platform VARCHAR(32) NOT NULL,
                platform_post_id VARCHAR(255) NOT NULL,
                author_id VARCHAR(255) NULL,
                title TEXT NULL,
                url TEXT NULL,
                publish_time DATETIME NULL,
                candidate_level VARCHAR(8) NOT NULL DEFAULT 'L2',
                similarity_score DOUBLE NOT NULL DEFAULT 0,
                engagement_total INTEGER NOT NULL DEFAULT 0,
                is_hot BOOLEAN NOT NULL DEFAULT false,
                matched_keywords_json JSON NOT NULL,
                fingerprint_json JSON NOT NULL,
                engagement_json JSON NOT NULL,
                evidence_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_research_content_tracker_candidate_sample UNIQUE (run_id, platform, platform_post_id),
                FOREIGN KEY(tracker_id) REFERENCES research_content_trackers(id),
                FOREIGN KEY(run_id) REFERENCES research_content_tracker_analysis_runs(id)
            )
        """,
    }
    return statements.get(dialect)


def _create_research_collection_runs_statement(dialect: str) -> str | None:
    statements: dict[str, str] = {
        "sqlite": """
            CREATE TABLE IF NOT EXISTS research_collection_runs (
                id INTEGER NOT NULL PRIMARY KEY,
                run_type VARCHAR(32) NOT NULL,
                target_type VARCHAR(32) NOT NULL,
                target_id INTEGER NOT NULL,
                mode VARCHAR(32) NOT NULL DEFAULT 'collect_only',
                trigger_source VARCHAR(32) NOT NULL DEFAULT 'manual',
                status VARCHAR(32) NOT NULL DEFAULT 'queued',
                phase VARCHAR(32) NOT NULL DEFAULT 'queued',
                job_id INTEGER NULL,
                analysis_run_id INTEGER NULL,
                started_at DATETIME NULL,
                completed_at DATETIME NULL,
                request_payload_json JSON NOT NULL DEFAULT '{}',
                summary_json JSON NOT NULL DEFAULT '{}',
                error_json JSON NOT NULL DEFAULT '{}',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(job_id) REFERENCES research_jobs(id),
                FOREIGN KEY(analysis_run_id) REFERENCES research_content_tracker_analysis_runs(id)
            )
        """,
        "postgresql": """
            CREATE TABLE IF NOT EXISTS research_collection_runs (
                id SERIAL PRIMARY KEY,
                run_type VARCHAR(32) NOT NULL,
                target_type VARCHAR(32) NOT NULL,
                target_id INTEGER NOT NULL,
                mode VARCHAR(32) NOT NULL DEFAULT 'collect_only',
                trigger_source VARCHAR(32) NOT NULL DEFAULT 'manual',
                status VARCHAR(32) NOT NULL DEFAULT 'queued',
                phase VARCHAR(32) NOT NULL DEFAULT 'queued',
                job_id INTEGER NULL REFERENCES research_jobs(id),
                analysis_run_id INTEGER NULL REFERENCES research_content_tracker_analysis_runs(id),
                started_at TIMESTAMP WITH TIME ZONE NULL,
                completed_at TIMESTAMP WITH TIME ZONE NULL,
                request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                error_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
        """,
        "mysql": """
            CREATE TABLE IF NOT EXISTS research_collection_runs (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                run_type VARCHAR(32) NOT NULL,
                target_type VARCHAR(32) NOT NULL,
                target_id INTEGER NOT NULL,
                mode VARCHAR(32) NOT NULL DEFAULT 'collect_only',
                trigger_source VARCHAR(32) NOT NULL DEFAULT 'manual',
                status VARCHAR(32) NOT NULL DEFAULT 'queued',
                phase VARCHAR(32) NOT NULL DEFAULT 'queued',
                job_id INTEGER NULL,
                analysis_run_id INTEGER NULL,
                started_at DATETIME NULL,
                completed_at DATETIME NULL,
                request_payload_json JSON NOT NULL,
                summary_json JSON NOT NULL,
                error_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(job_id) REFERENCES research_jobs(id),
                FOREIGN KEY(analysis_run_id) REFERENCES research_content_tracker_analysis_runs(id)
            )
        """,
        "mariadb": """
            CREATE TABLE IF NOT EXISTS research_collection_runs (
                id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
                run_type VARCHAR(32) NOT NULL,
                target_type VARCHAR(32) NOT NULL,
                target_id INTEGER NOT NULL,
                mode VARCHAR(32) NOT NULL DEFAULT 'collect_only',
                trigger_source VARCHAR(32) NOT NULL DEFAULT 'manual',
                status VARCHAR(32) NOT NULL DEFAULT 'queued',
                phase VARCHAR(32) NOT NULL DEFAULT 'queued',
                job_id INTEGER NULL,
                analysis_run_id INTEGER NULL,
                started_at DATETIME NULL,
                completed_at DATETIME NULL,
                request_payload_json JSON NOT NULL,
                summary_json JSON NOT NULL,
                error_json JSON NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(job_id) REFERENCES research_jobs(id),
                FOREIGN KEY(analysis_run_id) REFERENCES research_content_tracker_analysis_runs(id)
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
            "daily_collection_limit_per_platform": "ALTER TABLE research_growth_projects ADD COLUMN daily_collection_limit_per_platform INTEGER NOT NULL DEFAULT 50",
        },
        "postgresql": {
            "comment_collection_enabled": "ALTER TABLE research_growth_projects ADD COLUMN comment_collection_enabled BOOLEAN NOT NULL DEFAULT true",
            "refresh_cadence": "ALTER TABLE research_growth_projects ADD COLUMN refresh_cadence VARCHAR(32) NOT NULL DEFAULT 'off'",
            "custom_interval_value": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_value INTEGER NULL",
            "custom_interval_unit": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_unit VARCHAR(16) NULL",
            "daily_collection_limit_per_platform": "ALTER TABLE research_growth_projects ADD COLUMN daily_collection_limit_per_platform INTEGER NOT NULL DEFAULT 50",
        },
        "mysql": {
            "comment_collection_enabled": "ALTER TABLE research_growth_projects ADD COLUMN comment_collection_enabled BOOLEAN NOT NULL DEFAULT true",
            "refresh_cadence": "ALTER TABLE research_growth_projects ADD COLUMN refresh_cadence VARCHAR(32) NOT NULL DEFAULT 'off'",
            "custom_interval_value": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_value INTEGER NULL",
            "custom_interval_unit": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_unit VARCHAR(16) NULL",
            "daily_collection_limit_per_platform": "ALTER TABLE research_growth_projects ADD COLUMN daily_collection_limit_per_platform INTEGER NOT NULL DEFAULT 50",
        },
        "mariadb": {
            "comment_collection_enabled": "ALTER TABLE research_growth_projects ADD COLUMN comment_collection_enabled BOOLEAN NOT NULL DEFAULT true",
            "refresh_cadence": "ALTER TABLE research_growth_projects ADD COLUMN refresh_cadence VARCHAR(32) NOT NULL DEFAULT 'off'",
            "custom_interval_value": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_value INTEGER NULL",
            "custom_interval_unit": "ALTER TABLE research_growth_projects ADD COLUMN custom_interval_unit VARCHAR(16) NULL",
            "daily_collection_limit_per_platform": "ALTER TABLE research_growth_projects ADD COLUMN daily_collection_limit_per_platform INTEGER NOT NULL DEFAULT 50",
        },
    }
    return statements.get(dialect, {}).get(column)


def _alter_research_content_trackers_statement(dialect: str, column: str) -> str | None:
    statements: dict[str, dict[str, str]] = {
        "sqlite": {
            "latest_analysis_run_id": "ALTER TABLE research_content_trackers ADD COLUMN latest_analysis_run_id INTEGER NULL",
            "latest_analysis_snapshot_id": "ALTER TABLE research_content_trackers ADD COLUMN latest_analysis_snapshot_id INTEGER NULL",
        },
        "postgresql": {
            "latest_analysis_run_id": "ALTER TABLE research_content_trackers ADD COLUMN latest_analysis_run_id INTEGER NULL",
            "latest_analysis_snapshot_id": "ALTER TABLE research_content_trackers ADD COLUMN latest_analysis_snapshot_id INTEGER NULL",
        },
        "mysql": {
            "latest_analysis_run_id": "ALTER TABLE research_content_trackers ADD COLUMN latest_analysis_run_id INTEGER NULL",
            "latest_analysis_snapshot_id": "ALTER TABLE research_content_trackers ADD COLUMN latest_analysis_snapshot_id INTEGER NULL",
        },
        "mariadb": {
            "latest_analysis_run_id": "ALTER TABLE research_content_trackers ADD COLUMN latest_analysis_run_id INTEGER NULL",
            "latest_analysis_snapshot_id": "ALTER TABLE research_content_trackers ADD COLUMN latest_analysis_snapshot_id INTEGER NULL",
        },
    }
    return statements.get(dialect, {}).get(column)


def missing_research_job_columns(columns: Sequence[str]) -> set[str]:
    return RESEARCH_JOB_REQUIRED_COLUMNS - set(columns)

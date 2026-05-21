import os
from pathlib import Path
from typing import Any

import config
from config.db_config import postgres_db_config, sqlite_db_config
from database.models import Base
from research.database_guard import RESEARCH_SQL_SAVE_OPTIONS, is_research_database_enabled
from research.platforms import list_research_platform_options


RESEARCH_TABLE_NAMES = {
    "research_jobs",
    "crawl_checkpoints",
    "crawl_events",
    "research_crawl_units",
    "research_worker_heartbeats",
    "research_platform_rate_limits",
    "research_platform_capabilities",
    "research_global_settings",
    "research_keyword_sets",
    "research_verticals",
    "research_tag_groups",
    "research_tag_definitions",
    "research_auth_profiles",
    "raw_records",
    "research_authors",
    "research_posts",
    "research_comments",
    "research_entity_tags",
    "research_creator_profiles",
    "research_creator_daily_snapshots",
    "research_creator_candidates",
    "research_search_intents",
    "research_scene_packs",
    "research_scene_pack_keywords",
    "research_ai_keyword_suggestion_sessions",
    "research_monitor_pools",
    "research_monitor_pool_creators",
    "research_content_samples",
    "research_extracted_content_keywords",
    "research_similar_content_candidates",
    "research_content_trackers",
    "research_content_tracking_snapshots",
    "research_keyword_heat_snapshots",
    "research_competitor_composition_snapshots",
    "research_opportunity_feedback",
    "research_competitor_accounts",
    "research_keyword_opportunity_snapshots",
    "ai_provider_configs",
    "ai_prompt_templates",
    "ai_analysis_jobs",
    "ai_analysis_results",
}

REQUIRED_RESEARCH_TABLES = RESEARCH_TABLE_NAMES


def build_research_setup_status() -> dict[str, Any]:
    registered_tables = set(Base.metadata.tables)
    missing_tables = sorted(RESEARCH_TABLE_NAMES - registered_tables)
    postgres_env = {
        "POSTGRES_DB_HOST": "POSTGRES_DB_HOST" in os.environ,
        "POSTGRES_DB_PORT": "POSTGRES_DB_PORT" in os.environ,
        "POSTGRES_DB_USER": "POSTGRES_DB_USER" in os.environ,
        "POSTGRES_DB_NAME": "POSTGRES_DB_NAME" in os.environ,
        "POSTGRES_DB_PWD": "POSTGRES_DB_PWD" in os.environ,
    }
    author_hash_salt = os.getenv("RESEARCH_AUTHOR_HASH_SALT", "")

    return {
        "database": {
            "save_data_option": getattr(config, "SAVE_DATA_OPTION", None),
            "research_database_ready": is_research_database_enabled(),
            "supported_research_save_options": sorted(RESEARCH_SQL_SAVE_OPTIONS),
            "postgres": {
                "host": postgres_db_config["host"],
                "port": int(postgres_db_config["port"]),
                "user": postgres_db_config["user"],
                "db_name": postgres_db_config["db_name"],
                "password_set": bool(postgres_db_config["password"]),
                "using_default_password": (
                    postgres_db_config["password"] == "123456"
                    and "POSTGRES_DB_PWD" not in os.environ
                ),
                "env_overrides": postgres_env,
                "connectivity": "not_checked",
            },
            "sqlite": {
                "db_path": sqlite_db_config["db_path"],
                "db_file_exists": Path(sqlite_db_config["db_path"]).exists(),
            },
            "research_tables_registered": not missing_tables,
            "missing_research_tables": missing_tables,
        },
        "environment": {
            "author_hash_salt_set": bool(author_hash_salt),
            "author_hash_salt_length": len(author_hash_salt),
            "ai_provider_configurable": True,
        },
        "platforms": list_research_platform_options(),
    }

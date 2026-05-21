from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from database.models import Base


def json_column():
    return JSON().with_variant(JSONB, "postgresql")


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    topic = Column(Text, nullable=False)
    platforms = Column(json_column(), nullable=False)
    collection_mode = Column(String(32), nullable=False, default="search")
    keywords = Column(json_column(), nullable=False)
    target_ids = Column(json_column(), nullable=False, default=list)
    creator_ids = Column(json_column(), nullable=False, default=list)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    comment_policy = Column(json_column(), nullable=False)
    raw_record_mode = Column(String(32), nullable=False)
    anonymize_authors = Column(Boolean, nullable=False, default=True)
    schedule_enabled = Column(Boolean, nullable=False, default=False)
    schedule_interval_minutes = Column(Integer, nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CrawlCheckpoint(Base):
    __tablename__ = "crawl_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "platform", "keyword", "cursor_type", name="uq_crawl_checkpoint_unit"
        ),
    )

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    cursor_type = Column(String(64), nullable=False)
    cursor_value = Column(Text, nullable=True)
    last_publish_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CrawlEvent(Base):
    __tablename__ = "crawl_events"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    stats_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class ResearchCrawlUnit(Base):
    __tablename__ = "research_crawl_units"
    __table_args__ = (
        UniqueConstraint("job_id", "unit_key", name="uq_research_crawl_unit_key"),
    )

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    run_key = Column(String(64), nullable=False, default="default", index=True)
    unit_key = Column(String(96), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    collection_mode = Column(String(32), nullable=False, index=True)
    keyword = Column(String(255), nullable=True, index=True)
    target_id = Column(String(255), nullable=True, index=True)
    creator_id = Column(String(255), nullable=True, index=True)
    status = Column(String(32), nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=100)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    scheduled_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    locked_by = Column(String(128), nullable=True, index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchWorkerHeartbeat(Base):
    __tablename__ = "research_worker_heartbeats"

    id = Column(Integer, primary_key=True)
    worker_id = Column(String(128), nullable=False, unique=True, index=True)
    hostname = Column(String(255), nullable=False)
    pid = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    current_unit_id = Column(Integer, nullable=True, index=True)
    metadata_json = Column(json_column(), nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchPlatformRateLimit(Base):
    __tablename__ = "research_platform_rate_limits"

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, unique=True, index=True)
    requests_per_minute = Column(Integer, nullable=False, default=12)
    min_sleep_seconds = Column(Integer, nullable=False, default=1)
    max_sleep_seconds = Column(Integer, nullable=False, default=5)
    enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchPlatformCapability(Base):
    __tablename__ = "research_platform_capabilities"

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    crawl_search_enabled = Column(Boolean, nullable=False, default=True)
    crawl_creator_enabled = Column(Boolean, nullable=False, default=True)
    crawl_detail_enabled = Column(Boolean, nullable=False, default=True)
    comments_enabled = Column(Boolean, nullable=False, default=True)
    analysis_enabled = Column(Boolean, nullable=False, default=True)
    daily_monitor_enabled = Column(Boolean, nullable=False, default=True)
    keyword_heat_enabled = Column(Boolean, nullable=False, default=True)
    rate_limit_per_minute = Column(Integer, nullable=False, default=12)
    max_daily_jobs = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchGlobalSetting(Base):
    __tablename__ = "research_global_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(128), nullable=False, unique=True, index=True)
    value_json = Column(json_column(), nullable=False, default=dict)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchKeywordSet(Base):
    __tablename__ = "research_keyword_sets"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    platforms = Column(json_column(), nullable=False, default=list)
    keywords = Column(json_column(), nullable=False, default=list)
    negative_keywords = Column(json_column(), nullable=False, default=list)
    synonyms = Column(json_column(), nullable=False, default=list)
    topic = Column(String(255), nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchVertical(Base):
    __tablename__ = "research_verticals"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(128), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchTagGroup(Base):
    __tablename__ = "research_tag_groups"
    __table_args__ = (
        UniqueConstraint("vertical_id", "name", name="uq_research_tag_group_name"),
    )

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=100)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchTagDefinition(Base):
    __tablename__ = "research_tag_definitions"
    __table_args__ = (
        UniqueConstraint("vertical_id", "group_id", "tag_name", name="uq_research_tag_definition"),
    )

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("research_tag_groups.id"), nullable=False, index=True)
    tag_name = Column(String(128), nullable=False, index=True)
    keywords = Column(json_column(), nullable=False, default=list)
    synonyms = Column(json_column(), nullable=False, default=list)
    negative_keywords = Column(json_column(), nullable=False, default=list)
    ai_prompt_hint = Column(Text, nullable=True)
    weight = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchAuthProfile(Base):
    __tablename__ = "research_auth_profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    platform = Column(String(32), nullable=False, index=True)
    login_type = Column(String(32), nullable=False, default="cookie")
    cookies_encrypted = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RawRecord(Base):
    __tablename__ = "raw_records"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    source_type = Column(String(64), nullable=False, index=True)
    source_id = Column(String(255), nullable=True, index=True)
    source_url = Column(Text, nullable=True)
    payload_hash = Column(String(64), nullable=False, index=True)
    payload_json = Column(json_column(), nullable=False)
    fetched_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    parser_version = Column(String(64), nullable=False)


class ResearchAuthor(Base):
    __tablename__ = "research_authors"
    __table_args__ = (
        UniqueConstraint("job_id", "platform", "author_hash", name="uq_research_author"),
    )

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    author_hash = Column(String(96), nullable=False, index=True)
    raw_author_id_encrypted = Column(Text, nullable=True)
    display_name_hash = Column(String(64), nullable=True)
    profile_url_hash = Column(String(64), nullable=True)
    metrics_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchPost(Base):
    __tablename__ = "research_posts"
    __table_args__ = (
        UniqueConstraint("job_id", "platform", "platform_post_id", name="uq_research_post"),
    )

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    platform_post_id = Column(String(255), nullable=False, index=True)
    author_hash = Column(String(96), nullable=True, index=True)
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    publish_time = Column(DateTime(timezone=True), nullable=True, index=True)
    engagement_json = Column(json_column(), nullable=False, default=dict)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchComment(Base):
    __tablename__ = "research_comments"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "platform", "platform_comment_id", name="uq_research_comment"
        ),
    )

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    platform_comment_id = Column(String(255), nullable=False, index=True)
    platform_post_id = Column(String(255), nullable=False, index=True)
    parent_comment_id = Column(String(255), nullable=True, index=True)
    author_hash = Column(String(96), nullable=True, index=True)
    content = Column(Text, nullable=True)
    publish_time = Column(DateTime(timezone=True), nullable=True, index=True)
    like_count = Column(Integer, nullable=True)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchEntityTag(Base):
    __tablename__ = "research_entity_tags"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "platform",
            "vertical_id",
            "tag_id",
            "source",
            "analysis_version",
            name="uq_research_entity_tag",
        ),
    )

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(32), nullable=False, index=True)
    entity_id = Column(String(255), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=False, index=True)
    tag_id = Column(Integer, ForeignKey("research_tag_definitions.id"), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    source = Column(String(32), nullable=False, index=True)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    analysis_version = Column(String(64), nullable=False, default="v1", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchCreatorProfile(Base):
    __tablename__ = "research_creator_profiles"
    __table_args__ = (
        UniqueConstraint("platform", "creator_id", name="uq_research_creator_profile"),
    )

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, index=True)
    creator_id = Column(String(255), nullable=False, index=True)
    display_name = Column(Text, nullable=True)
    profile_url = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    follower_count = Column(Integer, nullable=True)
    following_count = Column(Integer, nullable=True)
    post_count = Column(Integer, nullable=True)
    avg_engagement_rate = Column(Float, nullable=True)
    hot_post_rate = Column(Float, nullable=True)
    recent_post_count_30d = Column(Integer, nullable=False, default=0)
    latest_snapshot_at = Column(DateTime(timezone=True), nullable=True)
    tag_summary_json = Column(json_column(), nullable=False, default=dict)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchCreatorDailySnapshot(Base):
    __tablename__ = "research_creator_daily_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "creator_id",
            "snapshot_date",
            name="uq_research_creator_daily_snapshot",
        ),
    )

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, index=True)
    creator_id = Column(String(255), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    follower_count = Column(Integer, nullable=True)
    total_like_count = Column(Integer, nullable=False, default=0)
    total_comment_count = Column(Integer, nullable=False, default=0)
    total_share_count = Column(Integer, nullable=False, default=0)
    new_post_count = Column(Integer, nullable=False, default=0)
    hot_post_count = Column(Integer, nullable=False, default=0)
    tag_distribution_json = Column(json_column(), nullable=False, default=dict)
    top_posts_json = Column(json_column(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchCreatorCandidate(Base):
    __tablename__ = "research_creator_candidates"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "creator_id",
            "pool_name",
            name="uq_research_creator_candidate",
        ),
    )

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, index=True)
    creator_id = Column(String(255), nullable=False, index=True)
    pool_name = Column(String(128), nullable=False, default="default", index=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    match_score = Column(Float, nullable=True)
    matched_tags_json = Column(json_column(), nullable=False, default=list)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchSearchIntent(Base):
    __tablename__ = "research_search_intents"

    id = Column(Integer, primary_key=True)
    raw_query = Column(Text, nullable=False)
    detected_verticals = Column(json_column(), nullable=False, default=list)
    selected_vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    required_tags = Column(json_column(), nullable=False, default=list)
    optional_tags = Column(json_column(), nullable=False, default=list)
    negative_tags = Column(json_column(), nullable=False, default=list)
    confidence = Column(Float, nullable=False, default=0.0)
    parser_source = Column(String(32), nullable=False, default="rule")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchScenePack(Base):
    __tablename__ = "research_scene_packs"
    __table_args__ = (
        UniqueConstraint("vertical_id", "name", name="uq_research_scene_pack_name"),
    )

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    weight = Column(Float, nullable=False, default=1.0)
    default_platforms = Column(json_column(), nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchScenePackKeyword(Base):
    __tablename__ = "research_scene_pack_keywords"
    __table_args__ = (
        UniqueConstraint(
            "scene_pack_id",
            "keyword",
            "keyword_type",
            name="uq_research_scene_pack_keyword",
        ),
    )

    id = Column(Integer, primary_key=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=False, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    keyword_type = Column(String(32), nullable=False, default="optional", index=True)
    platform = Column(String(32), nullable=True, index=True)
    weight = Column(Float, nullable=False, default=1.0)
    reason = Column(Text, nullable=True)
    usage_flags_json = Column(json_column(), nullable=False, default=list)
    platform_overrides_json = Column(json_column(), nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchAIKeywordSuggestionSession(Base):
    __tablename__ = "research_ai_keyword_suggestion_sessions"

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    seed_keywords_json = Column(json_column(), nullable=False, default=list)
    audience_context = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    provider_config_id = Column(Integer, ForeignKey("ai_provider_configs.id"), nullable=True)
    suggestions_json = Column(json_column(), nullable=False, default=list)
    selected_keywords_json = Column(json_column(), nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchMonitorPool(Base):
    __tablename__ = "research_monitor_pools"
    __table_args__ = (
        UniqueConstraint("name", name="uq_research_monitor_pool_name"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, index=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    scene_pack_ids_json = Column(json_column(), nullable=False, default=list)
    description = Column(Text, nullable=True)
    platforms = Column(json_column(), nullable=False, default=list)
    comment_policy = Column(String(32), nullable=False, default="limited")
    comment_policy_json = Column(json_column(), nullable=False, default=dict)
    schedule_interval_minutes = Column(Integer, nullable=False, default=720)
    automation_mode = Column(String(32), nullable=False, default="confirm_queue")
    auto_top_n = Column(Integer, nullable=False, default=10)
    min_match_score = Column(Float, nullable=False, default=80.0)
    min_recent_posts_30d = Column(Integer, nullable=False, default=3)
    follower_min = Column(Integer, nullable=True)
    follower_max = Column(Integer, nullable=True)
    exclude_existing_creators = Column(Boolean, nullable=False, default=True)
    research_job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchMonitorPoolCreator(Base):
    __tablename__ = "research_monitor_pool_creators"
    __table_args__ = (
        UniqueConstraint(
            "pool_id",
            "platform",
            "creator_id",
            name="uq_research_monitor_pool_creator",
        ),
    )

    id = Column(Integer, primary_key=True)
    pool_id = Column(Integer, ForeignKey("research_monitor_pools.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    creator_id = Column(String(255), nullable=False, index=True)
    display_name = Column(Text, nullable=True)
    source = Column(String(32), nullable=False, default="manual", index=True)
    match_score = Column(Float, nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_crawled_at = Column(DateTime(timezone=True), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    notes = Column(Text, nullable=True)


class ResearchContentSample(Base):
    __tablename__ = "research_content_samples"
    __table_args__ = (
        UniqueConstraint("platform", "content_id", name="uq_research_content_sample"),
    )

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, index=True)
    content_id = Column(String(255), nullable=False, index=True)
    creator_id = Column(String(255), nullable=True, index=True)
    title = Column(Text, nullable=True)
    text_content = Column(Text, nullable=True)
    video_summary = Column(Text, nullable=True)
    content_type = Column(String(32), nullable=True, index=True)
    url = Column(Text, nullable=True)
    publish_time = Column(DateTime(timezone=True), nullable=True, index=True)
    engagement_json = Column(json_column(), nullable=False, default=dict)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchExtractedContentKeyword(Base):
    __tablename__ = "research_extracted_content_keywords"
    __table_args__ = (
        UniqueConstraint(
            "content_sample_id",
            "keyword",
            "source",
            name="uq_research_extracted_content_keyword",
        ),
    )

    id = Column(Integer, primary_key=True)
    content_sample_id = Column(Integer, ForeignKey("research_content_samples.id"), nullable=False, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    keyword_type = Column(String(32), nullable=False, default="detected", index=True)
    score = Column(Float, nullable=False, default=0.0)
    source = Column(String(32), nullable=False, default="rule", index=True)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchSimilarContentCandidate(Base):
    __tablename__ = "research_similar_content_candidates"
    __table_args__ = (
        UniqueConstraint(
            "source_content_sample_id",
            "platform",
            "content_id",
            name="uq_research_similar_content_candidate",
        ),
    )

    id = Column(Integer, primary_key=True)
    source_content_sample_id = Column(
        Integer,
        ForeignKey("research_content_samples.id"),
        nullable=False,
        index=True,
    )
    platform = Column(String(32), nullable=False, index=True)
    content_id = Column(String(255), nullable=False, index=True)
    creator_id = Column(String(255), nullable=True, index=True)
    similarity_score = Column(Float, nullable=False, default=0.0)
    reason = Column(Text, nullable=True)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="candidate", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchContentTracker(Base):
    __tablename__ = "research_content_trackers"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, index=True)
    description = Column(Text, nullable=True)
    source_content_sample_id = Column(
        Integer,
        ForeignKey("research_content_samples.id"),
        nullable=True,
        index=True,
    )
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    scene_pack_ids_json = Column(json_column(), nullable=False, default=list)
    platforms = Column(json_column(), nullable=False, default=list)
    keywords_json = Column(json_column(), nullable=False, default=list)
    included_keywords_json = Column(json_column(), nullable=False, default=list)
    excluded_keywords_json = Column(json_column(), nullable=False, default=list)
    seed_refs_json = Column(json_column(), nullable=False, default=list)
    comment_policy_json = Column(json_column(), nullable=False, default=dict)
    tracking_mode = Column(String(32), nullable=False, default="mixed", index=True)
    schedule_interval_minutes = Column(Integer, nullable=False, default=720)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchContentTrackingSnapshot(Base):
    __tablename__ = "research_content_tracking_snapshots"

    id = Column(Integer, primary_key=True)
    tracker_id = Column(Integer, ForeignKey("research_content_trackers.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    platform = Column(String(32), nullable=True, index=True)
    keyword_distribution_json = Column(json_column(), nullable=False, default=dict)
    tag_distribution_json = Column(json_column(), nullable=False, default=dict)
    content_type_distribution_json = Column(json_column(), nullable=False, default=dict)
    publish_time_distribution_json = Column(json_column(), nullable=False, default=dict)
    hot_post_rate = Column(Float, nullable=False, default=0.0)
    total_content_count = Column(Integer, nullable=False, default=0)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchKeywordHeatSnapshot(Base):
    __tablename__ = "research_keyword_heat_snapshots"

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    heat_score = Column(Float, nullable=False, default=0.0)
    growth_score = Column(Float, nullable=False, default=0.0)
    push_signal_score = Column(Float, nullable=False, default=0.0)
    limit_signal_score = Column(Float, nullable=False, default=0.0)
    platform_signal = Column(String(64), nullable=False, default="normal_fluctuation")
    evidence_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchCompetitorCompositionSnapshot(Base):
    __tablename__ = "research_competitor_composition_snapshots"

    id = Column(Integer, primary_key=True)
    competitor_id = Column(
        Integer,
        ForeignKey("research_competitor_accounts.id"),
        nullable=False,
        index=True,
    )
    snapshot_date = Column(Date, nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    total_flow_count = Column(Integer, nullable=False, default=0)
    keyword_distribution_json = Column(json_column(), nullable=False, default=dict)
    tag_distribution_json = Column(json_column(), nullable=False, default=dict)
    content_type_distribution_json = Column(json_column(), nullable=False, default=dict)
    publish_time_distribution_json = Column(json_column(), nullable=False, default=dict)
    hot_post_rate = Column(Float, nullable=False, default=0.0)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchOpportunityFeedback(Base):
    __tablename__ = "research_opportunity_feedback"

    id = Column(Integer, primary_key=True)
    opportunity_id = Column(String(255), nullable=False, index=True)
    opportunity_type = Column(String(32), nullable=True, index=True)
    opportunity_name = Column(Text, nullable=True)
    feedback = Column(String(32), nullable=False, index=True)
    note = Column(Text, nullable=True)
    payload_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class ResearchCompetitorAccount(Base):
    __tablename__ = "research_competitor_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "creator_id", name="uq_research_competitor_account"),
    )

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, index=True)
    creator_id = Column(String(255), nullable=False, index=True)
    display_name = Column(Text, nullable=True)
    profile_url = Column(Text, nullable=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchBacktest(Base):
    __tablename__ = "research_backtests"

    id = Column(Integer, primary_key=True)
    scenario = Column(String(255), nullable=False, index=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    keywords_json = Column(json_column(), nullable=False, default=list)
    platforms_json = Column(json_column(), nullable=False, default=list)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    use_local_data = Column(Boolean, nullable=False, default=True)
    use_tikhub_backfill = Column(Boolean, nullable=False, default=False)
    replay_daily = Column(Boolean, nullable=False, default=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    research_job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=True, index=True)
    report_json = Column(json_column(), nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchAIInsightRun(Base):
    __tablename__ = "research_ai_insight_runs"

    id = Column(Integer, primary_key=True)
    provider_config_id = Column(Integer, ForeignKey("ai_provider_configs.id"), nullable=True, index=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    platforms_json = Column(json_column(), nullable=False, default=list)
    window_days = Column(Integer, nullable=False, default=7)
    status = Column(String(32), nullable=False, default="pending", index=True)
    input_summary_json = Column(json_column(), nullable=False, default=dict)
    output_json = Column(json_column(), nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    model = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchAIHotspot(Base):
    __tablename__ = "research_ai_hotspots"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("research_ai_insight_runs.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    platform = Column(String(32), nullable=False, default="all", index=True)
    heat_level = Column(String(32), nullable=False, default="watch")
    confidence = Column(String(32), nullable=False, default="low")
    reason = Column(Text, nullable=False)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    platform_strategy_json = Column(json_column(), nullable=False, default=dict)
    risk_notes_json = Column(json_column(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class ResearchAITopicIdea(Base):
    __tablename__ = "research_ai_topic_ideas"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("research_ai_insight_runs.id"), nullable=False, index=True)
    title = Column(Text, nullable=False)
    platform = Column(String(32), nullable=False, index=True)
    target_audience = Column(Text, nullable=True)
    keywords_json = Column(json_column(), nullable=False, default=list)
    content_angle = Column(Text, nullable=True)
    outline_json = Column(json_column(), nullable=False, default=list)
    reason = Column(Text, nullable=False)
    evidence_json = Column(json_column(), nullable=False, default=dict)
    risk_notes_json = Column(json_column(), nullable=False, default=list)
    expected_effect = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class ResearchAccountProfile(Base):
    __tablename__ = "research_account_profiles"
    __table_args__ = (
        UniqueConstraint("platform", "account_id", name="uq_research_account_profile"),
    )

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False, index=True)
    account_id = Column(String(255), nullable=False, index=True)
    sec_account_id = Column(String(255), nullable=True, index=True)
    display_name = Column(Text, nullable=True)
    avatar_url = Column(Text, nullable=True)
    profile_url = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    verified = Column(Boolean, nullable=False, default=False)
    region = Column(String(128), nullable=True, index=True)
    follower_count = Column(Integer, nullable=True)
    following_count = Column(Integer, nullable=True)
    post_count = Column(Integer, nullable=True)
    avg_engagement_rate = Column(Float, nullable=True)
    hot_post_rate = Column(Float, nullable=True)
    recent_post_count_30d = Column(Integer, nullable=True)
    latest_post_time = Column(DateTime(timezone=True), nullable=True)
    contact_clues_json = Column(json_column(), nullable=False, default=list)
    tag_summary_json = Column(json_column(), nullable=False, default=dict)
    last_crawled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchAccountRole(Base):
    __tablename__ = "research_account_roles"
    __table_args__ = (
        UniqueConstraint(
            "account_profile_id",
            "role",
            "vertical_id",
            "scene_pack_id",
            "monitor_pool_id",
            name="uq_research_account_role_scope",
        ),
    )

    id = Column(Integer, primary_key=True)
    account_profile_id = Column(
        Integer,
        ForeignKey("research_account_profiles.id"),
        nullable=False,
        index=True,
    )
    role = Column(String(64), nullable=False, index=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=True, index=True)
    scene_pack_id = Column(Integer, ForeignKey("research_scene_packs.id"), nullable=True, index=True)
    monitor_pool_id = Column(Integer, ForeignKey("research_monitor_pools.id"), nullable=True, index=True)
    source = Column(String(64), nullable=False, default="manual", index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ResearchKeywordOpportunitySnapshot(Base):
    __tablename__ = "research_keyword_opportunity_snapshots"

    id = Column(Integer, primary_key=True)
    vertical_id = Column(Integer, ForeignKey("research_verticals.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=True, index=True)
    tag_id = Column(Integer, ForeignKey("research_tag_definitions.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    heat_score = Column(Float, nullable=False, default=0.0)
    growth_score = Column(Float, nullable=False, default=0.0)
    competition_score = Column(Float, nullable=False, default=0.0)
    supply_gap_score = Column(Float, nullable=False, default=0.0)
    platform_signal = Column(String(64), nullable=False, default="normal_fluctuation")
    evidence_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    base_url = Column(Text, nullable=False)
    api_key_encrypted = Column(Text, nullable=False)
    model = Column(String(200), nullable=False)
    timeout = Column(Integer, nullable=False, default=60)
    max_concurrency = Column(Integer, nullable=False, default=2)
    default_params_json = Column(json_column(), nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIPromptTemplate(Base):
    __tablename__ = "ai_prompt_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    task_type = Column(String(64), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    prompt_text = Column(Text, nullable=False)
    output_schema_json = Column(json_column(), nullable=False, default=dict)
    version = Column(String(64), nullable=False, default="v1")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIAnalysisJob(Base):
    __tablename__ = "ai_analysis_jobs"

    id = Column(Integer, primary_key=True)
    research_job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    task_type = Column(String(64), nullable=False, index=True)
    scope = Column(json_column(), nullable=False, default=dict)
    status = Column(String(32), nullable=False, index=True)
    provider_config_id = Column(Integer, ForeignKey("ai_provider_configs.id"), nullable=False)
    prompt_template_id = Column(Integer, ForeignKey("ai_prompt_templates.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AIAnalysisResult(Base):
    __tablename__ = "ai_analysis_results"

    id = Column(Integer, primary_key=True)
    analysis_job_id = Column(Integer, ForeignKey("ai_analysis_jobs.id"), nullable=False, index=True)
    target_type = Column(String(32), nullable=False, index=True)
    target_id = Column(String(255), nullable=False, index=True)
    result_json = Column(json_column(), nullable=False)
    model = Column(String(200), nullable=False)
    prompt_version = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

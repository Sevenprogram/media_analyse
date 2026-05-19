from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
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
    keywords = Column(json_column(), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    comment_policy = Column(json_column(), nullable=False)
    raw_record_mode = Column(String(32), nullable=False)
    anonymize_authors = Column(Boolean, nullable=False, default=True)
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

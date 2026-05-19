# Research Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable research layer for MediaCrawler with reproducible Weibo/Zhihu research jobs, normalized storage, anonymization, AI configuration, chart statistics, and exports.

**Architecture:** Keep the existing platform crawlers intact and add a `research/` package plus `api/routers/research.py`. The first implementation creates the data contracts, persistence services, reporting/chart statistics, and API surface; crawler adapters can then plug into the runner without rewriting platform modules.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy async ORM, PostgreSQL/SQLite, pytest, pandas/openpyxl for export, matplotlib for static chart image generation.

---

## File Structure

- Create `research/__init__.py`: marks the research package.
- Create `research/enums.py`: central string constants for statuses, platforms, comment modes, raw record modes, AI task types, and export formats.
- Create `research/schemas.py`: Pydantic request/response models for research jobs, AI provider config, analysis jobs, chart responses, and exports.
- Create `research/anonymizer.py`: HMAC hashing helpers for author/user identifiers.
- Create `research/models.py`: SQLAlchemy ORM tables for the research layer.
- Modify `database/models.py`: import research ORM models so `Base.metadata.create_all()` creates the new tables.
- Create `research/repository.py`: async database operations for jobs, events, checkpoints, normalized records, AI configs, and AI results.
- Create `research/service.py`: orchestration logic for creating jobs, validating guardrails, updating status, and returning summaries.
- Create `research/charts.py`: SQL-backed chart/statistics builders for WebUI and export.
- Create `research/exporter.py`: exports CSV, JSONL, Excel, Markdown report, and static chart PNG/SVG files.
- Create `research/ai_provider.py`: OpenAI-compatible provider client and connection test logic.
- Create `api/routers/research.py`: HTTP API for jobs, AI config, analysis jobs, charts, and exports.
- Modify `api/main.py`: register the research router.
- Create `tests/test_research_anonymizer.py`: deterministic anonymization tests.
- Create `tests/test_research_schemas.py`: validation and guardrail tests.
- Create `tests/test_research_charts.py`: chart aggregation tests using in-memory records.
- Create `tests/test_research_exporter.py`: export file layout tests using temporary directories.

## Task 1: Research Constants and Schemas

**Files:**
- Create: `research/__init__.py`
- Create: `research/enums.py`
- Create: `research/schemas.py`
- Test: `tests/test_research_schemas.py`

- [ ] **Step 1: Write schema validation tests**

Create `tests/test_research_schemas.py`:

```python
from datetime import date

import pytest
from pydantic import ValidationError

from research.schemas import CommentPolicy, ResearchJobCreate


def test_research_job_requires_supported_platforms():
    request = ResearchJobCreate(
        name="Policy debate",
        topic="urban governance",
        platforms=["wb", "zhihu"],
        keywords=["公共政策", "城市治理"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        comment_policy=CommentPolicy.default(),
    )

    assert request.platforms == ["wb", "zhihu"]


def test_research_job_rejects_unsupported_platform():
    with pytest.raises(ValidationError, match="Unsupported platform"):
        ResearchJobCreate(
            name="Bad platform",
            topic="topic",
            platforms=["bili"],
            keywords=["topic"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            comment_policy=CommentPolicy.default(),
        )


def test_research_job_rejects_reversed_time_window():
    with pytest.raises(ValidationError, match="end_date must be on or after start_date"):
        ResearchJobCreate(
            name="Bad dates",
            topic="topic",
            platforms=["wb"],
            keywords=["topic"],
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
            comment_policy=CommentPolicy.default(),
        )


def test_full_comment_policy_requires_guardrails():
    with pytest.raises(ValidationError, match="max_posts_per_job or stop_after_hours"):
        ResearchJobCreate(
            name="Full comments",
            topic="topic",
            platforms=["wb"],
            keywords=["topic"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            comment_policy=CommentPolicy.full(rate_limit_per_minute=30),
        )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_research_schemas.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'research'`.

- [ ] **Step 3: Add package and constants**

Create `research/__init__.py`:

```python
"""Research workflow extensions for MediaCrawler."""
```

Create `research/enums.py`:

```python
from typing import Final

SUPPORTED_RESEARCH_PLATFORMS: Final[set[str]] = {"wb", "zhihu"}

JOB_PENDING: Final[str] = "pending"
JOB_RUNNING: Final[str] = "running"
JOB_PAUSED: Final[str] = "paused"
JOB_FAILED: Final[str] = "failed"
JOB_COMPLETED: Final[str] = "completed"
JOB_CANCELLED: Final[str] = "cancelled"
JOB_STATUSES: Final[set[str]] = {
    JOB_PENDING,
    JOB_RUNNING,
    JOB_PAUSED,
    JOB_FAILED,
    JOB_COMPLETED,
    JOB_CANCELLED,
}

RAW_MINIMAL: Final[str] = "minimal"
RAW_FULL: Final[str] = "full"
RAW_RECORD_MODES: Final[set[str]] = {RAW_MINIMAL, RAW_FULL}

AI_TASK_TYPES: Final[set[str]] = {
    "sentiment",
    "stance",
    "topic_tags",
    "summary",
    "controversy_points",
    "argument_structure",
    "comment_digest",
}
```

- [ ] **Step 4: Add Pydantic schemas**

Create `research/schemas.py`:

```python
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from research.enums import AI_TASK_TYPES, RAW_MINIMAL, RAW_RECORD_MODES, SUPPORTED_RESEARCH_PLATFORMS


class CommentPolicy(BaseModel):
    enable_comments: bool = True
    comment_limit_per_post: int | None = Field(default=100, ge=1)
    enable_sub_comments: bool = False
    sub_comment_limit_per_comment: int | None = Field(default=0, ge=0)
    full_comment_crawl: bool = False
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    max_posts_per_job: int | None = Field(default=None, ge=1)
    stop_after_hours: int | None = Field(default=None, ge=1)
    ethical_note: str | None = None

    @classmethod
    def default(cls) -> "CommentPolicy":
        return cls()

    @classmethod
    def full(
        cls,
        *,
        rate_limit_per_minute: int,
        max_posts_per_job: int | None = None,
        stop_after_hours: int | None = None,
        ethical_note: str | None = None,
    ) -> "CommentPolicy":
        return cls(
            enable_comments=True,
            comment_limit_per_post=None,
            enable_sub_comments=True,
            sub_comment_limit_per_comment=None,
            full_comment_crawl=True,
            rate_limit_per_minute=rate_limit_per_minute,
            max_posts_per_job=max_posts_per_job,
            stop_after_hours=stop_after_hours,
            ethical_note=ethical_note,
        )

    @model_validator(mode="after")
    def validate_full_comment_guardrails(self) -> "CommentPolicy":
        if not self.full_comment_crawl:
            return self
        if not self.rate_limit_per_minute:
            raise ValueError("full_comment_crawl requires rate_limit_per_minute")
        if not self.max_posts_per_job and not self.stop_after_hours:
            raise ValueError("full_comment_crawl requires max_posts_per_job or stop_after_hours")
        if not self.ethical_note:
            raise ValueError("full_comment_crawl requires ethical_note")
        return self


class ResearchJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=500)
    platforms: list[str] = Field(min_length=1)
    keywords: list[str] = Field(min_length=1)
    start_date: date
    end_date: date
    comment_policy: CommentPolicy = Field(default_factory=CommentPolicy.default)
    raw_record_mode: Literal["minimal", "full"] = RAW_MINIMAL
    anonymize_authors: bool = True

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value

    @field_validator("keywords")
    @classmethod
    def strip_keywords(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("keywords must contain at least one non-empty value")
        return cleaned

    @field_validator("raw_record_mode")
    @classmethod
    def validate_raw_record_mode(cls, value: str) -> str:
        if value not in RAW_RECORD_MODES:
            raise ValueError(f"Unsupported raw_record_mode: {value}")
        return value

    @model_validator(mode="after")
    def validate_date_window(self) -> "ResearchJobCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ResearchJobRead(BaseModel):
    id: int
    name: str
    topic: str
    platforms: list[str]
    keywords: list[str]
    start_date: date
    end_date: date
    status: str
    comment_policy: dict[str, Any]
    raw_record_mode: str
    anonymize_authors: bool
    created_at: datetime
    updated_at: datetime


class AIProviderConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1, max_length=200)
    timeout: int = Field(default=60, ge=1)
    max_concurrency: int = Field(default=2, ge=1, le=20)
    default_params: dict[str, Any] = Field(default_factory=lambda: {"temperature": 0.2, "max_tokens": 1000})
    enabled: bool = True


class AIAnalysisJobCreate(BaseModel):
    research_job_id: int
    task_type: str
    scope: dict[str, Any] = Field(default_factory=dict)
    provider_config_id: int
    prompt_template_id: int

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str) -> str:
        if value not in AI_TASK_TYPES:
            raise ValueError(f"Unsupported AI task type: {value}")
        return value
```

- [ ] **Step 5: Run schema tests**

Run:

```bash
pytest tests/test_research_schemas.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add research/__init__.py research/enums.py research/schemas.py tests/test_research_schemas.py
git commit -m "feat: add research schemas"
```

## Task 2: Anonymization Helpers

**Files:**
- Create: `research/anonymizer.py`
- Test: `tests/test_research_anonymizer.py`

- [ ] **Step 1: Write anonymizer tests**

Create `tests/test_research_anonymizer.py`:

```python
import pytest

from research.anonymizer import hash_author_id, hash_optional_text


def test_hash_author_id_is_deterministic_for_same_platform_and_salt():
    first = hash_author_id(platform="wb", raw_author_id="12345", salt="test-salt")
    second = hash_author_id(platform="wb", raw_author_id="12345", salt="test-salt")

    assert first == second
    assert first.startswith("wb_")


def test_hash_author_id_changes_by_platform():
    wb_hash = hash_author_id(platform="wb", raw_author_id="12345", salt="test-salt")
    zhihu_hash = hash_author_id(platform="zhihu", raw_author_id="12345", salt="test-salt")

    assert wb_hash != zhihu_hash


def test_hash_author_id_requires_salt():
    with pytest.raises(ValueError, match="salt is required"):
        hash_author_id(platform="wb", raw_author_id="12345", salt="")


def test_hash_optional_text_keeps_none_as_none():
    assert hash_optional_text(None, salt="test-salt") is None
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/test_research_anonymizer.py -v
```

Expected: FAIL with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: Implement anonymizer**

Create `research/anonymizer.py`:

```python
import hashlib
import hmac


def _digest(value: str, *, salt: str) -> str:
    if not salt:
        raise ValueError("salt is required for anonymization")
    return hmac.new(salt.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_author_id(*, platform: str, raw_author_id: str, salt: str) -> str:
    if not raw_author_id:
        raise ValueError("raw_author_id is required")
    digest = _digest(f"{platform}:{raw_author_id}", salt=salt)
    return f"{platform}_{digest[:32]}"


def hash_optional_text(value: str | None, *, salt: str) -> str | None:
    if value is None:
        return None
    if value == "":
        return ""
    return _digest(value, salt=salt)[:32]
```

- [ ] **Step 4: Run anonymizer tests**

Run:

```bash
pytest tests/test_research_anonymizer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add research/anonymizer.py tests/test_research_anonymizer.py
git commit -m "feat: add research anonymization helpers"
```

## Task 3: Research ORM Models

**Files:**
- Create: `research/models.py`
- Modify: `database/models.py`
- Test: `tests/test_research_models.py`

- [ ] **Step 1: Write metadata tests**

Create `tests/test_research_models.py`:

```python
from database.models import Base


def test_research_tables_are_registered_with_base_metadata():
    expected = {
        "research_jobs",
        "crawl_checkpoints",
        "crawl_events",
        "raw_records",
        "research_authors",
        "research_posts",
        "research_comments",
        "ai_provider_configs",
        "ai_prompt_templates",
        "ai_analysis_jobs",
        "ai_analysis_results",
    }

    assert expected.issubset(set(Base.metadata.tables))
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_research_models.py -v
```

Expected: FAIL because research tables are not registered.

- [ ] **Step 3: Add research ORM models**

Create `research/models.py`:

```python
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from database.models import Base


def json_column():
    return JSON().with_variant(JSONB, "postgresql")


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id = Column(Integer, primary_key=True)
```

Replace the incomplete class body above with this complete file:

```python
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Column
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
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class CrawlCheckpoint(Base):
    __tablename__ = "crawl_checkpoints"
    __table_args__ = (UniqueConstraint("job_id", "platform", "keyword", "cursor_type", name="uq_crawl_checkpoint_unit"),)

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=False, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    cursor_type = Column(String(64), nullable=False)
    cursor_value = Column(Text, nullable=True)
    last_publish_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class CrawlEvent(Base):
    __tablename__ = "crawl_events"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("research_jobs.id"), nullable=False, index=True)
    platform = Column(String(32), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    stats_json = Column(json_column(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


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
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    parser_version = Column(String(64), nullable=False)


class ResearchAuthor(Base):
    __tablename__ = "research_authors"
    __table_args__ = (UniqueConstraint("job_id", "platform", "author_hash", name="uq_research_author"),)

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
    __table_args__ = (UniqueConstraint("job_id", "platform", "platform_post_id", name="uq_research_post"),)

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
    __table_args__ = (UniqueConstraint("job_id", "platform", "platform_comment_id", name="uq_research_comment"),)

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
```

- [ ] **Step 4: Register models with Base metadata**

Append this import near the bottom of `database/models.py` after all model class definitions:

```python
# Import research extension models so Base.metadata includes them during init_db.
import research.models  # noqa: E402,F401
```

- [ ] **Step 5: Run model test**

Run:

```bash
pytest tests/test_research_models.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add research/models.py database/models.py tests/test_research_models.py
git commit -m "feat: add research database models"
```

## Task 4: Repository and Job Service

**Files:**
- Create: `research/repository.py`
- Create: `research/service.py`
- Test: `tests/test_research_service.py`

- [ ] **Step 1: Write service tests using a fake repository**

Create `tests/test_research_service.py`:

```python
from datetime import date

import pytest

from research.schemas import CommentPolicy, ResearchJobCreate
from research.service import ResearchJobService


class FakeResearchRepository:
    def __init__(self):
        self.created_payload = None

    async def create_job(self, payload):
        self.created_payload = payload
        return {
            "id": 1,
            **payload,
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }


@pytest.mark.asyncio
async def test_create_job_persists_pending_job_payload():
    repo = FakeResearchRepository()
    service = ResearchJobService(repo)
    request = ResearchJobCreate(
        name="Policy debate",
        topic="urban governance",
        platforms=["wb", "zhihu"],
        keywords=["公共政策"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        comment_policy=CommentPolicy.default(),
    )

    result = await service.create_job(request)

    assert result["status"] == "pending"
    assert repo.created_payload["platforms"] == ["wb", "zhihu"]
    assert repo.created_payload["comment_policy"]["comment_limit_per_post"] == 100
```

- [ ] **Step 2: Run service test and verify failure**

Run:

```bash
pytest tests/test_research_service.py -v
```

Expected: FAIL because `research.service` does not exist.

- [ ] **Step 3: Implement repository**

Create `research/repository.py`:

```python
from typing import Any

from sqlalchemy import select

from database.db_session import get_session
from research.models import ResearchJob


class ResearchRepository:
    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with get_session() as session:
            job = ResearchJob(**payload)
            session.add(job)
            await session.flush()
            await session.refresh(job)
            return self._job_to_dict(job)

    async def list_jobs(self) -> list[dict[str, Any]]:
        async with get_session() as session:
            result = await session.execute(select(ResearchJob).order_by(ResearchJob.created_at.desc()))
            return [self._job_to_dict(job) for job in result.scalars().all()]

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            job = await session.get(ResearchJob, job_id)
            if job is None:
                return None
            return self._job_to_dict(job)

    def _job_to_dict(self, job: ResearchJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "name": job.name,
            "topic": job.topic,
            "platforms": job.platforms,
            "keywords": job.keywords,
            "start_date": job.start_date,
            "end_date": job.end_date,
            "status": job.status,
            "comment_policy": job.comment_policy,
            "raw_record_mode": job.raw_record_mode,
            "anonymize_authors": job.anonymize_authors,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
```

- [ ] **Step 4: Implement service**

Create `research/service.py`:

```python
from typing import Any, Protocol

from research.enums import JOB_PENDING
from research.schemas import ResearchJobCreate


class JobRepository(Protocol):
    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def list_jobs(self) -> list[dict[str, Any]]:
        ...

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        ...


class ResearchJobService:
    def __init__(self, repository: JobRepository):
        self.repository = repository

    async def create_job(self, request: ResearchJobCreate) -> dict[str, Any]:
        payload = request.model_dump(mode="python")
        payload["comment_policy"] = request.comment_policy.model_dump(mode="json")
        payload["status"] = JOB_PENDING
        return await self.repository.create_job(payload)

    async def list_jobs(self) -> list[dict[str, Any]]:
        return await self.repository.list_jobs()

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        return await self.repository.get_job(job_id)
```

- [ ] **Step 5: Run service tests**

Run:

```bash
pytest tests/test_research_service.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add research/repository.py research/service.py tests/test_research_service.py
git commit -m "feat: add research job service"
```

## Task 5: Research API Router

**Files:**
- Create: `api/routers/research.py`
- Modify: `api/main.py`
- Test: `tests/test_research_api.py`

- [ ] **Step 1: Write API route tests**

Create `tests/test_research_api.py`:

```python
from fastapi.testclient import TestClient

from api.main import app


def test_research_health_route():
    client = TestClient(app)
    response = client.get("/api/research/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "research"}


def test_research_job_validation_runs_before_persistence():
    client = TestClient(app)
    response = client.post(
        "/api/research/jobs",
        json={
            "name": "Bad platform",
            "topic": "topic",
            "platforms": ["bili"],
            "keywords": ["topic"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "comment_policy": {"enable_comments": True},
        },
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```bash
pytest tests/test_research_api.py -v
```

Expected: FAIL because `/api/research/health` is not registered.

- [ ] **Step 3: Add research router**

Create `api/routers/research.py`:

```python
from fastapi import APIRouter, HTTPException

from research.repository import ResearchRepository
from research.schemas import ResearchJobCreate
from research.service import ResearchJobService

router = APIRouter(prefix="/research", tags=["research"])


def get_service() -> ResearchJobService:
    return ResearchJobService(ResearchRepository())


@router.get("/health")
async def research_health():
    return {"status": "ok", "module": "research"}


@router.post("/jobs")
async def create_research_job(request: ResearchJobCreate):
    service = get_service()
    return await service.create_job(request)


@router.get("/jobs")
async def list_research_jobs():
    service = get_service()
    return {"jobs": await service.list_jobs()}


@router.get("/jobs/{job_id}")
async def get_research_job(job_id: int):
    service = get_service()
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job
```

- [ ] **Step 4: Register router in API main**

Modify `api/main.py` imports:

```python
from .routers import crawler_router, data_router, websocket_router
from .routers.research import router as research_router
```

Add this after existing router registrations:

```python
app.include_router(research_router, prefix="/api")
```

- [ ] **Step 5: Run API tests**

Run:

```bash
pytest tests/test_research_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/main.py api/routers/research.py tests/test_research_api.py
git commit -m "feat: expose research API routes"
```

## Task 6: Chart Statistics

**Files:**
- Create: `research/charts.py`
- Test: `tests/test_research_charts.py`

- [ ] **Step 1: Write pure aggregation tests**

Create `tests/test_research_charts.py`:

```python
from datetime import datetime, timezone

from research.charts import build_platform_counts, build_daily_post_trend


def test_build_platform_counts_counts_posts_and_comments():
    posts = [{"platform": "wb"}, {"platform": "wb"}, {"platform": "zhihu"}]
    comments = [{"platform": "wb"}, {"platform": "zhihu"}, {"platform": "zhihu"}]

    result = build_platform_counts(posts, comments)

    assert result == [
        {"platform": "wb", "posts": 2, "comments": 1},
        {"platform": "zhihu", "posts": 1, "comments": 2},
    ]


def test_build_daily_post_trend_groups_by_date():
    posts = [
        {"publish_time": datetime(2026, 1, 1, 8, tzinfo=timezone.utc)},
        {"publish_time": datetime(2026, 1, 1, 9, tzinfo=timezone.utc)},
        {"publish_time": datetime(2026, 1, 2, 9, tzinfo=timezone.utc)},
        {"publish_time": None},
    ]

    result = build_daily_post_trend(posts)

    assert result == [
        {"date": "2026-01-01", "posts": 2},
        {"date": "2026-01-02", "posts": 1},
    ]
```

- [ ] **Step 2: Run chart tests and verify failure**

Run:

```bash
pytest tests/test_research_charts.py -v
```

Expected: FAIL because `research.charts` does not exist.

- [ ] **Step 3: Implement aggregation helpers**

Create `research/charts.py`:

```python
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


def build_platform_counts(posts: list[dict[str, Any]], comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    post_counts = Counter(item["platform"] for item in posts)
    comment_counts = Counter(item["platform"] for item in comments)
    platforms = sorted(set(post_counts) | set(comment_counts))
    return [
        {
            "platform": platform,
            "posts": post_counts.get(platform, 0),
            "comments": comment_counts.get(platform, 0),
        }
        for platform in platforms
    ]


def build_daily_post_trend(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = defaultdict(int)
    for post in posts:
        publish_time = post.get("publish_time")
        if not isinstance(publish_time, datetime):
            continue
        counts[publish_time.date().isoformat()] += 1
    return [{"date": date, "posts": counts[date]} for date in sorted(counts)]
```

- [ ] **Step 4: Run chart tests**

Run:

```bash
pytest tests/test_research_charts.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add research/charts.py tests/test_research_charts.py
git commit -m "feat: add research chart aggregations"
```

## Task 7: Exporter Skeleton

**Files:**
- Create: `research/exporter.py`
- Test: `tests/test_research_exporter.py`

- [ ] **Step 1: Write export tests**

Create `tests/test_research_exporter.py`:

```python
from pathlib import Path

from research.exporter import ResearchExporter


def test_exporter_creates_report_and_csv_files(tmp_path: Path):
    exporter = ResearchExporter(base_dir=tmp_path)
    result = exporter.export_job(
        job_id=7,
        job_summary={
            "name": "Policy debate",
            "platforms": ["wb", "zhihu"],
            "keywords": ["公共政策"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        },
        posts=[{"platform": "wb", "platform_post_id": "p1", "content": "hello"}],
        comments=[{"platform": "wb", "platform_comment_id": "c1", "content": "comment"}],
        authors=[{"platform": "wb", "author_hash": "wb_abc"}],
        ai_results=[{"target_id": "p1", "result_json": {"stance": "support"}}],
        charts=[],
    )

    export_dir = tmp_path / "research_job_7"
    assert result["export_dir"] == str(export_dir)
    assert (export_dir / "posts.csv").exists()
    assert (export_dir / "comments.csv").exists()
    assert (export_dir / "authors.csv").exists()
    assert (export_dir / "ai_results.jsonl").exists()
    assert (export_dir / "job_report.md").exists()
```

- [ ] **Step 2: Run exporter tests and verify failure**

Run:

```bash
pytest tests/test_research_exporter.py -v
```

Expected: FAIL because `research.exporter` does not exist.

- [ ] **Step 3: Implement exporter**

Create `research/exporter.py`:

```python
import csv
import json
from pathlib import Path
from typing import Any


class ResearchExporter:
    def __init__(self, base_dir: Path | str = "exports"):
        self.base_dir = Path(base_dir)

    def export_job(
        self,
        *,
        job_id: int,
        job_summary: dict[str, Any],
        posts: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        authors: list[dict[str, Any]],
        ai_results: list[dict[str, Any]],
        charts: list[Path],
    ) -> dict[str, Any]:
        export_dir = self.base_dir / f"research_job_{job_id}"
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "charts").mkdir(exist_ok=True)

        self._write_csv(export_dir / "posts.csv", posts)
        self._write_csv(export_dir / "comments.csv", comments)
        self._write_csv(export_dir / "authors.csv", authors)
        self._write_jsonl(export_dir / "ai_results.jsonl", ai_results)
        self._write_report(export_dir / "job_report.md", job_summary, posts, comments, authors, ai_results, charts)

        return {"export_dir": str(export_dir)}

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = sorted({key for row in rows for key in row})
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def _write_report(
        self,
        path: Path,
        job_summary: dict[str, Any],
        posts: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        authors: list[dict[str, Any]],
        ai_results: list[dict[str, Any]],
        charts: list[Path],
    ) -> None:
        lines = [
            f"# Research Job Report: {job_summary['name']}",
            "",
            f"- Platforms: {', '.join(job_summary['platforms'])}",
            f"- Keywords: {', '.join(job_summary['keywords'])}",
            f"- Time window: {job_summary['start_date']} to {job_summary['end_date']}",
            f"- Posts: {len(posts)}",
            f"- Comments: {len(comments)}",
            f"- Authors: {len(authors)}",
            f"- AI results: {len(ai_results)}",
            "",
            "## Charts",
        ]
        lines.extend(f"- charts/{chart.name}" for chart in charts)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run exporter tests**

Run:

```bash
pytest tests/test_research_exporter.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add research/exporter.py tests/test_research_exporter.py
git commit -m "feat: add research exporter"
```

## Task 8: OpenAI-Compatible Provider Client

**Files:**
- Create: `research/ai_provider.py`
- Test: `tests/test_research_ai_provider.py`

- [ ] **Step 1: Write provider URL tests**

Create `tests/test_research_ai_provider.py`:

```python
from research.ai_provider import build_chat_completions_url


def test_build_chat_completions_url_adds_v1_path():
    assert build_chat_completions_url("https://example.com") == "https://example.com/v1/chat/completions"


def test_build_chat_completions_url_does_not_duplicate_path():
    assert build_chat_completions_url("https://example.com/v1") == "https://example.com/v1/chat/completions"
```

- [ ] **Step 2: Run AI provider tests and verify failure**

Run:

```bash
pytest tests/test_research_ai_provider.py -v
```

Expected: FAIL because `research.ai_provider` does not exist.

- [ ] **Step 3: Implement provider URL helper and client skeleton**

Create `research/ai_provider.py`:

```python
from typing import Any

import httpx


def build_chat_completions_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1"):
        return f"{clean}/chat/completions"
    return f"{clean}/v1/chat/completions"


class OpenAICompatibleProvider:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def chat_json(self, *, messages: list[dict[str, str]], params: dict[str, Any]) -> dict[str, Any]:
        payload = {"model": self.model, "messages": messages, **params}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(build_chat_completions_url(self.base_url), headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def test_connection(self) -> dict[str, Any]:
        response = await self.chat_json(
            messages=[{"role": "user", "content": "Return JSON: {\"ok\": true}"}],
            params={"temperature": 0, "max_tokens": 20},
        )
        return {"ok": True, "response": response}
```

- [ ] **Step 4: Run AI provider tests**

Run:

```bash
pytest tests/test_research_ai_provider.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add research/ai_provider.py tests/test_research_ai_provider.py
git commit -m "feat: add OpenAI-compatible AI provider"
```

## Task 9: Integrate Research Routes for Charts and Export

**Files:**
- Modify: `api/routers/research.py`
- Test: `tests/test_research_api.py`

- [ ] **Step 1: Extend API tests for chart route**

Append to `tests/test_research_api.py`:

```python
def test_research_chart_kinds_route():
    client = TestClient(app)
    response = client.get("/api/research/charts/kinds")

    assert response.status_code == 200
    assert "platform_counts" in response.json()["kinds"]
    assert "sentiment_distribution" in response.json()["kinds"]
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```bash
pytest tests/test_research_api.py -v
```

Expected: FAIL because `/api/research/charts/kinds` is not registered.

- [ ] **Step 3: Add chart kinds route**

Append to `api/routers/research.py`:

```python
@router.get("/charts/kinds")
async def list_chart_kinds():
    return {
        "kinds": [
            "platform_counts",
            "post_trend",
            "comment_trend",
            "keyword_ranking",
            "time_window_ratio",
            "engagement_distribution",
            "top_posts",
            "high_engagement_timeline",
            "sentiment_distribution",
            "stance_distribution",
            "topic_tag_ranking",
            "controversy_points",
            "platform_comparison",
            "crawl_success_failure",
            "missing_field_ratio",
            "parse_failure_reasons",
        ]
    }
```

- [ ] **Step 4: Run API tests**

Run:

```bash
pytest tests/test_research_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routers/research.py tests/test_research_api.py
git commit -m "feat: add research chart API metadata"
```

## Task 10: Verification Pass

**Files:**
- No new files.

- [ ] **Step 1: Run focused research tests**

Run:

```bash
pytest tests/test_research_*.py -v
```

Expected: all research tests PASS.

- [ ] **Step 2: Run existing lightweight tests**

Run:

```bash
pytest tests/test_store_factory.py tests/test_cmd_arg_tieba.py tests/test_tieba_extractor.py -v
```

Expected: PASS. If failures are unrelated to research changes, record exact failing tests before proceeding.

- [ ] **Step 3: Initialize SQLite schema**

Run:

```bash
python main.py --init_db sqlite
```

Expected: command completes and creates the new research tables in `database/sqlite_tables.db`.

- [ ] **Step 4: Check git status**

Run:

```bash
git status --short
```

Expected: no unstaged implementation changes except generated local database files ignored by `.gitignore`.

- [ ] **Step 5: Final commit if needed**

If verification required small fixes, commit them:

```bash
git add research api tests database
git commit -m "test: verify research crawler foundation"
```

## Spec Coverage Review

- Research task model: Tasks 1, 3, 4, 5.
- PostgreSQL/SQLite schema: Task 3 and Task 10.
- Full comment guardrails: Task 1.
- Raw records and normalized tables: Task 3.
- Default anonymization: Task 2.
- AI provider configuration foundation: Tasks 1, 3, 8.
- WebUI/API foundation: Tasks 5 and 9.
- Charts: Task 6 and Task 9.
- Export and `job_report.md`: Task 7.
- Crawler adapters and real Weibo/Zhihu runner: intentionally deferred to the next plan after this foundation is merged and verified.

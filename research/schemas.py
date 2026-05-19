from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from research.enums import (
    AI_TASK_TYPES,
    RAW_MINIMAL,
    RAW_RECORD_MODES,
    SUPPORTED_RESEARCH_PLATFORMS,
)


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
            raise ValueError(
                "full_comment_crawl requires max_posts_per_job or stop_after_hours"
            )
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
    default_params: dict[str, Any] = Field(
        default_factory=lambda: {"temperature": 0.2, "max_tokens": 1000}
    )
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


class ExistingDataBackfillRequest(BaseModel):
    keywords: list[str] | None = None
    limit: int | None = Field(default=1000, ge=1, le=100000)

    @field_validator("keywords")
    @classmethod
    def strip_optional_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item.strip()]
        return cleaned or None

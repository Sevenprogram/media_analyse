from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas import LoginTypeEnum, SaveDataOptionEnum
from research.enums import (
    AI_TASK_TYPES,
    COLLECTION_CREATOR,
    COLLECTION_DETAIL,
    COLLECTION_MODES,
    COLLECTION_SEARCH,
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
    collection_mode: Literal["search", "detail", "creator"] = COLLECTION_SEARCH
    keywords: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    creator_ids: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    comment_policy: CommentPolicy = Field(default_factory=CommentPolicy.default)
    raw_record_mode: Literal["minimal", "full"] = RAW_MINIMAL
    anonymize_authors: bool = True
    schedule_enabled: bool = False
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    next_run_at: datetime | None = None

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
        return _strip_string_list(value)

    @field_validator("target_ids")
    @classmethod
    def strip_target_ids(cls, value: list[str]) -> list[str]:
        return _strip_string_list(value)

    @field_validator("creator_ids")
    @classmethod
    def strip_creator_ids(cls, value: list[str]) -> list[str]:
        return _strip_string_list(value)

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
        validate_collection_inputs(
            collection_mode=self.collection_mode,
            keywords=self.keywords,
            target_ids=self.target_ids,
            creator_ids=self.creator_ids,
        )
        return self


class ResearchJobUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    topic: str | None = Field(default=None, min_length=1, max_length=500)
    platforms: list[str] | None = Field(default=None, min_length=1)
    collection_mode: Literal["search", "detail", "creator"] | None = None
    keywords: list[str] | None = None
    target_ids: list[str] | None = None
    creator_ids: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
    comment_policy: CommentPolicy | None = None
    raw_record_mode: Literal["minimal", "full"] | None = None
    anonymize_authors: bool | None = None
    schedule_enabled: bool | None = None
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    next_run_at: datetime | None = None

    @field_validator("platforms")
    @classmethod
    def validate_optional_platforms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value

    @field_validator("keywords")
    @classmethod
    def strip_optional_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _strip_string_list(value)

    @field_validator("target_ids")
    @classmethod
    def strip_optional_target_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _strip_string_list(value)

    @field_validator("creator_ids")
    @classmethod
    def strip_optional_creator_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _strip_string_list(value)

    @field_validator("raw_record_mode")
    @classmethod
    def validate_optional_raw_record_mode(cls, value: str | None) -> str | None:
        if value is not None and value not in RAW_RECORD_MODES:
            raise ValueError(f"Unsupported raw_record_mode: {value}")
        return value

    @model_validator(mode="after")
    def validate_partial_date_window(self) -> "ResearchJobUpdate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ResearchJobRead(BaseModel):
    id: int
    name: str
    topic: str
    platforms: list[str]
    collection_mode: str
    keywords: list[str]
    target_ids: list[str]
    creator_ids: list[str]
    start_date: date
    end_date: date
    status: str
    comment_policy: dict[str, Any]
    raw_record_mode: str
    anonymize_authors: bool
    schedule_enabled: bool = False
    schedule_interval_minutes: int | None = None
    next_run_at: datetime | None = None
    last_scheduled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PlatformRateLimitUpsert(BaseModel):
    platform: str
    requests_per_minute: int = Field(default=12, ge=1, le=120)
    min_sleep_seconds: int = Field(default=1, ge=0, le=3600)
    max_sleep_seconds: int = Field(default=5, ge=0, le=3600)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_sleep_bounds(self) -> "PlatformRateLimitUpsert":
        if self.max_sleep_seconds < self.min_sleep_seconds:
            raise ValueError("max_sleep_seconds must be greater than or equal to min_sleep_seconds")
        if self.platform not in SUPPORTED_RESEARCH_PLATFORMS:
            raise ValueError(f"Unsupported platform: {self.platform}")
        return self


class PlatformCapabilityUpsert(BaseModel):
    platform: str
    enabled: bool = True
    crawl_search_enabled: bool = True
    crawl_creator_enabled: bool = True
    crawl_detail_enabled: bool = True
    comments_enabled: bool = True
    analysis_enabled: bool = True
    daily_monitor_enabled: bool = True
    keyword_heat_enabled: bool = True
    rate_limit_per_minute: int = Field(default=12, ge=1, le=120)
    max_daily_jobs: int | None = Field(default=None, ge=1)
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        if value not in SUPPORTED_RESEARCH_PLATFORMS:
            raise ValueError(f"Unsupported platform: {value}")
        return value


class GlobalDefaultsUpsert(BaseModel):
    default_platforms: list[str] = Field(default_factory=list)
    default_collection_mode: Literal["search", "detail", "creator"] = COLLECTION_SEARCH
    default_raw_record_mode: Literal["minimal", "full"] = RAW_MINIMAL
    default_comment_mode: Literal["limited", "full"] = "limited"
    default_comment_limit_per_post: int = Field(default=100, ge=1)
    default_anonymize_authors: bool = True
    default_schedule_enabled: bool = False
    default_schedule_interval_minutes: int = Field(default=1440, ge=1)
    default_keyword_set_id: int | None = Field(default=None, ge=1)
    default_ai_provider_id: int | None = Field(default=None, ge=1)
    default_prompt_template_id: int | None = Field(default=None, ge=1)

    @field_validator("default_platforms")
    @classmethod
    def validate_default_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value


class KeywordSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    platforms: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    topic: str | None = Field(default=None, max_length=255)
    enabled: bool = True

    @field_validator("platforms")
    @classmethod
    def validate_keyword_set_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value

    @field_validator("keywords", "negative_keywords", "synonyms")
    @classmethod
    def strip_keyword_set_terms(cls, value: list[str]) -> list[str]:
        return _strip_string_list(value)


class KeywordSetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    platforms: list[str] | None = None
    keywords: list[str] | None = None
    negative_keywords: list[str] | None = None
    synonyms: list[str] | None = None
    topic: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None

    @field_validator("platforms")
    @classmethod
    def validate_optional_keyword_set_platforms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value

    @field_validator("keywords", "negative_keywords", "synonyms")
    @classmethod
    def strip_optional_keyword_set_terms(cls, value: list[str] | None) -> list[str] | None:
        return _strip_string_list(value) if value is not None else None


class VerticalCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().lower()


class VerticalUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None

    @field_validator("code")
    @classmethod
    def normalize_optional_code(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None


class TagGroupCreate(BaseModel):
    vertical_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    sort_order: int = Field(default=100, ge=0)
    enabled: bool = True


class TagGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class TagDefinitionCreate(BaseModel):
    vertical_id: int = Field(ge=1)
    group_id: int = Field(ge=1)
    tag_name: str = Field(min_length=1, max_length=128)
    keywords: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    ai_prompt_hint: str | None = None
    weight: int = Field(default=1, ge=1)
    enabled: bool = True

    @field_validator("keywords", "synonyms", "negative_keywords")
    @classmethod
    def strip_tag_terms(cls, value: list[str]) -> list[str]:
        return _strip_string_list(value)


class TagDefinitionUpdate(BaseModel):
    group_id: int | None = Field(default=None, ge=1)
    tag_name: str | None = Field(default=None, min_length=1, max_length=128)
    keywords: list[str] | None = None
    synonyms: list[str] | None = None
    negative_keywords: list[str] | None = None
    ai_prompt_hint: str | None = None
    weight: int | None = Field(default=None, ge=1)
    enabled: bool | None = None

    @field_validator("keywords", "synonyms", "negative_keywords")
    @classmethod
    def strip_optional_tag_terms(cls, value: list[str] | None) -> list[str] | None:
        return _strip_string_list(value) if value is not None else None


class TagDefinitionImportItem(BaseModel):
    vertical_code: str = Field(min_length=1, max_length=64)
    group_name: str = Field(min_length=1, max_length=128)
    tag_name: str = Field(min_length=1, max_length=128)
    keywords: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    ai_prompt_hint: str | None = None
    weight: int = Field(default=1, ge=1)
    enabled: bool = True

    @field_validator("vertical_code")
    @classmethod
    def normalize_import_vertical_code(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("keywords", "synonyms", "negative_keywords")
    @classmethod
    def strip_import_terms(cls, value: list[str]) -> list[str]:
        return _strip_string_list(value)


class TagDefinitionImportRequest(BaseModel):
    items: list[TagDefinitionImportItem] = Field(min_length=1)


KeywordType = Literal[
    "primary",
    "secondary",
    "synonym",
    "negative",
    "platform_adapted",
    "ai_suggested",
]
AutomationMode = Literal["pending_confirmation", "direct"]


class ScenePackCreate(BaseModel):
    vertical_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    weight: float = Field(default=1.0, ge=0)
    default_platforms: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("default_platforms")
    @classmethod
    def validate_scene_pack_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value


class ScenePackUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    weight: float | None = Field(default=None, ge=0)
    default_platforms: list[str] | None = None
    enabled: bool | None = None

    @field_validator("default_platforms")
    @classmethod
    def validate_optional_scene_pack_platforms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value


class ScenePackKeywordCreate(BaseModel):
    scene_pack_id: int = Field(ge=1)
    keyword: str = Field(min_length=1, max_length=255)
    keyword_type: KeywordType
    platform: str | None = None
    weight: float = Field(default=1.0, ge=0)
    reason: str | None = None
    usage_flags: list[str] = Field(default_factory=list)
    platform_overrides: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("keyword")
    @classmethod
    def strip_scene_keyword(cls, value: str) -> str:
        return value.strip()

    @field_validator("platform")
    @classmethod
    def validate_optional_keyword_platform(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_RESEARCH_PLATFORMS:
            raise ValueError(f"Unsupported platform: {value}")
        return value


class AIKeywordExpansionRequest(BaseModel):
    input_text: str = Field(min_length=1, max_length=500)
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_id: int | None = Field(default=None, ge=1)
    target_platforms: list[str] = Field(default_factory=list)
    provider_config_id: int | None = Field(default=None, ge=1)

    @field_validator("target_platforms")
    @classmethod
    def validate_expansion_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value


class MonitorPoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    schedule_interval_minutes: int = Field(default=720, ge=1)
    comment_policy: dict[str, bool] = Field(
        default_factory=lambda: {
            "enable_comments": True,
            "enable_sub_comments": False,
        }
    )
    automation_mode: AutomationMode = "pending_confirmation"
    auto_top_n: int = Field(default=10, ge=1, le=200)
    min_match_score: float = Field(default=80.0, ge=0, le=100)
    min_recent_posts_30d: int = Field(default=3, ge=0)
    follower_min: int | None = Field(default=None, ge=0)
    follower_max: int | None = Field(default=None, ge=0)
    exclude_existing_creators: bool = True
    enabled: bool = True

    @field_validator("platforms")
    @classmethod
    def validate_monitor_pool_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value

    @model_validator(mode="after")
    def validate_monitor_pool_bounds(self) -> "MonitorPoolCreate":
        if self.follower_min is not None and self.follower_max is not None:
            if self.follower_max < self.follower_min:
                raise ValueError("follower_max must be greater than or equal to follower_min")
        return self


class MonitorPoolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] | None = None
    platforms: list[str] | None = None
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    comment_policy: dict[str, bool] | None = None
    automation_mode: AutomationMode | None = None
    auto_top_n: int | None = Field(default=None, ge=1, le=200)
    min_match_score: float | None = Field(default=None, ge=0, le=100)
    min_recent_posts_30d: int | None = Field(default=None, ge=0)
    follower_min: int | None = Field(default=None, ge=0)
    follower_max: int | None = Field(default=None, ge=0)
    exclude_existing_creators: bool | None = None
    enabled: bool | None = None

    @field_validator("platforms")
    @classmethod
    def validate_optional_monitor_pool_platforms(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value


class MonitorPoolAddCreatorsRequest(BaseModel):
    creators: list[dict[str, Any]] = Field(default_factory=list)
    account_profile_ids: list[int] = Field(default_factory=list)
    crawl_now: bool = False


class ContentKeywordExtractionRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str | None = None
    platform: str | None = None
    url: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] = Field(default_factory=list)
    use_ai: bool = False
    provider_config_id: int | None = Field(default=None, ge=1)

    @field_validator("platform")
    @classmethod
    def validate_optional_content_platform(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_RESEARCH_PLATFORMS:
            raise ValueError(f"Unsupported platform: {value}")
        return value


class SimilarContentSearchRequest(BaseModel):
    keywords: list[str] = Field(min_length=1)
    platforms: list[str] = Field(default_factory=list)
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] = Field(default_factory=list)
    realtime: bool = False
    exclude_tracked: bool = True
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("keywords")
    @classmethod
    def strip_similar_content_keywords(cls, value: list[str]) -> list[str]:
        return _strip_string_list(value)

    @field_validator("platforms")
    @classmethod
    def validate_similar_content_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value


class ContentTrackerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    scene_pack_ids: list[int] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    included_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    seed_refs: list[dict[str, str]] = Field(default_factory=list)
    schedule_interval_minutes: int = Field(default=720, ge=1)
    comment_policy: dict[str, bool] = Field(
        default_factory=lambda: {
            "enable_comments": True,
            "enable_sub_comments": False,
        }
    )
    enabled: bool = True

    @field_validator("platforms")
    @classmethod
    def validate_content_tracker_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value

    @field_validator("included_keywords", "excluded_keywords")
    @classmethod
    def strip_content_tracker_keywords(cls, value: list[str]) -> list[str]:
        return _strip_string_list(value)

    @model_validator(mode="after")
    def validate_tracking_inputs(self) -> "ContentTrackerCreate":
        if not self.included_keywords and not self.seed_refs:
            raise ValueError("content tracker requires included_keywords or seed_refs")
        return self


class TaggingRunRequest(BaseModel):
    vertical_id: int | None = Field(default=None, ge=1)
    analysis_version: str = Field(default="v1", min_length=1, max_length=64)
    use_ai: bool = False


class CreatorProfileRebuildRequest(BaseModel):
    job_id: int | None = Field(default=None, ge=1)
    platform: str | None = None
    creator_id: str | None = Field(default=None, min_length=1, max_length=255)
    analysis_version: str = Field(default="v1", min_length=1, max_length=64)

    @field_validator("platform")
    @classmethod
    def validate_optional_rebuild_platform(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_RESEARCH_PLATFORMS:
            raise ValueError(f"Unsupported platform: {value}")
        return value


class EntityTagRead(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    platform: str
    vertical_id: int
    tag_id: int
    confidence: float
    source: str
    evidence_json: dict[str, Any]
    analysis_version: str
    created_at: datetime | None = None


class CreatorSearchIntentRequest(BaseModel):
    raw_query: str = Field(min_length=1, max_length=500)
    selected_vertical_id: int | None = Field(default=None, ge=1)


class CreatorSearchRequest(BaseModel):
    raw_query: str = Field(default="", max_length=500)
    selected_vertical_id: int | None = Field(default=None, ge=1)
    required_tag_ids: list[int] = Field(default_factory=list)
    optional_tag_ids: list[int] = Field(default_factory=list)
    negative_tag_ids: list[int] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    follower_min: int | None = Field(default=None, ge=0)
    follower_max: int | None = Field(default=None, ge=0)
    recent_activity_min: int | None = Field(default=None, ge=0)
    engagement_rate_min: float | None = Field(default=None, ge=0)
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("platforms")
    @classmethod
    def validate_search_platforms(cls, value: list[str]) -> list[str]:
        unsupported = sorted(set(value) - SUPPORTED_RESEARCH_PLATFORMS)
        if unsupported:
            raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
        return value

    @model_validator(mode="after")
    def validate_search_inputs(self) -> "CreatorSearchRequest":
        if self.follower_min is not None and self.follower_max is not None:
            if self.follower_max < self.follower_min:
                raise ValueError("follower_max must be greater than or equal to follower_min")
        if not self.raw_query and not self.required_tag_ids and not self.selected_vertical_id:
            raise ValueError("creator search requires raw_query, required_tag_ids, or selected_vertical_id")
        return self


class CreatorSearchResult(BaseModel):
    platform: str
    creator_id: str
    display_name: str | None = None
    profile_url: str | None = None
    follower_count: int | None = None
    recent_post_count_30d: int = 0
    avg_engagement_rate: float | None = None
    hot_post_rate: float | None = None
    match_score: float
    matched_tags: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    representative_posts: list[dict[str, Any]] = Field(default_factory=list)


class CreatorCandidateUpsert(BaseModel):
    platform: str
    creator_id: str = Field(min_length=1, max_length=255)
    pool_name: str = Field(default="default", min_length=1, max_length=128)
    vertical_id: int | None = Field(default=None, ge=1)
    match_score: float | None = Field(default=None, ge=0)
    matched_tags: list[dict[str, Any]] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def validate_candidate_platform(cls, value: str) -> str:
        if value not in SUPPORTED_RESEARCH_PLATFORMS:
            raise ValueError(f"Unsupported platform: {value}")
        return value


class CompetitorAccountCreate(BaseModel):
    platform: str
    creator_id: str = Field(min_length=1, max_length=255)
    display_name: str | None = None
    profile_url: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    enabled: bool = True
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def validate_competitor_platform(cls, value: str) -> str:
        if value not in SUPPORTED_RESEARCH_PLATFORMS:
            raise ValueError(f"Unsupported platform: {value}")
        return value


class KeywordOpportunityRead(BaseModel):
    vertical_id: int
    platform: str | None = None
    tag_id: int
    tag_name: str | None = None
    heat_score: float
    growth_score: float
    competition_score: float
    supply_gap_score: float
    platform_signal: str
    evidence: dict[str, Any]


class CompetitorAccountUpdate(BaseModel):
    display_name: str | None = None
    profile_url: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    enabled: bool | None = None
    notes: str | None = None


class AuthProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    platform: str
    login_type: Literal["cookie", "qrcode", "phone"] = "cookie"
    cookies: str = Field(min_length=1)
    enabled: bool = True
    expires_at: datetime | None = None
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def validate_auth_platform(cls, value: str) -> str:
        if value not in SUPPORTED_RESEARCH_PLATFORMS:
            raise ValueError(f"Unsupported platform: {value}")
        return value


class AuthProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    login_type: Literal["cookie", "qrcode", "phone"] | None = None
    cookies: str | None = None
    enabled: bool | None = None
    expires_at: datetime | None = None
    notes: str | None = None


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


class AIPromptTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    task_type: str
    platform: str = Field(default="all", max_length=32)
    prompt_text: str = Field(min_length=1)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    version: str = Field(default="v1", min_length=1, max_length=64)
    enabled: bool = True

    @field_validator("task_type")
    @classmethod
    def validate_prompt_task_type(cls, value: str) -> str:
        if value not in AI_TASK_TYPES:
            raise ValueError(f"Unsupported AI task type: {value}")
        return value


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


class AIAnalysisResultCreate(BaseModel):
    target_type: str = Field(min_length=1, max_length=32)
    target_id: str = Field(min_length=1, max_length=255)
    result: dict[str, Any]
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=64)


class ExistingDataBackfillRequest(BaseModel):
    keywords: list[str] | None = None
    target_ids: list[str] | None = None
    creator_ids: list[str] | None = None
    limit: int | None = Field(default=1000, ge=1, le=100000)

    @field_validator("keywords")
    @classmethod
    def strip_optional_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _strip_string_list(value) or None

    @field_validator("target_ids")
    @classmethod
    def strip_optional_backfill_target_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _strip_string_list(value) or None

    @field_validator("creator_ids")
    @classmethod
    def strip_optional_backfill_creator_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _strip_string_list(value) or None


class ResearchExecutionRequest(BaseModel):
    login_type: LoginTypeEnum = LoginTypeEnum.QRCODE
    save_option: SaveDataOptionEnum = SaveDataOptionEnum.SQLITE
    cookies: str = ""
    headless: bool = False
    start_page: int = Field(default=1, ge=1)
    backfill_after_crawl: bool = True


def validate_collection_inputs(
    *,
    collection_mode: str,
    keywords: list[str],
    target_ids: list[str],
    creator_ids: list[str],
) -> None:
    if collection_mode not in COLLECTION_MODES:
        raise ValueError(f"Unsupported collection mode: {collection_mode}")
    if collection_mode == COLLECTION_SEARCH and not keywords:
        raise ValueError("search collection mode requires keywords")
    if collection_mode == COLLECTION_DETAIL and not target_ids:
        raise ValueError("detail collection mode requires target_ids")
    if collection_mode == COLLECTION_CREATOR and not creator_ids:
        raise ValueError("creator collection mode requires creator_ids")


def _strip_string_list(value: list[str]) -> list[str]:
    return [item.strip() for item in value if item.strip()]

from typing import Final

from research.platforms import SUPPORTED_RESEARCH_PLATFORMS

JOB_PENDING: Final[str] = "pending"
JOB_QUEUED: Final[str] = "queued"
JOB_RUNNING: Final[str] = "running"
JOB_PAUSED: Final[str] = "paused"
JOB_PAUSED_BY_PLATFORM_CONFIG: Final[str] = "paused_by_platform_config"
JOB_FAILED: Final[str] = "failed"
JOB_COMPLETED: Final[str] = "completed"
JOB_CANCELLED: Final[str] = "cancelled"
JOB_STATUSES: Final[set[str]] = {
    JOB_PENDING,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_PAUSED,
    JOB_PAUSED_BY_PLATFORM_CONFIG,
    JOB_FAILED,
    JOB_COMPLETED,
    JOB_CANCELLED,
}

ENTITY_POST: Final[str] = "post"
ENTITY_COMMENT: Final[str] = "comment"
ENTITY_CREATOR: Final[str] = "creator"
ENTITY_TYPES: Final[set[str]] = {ENTITY_POST, ENTITY_COMMENT, ENTITY_CREATOR}

TAG_SOURCE_RULE: Final[str] = "rule"
TAG_SOURCE_AI: Final[str] = "ai"
TAG_SOURCE_MANUAL: Final[str] = "manual"
TAG_SOURCES: Final[set[str]] = {TAG_SOURCE_RULE, TAG_SOURCE_AI, TAG_SOURCE_MANUAL}

PARSER_SOURCE_RULE: Final[str] = "rule"
PARSER_SOURCE_AI: Final[str] = "ai"
PARSER_SOURCE_HYBRID: Final[str] = "hybrid"
PARSER_SOURCES: Final[set[str]] = {
    PARSER_SOURCE_RULE,
    PARSER_SOURCE_AI,
    PARSER_SOURCE_HYBRID,
}

PLATFORM_SIGNAL_BOOST: Final[str] = "suspected_boost"
PLATFORM_SIGNAL_NORMAL: Final[str] = "normal_fluctuation"
PLATFORM_SIGNAL_COOLING: Final[str] = "suspected_cooling"

CRAWL_UNIT_PENDING: Final[str] = "pending"
CRAWL_UNIT_RUNNING: Final[str] = "running"
CRAWL_UNIT_RETRYING: Final[str] = "retrying"
CRAWL_UNIT_SUCCEEDED: Final[str] = "succeeded"
CRAWL_UNIT_FAILED: Final[str] = "failed"
CRAWL_UNIT_CANCELLED: Final[str] = "cancelled"
CRAWL_UNIT_TERMINAL_STATUSES: Final[set[str]] = {
    CRAWL_UNIT_SUCCEEDED,
    CRAWL_UNIT_FAILED,
    CRAWL_UNIT_CANCELLED,
}

COLLECTION_SEARCH: Final[str] = "search"
COLLECTION_DETAIL: Final[str] = "detail"
COLLECTION_CREATOR: Final[str] = "creator"
COLLECTION_MODES: Final[set[str]] = {
    COLLECTION_SEARCH,
    COLLECTION_DETAIL,
    COLLECTION_CREATOR,
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

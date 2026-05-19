from typing import Final

from research.platforms import SUPPORTED_RESEARCH_PLATFORMS

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

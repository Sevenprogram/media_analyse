from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ResearchPlatform:
    value: str
    label: str
    crawler_platform: str
    execution_supported: bool
    backfill_supported: bool
    content_types: tuple[str, ...]
    note: str

    def to_option(self) -> dict[str, object]:
        return {
            "value": self.value,
            "label": self.label,
            "crawler_platform": self.crawler_platform,
            "execution_supported": self.execution_supported,
            "backfill_supported": self.backfill_supported,
            "content_types": list(self.content_types),
            "note": self.note,
        }


RESEARCH_PLATFORMS: Final[dict[str, ResearchPlatform]] = {
    "wb": ResearchPlatform(
        value="wb",
        label="Weibo",
        crawler_platform="wb",
        execution_supported=True,
        backfill_supported=True,
        content_types=("post", "comment", "author"),
        note="Search crawl plus post/comment normalization.",
    ),
    "zhihu": ResearchPlatform(
        value="zhihu",
        label="Zhihu",
        crawler_platform="zhihu",
        execution_supported=True,
        backfill_supported=True,
        content_types=("answer", "article", "comment", "author"),
        note="Question, answer/article and comment normalization.",
    ),
    "xhs": ResearchPlatform(
        value="xhs",
        label="Xiaohongshu",
        crawler_platform="xhs",
        execution_supported=True,
        backfill_supported=True,
        content_types=("note", "comment", "author"),
        note="Note and comment normalization from existing crawler tables.",
    ),
    "dy": ResearchPlatform(
        value="dy",
        label="Douyin",
        crawler_platform="dy",
        execution_supported=True,
        backfill_supported=True,
        content_types=("video", "comment", "author"),
        note="Short-video metadata and comment normalization.",
    ),
    "ks": ResearchPlatform(
        value="ks",
        label="Kuaishou",
        crawler_platform="ks",
        execution_supported=True,
        backfill_supported=True,
        content_types=("video", "comment", "author"),
        note="Short-video metadata and comment normalization.",
    ),
    "bili": ResearchPlatform(
        value="bili",
        label="Bilibili",
        crawler_platform="bili",
        execution_supported=True,
        backfill_supported=True,
        content_types=("video", "comment", "author", "danmaku_count"),
        note="Video/comment normalization; danmaku text requires a source table if added later.",
    ),
    "tieba": ResearchPlatform(
        value="tieba",
        label="Baidu Tieba",
        crawler_platform="tieba",
        execution_supported=True,
        backfill_supported=True,
        content_types=("thread", "comment", "author"),
        note="Forum thread and reply normalization.",
    ),
}

SUPPORTED_RESEARCH_PLATFORMS: Final[set[str]] = set(RESEARCH_PLATFORMS)
EXECUTABLE_RESEARCH_PLATFORMS: Final[set[str]] = {
    key for key, item in RESEARCH_PLATFORMS.items() if item.execution_supported
}
BACKFILL_RESEARCH_PLATFORMS: Final[set[str]] = {
    key for key, item in RESEARCH_PLATFORMS.items() if item.backfill_supported
}


def list_research_platform_options() -> list[dict[str, object]]:
    return [platform.to_option() for platform in RESEARCH_PLATFORMS.values()]


def get_research_platform(value: str) -> ResearchPlatform | None:
    return RESEARCH_PLATFORMS.get(value)

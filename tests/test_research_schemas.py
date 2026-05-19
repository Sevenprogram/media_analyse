from datetime import date

import pytest
from pydantic import ValidationError

from research.schemas import CommentPolicy, ResearchJobCreate, ResearchJobUpdate


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
    with pytest.raises(
        ValidationError, match="end_date must be on or after start_date"
    ):
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


def test_research_job_update_strips_keywords():
    request = ResearchJobUpdate(keywords=[" 政策 ", "", "治理"])

    assert request.keywords == ["政策", "治理"]


def test_research_job_update_rejects_empty_keywords():
    with pytest.raises(ValidationError, match="keywords must contain"):
        ResearchJobUpdate(keywords=["", "  "])

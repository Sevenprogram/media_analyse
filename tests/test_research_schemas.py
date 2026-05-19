from datetime import date

import pytest
from pydantic import ValidationError

from research.schemas import CommentPolicy, ResearchJobCreate, ResearchJobUpdate


def test_research_job_requires_supported_platforms():
    request = ResearchJobCreate(
        name="Policy debate",
        topic="urban governance",
        platforms=["wb", "zhihu"],
        keywords=["public policy", "urban governance"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        comment_policy=CommentPolicy.default(),
    )

    assert request.platforms == ["wb", "zhihu"]
    assert request.collection_mode == "search"


def test_research_job_rejects_unsupported_platform():
    with pytest.raises(ValidationError, match="Unsupported platform"):
        ResearchJobCreate(
            name="Bad platform",
            topic="topic",
            platforms=["unknown"],
            keywords=["topic"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            comment_policy=CommentPolicy.default(),
        )


def test_research_job_accepts_video_platforms():
    request = ResearchJobCreate(
        name="Video platforms",
        topic="topic",
        platforms=["xhs", "dy", "ks", "bili"],
        keywords=["topic"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        comment_policy=CommentPolicy.default(),
    )

    assert request.platforms == ["xhs", "dy", "ks", "bili"]


def test_research_job_accepts_detail_mode_without_keywords():
    request = ResearchJobCreate(
        name="Specific posts",
        topic="topic",
        platforms=["wb"],
        collection_mode="detail",
        target_ids=[" 1001 ", "", "1002"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        comment_policy=CommentPolicy.default(),
    )

    assert request.keywords == []
    assert request.target_ids == ["1001", "1002"]


def test_research_job_requires_target_ids_for_detail_mode():
    with pytest.raises(ValidationError, match="detail collection mode requires target_ids"):
        ResearchJobCreate(
            name="Specific posts",
            topic="topic",
            platforms=["wb"],
            collection_mode="detail",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            comment_policy=CommentPolicy.default(),
        )


def test_research_job_accepts_creator_mode():
    request = ResearchJobCreate(
        name="Creator timeline",
        topic="topic",
        platforms=["zhihu"],
        collection_mode="creator",
        creator_ids=[" author-a ", "author-b"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        comment_policy=CommentPolicy.default(),
    )

    assert request.creator_ids == ["author-a", "author-b"]


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


def test_research_job_update_strips_collection_inputs():
    request = ResearchJobUpdate(
        keywords=[" policy ", "", "governance"],
        target_ids=[" 1001 "],
        creator_ids=[" author "],
    )

    assert request.keywords == ["policy", "governance"]
    assert request.target_ids == ["1001"]
    assert request.creator_ids == ["author"]


def test_research_job_update_allows_empty_keywords_for_partial_updates():
    request = ResearchJobUpdate(keywords=["", "  "])

    assert request.keywords == []

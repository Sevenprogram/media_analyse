from datetime import datetime, timezone

from research.normalizer import (
    normalize_weibo_comment,
    normalize_weibo_note,
    normalize_zhihu_content,
    parse_timestamp,
)


def test_parse_timestamp_accepts_epoch_seconds():
    assert parse_timestamp(1704067200) == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_normalize_weibo_note_maps_to_research_post():
    result = normalize_weibo_note(
        {
            "note_id": 123,
            "user_id": "u1",
            "content": "policy discussion",
            "note_url": "https://weibo.example/123",
            "create_time": 1704067200,
            "liked_count": "10",
            "comments_count": "2",
            "shared_count": "1",
            "source_keyword": "政策",
        },
        job_id=7,
        salt="salt",
    )

    assert result["job_id"] == 7
    assert result["platform"] == "wb"
    assert result["platform_post_id"] == "123"
    assert result["author_hash"].startswith("wb_")
    assert result["publish_time"] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert result["engagement_json"]["source_keyword"] == "政策"


def test_normalize_weibo_comment_handles_root_parent():
    result = normalize_weibo_comment(
        {
            "comment_id": 456,
            "note_id": 123,
            "parent_comment_id": "0",
            "user_id": "u2",
            "content": "comment",
            "create_time": "1704067200",
            "comment_like_count": "5",
        },
        job_id=7,
        salt="salt",
    )

    assert result["platform_comment_id"] == "456"
    assert result["parent_comment_id"] is None
    assert result["like_count"] == 5


def test_normalize_zhihu_content_maps_question_metadata():
    result = normalize_zhihu_content(
        {
            "content_id": "answer1",
            "content_type": "answer",
            "content_text": "answer body",
            "content_url": "https://zhihu.example/answer1",
            "question_id": "q1",
            "title": "Question",
            "created_time": "2026-01-02",
            "voteup_count": 12,
            "comment_count": 3,
            "source_keyword": "治理",
            "user_id": "author1",
        },
        job_id=8,
        salt="salt",
    )

    assert result["platform"] == "zhihu"
    assert result["platform_post_id"] == "answer1"
    assert result["title"] == "Question"
    assert result["engagement_json"]["question_id"] == "q1"

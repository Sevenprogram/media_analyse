from datetime import datetime, timezone

from research.normalizer import (
    normalize_bilibili_video,
    normalize_douyin_aweme,
    normalize_kuaishou_video,
    normalize_weibo_comment,
    normalize_weibo_note,
    normalize_xhs_note,
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


def test_normalize_xhs_note_maps_note_metadata():
    result = normalize_xhs_note(
        {
            "note_id": "x1",
            "user_id": "u1",
            "title": "note title",
            "desc": "note body",
            "note_url": "https://xhs.example/x1",
            "time": 1704067200,
            "liked_count": "8",
            "source_keyword": "topic",
        },
        job_id=9,
        salt="salt",
    )

    assert result["platform"] == "xhs"
    assert result["platform_post_id"] == "x1"
    assert result["engagement_json"]["source_keyword"] == "topic"


def test_normalize_short_video_platforms_map_engagement_fields():
    douyin = normalize_douyin_aweme(
        {
            "aweme_id": 1,
            "user_id": "u1",
            "title": "dy",
            "desc": "body",
            "aweme_url": "https://dy.example/1",
            "create_time": 1704067200,
            "share_count": "3",
        },
        job_id=10,
        salt="salt",
    )
    kuaishou = normalize_kuaishou_video(
        {
            "video_id": "k1",
            "user_id": "u2",
            "title": "ks",
            "desc": "body",
            "video_url": "https://ks.example/k1",
            "create_time": 1704067200,
            "viewd_count": "12",
        },
        job_id=10,
        salt="salt",
    )
    bilibili = normalize_bilibili_video(
        {
            "video_id": 2,
            "user_id": 3,
            "title": "bili",
            "desc": "body",
            "video_url": "https://bili.example/2",
            "create_time": 1704067200,
            "video_danmaku": "22",
        },
        job_id=10,
        salt="salt",
    )

    assert douyin["platform"] == "dy"
    assert kuaishou["engagement_json"]["viewd_count"] == "12"
    assert bilibili["engagement_json"]["danmaku_count"] == "22"

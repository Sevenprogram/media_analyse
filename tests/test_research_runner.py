import pytest
from datetime import date

from research.runner import ResearchJobRunner
from research.time_window import TimeWindow


class FakeRepository:
    def __init__(self):
        self.raw_records = []
        self.authors = []
        self.posts = []
        self.comments = []
        self.events = []

    async def create_event(self, **kwargs):
        self.events.append(kwargs)
        return {"id": len(self.events), **kwargs}

    async def create_raw_record(self, **kwargs):
        record = {"id": len(self.raw_records) + 1, **kwargs}
        self.raw_records.append(record)
        return record

    async def upsert_author(self, payload):
        self.authors.append(payload)
        return {"id": len(self.authors), "author_hash": payload["author_hash"]}

    async def upsert_post(self, payload):
        self.posts.append(payload)
        return {"id": len(self.posts), "platform_post_id": payload["platform_post_id"]}

    async def upsert_comment(self, payload):
        self.comments.append(payload)
        return {"id": len(self.comments), "platform_comment_id": payload["platform_comment_id"]}


@pytest.mark.asyncio
async def test_ingest_weibo_batch_writes_raw_and_normalized_records():
    repo = FakeRepository()
    runner = ResearchJobRunner(repo, author_hash_salt="salt")

    stats = await runner.ingest_weibo_batch(
        job_id=7,
        notes=[
            {
                "note_id": 123,
                "user_id": "u1",
                "content": "post",
                "note_url": "https://weibo.example/123",
                "create_time": 1704067200,
            }
        ],
        comments=[
            {
                "comment_id": 456,
                "note_id": 123,
                "user_id": "u2",
                "content": "comment",
                "create_time": 1704067200,
            }
        ],
        authors=[{"user_id": "u1", "nickname": "name"}],
    )

    assert stats["posts"] == 1
    assert stats["comments"] == 1
    assert stats["authors"] == 1
    assert stats["raw_records"] == 2
    assert repo.posts[0]["raw_record_id"] == 1
    assert repo.comments[0]["raw_record_id"] == 2
    assert repo.events[0]["event_type"] == "ingest_batch"


@pytest.mark.asyncio
async def test_ingest_zhihu_batch_writes_platform_specific_ids():
    repo = FakeRepository()
    runner = ResearchJobRunner(repo, author_hash_salt="salt")

    await runner.ingest_zhihu_batch(
        job_id=8,
        contents=[
            {
                "content_id": "answer1",
                "user_id": "author1",
                "content_text": "body",
                "content_url": "https://zhihu.example/answer1",
            }
        ],
        comments=[
            {
                "comment_id": "comment1",
                "content_id": "answer1",
                "user_id": "author2",
                "content": "comment",
            }
        ],
        authors=[{"user_id": "author1", "user_nickname": "name"}],
    )

    assert repo.posts[0]["platform"] == "zhihu"
    assert repo.posts[0]["platform_post_id"] == "answer1"
    assert repo.comments[0]["platform_comment_id"] == "comment1"


@pytest.mark.asyncio
async def test_ingest_weibo_batch_filters_posts_outside_time_window():
    repo = FakeRepository()
    runner = ResearchJobRunner(repo, author_hash_salt="salt")
    window = TimeWindow.from_dates(date(2024, 1, 1), date(2024, 1, 1))

    stats = await runner.ingest_weibo_batch(
        job_id=7,
        notes=[
            {
                "note_id": 123,
                "user_id": "u1",
                "content": "inside",
                "create_time": 1704067200,
            },
            {
                "note_id": 124,
                "user_id": "u1",
                "content": "outside",
                "create_time": 1704153600,
            },
        ],
        comments=[],
        authors=[],
        time_window=window,
    )

    assert stats["posts"] == 1
    assert stats["filtered_posts_outside_window"] == 1
    assert repo.posts[0]["platform_post_id"] == "123"

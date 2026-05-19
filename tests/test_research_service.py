from datetime import date

import pytest

from research.schemas import CommentPolicy, ResearchJobCreate, ResearchJobUpdate
from research.service import ResearchJobService


class FakeResearchRepository:
    def __init__(self):
        self.created_payload = None

    async def create_job(self, payload):
        self.created_payload = payload
        return {
            "id": 1,
            **payload,
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    async def get_job(self, job_id):
        return {
            "id": job_id,
            "name": "Policy debate",
            "topic": "urban governance",
            "platforms": ["wb"],
            "keywords": ["旧关键词"],
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 1, 31),
            "status": "pending",
            "comment_policy": CommentPolicy.default().model_dump(mode="json"),
            "raw_record_mode": "minimal",
            "anonymize_authors": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    async def update_job(self, job_id, payload):
        existing = await self.get_job(job_id)
        return {**existing, **payload}


@pytest.mark.asyncio
async def test_create_job_persists_pending_job_payload():
    repo = FakeResearchRepository()
    service = ResearchJobService(repo)
    request = ResearchJobCreate(
        name="Policy debate",
        topic="urban governance",
        platforms=["wb", "zhihu"],
        keywords=["公共政策"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        comment_policy=CommentPolicy.default(),
    )

    result = await service.create_job(request)

    assert result["status"] == "pending"
    assert repo.created_payload["platforms"] == ["wb", "zhihu"]
    assert repo.created_payload["comment_policy"]["comment_limit_per_post"] == 100


@pytest.mark.asyncio
async def test_update_job_allows_backend_keyword_configuration():
    service = ResearchJobService(FakeResearchRepository())

    result = await service.update_job(
        1, ResearchJobUpdate(keywords=["新关键词", "治理"], platforms=["wb", "zhihu"])
    )

    assert result["keywords"] == ["新关键词", "治理"]
    assert result["platforms"] == ["wb", "zhihu"]

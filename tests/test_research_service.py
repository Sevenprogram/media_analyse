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
            "collection_mode": "search",
            "keywords": ["old keyword"],
            "target_ids": [],
            "creator_ids": [],
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
        keywords=["public policy"],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        comment_policy=CommentPolicy.default(),
    )

    result = await service.create_job(request)

    assert result["status"] == "pending"
    assert repo.created_payload["platforms"] == ["wb", "zhihu"]
    assert repo.created_payload["collection_mode"] == "search"
    assert repo.created_payload["comment_policy"]["comment_limit_per_post"] == 100


@pytest.mark.asyncio
async def test_update_job_allows_backend_keyword_configuration():
    service = ResearchJobService(FakeResearchRepository())

    result = await service.update_job(
        1, ResearchJobUpdate(keywords=["new keyword", "governance"], platforms=["wb", "zhihu"])
    )

    assert result["keywords"] == ["new keyword", "governance"]
    assert result["platforms"] == ["wb", "zhihu"]


@pytest.mark.asyncio
async def test_update_job_rejects_invalid_collection_inputs_after_merge():
    service = ResearchJobService(FakeResearchRepository())

    with pytest.raises(ValueError, match="search collection mode requires keywords"):
        await service.update_job(1, ResearchJobUpdate(keywords=[]))


@pytest.mark.asyncio
async def test_update_job_can_switch_to_detail_mode():
    service = ResearchJobService(FakeResearchRepository())

    result = await service.update_job(
        1,
        ResearchJobUpdate(
            collection_mode="detail",
            keywords=[],
            target_ids=["1001", "1002"],
        ),
    )

    assert result["collection_mode"] == "detail"
    assert result["target_ids"] == ["1001", "1002"]


@pytest.mark.asyncio
async def test_service_lists_growth_projects_from_existing_jobs():
    class ProjectRepository(FakeResearchRepository):
        async def list_jobs(self):
            return [
                {
                    "id": 1,
                    "name": "Education keyword expansion",
                    "topic": "education_summer_2026",
                    "platforms": ["dy"],
                    "keywords": ["K12 education"],
                    "status": "completed",
                    "collection_mode": "search",
                    "updated_at": "2026-05-20T14:00:00Z",
                }
            ]

        async def get_job_stats(self, job_id):
            return {"posts": 60, "comments": 0, "raw_records": 50, "authors": 5}

    service = ResearchJobService(ProjectRepository())

    projects = await service.list_growth_projects()

    assert projects[0]["id"] == "education_summer_2026"
    assert projects[0]["recommended_action"]["kind"] == "backfill_comments"


@pytest.mark.asyncio
async def test_service_gets_growth_project_detail():
    class ProjectRepository(FakeResearchRepository):
        async def list_jobs(self):
            return [
                {
                    "id": 2,
                    "name": "AI tools keyword expansion",
                    "topic": "ai_tools",
                    "platforms": ["dy"],
                    "keywords": ["AI tools"],
                    "status": "completed",
                    "collection_mode": "search",
                    "updated_at": "2026-05-20T14:00:00Z",
                }
            ]

        async def get_job_stats(self, job_id):
            return {"posts": 80, "comments": 25, "raw_records": 70, "authors": 8}

    service = ResearchJobService(ProjectRepository())

    detail = await service.get_growth_project("ai_tools")

    assert detail is not None
    assert detail["project"]["id"] == "ai_tools"
    assert detail["collection_records"][0]["id"] == 2


@pytest.mark.asyncio
async def test_service_prefers_formal_growth_project_keyword_snapshot():
    class ProjectRepository(FakeResearchRepository):
        async def list_jobs(self):
            return [
                {
                    "id": 3,
                    "name": "Education Summer collection",
                    "topic": "education_summer",
                    "platforms": ["dy"],
                    "keywords": ["job keyword"],
                    "status": "pending",
                    "collection_mode": "search",
                    "updated_at": "2026-05-21T10:00:00Z",
                }
            ]

        async def get_job_stats(self, job_id):
            return {"posts": 0, "comments": 0, "raw_records": 0, "authors": 0}

        async def list_growth_project_records(self, include_archived=False):
            return [
                {
                    "id": 9,
                    "name": "Education Summer",
                    "primary_goal": "topic_discovery",
                    "platforms": ["dy", "xhs"],
                    "sample_status": "sample_insufficient",
                    "recommended_action": "start_collection",
                    "opportunity_score": None,
                    "last_collected_at": None,
                    "archived": False,
                }
            ]

        async def list_growth_project_keywords(self, project_id):
            return [
                {
                    "keyword": "K12 education",
                    "keyword_type": "core",
                    "source": "scene_pack",
                    "status": "active",
                },
                {
                    "keyword": "summer childcare",
                    "keyword_type": "expanded",
                    "source": "scene_pack",
                    "status": "active",
                },
            ]

    service = ResearchJobService(ProjectRepository())

    detail = await service.get_growth_project("education_summer")

    assert detail is not None
    assert detail["project"]["project_record_id"] == 9
    assert [item["keyword"] for item in detail["keywords"]] == [
        "K12 education",
        "summer childcare",
    ]

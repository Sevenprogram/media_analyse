from datetime import date

import pytest

from research.tracking_packs import build_tracking_pack, create_daily_sampling_jobs


def test_build_tracking_pack_splits_positive_platform_and_negative_keywords():
    pack = build_tracking_pack(
        scene_pack={"id": 1, "name": "K12", "vertical_id": 2, "default_platforms": ["xhs", "dy"], "enabled": True},
        keywords=[
            {"id": 1, "keyword": "K12教育", "keyword_type": "primary", "enabled": True},
            {"id": 2, "keyword": "陪读妈妈", "keyword_type": "secondary", "platform": "xhs", "enabled": True},
            {"id": 3, "keyword": "情感八卦", "keyword_type": "negative", "enabled": True},
            {"id": 4, "keyword": "抖音适配", "keyword_type": "platform_adapted", "platform": "dy", "enabled": True},
        ],
    )

    assert pack["effective_keywords_by_platform"]["xhs"] == ["K12教育", "陪读妈妈"]
    assert pack["effective_keywords_by_platform"]["dy"] == ["K12教育", "抖音适配"]
    assert pack["negative_keywords"][0]["keyword"] == "情感八卦"


@pytest.mark.asyncio
async def test_create_daily_sampling_jobs_creates_one_search_job_per_platform():
    class FakeRepository:
        def __init__(self):
            self.jobs = []

        async def get_scene_pack(self, scene_pack_id):
            return {"id": scene_pack_id, "name": "K12", "vertical_id": 1, "default_platforms": ["xhs", "dy"], "enabled": True}

        async def list_scene_pack_keywords(self, scene_pack_ids=None, enabled_only=False):
            return [
                {"keyword": "K12教育", "keyword_type": "primary", "enabled": True},
                {"keyword": "单亲妈妈", "keyword_type": "secondary", "enabled": True},
            ]

        async def create_job(self, payload):
            job = {"id": len(self.jobs) + 1, **payload}
            self.jobs.append(job)
            return job

    result = await create_daily_sampling_jobs(
        FakeRepository(),
        scene_pack_id=1,
        daily_sample_limit_per_keyword=100,
        today=date(2026, 5, 21),
    )

    assert result["created"] == 2
    assert {job["platforms"][0] for job in result["jobs"]} == {"xhs", "dy"}
    assert result["jobs"][0]["collection_mode"] == "search"
    assert result["jobs"][0]["comment_policy"]["max_posts_per_job"] == 200

import pytest

from research.monitor_pools import MonitorPoolService, automation_select_candidates


class FakeRepository:
    def __init__(self):
        self.pool = {
            "id": 1,
            "name": "K12 creator pool",
            "schedule_interval_minutes": 720,
            "comment_policy": {
                "enable_comments": True,
                "enable_sub_comments": False,
            },
            "research_job_id": None,
        }
        self.creators = []
        self.job_payload = None
        self.updated_job_payload = None

    async def get_monitor_pool(self, pool_id):
        return self.pool

    async def add_monitor_pool_creators(self, pool_id, creators):
        self.creators.extend(creators)
        return creators

    async def add_account_profile_to_monitor_pool(self, pool_id, profile_id, crawl_now=False):
        return {
            "account_profile_id": profile_id,
            "role": "monitored_creator",
            "monitor_pool_id": pool_id,
            "crawl_now": crawl_now,
        }

    async def list_monitor_pool_creators(self, pool_id, enabled_only=True):
        return self.creators

    async def create_research_job(self, payload):
        self.job_payload = payload
        return {"id": 77, **payload}

    async def update_job(self, job_id, payload):
        self.updated_job_payload = payload
        return {"id": job_id, **payload}

    async def update_monitor_pool(self, pool_id, payload):
        self.pool.update(payload)
        return self.pool


@pytest.mark.asyncio
async def test_monitor_pool_creates_creator_job_from_pool_members():
    repository = FakeRepository()
    service = MonitorPoolService(repository)

    result = await service.add_creators(
        pool_id=1,
        creators=[
            {
                "platform": "xhs",
                "creator_id": "u1",
                "display_name": "Teacher A",
                "match_score": 88,
            }
        ],
        crawl_now=False,
    )

    assert result["job"]["collection_mode"] == "creator"
    assert result["job"]["creator_ids"] == ["u1"]
    assert repository.job_payload["schedule_interval_minutes"] == 720


@pytest.mark.asyncio
async def test_monitor_pool_adds_monitored_role_for_account_profile():
    repository = FakeRepository()
    calls = []

    async def add_role(pool_id, profile_id, crawl_now=False):
        calls.append((pool_id, profile_id, crawl_now))
        return {"role": "monitored_creator"}

    repository.add_account_profile_to_monitor_pool = add_role
    service = MonitorPoolService(repository)

    await service.add_creators(
        pool_id=1,
        creators=[
            {
                "platform": "xhs",
                "creator_id": "u1",
                "account_profile_id": 11,
            }
        ],
        crawl_now=True,
    )

    assert calls == [(1, 11, True)]


@pytest.mark.asyncio
async def test_monitor_pool_sync_updates_existing_creator_job_settings():
    repository = FakeRepository()
    repository.pool["research_job_id"] = 77
    repository.pool["schedule_interval_minutes"] = 360
    repository.pool["comment_policy"] = {
        "enable_comments": True,
        "enable_sub_comments": True,
    }
    repository.creators = [
        {"platform": "xhs", "creator_id": "u1", "enabled": True},
        {"platform": "dy", "creator_id": "u2", "enabled": True},
    ]
    service = MonitorPoolService(repository)

    result = await service.sync_pool_job(1)

    assert result["job"]["id"] == 77
    assert repository.updated_job_payload["schedule_interval_minutes"] == 360
    assert repository.updated_job_payload["comment_policy"] == {
        "enable_comments": True,
        "enable_sub_comments": True,
    }
    assert repository.updated_job_payload["platforms"] == ["dy", "xhs"]
    assert repository.updated_job_payload["creator_ids"] == ["u1", "u2"]


def test_automation_select_candidates_respects_score_activity_and_limit():
    candidates = [
        {"creator_id": "a", "match_score": 90, "recent_post_count_30d": 4},
        {"creator_id": "b", "match_score": 70, "recent_post_count_30d": 8},
        {"creator_id": "c", "match_score": 95, "recent_post_count_30d": 1},
    ]

    selected = automation_select_candidates(
        candidates,
        {"top_n": 1, "min_match_score": 80, "min_recent_post_count_30d": 3},
    )

    assert [item["creator_id"] for item in selected] == ["a"]

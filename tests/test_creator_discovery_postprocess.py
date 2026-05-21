import pytest

from research.postprocess import rebuild_account_profiles_from_posts, run_post_crawl_analysis


@pytest.mark.asyncio
async def test_post_crawl_analysis_tags_posts_and_rebuilds_profiles():
    class FakeRepository:
        def __init__(self):
            self.tags = []
            self.profiles = []

        async def get_platform_capability(self, platform):
            return {"platform": platform, "enabled": True, "analysis_enabled": True}

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return [
                {
                    "id": 1,
                    "vertical_id": 1,
                    "tag_name": "K12教育",
                    "keywords": ["K12"],
                    "synonyms": [],
                    "negative_keywords": [],
                    "weight": 10,
                }
            ]

        async def list_all_posts(self, job_id=None, platform=None):
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "author_hash": "creator-1",
                    "title": "K12 learning plan",
                    "content": "K12 family education",
                    "engagement_json": {"liked_count": 200},
                }
            ]

        async def list_all_comments(self, job_id=None, platform=None):
            return []

        async def list_all_authors(self, job_id=None, platform=None):
            return []

        async def bulk_upsert_entity_tags(self, payloads):
            self.tags.extend(payloads)
            return [{"id": index + 1, **payload} for index, payload in enumerate(payloads)]

        async def list_entity_tags(
            self,
            entity_type=None,
            entity_id=None,
            platform=None,
            vertical_id=None,
            tag_ids=None,
        ):
            return [
                {"id": index + 1, **payload}
                for index, payload in enumerate(self.tags)
                if (entity_type is None or payload["entity_type"] == entity_type)
                and (entity_id is None or payload["entity_id"] == entity_id)
                and (platform is None or payload["platform"] == platform)
            ]

        async def upsert_creator_profile(self, payload):
            self.profiles.append(payload)
            return {"id": len(self.profiles), **payload}

    repository = FakeRepository()

    result = await run_post_crawl_analysis(repository, job_id=1, platform="xhs")

    assert result["skipped"] is False
    assert result["tagging"]["tagged_posts"] == 1
    assert result["profiles"]["rebuilt_count"] == 1
    assert repository.profiles[0]["creator_id"] == "creator-1"


@pytest.mark.asyncio
async def test_post_crawl_analysis_respects_disabled_analysis_capability():
    class FakeRepository:
        async def get_platform_capability(self, platform):
            return {"platform": platform, "enabled": True, "analysis_enabled": False}

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return []

        async def bulk_upsert_entity_tags(self, payloads):
            return []

        async def list_all_posts(self, job_id=None, platform=None):
            return []

        async def list_all_comments(self, job_id=None, platform=None):
            return []

        async def list_all_authors(self, job_id=None, platform=None):
            return []

        async def list_entity_tags(self, **kwargs):
            return []

        async def upsert_creator_profile(self, payload):
            return payload

    result = await run_post_crawl_analysis(FakeRepository(), job_id=1, platform="xhs")

    assert result["skipped"] is True
    assert result["reason"] == "platform_analysis_disabled"


@pytest.mark.asyncio
async def test_rebuild_account_profiles_from_posts_uses_author_evidence():
    class FakeRepository:
        def __init__(self):
            self.profiles = {}
            self.roles = []

        async def list_posts(self, job_id, limit=None):
            return [
                {
                    "platform": "xhs",
                    "engagement_json": {
                        "author_id": "u1",
                        "nickname": "Teacher A",
                        "source_keyword": "K12",
                    },
                },
                {"platform": "xhs", "engagement_json": {}},
            ]

        async def upsert_account_profile(self, payload):
            key = (payload["platform"], payload["account_id"])
            if key not in self.profiles:
                self.profiles[key] = {"id": len(self.profiles) + 1, **payload}
            return self.profiles[key]

        async def upsert_account_role(self, payload):
            self.roles.append(payload)
            return {"id": len(self.roles), **payload}

    repository = FakeRepository()

    result = await rebuild_account_profiles_from_posts(
        repository,
        job_id=1,
        platform="xhs",
        vertical_id=1,
        scene_pack_id=2,
    )

    assert result == {"skipped": False, "upserted": 1, "missing_author": 1}
    assert repository.profiles[("xhs", "u1")]["display_name"] == "Teacher A"
    assert repository.roles[0]["role"] == "candidate_creator"
    assert repository.roles[0]["scene_pack_id"] == 2

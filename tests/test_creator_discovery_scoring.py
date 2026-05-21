import pytest

from research.creator_search import (
    calculate_creator_match_score,
    extract_creator_candidates_from_discovery_job,
    parse_search_intent,
    rebuild_creator_profiles,
    search_creators,
)
from research.creator_scoring import score_creator_candidate


def test_parse_search_intent_requires_vertical_selection_for_multiple_verticals():
    verticals = [
        {"id": 1, "name": "Education"},
        {"id": 2, "name": "Technology"},
    ]
    tags = [
        {"id": 11, "vertical_id": 1, "tag_name": "AI教育", "keywords": ["AI"], "synonyms": []},
        {"id": 21, "vertical_id": 2, "tag_name": "AI工具", "keywords": ["AI"], "synonyms": []},
    ]

    result = parse_search_intent(
        raw_query="AI教育工具",
        verticals=verticals,
        tag_definitions=tags,
    )

    assert result["needs_vertical_selection"] is True
    assert {item["id"] for item in result["detected_verticals"]} == {1, 2}


def test_creator_match_score_prioritizes_required_tags():
    score = calculate_creator_match_score(
        required_tag_ids=[1, 2],
        optional_tag_ids=[],
        creator_profile={"recent_post_count_30d": 10, "tag_summary_json": {"1": {}, "2": {}}},
        entity_tags=[
            {"tag_id": 1, "confidence": 0.9, "evidence_json": {}},
            {"tag_id": 2, "confidence": 0.8, "evidence_json": {}},
        ],
        recent_posts=[],
    )

    assert score > 50


def test_score_creator_candidate_requires_primary_and_explains_evidence():
    profile = {
        "platform": "xhs",
        "account_id": "u1",
        "display_name": "K12 Mom",
        "recent_post_count_30d": 5,
        "avg_engagement_rate": 0.08,
    }
    posts = [
        {
            "platform_post_id": "p1",
            "title": "K12教育陪读经验",
            "content": "单亲妈妈如何做作业辅导",
            "engagement_json": {"liked_count": 100, "comment_count": 20},
            "url": "https://example.test/p1",
        }
    ]
    keywords = [
        {"keyword": "K12教育", "keyword_type": "primary", "weight": 1.0},
        {"keyword": "单亲妈妈", "keyword_type": "secondary", "weight": 0.8},
        {"keyword": "作业辅导", "keyword_type": "secondary", "weight": 0.6},
        {"keyword": "成人教育", "keyword_type": "negative", "weight": 1.0},
    ]

    result = score_creator_candidate(profile, posts, keywords)

    assert result["eligible"] is True
    assert result["score"] >= 70
    assert "K12教育" in result["matched_keywords"]["primary"]
    assert result["evidence"][0]["post_id"] == "p1"


@pytest.mark.asyncio
async def test_search_creators_auto_rebuilds_profiles_and_uses_text_fallback():
    class FakeRepository:
        def __init__(self):
            self.profiles = []

        async def list_tag_definitions(self, vertical_id=None, enabled_only=True):
            return []

        async def list_verticals(self, enabled_only=True):
            return []

        async def list_creator_profiles(self, platforms=None, limit=None):
            if platforms:
                return [item for item in self.profiles if item["platform"] in platforms]
            return self.profiles

        async def list_entity_tags(
            self,
            entity_type=None,
            entity_id=None,
            platform=None,
            vertical_id=None,
            tag_ids=None,
        ):
            return []

        async def list_all_posts(self, job_id=None, platform=None):
            posts = [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "author_hash": "creator-1",
                    "title": "K12 learning plan",
                    "content": "single mom family education notes",
                    "engagement_json": {
                        "nickname": "Teacher A",
                        "liked_count": 120,
                        "comment_count": 12,
                    },
                },
                {
                    "platform": "xhs",
                    "platform_post_id": "p2",
                    "author_hash": "creator-1",
                    "title": "K12 reading practice",
                    "content": "after school tutoring",
                    "engagement_json": {"liked_count": 80},
                },
                {
                    "platform": "dy",
                    "platform_post_id": "p3",
                    "author_hash": "creator-2",
                    "title": "cooking",
                    "content": "dinner",
                    "engagement_json": {},
                },
            ]
            return [post for post in posts if platform is None or post["platform"] == platform]

        async def list_posts_by_creator(self, platform, creator_id, limit=None):
            posts = await self.list_all_posts(platform=platform)
            matched = [post for post in posts if post["author_hash"] == creator_id]
            return matched[:limit] if limit else matched

        async def upsert_creator_profile(self, payload):
            item = {"id": len(self.profiles) + 1, **payload}
            self.profiles.append(item)
            return item

    result = await search_creators(
        FakeRepository(),
        {
            "raw_query": "K12 + single mom",
            "platforms": ["xhs"],
            "limit": 10,
        },
    )

    assert result["diagnostics"]["auto_rebuilt_profiles"] == 1
    assert result["diagnostics"]["fallback_used"] is True
    assert result["results"][0]["creator_id"] == "creator-1"
    assert result["results"][0]["display_name"] == "Teacher A"
    assert result["results"][0]["match_score"] > 0
    assert result["results"][0]["representative_posts"][0]["platform_post_id"] == "p1"


@pytest.mark.asyncio
async def test_rebuild_creator_profiles_derives_xhs_profile_url_from_post_author():
    class FakeRepository:
        def __init__(self):
            self.profiles = []

        async def list_all_posts(self, job_id=None, platform=None):
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "author_hash": "xhs_hash_1",
                    "title": "K12 note",
                    "content": "single mom education",
                    "engagement_json": {
                        "author_id": "5f58bd990000000001003753",
                        "nickname": "Teacher A",
                        "liked_count": 120,
                    },
                }
            ]

        async def list_entity_tags(self, **kwargs):
            return []

        async def upsert_creator_profile(self, payload):
            self.profiles.append(payload)
            return {"id": len(self.profiles), **payload}

    result = await rebuild_creator_profiles(FakeRepository(), platform="xhs")

    profile = result["profiles"][0]
    assert profile["display_name"] == "Teacher A"
    assert profile["profile_url"] == "https://www.xiaohongshu.com/user/profile/5f58bd990000000001003753"


@pytest.mark.asyncio
async def test_extract_creator_candidates_returns_profile_fields():
    class FakeRepository:
        async def get_job(self, job_id):
            return {"id": job_id, "platforms": ["xhs"], "keywords": ["K12"]}

        async def list_all_posts(self, job_id=None, platform=None):
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "author_hash": "xhs_hash_1",
                    "title": "K12 note",
                    "content": "single mom education",
                    "engagement_json": {
                        "author_id": "5f58bd990000000001003753",
                        "nickname": "Teacher A",
                        "liked_count": 120,
                    },
                }
            ]

        async def list_entity_tags(self, **kwargs):
            return []

        async def upsert_creator_profile(self, payload):
            return {"id": 1, **payload}

        async def list_creator_profiles(self, platforms=None):
            return []

        async def list_scene_pack_keywords(self, enabled_only=True):
            return [{"keyword": "K12", "keyword_type": "primary", "weight": 1.0}]

        async def list_posts_by_creator(self, platform, creator_id, limit=None):
            return await self.list_all_posts(platform=platform)

        async def upsert_creator_candidate(self, payload):
            return {"id": 1, **payload}

    result = await extract_creator_candidates_from_discovery_job(FakeRepository(), job_id=123)

    assert result["candidates"][0]["display_name"] == "Teacher A"
    assert result["candidates"][0]["profile_url"] == "https://www.xiaohongshu.com/user/profile/5f58bd990000000001003753"


@pytest.mark.asyncio
async def test_search_creators_uses_text_fallback_when_required_tags_are_not_built():
    class FakeRepository:
        async def list_tag_definitions(self, vertical_id=None, enabled_only=True):
            return [
                {
                    "id": 1,
                    "vertical_id": 1,
                    "tag_name": "K12",
                    "keywords": ["K12"],
                    "synonyms": [],
                    "negative_keywords": [],
                }
            ]

        async def list_verticals(self, enabled_only=True):
            return [{"id": 1, "name": "education"}]

        async def list_creator_profiles(self, platforms=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "creator_id": "creator-1",
                    "display_name": "Teacher A",
                    "recent_post_count_30d": 1,
                    "tag_summary_json": {},
                }
            ]

        async def list_entity_tags(self, **kwargs):
            return []

        async def list_posts_by_creator(self, platform, creator_id, limit=None):
            return [
                {
                    "platform": platform,
                    "platform_post_id": "p1",
                    "author_hash": creator_id,
                    "title": "K12 family education",
                    "content": "single mom learning notes",
                    "engagement_json": {"liked_count": 50},
                }
            ]

    result = await search_creators(
        FakeRepository(),
        {"raw_query": "K12", "selected_vertical_id": 1, "platforms": ["xhs"]},
    )

    assert result["diagnostics"]["matched_tag_count"] == 1
    assert result["diagnostics"]["fallback_used"] is True
    assert result["results"][0]["creator_id"] == "creator-1"

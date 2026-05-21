from fastapi.testclient import TestClient

import config
from api.main import app


def test_content_tracking_analyze_returns_hits(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_all_posts(self, platform=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "title": "K12教育",
                    "content": "单亲妈妈如何陪伴学习",
                    "author_hash": "a1",
                    "engagement_json": {"liked_count": 100},
                }
            ]

        async def list_all_comments(self, platform=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "platform_comment_id": "c1",
                    "platform_post_id": "p1",
                    "content": "单亲妈妈很需要这类K12建议",
                    "like_count": 3,
                }
            ]

        async def list_entity_tags(self, vertical_id=None, platform=None):
            return [
                {
                    "entity_type": "post",
                    "entity_id": "p1",
                    "platform": "xhs",
                    "tag_id": 1,
                    "confidence": 0.9,
                }
            ]

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return [{"id": 1, "tag_name": "单亲妈妈"}]

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/analyze",
        json={"query": "K12教育 + 单亲妈妈", "vertical_id": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["matched_posts"] == 1
    assert body["summary"]["matched_comments"] == 1
    assert body["fingerprints"][0]["fingerprint"]["summary"]


def test_content_tracking_extract_search_and_tracker_routes(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_scene_pack_keywords(self, scene_pack_ids=None, enabled_only=False):
            return [
                {
                    "scene_pack_id": 1,
                    "keyword": "K12",
                    "keyword_type": "primary",
                    "weight": 1,
                }
            ]

        async def list_all_posts(self, platform=None, limit=None):
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p1",
                    "title": "K12 tutoring",
                    "content": "single parent mothers",
                    "engagement_json": {"liked_count": 20},
                }
            ]

        async def create_content_tracker(self, payload):
            return {"id": 1, **payload}

        async def list_content_trackers(self, enabled_only=False):
            return [{"id": 1, "name": "tracker"}]

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/extract-keywords",
        json={"text": "K12 tutoring", "scene_pack_ids": [1]},
    )
    assert response.status_code == 200
    assert response.json()["keywords"][0]["keyword"] == "K12"

    response = client.post(
        "/api/content-tracking/search-similar",
        json={"keywords": ["K12"], "platforms": ["xhs"]},
    )
    assert response.status_code == 200
    assert response.json()["candidates"][0]["platform_post_id"] == "p1"

    response = client.post(
        "/api/content-tracking/trackers",
        json={"name": "K12 tracker", "platforms": ["xhs"], "included_keywords": ["K12"]},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "K12 tracker"


def test_content_tracking_extract_keywords_uses_ai_by_default(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("AI_GATEWAY_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "keyword-model")

    class FakeRepository:
        pass

    class FakeProvider:
        def __init__(self, *, base_url, api_key, model, timeout=60):
            assert base_url == "https://gateway.example/v1"
            assert api_key == "test-key"
            assert model == "keyword-model"

        async def complete_json(self, *, prompt, params=None):
            assert "未成年电竞" in prompt
            return {
                "keywords": [
                    {
                        "keyword": "未成年电竞",
                        "keyword_type": "primary",
                        "confidence": 0.96,
                        "evidence_text": "未成年电竞",
                        "reason": "核心追踪主题",
                        "query_variants": ["未成年电竞", "青少年电竞"],
                    },
                    {
                        "keyword": "游戏",
                        "keyword_type": "negative",
                        "confidence": 0.55,
                        "evidence_text": "电竞",
                        "reason": "单独搜索过宽",
                    },
                ]
            }

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "OpenAICompatibleProvider", FakeProvider)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/extract-keywords",
        json={"title": "电竞", "text": "未成年电竞", "platform": "xhs"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "ai"
    assert body["provider"]["model"] == "keyword-model"
    assert body["keywords"][0]["keyword"] == "未成年电竞"
    assert body["keywords"][0]["source"] == "ai"
    assert body["keywords"][1]["keyword_type"] == "negative"


def test_content_tracking_extract_keywords_falls_back_to_local_when_ai_fails(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")

    class FakeRepository:
        async def list_scene_pack_keywords(self, scene_pack_ids=None, enabled_only=False):
            return [
                {
                    "scene_pack_id": 1,
                    "keyword": "电竞",
                    "keyword_type": "primary",
                    "weight": 1,
                }
            ]

    class FakeProvider:
        def __init__(self, *, base_url, api_key, model, timeout=60):
            pass

        async def complete_json(self, *, prompt, params=None):
            raise RuntimeError("gateway down")

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "OpenAICompatibleProvider", FakeProvider)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/extract-keywords",
        json={"title": "电竞", "text": "未成年电竞"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "local_fallback"
    assert "gateway down" in body["fallback_reason"]
    assert body["keywords"][0]["keyword"] == "电竞"


def test_content_realtime_discovery_requires_explicit_switch(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/realtime-discovery",
        json={"keywords": ["K12"], "platforms": ["xhs"], "realtime": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"


def test_content_realtime_discovery_defaults_to_supported_platforms(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    calls = {"created_job": None, "scheduled": None}

    class FakeRepository:
        async def create_job(self, payload):
            calls["created_job"] = payload
            return {"id": 11, **payload}

    async def fake_schedule(job_id, background=True, force_schedule=True):
        calls["scheduled"] = {
            "job_id": job_id,
            "background": background,
            "force_schedule": force_schedule,
        }
        return {"status": "accepted", "job_id": job_id}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "schedule_and_execute_research_job", fake_schedule)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/realtime-discovery",
        json={"keywords": ["K12"], "platforms": [], "realtime": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == 11
    assert body["start_date"]
    assert body["end_date"]
    assert calls["created_job"]["platforms"] == ["xhs", "dy"]
    assert calls["created_job"]["start_date"] < calls["created_job"]["end_date"]
    assert (calls["created_job"]["end_date"] - calls["created_job"]["start_date"]).days == 2
    assert calls["created_job"]["comment_policy"]["content_tracking_total_limit"] == 50
    assert calls["created_job"]["comment_policy"]["max_posts_per_job"] == 25
    assert calls["scheduled"]["job_id"] == 11


def test_content_realtime_platform_resolution_all_defaults_to_xhs_and_dy():
    import api.routers.content_tracking as content_router

    assert content_router._resolve_realtime_platforms([]) == ["xhs", "dy"]


def test_content_realtime_platform_resolution_keeps_supported_single_platform():
    import api.routers.content_tracking as content_router

    assert content_router._resolve_realtime_platforms(["xhs"]) == ["xhs"]
    assert content_router._resolve_realtime_platforms(["dy"]) == ["dy"]


def test_content_realtime_platform_resolution_rejects_unsupported_platform():
    import api.routers.content_tracking as content_router

    try:
        content_router._resolve_realtime_platforms(["bili"])
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
        assert "小红书和抖音" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("unsupported realtime platform should fail")


def test_search_similar_realtime_schedules_job_and_refreshes(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    calls = {"created_job": None, "scheduled": None, "waited": None}

    class FakeRepository:
        async def create_job(self, payload):
            calls["created_job"] = payload
            return {"id": 42, **payload}

        async def get_job(self, job_id):
            return {"id": job_id, "status": "completed", "keywords": ["K12"]}

        async def list_all_posts(self, job_id=None, platform=None, limit=None):
            calls["list_job_id"] = job_id
            return [
                {
                    "platform": "xhs",
                    "platform_post_id": "p-live",
                    "title": "K12 realtime imported post",
                    "content": "K12 tutoring",
                    "engagement_json": {"liked_count": 40},
                }
            ]

    async def fake_schedule(job_id, background=True, force_schedule=True):
        calls["scheduled"] = {
            "job_id": job_id,
            "background": background,
            "force_schedule": force_schedule,
        }
        return {"status": "accepted", "job_id": job_id}

    async def fake_wait(job_id):
        calls["waited"] = job_id
        return {"id": job_id, "status": "completed", "keywords": ["K12"]}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "schedule_and_execute_research_job", fake_schedule)
    monkeypatch.setattr(content_router, "wait_for_research_job_status", fake_wait)

    client = TestClient(app)
    response = client.post(
        "/api/content-tracking/search-similar",
        json={"keywords": ["K12"], "platforms": [], "realtime": True, "limit": 50},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["realtime"]["enabled"] is True
    assert body["realtime"]["job_id"] == 42
    assert body["realtime"]["platforms"] == ["xhs", "dy"]
    assert body["realtime"]["status"] == "completed"
    assert body["realtime"]["matched_count"] == 1
    assert body["candidates"][0]["platform_post_id"] == "p-live"
    assert body["candidates"][0]["evidence"]["source"] == "realtime_imported"
    assert calls["created_job"]["topic"] == "content_realtime_discovery"
    assert calls["created_job"]["platforms"] == ["xhs", "dy"]
    assert calls["created_job"]["start_date"] < calls["created_job"]["end_date"]
    assert (calls["created_job"]["end_date"] - calls["created_job"]["start_date"]).days == 2
    assert calls["created_job"]["comment_policy"]["content_tracking_total_limit"] == 50
    assert calls["created_job"]["comment_policy"]["max_posts_per_job"] == 25
    assert calls["scheduled"]["job_id"] == 42
    assert calls["waited"] == 42


def test_content_realtime_total_limit_is_split_across_selected_platforms(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    calls = {"created_job": None}

    class FakeRepository:
        async def create_job(self, payload):
            calls["created_job"] = payload
            return {"id": 21, **payload}

    async def fake_schedule(job_id, background=True, force_schedule=True):
        return {"status": "accepted", "job_id": job_id}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "schedule_and_execute_research_job", fake_schedule)

    client = TestClient(app)
    response = client.post(
        "/api/content-tracking/realtime-discovery",
        json={"keywords": ["K12"], "platforms": ["xhs", "dy"], "realtime": True, "limit": 31, "collection_window_days": 7},
    )

    assert response.status_code == 200
    assert calls["created_job"]["comment_policy"]["content_tracking_total_limit"] == 31
    assert calls["created_job"]["comment_policy"]["max_posts_per_job"] == 16
    assert (calls["created_job"]["end_date"] - calls["created_job"]["start_date"]).days == 6


def test_search_similar_realtime_rejects_unsupported_platform(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/search-similar",
        json={"keywords": ["K12"], "platforms": ["bili"], "realtime": True},
    )

    assert response.status_code == 400
    assert "小红书和抖音" in response.json()["detail"]


def test_search_similar_realtime_busy_returns_409(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def create_job(self, payload):
            return {"id": 7, **payload}

    async def fake_schedule(job_id, background=True, force_schedule=True):
        return {"status": "busy", "job_id": 99, "message": "A research execution is already running"}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "schedule_and_execute_research_job", fake_schedule)

    client = TestClient(app)
    response = client.post(
        "/api/content-tracking/search-similar",
        json={"keywords": ["K12"], "platforms": ["xhs"], "realtime": True},
    )

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]


def test_content_realtime_discovery_busy_returns_non_cancellable_busy_state(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    calls = {"cancelled": None}

    class FakeRepository:
        async def create_job(self, payload):
            return {"id": 7, **payload}

        async def update_job(self, job_id, payload):
            calls["cancelled"] = (job_id, payload)
            return {"id": job_id, **payload}

    async def fake_schedule(job_id, background=True, force_schedule=True):
        return {"status": "busy", "job_id": 99, "message": "A research execution is already running"}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "schedule_and_execute_research_job", fake_schedule)

    client = TestClient(app)
    response = client.post(
        "/api/content-tracking/realtime-discovery",
        json={"keywords": ["K12"], "platforms": ["xhs"], "realtime": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "busy"
    assert body["job_id"] is None
    assert body["busy_job_id"] == 99
    assert calls["cancelled"] == (7, {"status": "cancelled"})


def test_cancel_content_realtime_job_stops_active_execution(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    calls = {"cancelled": None}

    class FakeRepository:
        async def get_job(self, job_id):
            return {"id": job_id, "topic": "content_realtime_discovery", "status": "running"}

        async def update_job(self, job_id, payload):
            calls["cancelled"] = (job_id, payload)
            return {"id": job_id, **payload}

    async def fake_cancel(job_id):
        return {"status": "stopping", "job_id": job_id, "crawler_stopped": True}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "cancel_active_research_execution_job", fake_cancel)

    client = TestClient(app)
    response = client.post("/api/content-tracking/realtime-jobs/42/cancel")

    assert response.status_code == 200
    assert response.json() == {"status": "stopping", "job_id": 42, "crawler_stopped": True}
    assert calls["cancelled"] is None


def test_cancel_content_realtime_job_rejects_other_topic(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def get_job(self, job_id):
            return {"id": job_id, "topic": "creator_realtime_discovery", "status": "running"}

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)

    client = TestClient(app)
    response = client.post("/api/content-tracking/realtime-jobs/42/cancel")

    assert response.status_code == 400
    assert "content tracking realtime" in response.json()["detail"]


def test_content_tracking_ai_analysis_uses_env_gateway(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("AI_GATEWAY_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "test-model")

    class FakeRepository:
        pass

    class FakeProvider:
        def __init__(self, *, base_url, api_key, model, timeout=60):
            assert base_url == "https://gateway.example/v1"
            assert api_key == "test-key"
            assert model == "test-model"

        async def complete_json(self, *, prompt, params=None):
            assert "本地证据" in prompt
            return {
                "topic_summary": "K12 内容追踪",
                "keyword_judgement": [
                    {
                        "keyword": "K12",
                        "value": "high",
                        "reason": "本地候选内容命中",
                        "tracking_action": "include",
                    }
                ],
                "similar_content_patterns": ["标题集中在家长焦虑和陪伴学习"],
                "comment_feedback": ["评论关注执行方法"],
                "tracking_suggestions": {
                    "included_keywords": ["K12"],
                    "excluded_keywords": ["无关"],
                    "platform_notes": ["优先看小红书"],
                },
                "opportunities": ["拆解陪伴学习场景"],
                "risk_notes": [],
            }

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    monkeypatch.setattr(content_router, "OpenAICompatibleProvider", FakeProvider)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/ai-analysis",
        json={
            "title": "K12教育",
            "text": "单亲妈妈如何陪伴学习",
            "platform": "xhs",
            "keywords": ["K12"],
            "candidates": [{"platform": "xhs", "title": "K12 陪伴", "similarity_score": 92}],
            "comments": [{"platform": "xhs", "content": "需要方法"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"]["model"] == "test-model"
    assert body["analysis"]["topic_summary"] == "K12 内容追踪"
    assert body["analysis"]["tracking_suggestions"]["included_keywords"] == ["K12"]


def test_content_tracking_ai_analysis_requires_provider(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)

    class FakeRepository:
        async def list_ai_providers(self):
            return []

    import api.routers.content_tracking as content_router

    monkeypatch.setattr(content_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.post(
        "/api/content-tracking/ai-analysis",
        json={"text": "K12 tutoring", "keywords": ["K12"]},
    )

    assert response.status_code == 400
    assert "AI_GATEWAY_API_KEY" in response.json()["detail"]


def test_growth_report_returns_summary(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return [{"platform": "xhs", "creator_id": "a1", "vertical_id": vertical_id, "match_score": 88}]

        async def list_creator_profiles(self, platforms=None, limit=None):
            return [{"platform": "xhs", "creator_id": "a1", "tag_summary_json": {"1": {"count": 3}}}]

        async def list_competitor_accounts(self, enabled_only=False):
            return [{"platform": "xhs", "creator_id": "c1", "vertical_id": 1, "enabled": True}]

        async def list_creator_daily_snapshots(self, platform=None, creator_id=None):
            return [{"platform": "xhs", "tag_distribution_json": {"1": 8}}]

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return [{"id": 1, "tag_name": "K12教育", "vertical_id": 1}]

        async def list_entity_tags(self, vertical_id=None, platform=None, tag_ids=None, entity_type=None, entity_id=None):
            return [{"tag_id": 1, "platform": "xhs"}]

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/growth-summary?vertical_id=1&platform=xhs")

    assert response.status_code == 200
    assert response.json()["metrics"]["candidate_creators"] == 1

    response = client.get("/api/reports/boss-summary?vertical_id=1&platform=xhs")

    assert response.status_code == 200
    assert response.json()["sections"]["creator_discovery"]["count"] == 1
    assert response.json()["recommended_actions"]


def test_growth_report_falls_back_to_keyword_heat_snapshots(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)

    class FakeRepository:
        async def list_creator_candidates(self, vertical_id=None, platform=None, pool_name=None):
            return []

        async def list_creator_profiles(self, platforms=None, limit=None):
            return []

        async def list_competitor_accounts(self, enabled_only=False):
            return []

        async def list_creator_daily_snapshots(self, platform=None, creator_id=None):
            return []

        async def list_tag_definitions(self, vertical_id=None, enabled_only=False):
            return []

        async def list_entity_tags(self, vertical_id=None, platform=None, tag_ids=None, entity_type=None, entity_id=None):
            return []

        async def list_competitor_composition_snapshots(self, platform=None, limit=50):
            return []

        async def list_keyword_heat_snapshots(self, platform=None, limit=50):
            return [
                {
                    "keyword": "单亲妈妈陪读",
                    "platform": "xhs",
                    "heat_score": 88,
                    "growth_score": 19,
                    "platform_signal": "boosting",
                    "evidence": {"items": ["source keyword ranking"]},
                }
            ]

        async def list_content_tracking_snapshots(self, platform=None, limit=50):
            return []

    import api.routers.reports as reports_router

    monkeypatch.setattr(reports_router, "ResearchRepository", FakeRepository)
    client = TestClient(app)

    response = client.get("/api/reports/growth-summary?vertical_id=1&platform=xhs")

    assert response.status_code == 200
    assert response.json()["top_opportunities"]
    assert response.json()["top_opportunities"][0]["tag_name"] == "单亲妈妈陪读"

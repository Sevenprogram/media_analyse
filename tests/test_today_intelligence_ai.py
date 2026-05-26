from __future__ import annotations

from pathlib import Path
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables
import research.today_intelligence as today_intelligence
from research.today_intelligence import (
    TODAY_INTELLIGENCE_SETTING_KEY,
    build_today_intelligence_input,
    get_latest_today_intelligence,
    run_today_intelligence_analysis,
)
from research.repository import ResearchRepository
from saas_test_utils import authenticate_test_client


class FakeTodayRepository:
    def __init__(self) -> None:
        self.saved_setting: dict | None = None
        self.saved_settings: dict[str, dict] = {}

    async def list_jobs(self) -> list[dict]:
        return [{"id": 1, "name": "暑假规划采集", "status": "completed", "platforms": ["xhs"]}]

    async def list_jobs_for_project(self, project_keys: list[str]) -> list[dict]:
        keys = {str(item) for item in project_keys}
        if {"77", "Summer Education", "summer_education"} & keys:
            return [
                {
                    "id": 1,
                    "name": "Summer Education collection",
                    "topic": "summer_education",
                    "status": "completed",
                    "platforms": ["xhs"],
                }
            ]
        return []

    async def get_job_stats_many(self, job_ids: list[int]) -> dict[int, dict]:
        return {
            1: {
                "posts": 120,
                "comments": 40,
                "raw_records": 40,
                "authors": 8,
                "by_platform": {"posts": {"xhs": 120}, "comments": {"xhs": 40}},
            }
        }

    async def list_growth_project_keywords(self, project_id: int, status: str | None = None) -> list[dict]:
        if project_id != 77:
            return []
        return [
            {
                "project_id": 77,
                "keyword": "鏆戝亣瑙勫垝",
                "keyword_type": "core",
                "status": "active",
            }
        ]

    async def list_creator_candidates(self, **kwargs) -> list[dict]:
        return []

    async def list_keyword_heat_snapshots(self, **kwargs) -> list[dict]:
        return [
            {
                "keyword": "暑假规划",
                "platform": "xhs",
                "heat_score": 88,
                "growth_score": 73,
                "sample_count": 120,
                "evidence": {"samples": [{"title": "暑假前先做目标拆解", "platform": "xhs"}]},
            }
        ]

    async def list_competitor_composition_snapshots(self, **kwargs) -> list[dict]:
        return []

    async def list_content_tracking_snapshots(self, **kwargs) -> list[dict]:
        return []

    async def list_monitor_pools(self, **kwargs) -> list[dict]:
        return []

    async def list_opportunity_feedback(self, **kwargs) -> list[dict]:
        return []

    async def get_database_collection_stats(self) -> dict:
        return {
            "total_collected": 200,
            "research_posts": 120,
            "research_comments": 40,
            "raw_records": 40,
            "creator_profiles": 8,
            "entity_tags": 0,
            "creator_candidates": 0,
            "by_platform": {"posts": {"xhs": 120}, "comments": {"xhs": 40}, "raw_records": {"xhs": 40}},
            "raw_platform_tables": {},
            "raw_platform_totals": {},
        }

    async def upsert_global_setting(self, key: str, value: dict) -> dict:
        self.saved_setting = {"key": key, "value": value}
        self.saved_settings[key] = self.saved_setting
        return self.saved_setting

    async def get_global_setting(self, key: str) -> dict | None:
        return self.saved_settings.get(key)


class StubTodayAIProvider:
    calls: list[dict] = []

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete_json(self, *, prompt: str, params: dict | None = None) -> dict:
        self.calls.append({"prompt": prompt, "params": params or {}, "model": self.model})
        return {
            "executive_summary": "AI 今日情报已生成。",
            "actions": [
                {
                    "id": "ai-action-1",
                    "title": "发布暑假规划内容",
                    "reason": "暑假规划热度和样本质量都达标。",
                    "priority_explanation": "今日窗口明显",
                    "target_type": "keyword",
                    "action": "open_opportunity",
                    "payload": {"keyword": "暑假规划"},
                    "evidence_refs": ["暑假前先做目标拆解"],
                    "risk_notes": [],
                }
            ],
            "opportunity_explanations": [
                {
                    "opportunity_id": "keyword:xhs:暑假规划",
                    "why_now": "小红书样本里暑假规划正在升温。",
                    "suggested_angle": "用家长决策清单切入。",
                    "execution_advice": "先做一条清单型笔记。",
                    "risk_notes": ["样本偏向小红书"],
                    "evidence_refs": ["暑假前先做目标拆解"],
                }
            ],
            "risk_explanations": [],
            "sample_quality_explanation": {
                "summary": "样本量可用，但平台偏单一。",
                "coverage_gap": "缺少抖音样本。",
                "collection_advice": "补采抖音近 3 天样本。",
            },
            "data_bias_notes": ["样本偏向小红书"],
            "assumptions": ["仅使用输入数据"],
        }


class FailingTodayAIProvider(StubTodayAIProvider):
    async def complete_json(self, *, prompt: str, params: dict | None = None) -> dict:
        raise RuntimeError("gateway down")


class ProjectCreatorRepository(FakeTodayRepository):
    async def list_growth_project_keywords(self, project_id: int, status: str | None = None) -> list[dict]:
        return [
            {
                "project_id": project_id,
                "keyword": "education",
                "keyword_type": "core",
                "status": "active",
            }
        ]

    async def list_creator_candidates(self, **kwargs) -> list[dict]:
        if kwargs.get("pool_name"):
            return []
        return [
            {
                "id": 1,
                "platform": "xhs",
                "creator_id": "creator_education",
                "match_score": 92,
                "matched_tags": ["education"],
                "evidence": {
                    "matched_keywords": ["education"],
                    "representative_posts": [{"title": "education planning tips"}],
                },
            },
            {
                "id": 2,
                "platform": "xhs",
                "creator_id": "creator_gaming",
                "match_score": 100,
                "matched_tags": ["gaming"],
                "evidence": {
                    "matched_keywords": ["gaming"],
                    "representative_posts": [{"title": "gaming clip"}],
                },
            },
        ]

    async def get_creator_profile(self, platform: str, creator_id: str) -> dict | None:
        if creator_id == "creator_education":
            return {
                "platform": platform,
                "creator_id": creator_id,
                "display_name": "Education Creator",
                "profile_url": "https://example.test/creator_education",
                "recent_post_count_30d": 12,
            }
        return None


class ProjectPoolCreatorRepository(ProjectCreatorRepository):
    async def list_creator_candidates(self, **kwargs) -> list[dict]:
        if kwargs.get("pool_name") == "project:77:realtime":
            return [
                {
                    "id": 3,
                    "platform": "xhs",
                    "creator_id": "project_creator",
                    "match_score": 97,
                    "matched_tags": ["unrelated text"],
                    "evidence": {"matched_keywords": ["unrelated text"]},
                }
            ]
        return await super().list_creator_candidates(**kwargs)

    async def get_creator_profile(self, platform: str, creator_id: str) -> dict | None:
        if creator_id == "project_creator":
            return {
                "platform": platform,
                "creator_id": creator_id,
                "display_name": "Project Pool Creator",
            }
        return await super().get_creator_profile(platform, creator_id)


@pytest.mark.asyncio
async def test_project_today_filters_global_creator_candidates_and_enriches_names():
    repository = ProjectCreatorRepository()
    project_record = {
        "id": 77,
        "name": "Education Project",
        "primary_goal": "topic_discovery",
        "platforms": ["xhs"],
    }

    bundle = await build_today_intelligence_input(
        repository,
        project_id="education_project",
        project_record=project_record,
    )

    creator_opportunities = [
        item for item in bundle["dashboard"]["opportunities"] if item["type"] == "creator"
    ]
    assert [item["payload"]["creator_id"] for item in creator_opportunities] == ["creator_education"]
    assert creator_opportunities[0]["display_title"] == "Education Creator"
    assert creator_opportunities[0]["payload"]["display_name"] == "Education Creator"


@pytest.mark.asyncio
async def test_project_today_prefers_project_creator_pool_before_keyword_filter():
    repository = ProjectPoolCreatorRepository()
    project_record = {
        "id": 77,
        "name": "Education Project",
        "primary_goal": "topic_discovery",
        "platforms": ["xhs"],
    }

    bundle = await build_today_intelligence_input(
        repository,
        project_id="education_project",
        project_record=project_record,
    )

    creator_opportunities = [
        item for item in bundle["dashboard"]["opportunities"] if item["type"] == "creator"
    ]
    assert [item["payload"]["creator_id"] for item in creator_opportunities] == ["project_creator"]
    assert creator_opportunities[0]["display_title"] == "Project Pool Creator"


@pytest.mark.asyncio
async def test_run_today_intelligence_uses_ai_provider_and_persists(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("AI_GATEWAY_BASE_URL", "https://4router.net/v1")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "gpt-5.4-mini")
    repository = FakeTodayRepository()

    result = await run_today_intelligence_analysis(repository, provider_factory=StubTodayAIProvider)

    assert result["status"] == "completed"
    assert result["source"] == "ai"
    assert result["executive_summary"] == "AI 今日情报已生成。"
    assert result["provider"]["model"] == "gpt-5.4-mini"
    assert result["dashboard"]["opportunities"][0]["id"] == "keyword:xhs:暑假规划"
    assert repository.saved_setting is not None
    assert repository.saved_setting["key"] == TODAY_INTELLIGENCE_SETTING_KEY
    assert repository.saved_setting["value"]["ai_status"]["status"] == "completed"

    latest = await get_latest_today_intelligence(repository)
    assert latest is not None
    assert latest["ai_status"]["source"] == "ai"


@pytest.mark.asyncio
async def test_run_today_intelligence_persists_project_scope(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "gpt-5.4-mini")
    StubTodayAIProvider.calls.clear()
    repository = FakeTodayRepository()
    project_record = {
        "id": 77,
        "name": "Summer Education",
        "primary_goal": "topic_discovery",
        "platforms": ["xhs"],
    }

    result = await run_today_intelligence_analysis(
        repository,
        project_id="summer_education",
        project_record=project_record,
        provider_factory=StubTodayAIProvider,
    )

    expected_key = f"{TODAY_INTELLIGENCE_SETTING_KEY}:project:77"
    assert result["project_id"] == "77"
    assert result["project"]["name"] == "Summer Education"
    assert result["input_summary"]["scope"] == "project"
    assert result["database_stats"]["research_posts"] == 120
    assert expected_key in repository.saved_settings

    latest = await get_latest_today_intelligence(
        repository,
        project_id="summer_education",
        project_record=project_record,
    )
    assert latest is not None
    assert latest["project_id"] == "77"


@pytest.mark.asyncio
async def test_run_today_intelligence_falls_back_when_ai_fails(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    repository = FakeTodayRepository()

    result = await run_today_intelligence_analysis(repository, provider_factory=FailingTodayAIProvider)

    assert result["status"] == "fallback"
    assert result["source"] == "rules"
    assert "gateway down" in result["error"]
    assert result["actions"]
    assert result["sample_quality_explanation"]["summary"]


@pytest_asyncio.fixture
async def today_intelligence_client(tmp_path, monkeypatch):
    db_path = tmp_path / "today-intelligence-test.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "gpt-5.4-mini")
    monkeypatch.setattr(today_intelligence, "OpenAICompatibleProvider", StubTodayAIProvider)

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="today-intelligence@example.com",
            organization_name="Today Intelligence Workspace",
        )
        yield client

    await close_engines()


@pytest.mark.asyncio
async def test_today_intelligence_get_returns_ai_payload(today_intelligence_client: AsyncClient):
    response = await today_intelligence_client.get("/api/reports/today-intelligence")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["dashboard"]
    assert payload["database_stats"]
    assert payload["ai_status"]["status"] in {"completed", "fallback", "missing"}
    assert payload["ai_status"]["provider"]["model"] == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_today_intelligence_get_returns_project_payload(today_intelligence_client: AsyncClient):
    repository = ResearchRepository.global_scope()
    project = await repository.create_growth_project(
        {
            "name": "Project Scoped Today Test",
            "primary_goal": "topic_discovery",
            "platforms": ["xhs"],
            "archived": False,
        }
    )

    response = await today_intelligence_client.get(
        f"/api/reports/today-intelligence?project_id={project['id']}"
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == str(project["id"])
    assert payload["project"]["name"] == "Project Scoped Today Test"
    assert payload["input_summary"]["scope"] == "project"
    assert payload["ai_status"]["provider"]["model"] == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_today_intelligence_run_regenerates_payload(today_intelligence_client: AsyncClient):
    response = await today_intelligence_client.post(
        "/api/reports/today-intelligence/run",
        json={"force": True},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["generated_at"]
    assert payload["ai_status"]["source"] == "ai"


@pytest.mark.asyncio
async def test_today_intelligence_run_regenerates_project_payload(today_intelligence_client: AsyncClient):
    repository = ResearchRepository.global_scope()
    project = await repository.create_growth_project(
        {
            "name": "Project Scoped Regenerate Test",
            "primary_goal": "topic_discovery",
            "platforms": ["xhs"],
            "archived": False,
        }
    )

    response = await today_intelligence_client.post(
        "/api/reports/today-intelligence/run",
        json={"force": True, "project_id": str(project["id"])},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == str(project["id"])
    assert payload["project"]["name"] == "Project Scoped Regenerate Test"
    assert payload["input_summary"]["scope"] == "project"

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
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
from database.db_session import close_engines, create_tables, get_session
import research.content_strategy_refresh as content_strategy_refresh
from research.content_strategy_refresh import content_strategy_state_key
from research.models import (
    ResearchGrowthProject,
    ResearchGrowthProjectCollectionPlan,
    ResearchGrowthProjectKeyword,
    ResearchJob,
    ResearchPost,
)
from research.repository import ResearchRepository
from saas_test_utils import authenticate_test_client


class StubContentStrategyAIProvider:
    calls: list[dict] = []

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete_json(self, *, prompt: str, params: dict | None = None) -> dict:
        self.calls.append({"prompt": prompt, "params": params or {}, "model": self.model})
        return {
            "executive_summary": "AI 手动刷新已完成，建议优先做家长决策内容。",
            "platform_strategy": {"xhs": "先做决策型内容，再做案例复盘。"},
            "hotspots": [],
            "topic_ideas": [
                {
                    "title": "AI 手动刷新：暑假规划前先定目标",
                    "platform": "xhs",
                    "target_audience": "K12 家长",
                    "keywords": ["暑假规划", "K12 选课"],
                    "content_angle": "决策路径",
                    "outline": ["定目标", "定预算", "定执行表"],
                    "reason": "来自手动 AI 刷新的项目策略建议",
                    "risk_notes": ["避免承诺结果"],
                    "confidence": 0.9,
                }
            ],
            "risk_notes": ["避免承诺结果"],
            "content_strategy": {
                "strategy_note": "AI 手动刷新建议先跑决策路径，再补案例复盘。",
                "hero": {
                    "headline": "AI 手动刷新：优先做暑假规划决策内容",
                    "sample_summary": "AI 已使用项目样本和快照完成手动重算。",
                    "confidence": "high",
                },
                "keyword_trends": [
                    {
                        "keyword": "暑假规划",
                        "platform": "xhs",
                        "heat": "91",
                        "score": 91,
                        "direction": "up",
                    }
                ],
                "frameworks": [
                    {
                        "title": "AI 手动决策路径型",
                        "tags": ["决策", "家长"],
                        "posts": 6,
                        "interactions": "1.8k",
                        "leads": 22,
                    }
                ],
                "suggestions": [
                    {
                        "title": "AI 手动刷新：暑假规划前先定目标",
                        "audience": "K12 家长",
                        "chance": 91,
                        "risk": "medium",
                        "direction": "AI 手动刷新",
                        "platform": "xhs",
                        "keywords": ["暑假规划", "K12 选课"],
                        "outline": ["定目标", "定预算", "定执行表"],
                        "reason": "来自手动 AI 刷新的项目策略建议",
                        "risk_notes": ["避免承诺结果"],
                    }
                ],
                "risks": [
                    {
                        "title": "承诺表达风险",
                        "detail": "标题和正文需要避免绝对化结果承诺。",
                        "level": "medium",
                        "count": 1,
                    }
                ],
                "weekly_mix": [
                    {
                        "label": "决策内容",
                        "percent": 50,
                        "pieces": 5,
                        "exposure": "2.1k",
                        "leads": 20,
                    },
                    {
                        "label": "案例复盘",
                        "percent": 30,
                        "pieces": 3,
                        "exposure": "1.3k",
                        "leads": 12,
                    },
                    {
                        "label": "避坑清单",
                        "percent": 20,
                        "pieces": 2,
                        "exposure": "900",
                        "leads": 8,
                    },
                ],
            },
        }


class SectionedContentStrategyAIProvider:
    calls: list[dict] = []
    delay_seconds = 0.0

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def complete_json(self, *, prompt: str, params: dict | None = None) -> dict:
        self.calls.append({"prompt": prompt, "params": params or {}, "model": self.model})
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        section = _requested_section(prompt)
        if section == "suggestions":
            raise TimeoutError("suggestions timed out")
        if section == "overview":
            content_strategy = {
                "strategy_note": "Sectioned AI overview completed.",
                "hero": {
                    "headline": "Sectioned AI headline",
                    "sample_summary": "Sectioned AI used the local sample.",
                    "confidence": "high",
                },
            }
        elif section == "keyword_trends":
            content_strategy = {
                "keyword_trends": [
                    {
                        "keyword": "sectioned keyword",
                        "platform": "xhs",
                        "heat": "90",
                        "score": 90,
                        "direction": "up",
                    }
                ]
            }
        elif section == "frameworks":
            content_strategy = {
                "frameworks": [
                    {
                        "title": "Sectioned framework",
                        "tags": ["sectioned"],
                        "posts": 3,
                        "interactions": "900",
                        "leads": 8,
                    }
                ]
            }
        elif section == "risks":
            content_strategy = {
                "risks": [
                    {
                        "title": "Sectioned risk",
                        "detail": "Keep claims conservative.",
                        "level": "medium",
                        "count": 1,
                    }
                ]
            }
        elif section == "weekly_mix":
            content_strategy = {
                "weekly_mix": [
                    {"label": "Sectioned mix A", "percent": 60, "pieces": 6, "exposure": "1.2k", "leads": 12},
                    {"label": "Sectioned mix B", "percent": 40, "pieces": 4, "exposure": "800", "leads": 6},
                ]
            }
        else:
            raise AssertionError(f"expected sectioned prompt, got {section!r}")
        return {
            "executive_summary": "Sectioned AI summary.",
            "platform_strategy": {"xhs": "Use sectioned AI outputs."},
            "hotspots": [],
            "topic_ideas": [],
            "risk_notes": ["Sectioned AI risk note."],
            "content_strategy": content_strategy,
        }


def _requested_section(prompt: str) -> str:
    marker = "Requested section:"
    if marker not in prompt:
        return ""
    return prompt.split(marker, 1)[1].splitlines()[0].strip()


@pytest_asyncio.fixture
async def content_strategy_client(tmp_path, monkeypatch):
    db_path = tmp_path / "content-strategy-refresh-test.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="content-strategy@example.com",
            organization_name="Content Strategy Workspace",
        )
        yield client

    await close_engines()


async def _seed_project_strategy_scope(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/research/growth-projects",
        json={
            "name": "K12 Summer Planning",
            "primary_goal": "mixed_research",
            "platforms": ["xhs"],
            "keywords": ["暑假规划", "K12 选课"],
            "collection_depth": "standard",
            "refresh_cadence": "daily",
            "auto_ai_analysis": False,
            "start_immediately": False,
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()

    now = datetime.now(timezone.utc)
    async with get_session() as session:
        session.add(
            ResearchPost(
                job_id=int(created["job"]["id"]),
                platform="xhs",
                platform_post_id="project-post-1",
                author_hash="author-k12-1",
                title="暑假规划先别急着报班，先把 K12 目标定清楚",
                content="K12 家长在暑假规划前，要先看学习目标、预算和执行难度。",
                url="https://example.com/xhs/k12-1",
                publish_time=now - timedelta(days=1),
                engagement_json={"like_count": 126, "comment_count": 21, "share_count": 4},
            )
        )

    repository = ResearchRepository()
    await repository.upsert_global_setting(
        content_strategy_state_key(int(created["project_record_id"])),
        {
            "scheduled_refresh": {
                "status": "completed",
                "trigger": "schedule",
                "last_started_at": (now - timedelta(minutes=10)).isoformat(),
                "last_collection_completed_at": (now - timedelta(minutes=6)).isoformat(),
                "last_completed_at": (now - timedelta(minutes=4)).isoformat(),
                "last_collection_job_id": int(created["job"]["id"]),
                "last_error": None,
            },
            "manual_analysis": {
                "last_refreshed_at": None,
            },
            "ai_insights": {
                "mode": "ai",
                "status": "completed",
                "generated_at": (now - timedelta(minutes=4)).isoformat(),
                "provider": {"name": "AI Gateway", "model": "gateway-test-model"},
                "executive_summary": "AI 判断当前项目适合先做家长决策型内容。",
                "platform_strategy": {"xhs": "先做家长决策型内容"},
                "hotspots": [],
                "topic_ideas": [
                    {
                        "title": "暑假规划别先报班，K12 家长先做这 3 步",
                        "platform": "xhs",
                        "target_audience": "K12 家长",
                        "keywords": ["暑假规划", "K12 选课"],
                        "content_angle": "决策路径",
                        "outline": ["先定目标", "再定预算", "最后做执行表"],
                        "reason": "项目关键词在样本里命中，适合转化测试",
                        "risk_notes": ["避免绝对化结果承诺"],
                        "confidence": 0.88,
                    }
                ],
                "risk_notes": ["避免绝对化结果承诺"],
                "strategy_summary": {
                    "strategy_note": "AI 建议先跑决策路径内容，再补案例和复盘。",
                    "hero": {
                        "headline": "AI 判断：优先做暑假规划决策内容",
                        "sample_summary": "AI 已结合项目样本、关键词和快照完成判断。",
                        "confidence": "high",
                    },
                    "keyword_trends": [
                        {
                            "rank": 1,
                            "keyword": "暑假规划",
                            "platform": "xhs",
                            "platform_label": "小红书",
                            "heat": "88",
                            "score": 88,
                            "direction": "up",
                            "points": [44, 52, 61, 73],
                            "evidence": {"sample_count": 4},
                        }
                    ],
                    "frameworks": [
                        {
                            "title": "AI 决策路径型",
                            "tags": ["决策", "家长"],
                            "posts": 9,
                            "interactions": "2.1k",
                            "leads": 26,
                            "samples": [],
                        }
                    ],
                    "suggestions": [
                        {
                            "id": "ai-topic:seeded-1",
                            "title": "暑假规划别先报班，K12 家长先做这 3 步",
                            "audience": "K12 家长",
                            "chance": 86,
                            "risk": "中风险",
                            "direction": "AI 策略判断",
                            "platform": "xhs",
                            "keywords": ["暑假规划", "K12 选课"],
                            "outline": ["先定目标", "再定预算", "最后做执行表"],
                            "reason": "项目关键词在样本里命中，适合转化测试",
                            "evidence": {"keywords": ["暑假规划"]},
                            "samples": [],
                            "source": "ai",
                            "risk_notes": ["避免绝对化结果承诺"],
                        }
                    ],
                    "risks": [
                        {
                            "title": "标题承诺过强",
                            "detail": "需要避免承诺式表达，保留决策建议语气。",
                            "level": "中风险",
                            "count": 2,
                        }
                    ],
                    "weekly_mix": [
                        {
                            "label": "决策内容",
                            "percent": 45,
                            "pieces": 5,
                            "exposure": "2.4k",
                            "leads": 20,
                            "color": "#0f8f85",
                        },
                        {
                            "label": "案例内容",
                            "percent": 30,
                            "pieces": 3,
                            "exposure": "1.5k",
                            "leads": 10,
                            "color": "#2d9fd6",
                        },
                        {
                            "label": "复盘内容",
                            "percent": 25,
                            "pieces": 3,
                            "exposure": "1.2k",
                            "leads": 8,
                            "color": "#f59d48",
                        },
                    ],
                },
                "strategy_summary_source": "ai",
                "error": None,
                "input_summary": {"scope": {"project_name": "K12 Summer Planning"}},
            },
        },
    )
    return created


async def _seed_legacy_project_strategy_scope() -> dict:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        project = ResearchGrowthProject(
            org_id=None,
            name="Legacy Strategy",
            primary_goal="mixed_research",
            platforms=["xhs"],
            project_status="active",
            collection_status="scheduled",
            comment_collection_enabled=True,
            refresh_cadence="daily",
            sample_status="sample_insufficient",
            recommended_action="review_strategy",
            archived=False,
        )
        session.add(project)
        await session.flush()

        keyword = ResearchGrowthProjectKeyword(
            org_id=None,
            project_id=int(project.id),
            keyword="legacy summer planning",
            keyword_type="core",
            source="manual",
            status="active",
        )
        plan = ResearchGrowthProjectCollectionPlan(
            org_id=None,
            project_id=int(project.id),
            platform="xhs",
            collection_mode="search",
            keyword_scope="active",
            enabled=True,
            schedule_mode="interval",
            schedule_interval_minutes=1440,
        )
        job = ResearchJob(
            org_id=None,
            name="Legacy Strategy scheduled refresh",
            topic="legacy_strategy",
            platforms=["xhs"],
            collection_mode="search",
            keywords=["legacy summer planning"],
            target_ids=[],
            creator_ids=[],
            start_date=date.today() - timedelta(days=29),
            end_date=date.today(),
            status="completed",
            comment_policy={"growth_project_key": f"growth_project_record_{project.id}"},
            raw_record_mode="full",
            anonymize_authors=True,
            schedule_enabled=True,
            schedule_interval_minutes=1440,
            last_scheduled_at=now - timedelta(hours=1),
        )
        session.add_all([keyword, plan, job])
        await session.flush()

        post = ResearchPost(
            org_id=None,
            job_id=int(job.id),
            platform="xhs",
            platform_post_id="legacy-strategy-post-1",
            author_hash="legacy-strategy-author-1",
            title="Legacy summer planning topic",
            content="legacy summer planning for K12 families",
            url="https://example.com/xhs/legacy-strategy-1",
            publish_time=now - timedelta(days=1),
            engagement_json={"like_count": 98, "comment_count": 12, "share_count": 3},
        )
        session.add(post)
        await session.flush()
        return {
            "project_record_id": int(project.id),
            "project_slug": "legacy_strategy",
            "keyword_id": int(keyword.id),
            "plan_id": int(plan.id),
            "job_id": int(job.id),
            "post_id": int(post.id),
        }


@pytest.mark.asyncio
async def test_content_strategy_summary_uses_project_scope_and_manual_refresh(
    content_strategy_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await _seed_project_strategy_scope(content_strategy_client)

    summary_response = await content_strategy_client.get(
        f"/api/reports/content-strategy/summary?project_id={created['project_id']}&range=30d&goal=conversion&audience=all&stage=boost"
    )
    assert summary_response.status_code == 200, summary_response.text
    summary = summary_response.json()
    assert summary["project_context"]["project_id"] == created["project_id"]
    assert summary["project_context"]["project_record_id"] == created["project_record_id"]
    assert summary["refresh_status"]["scheduled_refresh"]["status"] == "completed"
    assert summary["ai_status"]["enabled"] is True
    assert summary["ai_status"]["source"] == "project_ai_strategy"
    assert summary["section_sources"]["hero"] == "ai"
    assert summary["hero"]["headline"] == "AI 判断：优先做暑假规划决策内容"
    assert summary["strategy_note"] == "AI 建议先跑决策路径内容，再补案例和复盘。"
    assert summary["refresh_status"]["ai_insights"]["strategy_summary_source"] == "ai"
    assert any(
        item["title"] == "暑假规划别先报班，K12 家长先做这 3 步"
        for item in summary["suggestions"]
    )

    tracker_response = await content_strategy_client.post(
        "/api/content-tracking/trackers",
        json={
            "name": "K12 暑假规划追踪器",
            "description": "追踪暑假规划相关同类内容",
            "platforms": ["xhs"],
            "included_keywords": ["暑假规划", "K12 选课"],
            "excluded_keywords": ["抽奖"],
            "schedule_interval_minutes": 720,
            "enabled": True,
        },
    )
    assert tracker_response.status_code == 200, tracker_response.text
    tracker = tracker_response.json()
    tracker_scoped_response = await content_strategy_client.get(
        f"/api/reports/content-strategy/summary?project_id={created['project_id']}&tracker_id={tracker['id']}&range=30d&goal=conversion&audience=all&stage=boost"
    )
    assert tracker_scoped_response.status_code == 200, tracker_scoped_response.text
    tracker_scoped = tracker_scoped_response.json()
    assert tracker_scoped["filters"]["tracker_id"] == tracker["id"]
    assert tracker_scoped["source_tracker"]["id"] == tracker["id"]
    assert tracker_scoped["source_tracker"]["name"] == "K12 暑假规划追踪器"
    assert tracker_scoped["project_context"]["project_id"] == created["project_id"]
    assert tracker_scoped["evidence_pack"]["items"][0]["type"] == "source_tracker"

    StubContentStrategyAIProvider.calls.clear()
    monkeypatch.setattr(content_strategy_refresh, "OpenAICompatibleProvider", StubContentStrategyAIProvider)

    refresh_response = await content_strategy_client.post(
        f"/api/reports/content-strategy/summary/refresh?project_id={created['project_id']}&range=30d&goal=conversion&audience=all&stage=boost&wait=true"
    )
    assert refresh_response.status_code == 200, refresh_response.text
    refreshed = refresh_response.json()
    manual_refreshed_at = refreshed["refresh_status"]["manual_analysis"]["last_refreshed_at"]
    assert manual_refreshed_at
    assert StubContentStrategyAIProvider.calls
    assert refreshed["ai_status"]["source"] == "project_ai_strategy"
    assert refreshed["ai_status"]["provider"] == {"name": "AI Gateway", "model": "gpt-5.4-mini"}
    assert refreshed["ai_status"]["strategy_summary_source"] == "ai"
    assert refreshed["section_sources"]["hero"] == "ai"
    assert refreshed["hero"]["headline"] == "AI 手动刷新：优先做暑假规划决策内容"
    assert any(
        item["title"] == "AI 手动刷新：暑假规划前先定目标"
        for item in refreshed["suggestions"]
    )

    repository = ResearchRepository()
    setting = await repository.get_global_setting(
        content_strategy_state_key(int(created["project_record_id"]))
    )
    assert setting is not None
    assert setting["value"]["manual_analysis"]["last_refreshed_at"] == manual_refreshed_at
    assert setting["value"]["ai_insights"]["strategy_summary_source"] == "ai"
    assert setting["value"]["ai_insights"]["strategy_summary"]["hero"]["headline"] == "AI 手动刷新：优先做暑假规划决策内容"


@pytest.mark.asyncio
async def test_content_strategy_manual_refresh_keeps_partial_ai_sections(
    content_strategy_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await _seed_project_strategy_scope(content_strategy_client)
    SectionedContentStrategyAIProvider.calls.clear()
    monkeypatch.setattr(content_strategy_refresh, "OpenAICompatibleProvider", SectionedContentStrategyAIProvider)

    response = await content_strategy_client.post(
        f"/api/reports/content-strategy/summary/refresh?project_id={created['project_id']}&range=30d&goal=conversion&audience=all&stage=boost&wait=true"
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    requested_sections = {_requested_section(item["prompt"]) for item in SectionedContentStrategyAIProvider.calls}

    assert requested_sections == {"overview", "keyword_trends", "frameworks", "suggestions", "risks", "weekly_mix"}
    assert payload["ai_status"]["status"] == "partial"
    assert payload["ai_status"]["source"] == "project_ai_partial"
    assert payload["ai_status"]["strategy_summary_source"] == "partial_ai"
    assert "suggestions: TimeoutError: suggestions timed out" in payload["ai_status"]["error"]
    assert payload["section_sources"]["hero"] == "ai"
    assert payload["section_sources"]["keyword_trends"] == "ai"
    assert payload["section_sources"]["frameworks"] == "ai"
    assert payload["section_sources"]["suggestions"] == "rules"
    assert payload["section_sources"]["risks"] == "ai"
    assert payload["section_sources"]["weekly_mix"] == "ai"
    assert payload["hero"]["headline"] == "Sectioned AI headline"
    assert payload["keyword_trends"][0]["keyword"] == "sectioned keyword"
    assert payload["frameworks"][0]["title"] == "Sectioned framework"
    assert payload["risks"][0]["title"] == "Sectioned risk"
    assert payload["weekly_mix"][0]["label"] == "Sectioned mix A"
    assert all(item["source"] == "rules" for item in payload["suggestions"])
    assert payload["refresh_status"]["ai_insights"]["section_statuses"]["suggestions"]["status"] == "fallback"
    assert payload["refresh_status"]["ai_insights"]["section_statuses"]["keyword_trends"]["status"] == "completed"


@pytest.mark.asyncio
async def test_content_strategy_manual_refresh_starts_background_ai_analysis(
    content_strategy_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await _seed_project_strategy_scope(content_strategy_client)
    SectionedContentStrategyAIProvider.calls.clear()
    SectionedContentStrategyAIProvider.delay_seconds = 0.05
    monkeypatch.setattr(content_strategy_refresh, "OpenAICompatibleProvider", SectionedContentStrategyAIProvider)

    try:
        response = await content_strategy_client.post(
            f"/api/reports/content-strategy/summary/refresh?project_id={created['project_id']}&range=30d&goal=conversion&audience=all&stage=boost"
        )

        assert response.status_code == 200, response.text
        started = response.json()
        assert started["refresh_status"]["scheduled_refresh"]["status"] == "ai_analyzing"

        completed = started
        for _ in range(20):
            await asyncio.sleep(0.05)
            poll = await content_strategy_client.get(
                f"/api/reports/content-strategy/summary?project_id={created['project_id']}&range=30d&goal=conversion&audience=all&stage=boost"
            )
            assert poll.status_code == 200, poll.text
            completed = poll.json()
            if completed["refresh_status"]["scheduled_refresh"]["status"] != "ai_analyzing":
                break

        assert completed["ai_status"]["status"] == "partial"
        assert completed["section_sources"]["keyword_trends"] == "ai"
        assert completed["section_sources"]["suggestions"] == "rules"
    finally:
        SectionedContentStrategyAIProvider.delay_seconds = 0.0


@pytest.mark.asyncio
async def test_content_strategy_summary_claims_legacy_project_into_current_org(
    content_strategy_client: AsyncClient,
) -> None:
    legacy = await _seed_legacy_project_strategy_scope()

    response = await content_strategy_client.get(
        f"/api/reports/content-strategy/summary?project_id={legacy['project_slug']}&range=30d&goal=conversion&audience=all&stage=boost"
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_context"]["project_record_id"] == legacy["project_record_id"]
    assert payload["project_context"]["project_name"] == "Legacy Strategy"
    assert payload["hero"]["evidence_count"] >= 1

    async with get_session() as session:
        project = await session.get(ResearchGrowthProject, legacy["project_record_id"])
        keyword = await session.get(ResearchGrowthProjectKeyword, legacy["keyword_id"])
        plan = await session.get(ResearchGrowthProjectCollectionPlan, legacy["plan_id"])
        job = await session.get(ResearchJob, legacy["job_id"])
        post = await session.get(ResearchPost, legacy["post_id"])

        assert project is not None
        assert keyword is not None
        assert plan is not None
        assert job is not None
        assert post is not None
        claimed_org_ids = {
            project.org_id,
            keyword.org_id,
            plan.org_id,
            job.org_id,
            post.org_id,
        }
        assert None not in claimed_org_ids
        assert len(claimed_org_ids) == 1

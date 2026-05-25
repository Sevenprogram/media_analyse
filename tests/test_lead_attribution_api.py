from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import config
from config.db_config import sqlite_db_config
from api.routers.reports import _project_jobs_for_sample_analysis
from database.db_session import close_engines, create_tables, get_session
from saas_test_utils import authenticate_test_client
from research.models import (
    ResearchComment,
    ResearchJob,
    ResearchLeadAttributionDailySnapshot,
    ResearchLeadAttributionResult,
    ResearchPost,
)


@pytest_asyncio.fixture
async def lead_attribution_client(tmp_path, monkeypatch):
    db_path = tmp_path / "lead-attribution-test.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="lead-attribution@example.com",
            organization_name="Lead Attribution Workspace",
        )
        create_response = await client.post(
            "/api/research/growth-projects",
            json={
                "name": "Pet Food Growth",
                "primary_goal": "keyword_expansion",
                "platforms": ["xhs", "dy"],
                "keywords": ["cat food", "kitten food"],
                "collection_depth": "standard",
                "refresh_cadence": "off",
                "auto_ai_analysis": False,
                "start_immediately": False,
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        post_id = await _seed_project_post(created["job"]["id"])
        yield client, created["project_id"], post_id

    await close_engines()


async def _seed_project_post(job_id: int) -> int:
    async with get_session() as session:
        job = await session.get(ResearchJob, job_id)
        assert job is not None
        post = ResearchPost(
            org_id=job.org_id,
            job_id=job_id,
            platform="xhs",
            platform_post_id="lead-attr-post-1",
            author_hash="creator-1",
            title="Kitten Food Buying Guide",
            content="Sample post used in lead attribution tests",
            url="https://example.com/post/1",
            publish_time=datetime.now(timezone.utc) - timedelta(days=1),
            engagement_json={"source_keyword": "kitten food", "like_count": 88},
        )
        session.add(post)
        await session.flush()
    return int(post.id)


async def _seed_project_comment(job_id: int, platform_post_id: str = "lead-attr-post-1") -> int:
    async with get_session() as session:
        job = await session.get(ResearchJob, job_id)
        assert job is not None
        comment = ResearchComment(
            org_id=job.org_id,
            job_id=job_id,
            platform="xhs",
            platform_comment_id=f"comment-{job_id}-1",
            platform_post_id=platform_post_id,
            author_hash="commenter-1",
            content="想咨询课程多少钱，可以加微信吗？",
            publish_time=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        session.add(comment)
        await session.flush()
    return int(comment.id)


async def _seed_project_comment_for_post(post_id: int) -> int:
    async with get_session() as session:
        post = await session.get(ResearchPost, post_id)
        assert post is not None
        job_id = int(post.job_id)
        platform_post_id = str(post.platform_post_id)
    return await _seed_project_comment(job_id, platform_post_id)


@pytest.mark.asyncio
async def test_sample_analysis_matches_semantic_project_alias() -> None:
    class Repository:
        async def list_jobs_for_project(self, project_keys: list[str]) -> list[dict]:
            return [
                {
                    "id": 1,
                    "name": "2026 Summer 教育项目 initial collection",
                    "topic": "2026_summer_教育项目",
                }
            ]

        async def list_jobs(self) -> list[dict]:
            return [
                {
                    "id": 2,
                    "name": "2026 summer education topic research collection",
                    "topic": "2026_summer_education_topic_research",
                },
                {
                    "id": 3,
                    "name": "Creator Realtime Discovery collection",
                    "topic": "creator_realtime_discovery",
                },
                {
                    "id": 4,
                    "name": "2026 Summer 教育项目12 initial collection",
                    "topic": "2026_summer_教育项目12",
                },
            ]

    jobs = await _project_jobs_for_sample_analysis(
        Repository(),  # type: ignore[arg-type]
        {"id": 9, "name": "2026 Summer 教育项目"},
    )

    assert [job["id"] for job in jobs] == [1, 2]


@pytest.mark.asyncio
async def test_global_sample_analysis_uses_all_crawler_data(
    lead_attribution_client: tuple[AsyncClient, str, int],
) -> None:
    client, _project_id, post_id = lead_attribution_client
    await _seed_project_comment_for_post(post_id)

    response = await client.get("/api/reports/lead-attribution/summary?scope=global")
    assert response.status_code == 200
    payload = response.json()

    assert payload["project_id"] == "__global__"
    assert payload["project_name"] == "全部数据"
    assert payload["scope"] == "global"
    assert payload["summary"]["lead_count"] == 0
    assert payload["sample_analysis"]["summary"]["job_count"] == 1
    assert payload["sample_analysis"]["summary"]["post_count"] == 1
    assert payload["sample_analysis"]["summary"]["comment_count"] == 1
    assert payload["sample_analysis"]["summary"]["intent_comment_count"] == 1
    assert payload["sample_analysis"]["platform_rows"][0]["dimension_key"] == "xhs"
    assert payload["sample_analysis"]["top_contents"][0]["title"] == "Kitten Food Buying Guide"
    assert {row["keyword"] for row in payload["sample_analysis"]["top_keywords"]} >= {
        "cat food",
        "kitten food",
    }


@pytest.mark.asyncio
async def test_lead_attribution_import_summary_and_detail(
    lead_attribution_client: tuple[AsyncClient, str, int],
) -> None:
    client, project_id, post_id = lead_attribution_client

    config_response = await client.put(
        f"/api/research/growth-projects/{project_id}/attribution-config",
        json={
            "default_model": "last_touch",
            "window_days": 7,
            "enabled_dimensions": ["platform", "keyword", "content", "creator"],
            "dedupe_by": "external_lead_id",
        },
    )
    assert config_response.status_code == 200
    assert config_response.json()["config"]["default_model"] == "last_touch"

    lead_response = await client.post(
        f"/api/research/growth-projects/{project_id}/leads/import",
        json={
            "source_system": "manual",
            "items": [
                {
                    "external_lead_id": "L-1",
                    "lead_status": "new",
                    "owner": "alice",
                    "source_platform": "xhs",
                    "source_keyword": "kitten food",
                }
            ],
        },
    )
    assert lead_response.status_code == 200
    assert lead_response.json()["created"] == 1
    lead_id = int(lead_response.json()["leads"][0]["id"])

    touchpoint_response = await client.post(
        f"/api/research/growth-projects/{project_id}/touchpoints/import",
        json={
            "items": [
                {
                    "external_lead_id": "L-1",
                    "touch_type": "content_click",
                    "platform": "xhs",
                    "source_keyword": "cat food",
                    "creator_id": "creator-alpha",
                    "post_id": post_id,
                    "touch_time": "2026-05-23T10:00:00+00:00",
                },
                {
                    "external_lead_id": "L-1",
                    "touch_type": "content_click",
                    "platform": "dy",
                    "source_keyword": "kitten food",
                    "creator_id": "creator-beta",
                    "post_id": post_id,
                    "touch_time": "2026-05-24T08:00:00+00:00",
                },
            ]
        },
    )
    assert touchpoint_response.status_code == 200
    assert touchpoint_response.json()["created"] == 2

    conversion_response = await client.post(
        f"/api/research/growth-projects/{project_id}/conversion-events/import",
        json={
            "source_system": "csv_import",
            "items": [
                {
                    "external_lead_id": "L-1",
                    "event_type": "wechat_added",
                    "event_time": "2026-05-24T08:30:00+00:00",
                },
                {
                    "external_lead_id": "L-1",
                    "event_type": "first_reply",
                    "event_time": "2026-05-24T09:00:00+00:00",
                },
                {
                    "external_lead_id": "L-1",
                    "event_type": "qualified",
                    "event_time": "2026-05-24T09:30:00+00:00",
                },
                {
                    "external_lead_id": "L-1",
                    "event_type": "deal_closed",
                    "event_value": 399.0,
                    "event_time": "2026-05-24T10:00:00+00:00",
                },
            ],
        },
    )
    assert conversion_response.status_code == 200
    assert conversion_response.json()["created"] == 4

    spend_response = await client.post(
        f"/api/research/growth-projects/{project_id}/attribution-spend/import",
        json={
            "source_system": "manual",
            "items": [
                {
                    "spend_date": "2026-05-24",
                    "dimension": "platform",
                    "dimension_key": "dy",
                    "amount": 100.0,
                },
                {
                    "spend_date": "2026-05-24",
                    "dimension": "keyword",
                    "dimension_key": "kitten food",
                    "amount": 50.0,
                },
                {
                    "spend_date": "2026-05-24",
                    "dimension": "content",
                    "dimension_key": f"post:{post_id}",
                    "amount": 25.0,
                },
                {
                    "spend_date": "2026-05-24",
                    "dimension": "creator",
                    "dimension_key": "creator-beta",
                    "amount": 40.0,
                },
            ],
        },
    )
    assert spend_response.status_code == 200
    assert spend_response.json()["created"] == 4

    summary_response = await client.get(
        f"/api/reports/lead-attribution/summary?project_id={project_id}&model=last_touch"
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["summary"]["lead_count"] == 1
    assert summary["summary"]["qualified_lead_count"] == 1
    assert summary["summary"]["wechat_added_count"] == 1
    assert summary["summary"]["first_reply_count"] == 1
    assert summary["summary"]["deal_count"] == 1
    assert summary["summary"]["deal_amount"] == 399.0
    assert summary["summary"]["cost"] == 215.0
    assert summary["summary"]["cpl"] == 215.0
    assert summary["summary"]["cost_per_qualified_lead"] == 215.0
    assert summary["summary"]["roi"] == 1.8558
    assert summary["summary"]["lead_to_wechat_rate"] == 1.0
    assert summary["summary"]["wechat_to_reply_rate"] == 1.0
    assert summary["summary"]["reply_to_deal_rate"] == 1.0
    assert summary["top_platforms"][0]["dimension_key"] == "dy"
    assert summary["top_platforms"][0]["qualified_lead_count"] == 1
    assert summary["top_platforms"][0]["cost"] == 100.0
    assert summary["top_platforms"][0]["roi"] == 3.99

    global_summary_response = await client.get(
        "/api/reports/lead-attribution/summary?scope=global&model=last_touch"
    )
    assert global_summary_response.status_code == 200
    global_summary = global_summary_response.json()
    assert global_summary["project_id"] == "__global__"
    assert global_summary["scope"] == "global"
    assert global_summary["summary"]["lead_count"] == 1
    assert global_summary["summary"]["deal_amount"] == 399.0
    assert global_summary["top_platforms"][0]["dimension_key"] == "dy"

    global_leads_response = await client.get("/api/research/leads?scope=global")
    assert global_leads_response.status_code == 200
    global_leads = global_leads_response.json()["leads"]
    assert len(global_leads) == 1
    assert global_leads[0]["external_lead_id"] == "L-1"

    creator_response = await client.get(
        f"/api/reports/lead-attribution/creator?project_id={project_id}&model=last_touch"
    )
    assert creator_response.status_code == 200
    creator_rows = creator_response.json()["rows"]
    assert creator_rows[0]["dimension_key"] == "creator-beta"
    assert creator_rows[0]["cost"] == 40.0
    assert creator_rows[0]["roi"] == 9.975

    content_response = await client.get(
        f"/api/reports/lead-attribution/content?project_id={project_id}&model=last_touch"
    )
    assert content_response.status_code == 200
    content_rows = content_response.json()["rows"]
    assert content_rows[0]["dimension_key"] == f"post:{post_id}"
    assert content_rows[0]["title"] == "Kitten Food Buying Guide"

    detail_response = await client.get(
        f"/api/research/leads/{lead_id}?model=first_touch"
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["lead"]["external_lead_id"] == "L-1"
    assert len(detail["touchpoints"]) == 2
    assert len(detail["conversion_events"]) == 4
    assert len(detail["attribution"]) >= 1
    assert detail["attribution_explanation"]["model"] == "first_touch"
    assert (
        detail["attribution_explanation"]["top_dimensions"]["platform"]["dimension_key"]
        == "xhs"
    )
    assert (
        detail["attribution_explanation"]["top_dimensions"]["creator"]["dimension_key"]
        == "creator-alpha"
    )
    assert detail["attribution_explanation"]["touchpoint_summary"]["touch_count"] == 2
    assert "first_touch" in detail["attribution_explanation"]["narrative"]
    assert "xhs" in detail["attribution_explanation"]["narrative"]

    timeline_response = await client.get(
        f"/api/research/leads/{lead_id}/timeline?model=last_touch"
    )
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()["timeline"]
    assert [item["kind"] for item in timeline] == [
        "touchpoint",
        "touchpoint",
        "conversion_event",
        "conversion_event",
        "conversion_event",
        "conversion_event",
    ]
    assert timeline[0]["role"] == "assist"
    assert timeline[1]["role"] == "winning"


@pytest.mark.asyncio
async def test_touchpoint_and_conversion_import_skip_unknown_lead(
    lead_attribution_client: tuple[AsyncClient, str, int],
) -> None:
    client, project_id, post_id = lead_attribution_client

    touchpoint_response = await client.post(
        f"/api/research/growth-projects/{project_id}/touchpoints/import",
        json={
            "items": [
                {
                    "external_lead_id": "missing",
                    "touch_type": "content_click",
                    "platform": "xhs",
                    "source_keyword": "cat food",
                    "post_id": post_id,
                    "touch_time": "2026-05-23T10:00:00+00:00",
                }
            ]
        },
    )
    assert touchpoint_response.status_code == 200
    assert touchpoint_response.json()["created"] == 0
    assert touchpoint_response.json()["skipped"][0]["reason"] == "lead_not_found"

    conversion_response = await client.post(
        f"/api/research/growth-projects/{project_id}/conversion-events/import",
        json={
            "source_system": "manual",
            "items": [
                {
                    "external_lead_id": "missing",
                    "event_type": "deal_closed",
                    "event_value": 99.0,
                    "event_time": "2026-05-24T10:00:00+00:00",
                }
            ],
        },
    )
    assert conversion_response.status_code == 200
    assert conversion_response.json()["created"] == 0
    assert conversion_response.json()["skipped"][0]["reason"] == "lead_not_found"


@pytest.mark.asyncio
async def test_duplicate_touchpoint_and_conversion_import_are_idempotent(
    lead_attribution_client: tuple[AsyncClient, str, int],
) -> None:
    client, project_id, post_id = lead_attribution_client

    config_response = await client.put(
        f"/api/research/growth-projects/{project_id}/attribution-config",
        json={
            "default_model": "last_touch",
            "window_days": 7,
            "enabled_dimensions": ["platform", "keyword", "content", "creator"],
            "dedupe_by": "external_lead_id",
        },
    )
    assert config_response.status_code == 200

    lead_response = await client.post(
        f"/api/research/growth-projects/{project_id}/leads/import",
        json={
            "source_system": "manual",
            "items": [
                {
                    "external_lead_id": "L-dup",
                    "lead_status": "new",
                    "source_platform": "xhs",
                    "source_keyword": "cat food",
                }
            ],
        },
    )
    assert lead_response.status_code == 200

    touchpoint_payload = {
        "items": [
            {
                "external_lead_id": "L-dup",
                "touch_type": "content_click",
                "platform": "xhs",
                "source_keyword": "cat food",
                "post_id": post_id,
                "touch_time": "2026-05-23T10:00:00+00:00",
            }
        ]
    }
    first_touchpoint = await client.post(
        f"/api/research/growth-projects/{project_id}/touchpoints/import",
        json=touchpoint_payload,
    )
    assert first_touchpoint.status_code == 200
    assert first_touchpoint.json()["created"] == 1

    second_touchpoint = await client.post(
        f"/api/research/growth-projects/{project_id}/touchpoints/import",
        json=touchpoint_payload,
    )
    assert second_touchpoint.status_code == 200
    assert second_touchpoint.json()["created"] == 0
    assert second_touchpoint.json()["skipped"][0]["reason"] == "duplicate_touchpoint"

    conversion_payload = {
        "source_system": "csv_import",
        "items": [
            {
                "external_lead_id": "L-dup",
                "event_type": "deal_closed",
                "event_value": 199.0,
                "event_time": "2026-05-24T10:00:00+00:00",
            }
        ],
    }
    first_conversion = await client.post(
        f"/api/research/growth-projects/{project_id}/conversion-events/import",
        json=conversion_payload,
    )
    assert first_conversion.status_code == 200
    assert first_conversion.json()["created"] == 1

    second_conversion = await client.post(
        f"/api/research/growth-projects/{project_id}/conversion-events/import",
        json=conversion_payload,
    )
    assert second_conversion.status_code == 200
    assert second_conversion.json()["created"] == 0
    assert second_conversion.json()["skipped"][0]["reason"] == "duplicate_conversion_event"


@pytest.mark.asyncio
async def test_refresh_persists_single_snapshot_and_summary_reuses_it(
    lead_attribution_client: tuple[AsyncClient, str, int],
) -> None:
    client, project_id, post_id = lead_attribution_client

    await client.put(
        f"/api/research/growth-projects/{project_id}/attribution-config",
        json={
            "default_model": "last_touch",
            "window_days": 7,
            "enabled_dimensions": ["platform", "keyword", "content", "creator"],
            "dedupe_by": "external_lead_id",
        },
    )
    await client.post(
        f"/api/research/growth-projects/{project_id}/leads/import",
        json={
            "source_system": "manual",
            "items": [
                {
                    "external_lead_id": "L-snapshot",
                    "lead_status": "qualified",
                    "source_platform": "xhs",
                    "source_keyword": "cat food",
                }
            ],
        },
    )
    await client.post(
        f"/api/research/growth-projects/{project_id}/touchpoints/import",
        json={
            "items": [
                {
                    "external_lead_id": "L-snapshot",
                    "touch_type": "content_click",
                    "platform": "xhs",
                    "source_keyword": "cat food",
                    "creator_id": "creator-one",
                    "post_id": post_id,
                    "touch_time": "2026-05-23T10:00:00+00:00",
                }
            ]
        },
    )
    await client.post(
        f"/api/research/growth-projects/{project_id}/conversion-events/import",
        json={
            "source_system": "csv_import",
            "items": [
                {
                    "external_lead_id": "L-snapshot",
                    "event_type": "deal_closed",
                    "event_value": 299.0,
                    "event_time": "2026-05-24T10:00:00+00:00",
                }
            ],
        },
    )
    await client.post(
        f"/api/research/growth-projects/{project_id}/attribution-spend/import",
        json={
            "source_system": "manual",
            "items": [
                {
                    "spend_date": "2026-05-24",
                    "dimension": "platform",
                    "dimension_key": "xhs",
                    "amount": 150.0,
                }
            ],
        },
    )

    first_refresh = await client.post(
        f"/api/reports/lead-attribution/summary/refresh?project_id={project_id}&model=last_touch"
    )
    assert first_refresh.status_code == 200
    second_refresh = await client.post(
        f"/api/reports/lead-attribution/summary/refresh?project_id={project_id}&model=last_touch"
    )
    assert second_refresh.status_code == 200

    async with get_session() as session:
        snapshot_count = await session.scalar(
            select(func.count(ResearchLeadAttributionDailySnapshot.id))
        )
        assert snapshot_count == 1
        await session.execute(delete(ResearchLeadAttributionResult))

    summary_response = await client.get(
        f"/api/reports/lead-attribution/summary?project_id={project_id}&model=last_touch"
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["summary"]["deal_amount"] == 299.0
    assert summary["summary"]["cost"] == 150.0
    assert summary["summary"]["roi"] == 1.9933
    assert summary["top_platforms"][0]["dimension_key"] == "xhs"


@pytest.mark.asyncio
async def test_range_refresh_reuses_matching_snapshot_and_breakdown(
    lead_attribution_client: tuple[AsyncClient, str, int],
) -> None:
    client, project_id, post_id = lead_attribution_client

    await client.put(
        f"/api/research/growth-projects/{project_id}/attribution-config",
        json={
            "default_model": "last_touch",
            "window_days": 7,
            "enabled_dimensions": ["platform", "keyword", "content", "creator"],
            "dedupe_by": "external_lead_id",
        },
    )
    await client.post(
        f"/api/research/growth-projects/{project_id}/leads/import",
        json={
            "source_system": "manual",
            "items": [
                {
                    "external_lead_id": "L-range",
                    "lead_status": "qualified",
                    "source_platform": "xhs",
                    "source_keyword": "range_keyword",
                }
            ],
        },
    )
    await client.post(
        f"/api/research/growth-projects/{project_id}/touchpoints/import",
        json={
            "items": [
                {
                    "external_lead_id": "L-range",
                    "touch_type": "content_click",
                    "platform": "xhs",
                    "source_keyword": "range_keyword",
                    "creator_id": "creator-range",
                    "post_id": post_id,
                    "touch_time": "2026-05-23T10:00:00+00:00",
                },
                {
                    "external_lead_id": "L-range",
                    "touch_type": "content_click",
                    "platform": "xhs",
                    "source_keyword": "range_keyword",
                    "creator_id": "creator-after",
                    "post_id": post_id,
                    "touch_time": "2026-05-25T10:00:00+00:00",
                },
            ]
        },
    )
    await client.post(
        f"/api/research/growth-projects/{project_id}/conversion-events/import",
        json={
            "source_system": "csv_import",
            "items": [
                {
                    "external_lead_id": "L-range",
                    "event_type": "deal_closed",
                    "event_value": 499.0,
                    "event_time": "2026-05-24T10:00:00+00:00",
                }
            ],
        },
    )
    await client.post(
        f"/api/research/growth-projects/{project_id}/attribution-spend/import",
        json={
            "source_system": "manual",
            "items": [
                {
                    "spend_date": "2026-05-24",
                    "dimension": "platform",
                    "dimension_key": "xhs",
                    "amount": 200.0,
                },
                {
                    "spend_date": "2026-05-24",
                    "dimension": "creator",
                    "dimension_key": "creator-range",
                    "amount": 30.0,
                },
            ],
        },
    )

    refresh_response = await client.post(
        f"/api/reports/lead-attribution/summary/refresh?project_id={project_id}&model=last_touch&date_from=2026-05-24T00:00:00+00:00&date_to=2026-05-24T23:59:59+00:00"
    )
    assert refresh_response.status_code == 200

    async with get_session() as session:
        snapshot_count = await session.scalar(
            select(func.count(ResearchLeadAttributionDailySnapshot.id))
        )
        assert snapshot_count == 1
        await session.execute(delete(ResearchLeadAttributionResult))

    summary_response = await client.get(
        f"/api/reports/lead-attribution/summary?project_id={project_id}&model=last_touch&date_from=2026-05-24T00:00:00+00:00&date_to=2026-05-24T23:59:59+00:00"
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["summary"]["date_from"] == "2026-05-24T00:00:00+00:00"
    assert summary["summary"]["date_to"] == "2026-05-24T23:59:59+00:00"
    assert summary["summary"]["deal_amount"] == 499.0
    assert summary["summary"]["cost"] == 230.0
    assert summary["summary"]["roi"] == 2.1696
    assert summary["top_platforms"][0]["dimension_key"] == "xhs"
    assert summary["top_platforms"][0]["cost"] == 200.0

    creator_response = await client.get(
        f"/api/reports/lead-attribution/creator?project_id={project_id}&model=last_touch&date_from=2026-05-24T00:00:00+00:00&date_to=2026-05-24T23:59:59+00:00"
    )
    assert creator_response.status_code == 200
    assert creator_response.json()["rows"][0]["dimension_key"] == "creator-range"
    assert creator_response.json()["rows"][0]["roi"] == 16.6333

    lead_list_response = await client.get(
        f"/api/research/growth-projects/{project_id}/leads"
    )
    lead_id = int(lead_list_response.json()["leads"][0]["id"])
    timeline_response = await client.get(
        f"/api/research/leads/{lead_id}/timeline?model=last_touch"
    )
    assert timeline_response.status_code == 200
    touchpoint_entries = [
        item for item in timeline_response.json()["timeline"] if item["kind"] == "touchpoint"
    ]
    assert touchpoint_entries[0]["role"] == "winning"
    assert touchpoint_entries[1]["role"] == "after_conversion"

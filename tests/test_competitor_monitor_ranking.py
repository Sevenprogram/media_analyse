from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables, get_session
from database.models import XhsNote
from saas_test_utils import authenticate_test_client
from research.competitors import build_competitor_composition
from research.competitor_public_flow import build_competitor_public_flow_snapshot
from research.models import ResearchJob, ResearchPost
from research.repository import ResearchRepository


@pytest_asyncio.fixture
async def competitor_client(tmp_path, monkeypatch):
    db_path = tmp_path / "competitor-ranking-test.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await authenticate_test_client(
            client,
            email="competitor-ranking@example.com",
            organization_name="Competitor Ranking Workspace",
        )
        client.headers.update({"X-Org-Id": str(auth["organization"]["id"])})
        yield client

    await close_engines()


async def _seed_competitor_snapshot(*, org_id: int) -> int:
    repository = ResearchRepository(org_id=org_id)
    competitor = await repository.upsert_competitor_account(
        {
            "platform": "xhs",
            "creator_id": "creator-001",
            "display_name": "Competitor One",
            "enabled": True,
        }
    )

    now = datetime.now(timezone.utc)
    async with get_session() as session:
        job = ResearchJob(
            org_id=org_id,
            name="competitor ranking seed",
            topic="competitor_ranking_seed",
            platforms=["xhs"],
            collection_mode="creator",
            keywords=[],
            target_ids=[],
            creator_ids=["creator-001"],
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            status="completed",
            comment_policy={"enable_comments": False, "enable_sub_comments": False},
            raw_record_mode="minimal",
            anonymize_authors=True,
        )
        session.add(job)
        await session.flush()
        session.add_all(
            [
                ResearchPost(
                    org_id=org_id,
                    job_id=job.id,
                    platform="xhs",
                    platform_post_id="note-valid",
                    author_hash="xhs_fake_hash",
                    title="Valid Note",
                    content="valid content",
                    url="https://www.xiaohongshu.com/explore/note-valid?xsec_token=good-token&xsec_source=pc_search",
                    publish_time=now,
                    engagement_json={"liked_count": 100, "comment_count": 10, "author_id": "creator-001"},
                ),
                ResearchPost(
                    org_id=org_id,
                    job_id=job.id,
                    platform="xhs",
                    platform_post_id="note-missing",
                    author_hash="xhs_fake_hash",
                    title="Missing Token Note",
                    content="missing token",
                    url="https://www.xiaohongshu.com/explore/note-missing?xsec_token=&xsec_source=pc_search",
                    publish_time=now - timedelta(hours=1),
                    engagement_json={"liked_count": 80, "comment_count": 8, "author_id": "creator-001"},
                ),
                ResearchPost(
                    org_id=org_id,
                    job_id=job.id,
                    platform="xhs",
                    platform_post_id="note-other",
                    author_hash="xhs_fake_hash",
                    title="Wrong Author Note",
                    content="wrong author",
                    url="https://www.xiaohongshu.com/explore/note-other?xsec_token=other-token&xsec_source=pc_search",
                    publish_time=now - timedelta(hours=2),
                    engagement_json={"liked_count": 90, "comment_count": 9, "author_id": "creator-001"},
                ),
            ]
        )
        session.add_all(
            [
                XhsNote(
                    user_id="creator-001",
                    nickname="Competitor One",
                    note_id="note-valid",
                    title="Valid Note",
                    time=int(now.timestamp()),
                    liked_count="100",
                    collected_count="5",
                    comment_count="10",
                    share_count="3",
                    note_url="https://www.xiaohongshu.com/explore/note-valid?xsec_token=good-token&xsec_source=pc_search",
                    xsec_token="good-token",
                ),
                XhsNote(
                    user_id="creator-001",
                    nickname="Competitor One",
                    note_id="note-missing",
                    title="Missing Token Note",
                    time=int((now - timedelta(hours=1)).timestamp()),
                    liked_count="80",
                    collected_count="4",
                    comment_count="8",
                    share_count="2",
                    note_url="https://www.xiaohongshu.com/explore/note-missing?xsec_token=&xsec_source=pc_search",
                    xsec_token="",
                ),
                XhsNote(
                    user_id="other-creator",
                    nickname="Other Account",
                    note_id="note-other",
                    title="Wrong Author Note",
                    time=int((now - timedelta(hours=2)).timestamp()),
                    liked_count="90",
                    collected_count="3",
                    comment_count="9",
                    share_count="1",
                    note_url="https://www.xiaohongshu.com/explore/note-other?xsec_token=other-token&xsec_source=pc_search",
                    xsec_token="other-token",
                ),
            ]
        )

    await repository.upsert_competitor_composition_snapshot(
        {
            "competitor_id": competitor["id"],
            "snapshot_date": date.today(),
            "platform": "xhs",
            "total_flow_count": 270,
            "keyword_distribution": {},
            "tag_distribution": {},
            "content_type_distribution": {},
            "publish_time_distribution": {},
            "hot_post_rate": 0.0,
            "evidence": {
                "public_flow": {
                    "latest_limit": 50,
                    "deduped_post_count": 3,
                    "cumulative": {"total_interaction": 270},
                    "delta": {"total_interaction": 270},
                    "posts_by_id": {
                        "note-valid": {"total_interaction": 100},
                        "note-missing": {"total_interaction": 80},
                        "note-other": {"total_interaction": 90},
                    },
                    "top_delta_posts": [
                        {
                            "platform_post_id": "note-valid",
                            "title": "Valid Note",
                            "url": "https://www.xiaohongshu.com/explore/note-valid?xsec_token=good-token&xsec_source=pc_search",
                            "author_verified": True,
                            "has_valid_url": True,
                            "link_status": "ok",
                            "delta_total": 100,
                            "delta": {"total_interaction": 100},
                        },
                        {
                            "platform_post_id": "note-missing",
                            "title": "Missing Token Note",
                            "url": "https://www.xiaohongshu.com/explore/note-missing?xsec_token=&xsec_source=pc_search",
                            "author_verified": True,
                            "has_valid_url": False,
                            "link_status": "missing_xsec_token",
                            "delta_total": 80,
                            "delta": {"total_interaction": 80},
                        },
                    ],
                }
            },
        }
    )
    return int(competitor["id"])


@pytest.mark.asyncio
async def test_competitor_ranking_keeps_verified_posts_with_missing_token(
    competitor_client: AsyncClient,
) -> None:
    org_id = int(competitor_client.headers["X-Org-Id"])
    competitor_id = await _seed_competitor_snapshot(org_id=org_id)

    response = await competitor_client.get(
        f"/api/competitors/{competitor_id}/contribution-ranking?date={date.today().isoformat()}&scope=all&limit=20"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [row["post_id"] for row in payload["rows"]] == ["note-valid", "note-missing"]

    valid_row, missing_row = payload["rows"]
    assert valid_row["platform_url"].endswith("xsec_token=good-token&xsec_source=pc_search")
    assert valid_row["source_url"].endswith("xsec_token=good-token&xsec_source=pc_search")
    assert valid_row["has_valid_url"] is True
    assert valid_row["link_available"] is True
    assert valid_row["interaction_total"] == 100
    assert missing_row["platform_url"] == ""
    assert missing_row["source_url"].endswith("xsec_token=&xsec_source=pc_search")
    assert missing_row["has_valid_url"] is False
    assert missing_row["link_available"] is False
    assert missing_row["interaction_total"] == 80
    assert "xsec_token" in missing_row["link_status"]


@pytest.mark.asyncio
async def test_competitor_ranking_dedupes_existing_snapshot_duplicate_rows(
    competitor_client: AsyncClient,
) -> None:
    org_id = int(competitor_client.headers["X-Org-Id"])
    competitor_id = await _seed_competitor_snapshot(org_id=org_id)
    repository = ResearchRepository(org_id=org_id)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    async with get_session() as session:
        job = ResearchJob(
            org_id=org_id,
            name="competitor duplicate ranking seed",
            topic="competitor_duplicate_ranking_seed",
            platforms=["xhs"],
            collection_mode="creator",
            keywords=[],
            target_ids=[],
            creator_ids=["creator-001"],
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            status="completed",
            comment_policy={"enable_comments": False, "enable_sub_comments": False},
            raw_record_mode="minimal",
            anonymize_authors=True,
        )
        session.add(job)
        await session.flush()
        session.add_all(
            [
                ResearchPost(
                    org_id=org_id,
                    job_id=job.id,
                    platform="xhs",
                    platform_post_id="note-dupe-a",
                    author_hash="xhs_fake_hash",
                    title="8岁小孩姐“0秒”复原魔方！",
                    content="duplicate content",
                    url="",
                    publish_time=now,
                    engagement_json={"liked_count": 10, "comment_count": 0, "author_id": "creator-001"},
                ),
                ResearchPost(
                    org_id=org_id,
                    job_id=job.id,
                    platform="xhs",
                    platform_post_id="note-dupe-b",
                    author_hash="xhs_fake_hash",
                    title="8岁小孩姐“0秒”复原魔方！",
                    content="duplicate content",
                    url="",
                    publish_time=now,
                    engagement_json={"liked_count": 10, "comment_count": 0, "author_id": "creator-001"},
                ),
                XhsNote(
                    user_id="creator-001",
                    nickname="Competitor One",
                    note_id="note-dupe-a",
                    title="8岁小孩姐“0秒”复原魔方！",
                    time=int(now.timestamp()),
                    liked_count="10",
                    collected_count="0",
                    comment_count="0",
                    share_count="0",
                    note_url="",
                    xsec_token="",
                ),
                XhsNote(
                    user_id="creator-001",
                    nickname="Competitor One",
                    note_id="note-dupe-b",
                    title="8岁小孩姐“0秒”复原魔方！",
                    time=int(now.timestamp()),
                    liked_count="10",
                    collected_count="0",
                    comment_count="0",
                    share_count="0",
                    note_url="",
                    xsec_token="",
                ),
            ]
        )

    await repository.upsert_competitor_composition_snapshot(
        {
            "competitor_id": competitor_id,
            "snapshot_date": date.today(),
            "platform": "xhs",
            "total_flow_count": 20,
            "keyword_distribution": {},
            "tag_distribution": {},
            "content_type_distribution": {},
            "publish_time_distribution": {},
            "hot_post_rate": 0.0,
            "evidence": {
                "public_flow": {
                    "latest_limit": 50,
                    "deduped_post_count": 2,
                    "cumulative": {"total_interaction": 20},
                    "delta": {"total_interaction": 0},
                    "posts_by_id": {
                        "note-dupe-a": {"total_interaction": 10},
                        "note-dupe-b": {"total_interaction": 10},
                    },
                    "delta_by_post": {
                        "note-dupe-a": {"total_interaction": 0},
                        "note-dupe-b": {"total_interaction": 0},
                    },
                    "top_delta_posts": [
                        {"platform_post_id": "note-dupe-a", "title": "8岁小孩姐“0秒”复原魔方！", "delta_total": 0},
                        {"platform_post_id": "note-dupe-b", "title": "8岁小孩姐“0秒”复原魔方！", "delta_total": 0},
                    ],
                }
            },
        }
    )

    response = await competitor_client.get(
        f"/api/competitors/{competitor_id}/contribution-ranking?date={date.today().isoformat()}&scope=all&limit=20"
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    duplicate_rows = [row for row in rows if row["title"] == "8岁小孩姐“0秒”复原魔方！"]
    assert len(duplicate_rows) == 1
    assert duplicate_rows[0]["source_url"].endswith(("/note-dupe-a", "/note-dupe-b"))
    assert duplicate_rows[0]["interaction_total"] == 10


@pytest.mark.asyncio
async def test_refresh_diagnostics_explains_filtered_posts(competitor_client: AsyncClient) -> None:
    org_id = int(competitor_client.headers["X-Org-Id"])
    competitor_id = await _seed_competitor_snapshot(org_id=org_id)
    repository = ResearchRepository(org_id=org_id)
    started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    completed_at = datetime.now(timezone.utc) - timedelta(minutes=4)
    await repository.create_collection_run(
        {
            "run_type": "competitor_monitor",
            "target_type": "competitor",
            "target_id": competitor_id,
            "mode": "collect_and_refresh",
            "trigger_source": "manual",
            "status": "succeeded",
            "phase": "completed",
            "started_at": started_at,
            "completed_at": completed_at,
            "request_payload": {"days_back": 7, "latest_limit": 50},
        }
    )

    response = await competitor_client.get(
        f"/api/competitors/{competitor_id}/refresh-diagnostics?date={date.today().isoformat()}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["timezone"] == "Asia/Shanghai"
    assert payload["last_refresh_status"] == "succeeded"
    assert payload["last_refresh_at"].endswith("Z")
    assert payload["stats"] == {
        "raw_matched_posts": 2,
        "author_verified_posts": 2,
        "displayable_posts": 2,
        "eligible_posts": 1,
        "degraded_link_posts": 1,
        "invalid_url_posts": 1,
        "missing_token_posts": 1,
        "author_mismatch_posts": 0,
    }
    messages = [entry["message"] for entry in payload["entries"]]
    assert any("采集窗口：近 7 天，上限 50 条" in message for message in messages)
    assert any("缺少 xsec_token" in message for message in messages)
    assert any("可点击链接 1 条" in message for message in messages)
    assert any("当前贡献榜展示 2 条" in message for message in messages)


@pytest.mark.asyncio
async def test_sampled_posts_endpoint_returns_snapshot_rows(competitor_client: AsyncClient) -> None:
    org_id = int(competitor_client.headers["X-Org-Id"])
    competitor_id = await _seed_competitor_snapshot(org_id=org_id)

    response = await competitor_client.get(
        f"/api/competitors/{competitor_id}/sampled-posts?date={date.today().isoformat()}&limit=20"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["timezone"] == "Asia/Shanghai"
    assert payload["total"] == 3
    assert [row["post_id"] for row in payload["rows"]] == [
        "note-valid",
        "note-missing",
        "note-other",
    ]

    valid_row, missing_row, other_row = payload["rows"]
    assert valid_row["author_verified"] is True
    assert valid_row["has_valid_url"] is True
    assert valid_row["interaction_total"] == 100
    assert valid_row["like_count"] == 100

    assert missing_row["author_verified"] is True
    assert missing_row["has_valid_url"] is False
    assert missing_row["source_url"].endswith("/note-missing")
    assert "xsec_token" in missing_row["link_status"]

    assert other_row["author_verified"] is False
    assert other_row["has_valid_url"] is True
    assert "作者" in other_row["link_status"]


@pytest.mark.asyncio
async def test_create_competitor_can_auto_fill_display_name_without_profile_url(
    competitor_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import competitors as competitors_router

    async def fake_enrich_creator_metrics_from_tikhub(repository, creators, *, client=None):
        assert creators[0]["platform"] == "xhs"
        assert creators[0]["creator_id"] == "creator-lookup"
        return {
            "enriched_count": 1,
            "failed_count": 0,
            "enriched": [{"display_name": "真实昵称"}],
            "failed": [],
        }

    monkeypatch.setattr(
        competitors_router,
        "enrich_creator_metrics_from_tikhub",
        fake_enrich_creator_metrics_from_tikhub,
    )
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)
    monkeypatch.setattr(config, "TIKHUB_API_KEY", "test-key", raising=False)

    response = await competitor_client.post(
        "/api/competitors",
        json={
            "platform": "xhs",
            "creator_id": "creator-lookup",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "真实昵称"


@pytest.mark.asyncio
async def test_partner_creator_monitor_is_filtered_from_default_competitor_list(
    competitor_client: AsyncClient,
) -> None:
    competitor_response = await competitor_client.post(
        "/api/competitors",
        json={
            "platform": "xhs",
            "creator_id": "competitor-monitor",
            "display_name": "友商账号",
            "enabled": True,
        },
    )
    assert competitor_response.status_code == 200
    assert competitor_response.json()["monitor_type"] == "competitor"

    url_response = await competitor_client.post(
        "/api/competitors/from-url",
        json={
            "platform": "xhs",
            "profile_url": "https://www.xiaohongshu.com/user/profile/creator-link-monitor",
            "monitor_type": "partner_creator",
            "display_name": "链接添加达人",
        },
    )
    assert url_response.status_code == 200
    assert url_response.json()["creator_id"] == "creator-link-monitor"
    assert url_response.json()["monitor_type"] == "partner_creator"

    candidate_response = await competitor_client.post(
        "/api/competitors/from-candidate",
        json={
            "platform": "dy",
            "creator_id": "123456789",
            "monitor_type": "partner_creator",
            "display_name": "发现页达人",
        },
    )
    assert candidate_response.status_code == 200
    assert candidate_response.json()["monitor_type"] == "partner_creator"

    default_list = await competitor_client.get("/api/competitors?enabled_only=true")
    assert default_list.status_code == 200
    default_ids = {item["creator_id"] for item in default_list.json()["competitors"]}
    assert default_ids == {"competitor-monitor"}

    partner_list = await competitor_client.get(
        "/api/competitors?enabled_only=true&monitor_type=partner_creator"
    )
    assert partner_list.status_code == 200
    partner_ids = {item["creator_id"] for item in partner_list.json()["competitors"]}
    assert partner_ids == {"creator-link-monitor", "123456789"}


def test_build_competitor_composition_uses_asia_shanghai_publish_hour() -> None:
    composition = build_competitor_composition(
        posts=[
            {
                "platform": "xhs",
                "platform_post_id": "utc-note",
                "title": "UTC note",
                "publish_time": datetime(2026, 5, 24, 1, 0, tzinfo=timezone.utc),
                "engagement_json": {"liked_count": 10},
            }
        ],
        entity_tags=[],
        keywords=[],
    )

    assert composition["publish_time_distribution"] == {"morning": 1}


@pytest.mark.asyncio
async def test_xhs_token_backfill_updates_missing_note_links(competitor_client: AsyncClient) -> None:
    from api.routers import competitors as competitors_router

    org_id = int(competitor_client.headers["X-Org-Id"])
    competitor_id = await _seed_competitor_snapshot(org_id=org_id)
    repository = ResearchRepository(org_id=org_id)
    competitor = await repository.get_competitor_account(competitor_id)
    assert competitor is not None

    now = datetime.now(timezone.utc)

    class FakeTikHubClient:
        async def request(self, method: str, path: str, params=None, json=None):
            assert method == "GET"
            assert path == competitors_router._XHS_IMAGE_DETAIL_PATH
            assert params == {"note_id": "note-missing"}
            return {
                "note": {
                    "id": "note-missing",
                    "type": "normal",
                    "title": "Missing Token Note",
                    "desc": "missing token",
                    "timestamp": int(now.timestamp()),
                    "user": {"userid": "creator-001", "nickname": "Competitor One"},
                    "interact_info": {
                        "liked_count": 80,
                        "collected_count": 4,
                        "comment_count": 8,
                        "share_count": 2,
                    },
                    "xsec_token": "filled-token",
                    "note_url": (
                        "https://www.xiaohongshu.com/explore/note-missing"
                        "?xsec_token=filled-token&xsec_source=pc_search"
                    ),
                }
            }

        async def close(self) -> None:
            return None

    result = await competitors_router._backfill_xhs_tokens_for_competitor(
        repository,
        competitor=competitor,
        days_back=7,
        client=FakeTikHubClient(),
    )

    assert result == {
        "platform": "xhs",
        "attempted": 1,
        "updated": 1,
        "failed": 0,
        "skipped": 0,
    }

    async with get_session() as session:
        note = (
            await session.execute(select(XhsNote).where(XhsNote.note_id == "note-missing"))
        ).scalar_one()
        post = (
            await session.execute(
                select(ResearchPost).where(
                    ResearchPost.platform == "xhs",
                    ResearchPost.platform_post_id == "note-missing",
                )
            )
        ).scalar_one()

    assert note.xsec_token == "filled-token"
    assert note.note_url.endswith("xsec_token=filled-token&xsec_source=pc_search")
    assert post.url.endswith("xsec_token=filled-token&xsec_source=pc_search")
    assert post.engagement_json["xsec_token"] == "filled-token"


@pytest.mark.asyncio
async def test_xhs_token_backfill_reports_detail_failures(competitor_client: AsyncClient) -> None:
    from api.routers import competitors as competitors_router

    org_id = int(competitor_client.headers["X-Org-Id"])
    competitor_id = await _seed_competitor_snapshot(org_id=org_id)
    repository = ResearchRepository(org_id=org_id)
    competitor = await repository.get_competitor_account(competitor_id)
    assert competitor is not None

    class FailingTikHubClient:
        async def request(self, method: str, path: str, params=None, json=None):
            raise RuntimeError("detail endpoint unavailable")

        async def close(self) -> None:
            return None

    result = await competitors_router._backfill_xhs_tokens_for_competitor(
        repository,
        competitor=competitor,
        days_back=7,
        client=FailingTikHubClient(),
    )

    assert result["attempted"] == 1
    assert result["updated"] == 0
    assert result["failed"] == 1
    assert result["errors"] == [
        {
            "note_id": "note-missing",
            "type": "RuntimeError",
            "message": "detail endpoint unavailable",
        }
    ]
    assert result["last_error"] == "detail endpoint unavailable"
    assert result["failed_by_type"] == {"RuntimeError": 1}


def test_public_flow_snapshot_keeps_verified_posts_with_missing_links() -> None:
    snapshot = build_competitor_public_flow_snapshot(
        competitor={"id": 1, "platform": "xhs"},
        posts=[
            {
                "platform": "xhs",
                "platform_post_id": "note-valid",
                "title": "Valid Note",
                "url": "https://www.xiaohongshu.com/explore/note-valid?xsec_token=good-token&xsec_source=pc_search",
                "author_verified": True,
                "has_valid_url": True,
                "engagement_json": {"liked_count": 100},
            },
            {
                "platform": "xhs",
                "platform_post_id": "note-missing",
                "title": "Missing Token Note",
                "url": "",
                "author_verified": True,
                "has_valid_url": False,
                "engagement_json": {"liked_count": 80},
            },
            {
                "platform": "xhs",
                "platform_post_id": "note-other",
                "title": "Wrong Author Note",
                "url": "https://www.xiaohongshu.com/explore/note-other?xsec_token=other-token&xsec_source=pc_search",
                "author_verified": False,
                "has_valid_url": True,
                "engagement_json": {"liked_count": 90},
            },
        ],
        keywords=[],
        entity_tags=[],
        snapshot_date=date.today(),
    )

    public_flow = snapshot["evidence"]["public_flow"]
    assert [row["platform_post_id"] for row in public_flow["top_delta_posts"]] == [
        "note-valid",
        "note-missing",
    ]
    missing_row = public_flow["top_delta_posts"][1]
    assert missing_row["has_valid_url"] is False
    assert missing_row["link_status"] == "missing_xsec_token"


def test_public_flow_snapshot_dedupes_duplicate_title_time_records() -> None:
    publish_time = datetime(2026, 5, 24, 12, 30, tzinfo=timezone.utc)

    snapshot = build_competitor_public_flow_snapshot(
        competitor={"id": 1, "platform": "xhs"},
        posts=[
            {
                "platform": "xhs",
                "platform_post_id": "note-dupe-a",
                "author_hash": "creator-001",
                "title": "8岁小孩姐“0秒”复原魔方！",
                "publish_time": publish_time,
                "author_verified": True,
                "has_valid_url": False,
                "engagement_json": {"liked_count": 10},
            },
            {
                "platform": "xhs",
                "platform_post_id": "note-dupe-b",
                "author_hash": "creator-001",
                "title": "8岁小孩姐“0秒”复原魔方！",
                "publish_time": publish_time,
                "author_verified": True,
                "has_valid_url": False,
                "engagement_json": {"liked_count": 10},
            },
            {
                "platform": "xhs",
                "platform_post_id": "note-unique",
                "author_hash": "creator-001",
                "title": "数学不开窍 这9部高分纪录片值得N刷",
                "publish_time": publish_time - timedelta(days=1),
                "author_verified": True,
                "has_valid_url": False,
                "engagement_json": {"liked_count": 8},
            },
        ],
        keywords=[],
        entity_tags=[],
        snapshot_date=date.today(),
    )

    public_flow = snapshot["evidence"]["public_flow"]
    titles = [row["title"] for row in public_flow["top_delta_posts"]]
    assert titles.count("8岁小孩姐“0秒”复原魔方！") == 1
    assert public_flow["deduped_post_count"] == 2

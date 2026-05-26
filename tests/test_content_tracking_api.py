from __future__ import annotations

import json
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
from saas_test_utils import authenticate_test_client
from research.models import ResearchJob, ResearchPost
from research.content_tracking import (
    apply_tracker_ai_sample_selection,
    build_tracker_ai_enhancement_prompt,
    build_tracker_analysis_snapshot,
    normalize_tracker_ai_enhancement_output,
)


@pytest_asyncio.fixture
async def content_tracking_client(tmp_path, monkeypatch):
    db_path = tmp_path / "content-tracking-test.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)

    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        auth = await authenticate_test_client(
            client,
            email="content-tracking@example.com",
            organization_name="Content Tracking Workspace",
        )
        await _seed_tracking_posts(org_id=int(auth["organization"]["id"]))
        yield client

    await close_engines()


async def _seed_tracking_posts(*, org_id: int) -> None:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        job = ResearchJob(
            org_id=org_id,
            name="content tracking test seed",
            topic="content_tracking_test",
            platforms=["xhs", "dy"],
            collection_mode="search",
            keywords=["cat food review", "new cat owner"],
            target_ids=[],
            creator_ids=[],
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            status="completed",
            comment_policy={"enable_comments": False, "enable_sub_comments": False},
            raw_record_mode="minimal",
            anonymize_authors=True,
        )
        session.add(job)
        await session.flush()

        posts = [
            ResearchPost(
                org_id=org_id,
                job_id=job.id,
                platform="xhs",
                platform_post_id="seed-post-1",
                author_hash="author-xhs-1",
                title="new cat owner cat food review avoid mistakes",
                content="cat food review for new cat owners, with a practical shortlist and pitfalls",
                url="https://example.com/xhs/1",
                publish_time=now - timedelta(days=1),
                engagement_json={
                    "nickname": "小猫测评官",
                    "like_count": 120,
                    "comment_count": 18,
                    "share_count": 5,
                },
            ),
            ResearchPost(
                org_id=org_id,
                job_id=job.id,
                platform="dy",
                platform_post_id="seed-post-2",
                author_hash="author-dy-2",
                title="cat food review do not waste money",
                content="new cat owners should not buy blindly, here is a real cat food review",
                url="https://example.com/dy/2",
                publish_time=now - timedelta(days=2),
                engagement_json={
                    "nickname": "新手养猫指南",
                    "like_count": 88,
                    "comment_count": 12,
                    "share_count": 3,
                },
            ),
            ResearchPost(
                org_id=org_id,
                job_id=job.id,
                platform="xhs",
                platform_post_id="seed-post-3",
                author_hash="author-xhs-3",
                title="cat food giveaway",
                content="giveaway campaign and sponsored placement",
                url="https://example.com/xhs/3",
                publish_time=now - timedelta(days=1),
                engagement_json={"nickname": "抽奖号", "like_count": 3, "comment_count": 1},
            ),
        ]
        session.add_all(posts)


async def _seed_duplicate_tracking_posts() -> None:
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        org_id = (
            await session.execute(select(ResearchPost.org_id).limit(1))
        ).scalar_one()
        first_job = ResearchJob(
            org_id=org_id,
            name="duplicate content tracking seed 1",
            topic="content_tracking_duplicate_test",
            platforms=["xhs"],
            collection_mode="search",
            keywords=["duplicate cat insight"],
            target_ids=[],
            creator_ids=[],
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            status="completed",
            comment_policy={"enable_comments": False, "enable_sub_comments": False},
            raw_record_mode="minimal",
            anonymize_authors=True,
        )
        second_job = ResearchJob(
            org_id=org_id,
            name="duplicate content tracking seed 2",
            topic="content_tracking_duplicate_test",
            platforms=["xhs"],
            collection_mode="search",
            keywords=["duplicate cat insight"],
            target_ids=[],
            creator_ids=[],
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
            status="completed",
            comment_policy={"enable_comments": False, "enable_sub_comments": False},
            raw_record_mode="minimal",
            anonymize_authors=True,
        )
        session.add_all([first_job, second_job])
        await session.flush()
        session.add_all(
            [
                ResearchPost(
                    org_id=org_id,
                    job_id=first_job.id,
                    platform="xhs",
                    platform_post_id="duplicate-seed-post",
                    author_hash="duplicate-author-a",
                    title="duplicate cat insight from first crawl",
                    content="duplicate cat insight appears in the first imported crawl",
                    url="https://example.com/xhs/duplicate-a",
                    publish_time=now - timedelta(days=1),
                    engagement_json={"like_count": 80, "comment_count": 4},
                ),
                ResearchPost(
                    org_id=org_id,
                    job_id=second_job.id,
                    platform="xhs",
                    platform_post_id="duplicate-seed-post",
                    author_hash="duplicate-author-b",
                    title="duplicate cat insight from second crawl",
                    content="duplicate cat insight appears again from another crawl",
                    url="https://example.com/xhs/duplicate-b",
                    publish_time=now - timedelta(hours=12),
                    engagement_json={"like_count": 150, "comment_count": 9},
                ),
            ]
        )


def test_representative_samples_require_market_validation_threshold() -> None:
    now = datetime.now(timezone.utc)
    tracker = {
        "id": 100,
        "name": "single mom education tracker",
        "description": "track K12 education discussions from single moms",
        "platforms": ["xhs", "dy"],
        "included_keywords": ["single mom", "k12 education"],
        "excluded_keywords": [],
        "tracking_mode": "mixed",
    }
    posts = [
        {
            "platform": "xhs",
            "platform_post_id": "zero-high-fit",
            "author_hash": "author-zero",
            "title": "single mom k12 education single mom k12 education",
            "content": "single mom k12 education planning and daily record",
            "url": "https://example.com/zero",
            "publish_time": now - timedelta(hours=1),
            "engagement_json": {"nickname": "zero author"},
        },
        {
            "platform": "xhs",
            "platform_post_id": "engaged-1",
            "author_hash": "author-one",
            "title": "single mom k12 education practical route",
            "content": "single mom shares education planning",
            "url": "https://example.com/engaged-1",
            "publish_time": now - timedelta(hours=3),
            "engagement_json": {"nickname": "engaged author 1", "like_count": 20, "comment_count": 4},
        },
        {
            "platform": "dy",
            "platform_post_id": "threshold-20",
            "author_hash": "author-two",
            "title": "single mom k12 education budget",
            "content": "single mom education cost and school choice",
            "url": "https://example.com/engaged-2",
            "publish_time": now - timedelta(hours=5),
            "engagement_json": {"nickname": "engaged author 2", "like_count": 18, "share_count": 2},
        },
        {
            "platform": "dy",
            "platform_post_id": "below-threshold",
            "author_hash": "author-three",
            "title": "single mom k12 education daily plan",
            "content": "single mom education plan and school choice",
            "url": "https://example.com/below-threshold",
            "publish_time": now - timedelta(hours=2),
            "engagement_json": {"nickname": "below threshold author", "like_count": 12, "share_count": 7},
        },
    ]

    analysis = build_tracker_analysis_snapshot(tracker=tracker, posts=posts)
    representative_ids = [
        item["platform_post_id"]
        for item in analysis["samples"]["representative_samples"]
    ]

    assert "engaged-1" in representative_ids
    assert "threshold-20" in representative_ids
    assert "zero-high-fit" not in representative_ids
    assert "below-threshold" not in representative_ids
    threshold_sample = next(
        item
        for item in analysis["samples"]["representative_samples"]
        if item["platform_post_id"] == "threshold-20"
    )
    assert threshold_sample["market_validation_status"] == "validated"
    below_threshold_sample = next(
        item
        for item in analysis["samples"]["all_samples"]
        if item["platform_post_id"] == "below-threshold"
    )
    assert below_threshold_sample["market_validation_status"] == "pending_validation"


def test_ai_sample_selection_filters_representatives_below_market_threshold() -> None:
    analysis_bundle = {
        "samples": {
            "representative_samples": [
                {
                    "sample_key": "xhs:high",
                    "platform": "xhs",
                    "platform_post_id": "high",
                    "engagement_total": 20,
                    "evidence": {},
                },
                {
                    "sample_key": "xhs:low",
                    "platform": "xhs",
                    "platform_post_id": "low",
                    "engagement_total": 19,
                    "evidence": {},
                },
            ],
            "hot_samples": [],
            "early_signal_samples": [],
            "all_samples": [
                {
                    "sample_key": "xhs:high",
                    "platform": "xhs",
                    "platform_post_id": "high",
                    "engagement_total": 20,
                    "evidence": {},
                },
                {
                    "sample_key": "xhs:low",
                    "platform": "xhs",
                    "platform_post_id": "low",
                    "engagement_total": 19,
                    "evidence": {},
                },
            ],
        },
        "meta": {},
    }

    result = apply_tracker_ai_sample_selection(
        analysis_bundle,
        {
            "representative_samples": [
                {
                    "sample_key": "xhs:low",
                    "relevance_score": 99,
                    "reason": "High semantic fit but too little engagement.",
                },
                {
                    "sample_key": "xhs:high",
                    "relevance_score": 90,
                    "reason": "Meets the market validation threshold.",
                },
            ],
            "hot_samples": [],
            "early_signal_samples": [],
            "noise_samples": [],
        },
        source="ai_gateway",
    )

    representative_ids = [
        item["platform_post_id"]
        for item in result["samples"]["representative_samples"]
    ]
    assert representative_ids == ["high"]
    assert result["samples"]["representative_samples"][0]["selection_source"] == "ai_gateway"


def test_keyword_groups_do_not_classify_tracker_terms_as_noise_or_excludes() -> None:
    now = datetime.now(timezone.utc)
    tracker = {
        "id": 101,
        "name": "single mom education tracker",
        "description": "track K12 education discussions from single moms",
        "platforms": ["xhs", "dy"],
        "included_keywords": ["single mom", "k12 education"],
        "excluded_keywords": [],
        "tracking_mode": "mixed",
    }
    posts = [
        {
            "platform": "xhs",
            "platform_post_id": "high-signal-1",
            "author_hash": "author-a",
            "title": "single mom k12 education planning",
            "content": "single mom shares k12 education planning and school choice",
            "url": "https://example.com/high-1",
            "publish_time": now - timedelta(hours=1),
            "engagement_json": {"like_count": 180, "comment_count": 20},
        },
        {
            "platform": "dy",
            "platform_post_id": "high-signal-2",
            "author_hash": "author-b",
            "title": "single mom k12 education budget",
            "content": "k12 education budget and daily decisions for single mom families",
            "url": "https://example.com/high-2",
            "publish_time": now - timedelta(hours=2),
            "engagement_json": {"like_count": 90, "share_count": 16},
        },
    ]

    analysis = build_tracker_analysis_snapshot(tracker=tracker, posts=posts)
    keywords = analysis["keywords"]
    high_value_terms = {item["keyword"] for item in keywords["high_value_keywords"]}
    recommended_include_terms = set(keywords["recommended_include_keywords"])
    noise_terms = {item["keyword"] for item in keywords["noise_keywords"]}
    recommended_exclude_terms = set(keywords["recommended_exclude_keywords"])

    assert high_value_terms == {"single mom", "k12 education"}
    assert recommended_include_terms.isdisjoint(high_value_terms)
    assert recommended_include_terms.isdisjoint(set(tracker["included_keywords"]))
    assert noise_terms.isdisjoint(high_value_terms)
    assert recommended_exclude_terms.isdisjoint(set(tracker["included_keywords"]))


def test_noisy_tracker_terms_are_visible_without_auto_excluding_them() -> None:
    now = datetime.now(timezone.utc)
    tracker = {
        "id": 103,
        "name": "single mom education tracker",
        "description": "track K12 education discussions from single moms",
        "platforms": ["xhs"],
        "included_keywords": ["single mom", "k12 education"],
        "excluded_keywords": [],
        "tracking_mode": "mixed",
    }
    posts = [
        {
            "platform": "xhs",
            "platform_post_id": "noisy-single-mom",
            "author_hash": "author-noise-a",
            "title": "",
            "content": "single mom k12 education",
            "url": "https://example.com/noisy-single-mom",
            "publish_time": now - timedelta(hours=1),
            "engagement_json": {},
        },
        {
            "platform": "xhs",
            "platform_post_id": "noisy-k12",
            "author_hash": "author-noise-b",
            "title": "",
            "content": "single mom k12 education",
            "url": "https://example.com/noisy-k12",
            "publish_time": now - timedelta(hours=2),
            "engagement_json": {},
        },
    ]

    analysis = build_tracker_analysis_snapshot(tracker=tracker, posts=posts)
    keywords = analysis["keywords"]
    noise_terms = {item["keyword"] for item in keywords["noise_keywords"]}
    recommended_exclude_terms = set(keywords["recommended_exclude_keywords"])
    actions = {
        item["keyword"]: item["recommended_action"]
        for item in keywords["keyword_rows"]
    }

    assert noise_terms == {"single mom", "k12 education"}
    assert recommended_exclude_terms.isdisjoint(set(tracker["included_keywords"]))
    assert actions == {"single mom": "refine", "k12 education": "refine"}


def test_tracker_ai_prompt_requires_all_visible_keyword_categories() -> None:
    now = datetime.now(timezone.utc)
    tracker = {
        "id": 104,
        "name": "single mom education tracker",
        "description": "track K12 education discussions from single moms",
        "platforms": ["xhs"],
        "included_keywords": ["single mom", "k12 education"],
        "excluded_keywords": [],
        "tracking_mode": "mixed",
    }
    posts = [
        {
            "platform": "xhs",
            "platform_post_id": "signal-1",
            "author_hash": "author-a",
            "title": "single mom k12 education planning",
            "content": "single mom k12 education route",
            "url": "https://example.com/signal-1",
            "publish_time": now - timedelta(hours=1),
            "engagement_json": {"like_count": 80, "comment_count": 8},
        }
    ]
    analysis = build_tracker_analysis_snapshot(tracker=tracker, posts=posts)

    prompt = json.loads(
        build_tracker_ai_enhancement_prompt(
            analysis_bundle=analysis,
            candidates=analysis["candidate_rows"],
        )
    )
    keyword_schema = prompt["output_schema"]["keyword_strategy"]
    rules = "\n".join(prompt["rules"])

    assert {
        "high_value_keywords",
        "recommended_include_keywords",
        "noise_keywords",
        "recommended_exclude_keywords",
    } <= set(keyword_schema)
    assert "must each contain at least one evidence-backed term" in rules


def test_ai_keyword_strategy_populates_all_visible_keyword_groups() -> None:
    now = datetime.now(timezone.utc)
    tracker = {
        "id": 105,
        "name": "single mom education tracker",
        "description": "track K12 education discussions from single moms",
        "platforms": ["xhs"],
        "included_keywords": ["single mom", "k12 education"],
        "excluded_keywords": [],
        "tracking_mode": "mixed",
    }
    posts = [
        {
            "platform": "xhs",
            "platform_post_id": "signal-1",
            "author_hash": "author-a",
            "title": "single mom k12 education planning",
            "content": "single mom k12 education route and school choice",
            "url": "https://example.com/signal-1",
            "publish_time": now - timedelta(hours=1),
            "engagement_json": {"like_count": 80, "comment_count": 8},
        }
    ]
    analysis = build_tracker_analysis_snapshot(tracker=tracker, posts=posts)
    from research.content_tracking import apply_tracker_ai_enhancement

    raw_ai_output = {
        "keyword_strategy": {
            "high_value_keywords": ["single mom route"],
            "recommended_include_keywords": ["school choice plan"],
            "noise_keywords": ["generic education"],
            "recommended_exclude_keywords": ["giveaway"],
            "keyword_notes": ["AI must provide every visible keyword category."],
        }
    }
    enhancement = normalize_tracker_ai_enhancement_output(
        raw_ai_output,
        allowed_sample_keys={"xhs:signal-1"},
    )
    apply_tracker_ai_enhancement(
        analysis,
        enhancement,
        source="ai_gateway",
        provider={"name": "test", "model": "test-model"},
    )

    keywords = analysis["keywords"]
    high_value_terms = {item["keyword"] for item in keywords["high_value_keywords"]}
    noise_terms = {item["keyword"] for item in keywords["noise_keywords"]}

    assert "single mom route" in high_value_terms
    assert "school choice plan" in set(keywords["recommended_include_keywords"])
    assert "generic education" in noise_terms
    assert "giveaway" in set(keywords["recommended_exclude_keywords"])
    assert "k12 education" not in set(keywords["recommended_exclude_keywords"])


def test_ai_keyword_excludes_are_sanitized_against_tracker_terms() -> None:
    now = datetime.now(timezone.utc)
    tracker = {
        "id": 102,
        "name": "single mom education tracker",
        "description": "track K12 education discussions from single moms",
        "platforms": ["xhs"],
        "included_keywords": ["single mom", "k12 education"],
        "excluded_keywords": [],
        "tracking_mode": "mixed",
    }
    posts = [
        {
            "platform": "xhs",
            "platform_post_id": "signal-1",
            "author_hash": "author-a",
            "title": "single mom k12 education planning",
            "content": "single mom k12 education route",
            "url": "https://example.com/signal-1",
            "publish_time": now - timedelta(hours=1),
            "engagement_json": {"like_count": 80, "comment_count": 8},
        }
    ]

    analysis = build_tracker_analysis_snapshot(tracker=tracker, posts=posts)
    from research.content_tracking import apply_tracker_ai_enhancement

    apply_tracker_ai_enhancement(
        analysis,
        {
            "keyword_strategy": {
                "recommended_include_keywords": [
                    "single mom",
                    "k12 education",
                    "private school route",
                ],
                "recommended_exclude_keywords": ["single mom", "k12 education", "giveaway"],
                "keyword_notes": ["tracker terms should not become exclude keywords"],
            },
            "noise_diagnosis": {
                "suggested_exclude_keywords": ["single mom", "advertising"],
            },
        },
        source="ai_gateway",
        provider={"name": "test", "model": "test-model"},
    )

    recommended_include_terms = set(analysis["keywords"]["recommended_include_keywords"])
    recommended_exclude_terms = set(analysis["keywords"]["recommended_exclude_keywords"])

    assert "single mom" not in recommended_include_terms
    assert "k12 education" not in recommended_include_terms
    assert "private school route" in recommended_include_terms
    assert "single mom" not in recommended_exclude_terms
    assert "k12 education" not in recommended_exclude_terms
    assert {"giveaway", "advertising"} <= recommended_exclude_terms


@pytest.mark.asyncio
async def test_content_tracking_analysis_lifecycle(content_tracking_client: AsyncClient) -> None:
    create_response = await content_tracking_client.post(
        "/api/content-tracking/trackers",
        json={
            "name": "cat food review tracker",
            "description": "lifecycle regression test for content tracking analysis",
            "platforms": ["xhs", "dy"],
            "included_keywords": ["cat food review", "new cat owner"],
            "excluded_keywords": ["giveaway", "sponsored"],
            "schedule_interval_minutes": 720,
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    tracker = create_response.json()
    tracker_id = tracker["id"]

    analyze_response = await content_tracking_client.post(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()
    assert analysis["tracker"]["id"] == tracker_id
    assert analysis["run"]["candidate_count"] >= 2
    assert analysis["snapshot"]["tracker_id"] == tracker_id
    assert analysis["decisions"]["headline"]
    sample_author_names = {
        item["author_name"]
        for item in analysis["samples"]["representative_samples"]
    }
    assert {"小猫测评官", "新手养猫指南"} <= sample_author_names
    sample_urls = {
        item["url"]
        for item in analysis["samples"]["representative_samples"]
    }
    assert {"https://example.com/xhs/1", "https://example.com/dy/2"} <= sample_urls
    run_id = analysis["run"]["id"]

    latest_response = await content_tracking_client.get(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert latest_response.status_code == 200
    latest = latest_response.json()
    assert latest["tracker"]["id"] == tracker_id
    assert latest["snapshot"]["run_id"] == run_id
    assert latest["tracker"]["latest_analysis_run_id"] == run_id
    assert latest["tracker"]["latest_analysis_snapshot_id"] == latest["snapshot"]["id"]
    latest_author_names = {
        item["author_name"]
        for item in latest["snapshot"]["samples"]["representative_samples"]
    }
    assert {"小猫测评官", "新手养猫指南"} <= latest_author_names
    latest_urls = {
        item["url"]
        for item in latest["snapshot"]["samples"]["representative_samples"]
    }
    assert {"https://example.com/xhs/1", "https://example.com/dy/2"} <= latest_urls

    second_analyze_response = await content_tracking_client.post(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert second_analyze_response.status_code == 200
    second_analysis = second_analyze_response.json()
    assert second_analysis["run"]["id"] != run_id
    assert second_analysis["snapshot"]["id"] != latest["snapshot"]["id"]

    latest_after_second_response = await content_tracking_client.get(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert latest_after_second_response.status_code == 200
    latest_after_second = latest_after_second_response.json()
    assert latest_after_second["run"]["id"] == second_analysis["run"]["id"]
    assert latest_after_second["snapshot"]["id"] == second_analysis["snapshot"]["id"]
    assert latest_after_second["tracker"]["latest_analysis_run_id"] == second_analysis["run"]["id"]
    assert (
        latest_after_second["tracker"]["latest_analysis_snapshot_id"]
        == second_analysis["snapshot"]["id"]
    )

    history_response = await content_tracking_client.get(
        f"/api/content-tracking/trackers/{tracker_id}/analysis/history"
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history["snapshots"]) >= 1

    run_response = await content_tracking_client.get(
        f"/api/content-tracking/analysis-runs/{run_id}"
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["run"]["id"] == run_id
    assert len(run_payload["candidates"]) >= 2

    update_response = await content_tracking_client.patch(
        f"/api/content-tracking/trackers/{tracker_id}",
        json={
            "name": "cat food review tracker updated",
            "included_keywords": ["cat food review", "cat food recommendations"],
            "enabled": True,
        },
    )
    assert update_response.status_code == 200
    updated_tracker = update_response.json()
    assert updated_tracker["name"] == "cat food review tracker updated"
    assert updated_tracker["included_keywords"] == [
        "cat food review",
        "cat food recommendations",
    ]

    delete_response = await content_tracking_client.delete(
        f"/api/content-tracking/trackers/{tracker_id}"
    )
    assert delete_response.status_code == 200
    deleted_payload = delete_response.json()
    assert deleted_payload["status"] == "disabled"
    assert deleted_payload["tracker"]["enabled"] is False

    enabled_list_response = await content_tracking_client.get(
        "/api/content-tracking/trackers?enabled_only=true"
    )
    assert enabled_list_response.status_code == 200
    enabled_ids = [item["id"] for item in enabled_list_response.json()["trackers"]]
    assert tracker_id not in enabled_ids

    latest_after_disable_response = await content_tracking_client.get(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert latest_after_disable_response.status_code == 200
    latest_after_disable = latest_after_disable_response.json()
    assert latest_after_disable["snapshot"]["tracker_id"] == tracker_id


@pytest.mark.asyncio
async def test_content_tracking_analysis_uses_ai_sample_selection(
    content_tracking_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import content_tracking as content_tracking_router

    class StubAIProvider:
        def __init__(self, **_: object) -> None:
            pass

        async def complete_json(self, **_: object) -> dict[str, object]:
            return {
                "representative_samples": [
                    {
                        "sample_key": "dy:seed-post-2",
                        "relevance_score": 96,
                        "reason": "Directly matches new cat owner pain point.",
                    },
                    {
                        "sample_key": "xhs:seed-post-1",
                        "relevance_score": 94,
                        "reason": "Strong practical cat food review sample.",
                    },
                ],
                "hot_samples": [
                    {
                        "sample_key": "xhs:seed-post-1",
                        "relevance_score": 94,
                        "reason": "Relevant and high-engagement.",
                    }
                ],
                "early_signal_samples": [
                    {
                        "sample_key": "dy:seed-post-2",
                        "relevance_score": 90,
                        "reason": "High fit before crossing hot threshold.",
                    }
                ],
                "noise_samples": [],
            }

    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "test-model")
    monkeypatch.setattr(content_tracking_router, "OpenAICompatibleProvider", StubAIProvider)

    create_response = await content_tracking_client.post(
        "/api/content-tracking/trackers",
        json={
            "name": "ai selected cat tracker",
            "description": "AI sample selection should reorder evidence samples",
            "platforms": ["xhs", "dy"],
            "included_keywords": ["cat food review", "new cat owner"],
            "excluded_keywords": ["giveaway", "sponsored"],
            "schedule_interval_minutes": 720,
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    tracker_id = create_response.json()["id"]

    analyze_response = await content_tracking_client.post(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()

    representative_samples = analysis["samples"]["representative_samples"]
    assert representative_samples[0]["platform_post_id"] == "seed-post-2"
    assert representative_samples[0]["selection_source"] == "ai_gateway"
    assert representative_samples[0]["ai_relevance_score"] == 96
    assert (
        representative_samples[0]["evidence"]["ai_selection_reason"]
        == "Directly matches new cat owner pain point."
    )
    assert analysis["meta"]["sample_selection"]["source"] == "ai_gateway"
    assert analysis["meta"]["sample_selection"]["provider"]["model"] == "test-model"


@pytest.mark.asyncio
async def test_tracker_keyword_suggestions_use_ai_gateway(
    content_tracking_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers import content_tracking as content_tracking_router

    class StubKeywordProvider:
        def __init__(self, **_: object) -> None:
            pass

        async def complete_json(self, **_: object) -> dict[str, object]:
            return {
                "included_keywords": ["single mom education", "k12 route"],
                "expanded_keywords": ["school choice budget"],
                "excluded_keywords": ["ad", "giveaway"],
                "platform_keywords": {"xhs": ["单亲妈妈教育"]},
                "reason": "Use precise education and budget terms.",
            }

    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    monkeypatch.setenv("AI_GATEWAY_MODEL", "keyword-model")
    monkeypatch.setattr(content_tracking_router, "OpenAICompatibleProvider", StubKeywordProvider)

    response = await content_tracking_client.post(
        "/api/content-tracking/tracker-keyword-suggestions",
        json={
            "name": "single mom K12 tracker",
            "description": "track education pain points",
            "platforms": ["xhs", "dy"],
            "included_keywords": ["single mom"],
            "excluded_keywords": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"]["model"] == "keyword-model"
    assert payload["suggestions"]["included_keywords"] == ["single mom education", "k12 route"]
    assert payload["suggestions"]["expanded_keywords"] == ["school choice budget"]
    assert payload["suggestions"]["excluded_keywords"] == ["ad", "giveaway"]


@pytest.mark.asyncio
async def test_content_tracking_first_analysis_without_existing_snapshot(
    content_tracking_client: AsyncClient,
) -> None:
    create_response = await content_tracking_client.post(
        "/api/content-tracking/trackers",
        json={
            "name": "fresh tracker",
            "description": "first analysis should work without a pre-existing snapshot",
            "platforms": ["xhs"],
            "included_keywords": ["cat food review"],
            "excluded_keywords": ["giveaway"],
            "schedule_interval_minutes": 1440,
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    tracker_id = create_response.json()["id"]

    latest_before_response = await content_tracking_client.get(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert latest_before_response.status_code == 404
    assert latest_before_response.json()["detail"] == "Tracker analysis snapshot not found"

    history_before_response = await content_tracking_client.get(
        f"/api/content-tracking/trackers/{tracker_id}/analysis/history"
    )
    assert history_before_response.status_code == 200
    assert history_before_response.json()["snapshots"] == []

    analyze_response = await content_tracking_client.post(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()
    assert analysis["snapshot"]["tracker_id"] == tracker_id
    assert analysis["run"]["status"] == "completed"

    latest_after_response = await content_tracking_client.get(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert latest_after_response.status_code == 200
    assert latest_after_response.json()["snapshot"]["tracker_id"] == tracker_id


@pytest.mark.asyncio
async def test_content_tracking_analysis_deduplicates_candidate_samples(
    content_tracking_client: AsyncClient,
) -> None:
    await _seed_duplicate_tracking_posts()

    create_response = await content_tracking_client.post(
        "/api/content-tracking/trackers",
        json={
            "name": "duplicate candidate tracker",
            "platforms": ["xhs"],
            "included_keywords": ["duplicate cat insight"],
            "excluded_keywords": [],
            "schedule_interval_minutes": 720,
            "enabled": True,
        },
    )
    assert create_response.status_code == 200
    tracker_id = create_response.json()["id"]

    analyze_response = await content_tracking_client.post(
        f"/api/content-tracking/trackers/{tracker_id}/analysis"
    )
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()
    assert analysis["run"]["status"] == "completed"
    assert analysis["run"]["candidate_count"] == 1
    assert analysis["snapshot"]["tracker_id"] == tracker_id

    run_response = await content_tracking_client.get(
        f"/api/content-tracking/analysis-runs/{analysis['run']['id']}"
    )
    assert run_response.status_code == 200
    candidates = run_response.json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["platform_post_id"] == "duplicate-seed-post"

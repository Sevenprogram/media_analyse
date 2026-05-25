from typing import Any

from research.account_profiles import AccountProfileService
from research.auto_pooling import auto_pool_a_tier_candidates
from research.candidate_tiering import candidate_payload_with_tier, tier_creator_candidates
from research.competitor_public_flow import DEFAULT_LATEST_LIMIT, build_competitor_public_flow_snapshot
from research.content_fingerprint import analyze_posts_for_tracking
from research.content_tracking import build_tracker_analysis, search_similar_content
from research.creator_search import rebuild_creator_profiles
from research.keyword_heat import aggregate_keyword_heat_from_posts
from research.tagging import tag_research_job


async def run_post_crawl_analysis(
    repository,
    *,
    job_id: int,
    platform: str | None = None,
    analysis_version: str = "v1",
) -> dict[str, Any]:
    required_methods = (
        "list_tag_definitions",
        "bulk_upsert_entity_tags",
        "list_all_posts",
        "list_all_comments",
        "list_all_authors",
        "list_entity_tags",
        "upsert_creator_profile",
    )
    if any(not hasattr(repository, method) for method in required_methods):
        return {
            "skipped": True,
            "reason": "postprocess_repository_methods_unavailable",
            "platform": platform,
        }
    if platform:
        capability = await repository.get_platform_capability(platform)
        if capability and (not capability["enabled"] or not capability["analysis_enabled"]):
            return {
                "skipped": True,
                "reason": "platform_analysis_disabled",
                "platform": platform,
            }
    tag_stats = await tag_research_job(
        repository,
        job_id=job_id,
        vertical_id=None,
        analysis_version=analysis_version,
        use_ai=False,
    )
    profile_stats = await rebuild_creator_profiles(
        repository,
        job_id=job_id,
        platform=platform,
        analysis_version=analysis_version,
    )
    account_profile_stats = await rebuild_account_profiles_from_posts(
        repository,
        job_id=job_id,
        platform=platform,
    )
    operations_stats = await run_growth_ops_postprocess(
        repository,
        job_id=job_id,
        platform=platform,
    )
    return {
        "skipped": False,
        "platform": platform,
        "tagging": tag_stats,
        "profiles": profile_stats,
        "account_profiles": account_profile_stats,
        "operations": operations_stats,
    }


async def run_growth_ops_postprocess(
    repository,
    *,
    job_id: int,
    platform: str | None = None,
) -> dict[str, Any]:
    posts = await _maybe_list_all_posts(repository, job_id=job_id, platform=platform)
    stats: dict[str, Any] = {
        "content_fingerprints": analyze_posts_for_tracking(posts),
        "tiered_candidates": 0,
        "auto_pooled": 0,
        "content_snapshots": 0,
        "keyword_heat_snapshots": 0,
        "competitor_compositions": 0,
        "skipped": [],
    }
    candidate_stats = await _tier_existing_candidates(repository, platform=platform)
    stats["tiered_candidates"] = candidate_stats["tiered"]
    stats["auto_pooled"] = candidate_stats["auto_pooled"]
    content_stats = await _rebuild_content_tracker_snapshots(repository, posts=posts, platform=platform)
    stats["content_snapshots"] = content_stats["created"]
    heat_stats = await _rebuild_keyword_heat_snapshots(repository, posts=posts, platform=platform)
    stats["keyword_heat_snapshots"] = heat_stats["created"]
    competitor_stats = await _rebuild_competitor_composition_snapshots(repository, platform=platform)
    stats["competitor_compositions"] = competitor_stats["created"]
    stats["skipped"] = (
        candidate_stats["skipped"]
        + content_stats["skipped"]
        + heat_stats["skipped"]
        + competitor_stats["skipped"]
    )
    return stats


async def _maybe_list_all_posts(repository, *, job_id: int | None, platform: str | None) -> list[dict[str, Any]]:
    if not hasattr(repository, "list_all_posts"):
        return []
    try:
        return await repository.list_all_posts(job_id=job_id, platform=platform)
    except TypeError:
        return await repository.list_all_posts(platform=platform)


async def _tier_existing_candidates(repository, *, platform: str | None) -> dict[str, Any]:
    skipped = []
    if not all(
        hasattr(repository, method)
        for method in ("list_creator_candidates", "upsert_creator_candidate", "list_monitor_pools")
    ):
        return {"tiered": 0, "auto_pooled": 0, "skipped": ["candidate_methods_unavailable"]}
    candidates = await repository.list_creator_candidates(platform=platform)
    tiered = tier_creator_candidates(candidates)
    updated = 0
    for candidate in tiered:
        payload = candidate_payload_with_tier(
            {
                "platform": candidate["platform"],
                "creator_id": candidate["creator_id"],
                "pool_name": candidate.get("pool_name") or "default",
                "vertical_id": candidate.get("vertical_id"),
                "match_score": candidate.get("match_score"),
                "matched_tags_json": candidate.get("matched_tags") or candidate.get("matched_tags_json") or [],
                "evidence_json": candidate.get("evidence") or candidate.get("evidence_json") or {},
                "notes": candidate.get("notes"),
            }
        )
        await repository.upsert_creator_candidate(payload)
        updated += 1
    pools = await repository.list_monitor_pools(enabled_only=True)
    auto_pooled = 0
    if pools and all(
        hasattr(repository, method)
        for method in ("get_monitor_pool", "list_monitor_pool_creators", "add_monitor_pool_creators")
    ):
        result = await auto_pool_a_tier_candidates(
            repository,
            pool_id=pools[0]["id"],
            candidates=tiered,
            daily_cap=20,
            crawl_now=False,
        )
        auto_pooled = len(result["added"])
    else:
        skipped.append("monitor_pool_methods_unavailable")
    return {"tiered": updated, "auto_pooled": auto_pooled, "skipped": skipped}


async def _rebuild_content_tracker_snapshots(repository, *, posts: list[dict[str, Any]], platform: str | None) -> dict[str, Any]:
    if not all(hasattr(repository, method) for method in ("list_content_trackers", "create_content_tracking_snapshot")):
        return {"created": 0, "skipped": ["content_tracker_methods_unavailable"]}
    from datetime import date

    created = 0
    trackers = await repository.list_content_trackers(enabled_only=True)
    for tracker in trackers:
        tracker_platform = tracker["platforms"][0] if len(tracker.get("platforms") or []) == 1 else platform
        candidates = search_similar_content(
            keywords=tracker.get("included_keywords") or [],
            posts=[post for post in posts if tracker_platform is None or post.get("platform") == tracker_platform],
            limit=50,
        )
        analysis = build_tracker_analysis(tracker=tracker, candidates=candidates)
        await repository.create_content_tracking_snapshot(
            {
                "tracker_id": tracker["id"],
                "snapshot_date": date.today(),
                "platform": tracker_platform,
                "keyword_distribution": {
                    item["name"]: item["value"]
                    for item in analysis.get("summary", {}).get("top_keywords", [])
                },
                "tag_distribution": {},
                "content_type_distribution": {},
                "publish_time_distribution": {},
                "hot_post_rate": 0.0,
                "total_content_count": len(candidates),
                "evidence": {
                    "hot_content": analysis.get("hot_content", [])[:10],
                    "fingerprints": analyze_posts_for_tracking(posts[:20]),
                },
            }
        )
        created += 1
    return {"created": created, "skipped": []}


async def _rebuild_keyword_heat_snapshots(repository, *, posts: list[dict[str, Any]], platform: str | None) -> dict[str, Any]:
    if not all(hasattr(repository, method) for method in ("list_scene_pack_keywords", "upsert_keyword_heat_snapshot")):
        return {"created": 0, "skipped": ["keyword_heat_methods_unavailable"]}
    from datetime import date

    keywords = await repository.list_scene_pack_keywords(enabled_only=True)
    created = 0
    seen: set[tuple[int | None, str]] = set()
    for item in keywords:
        if item.get("keyword_type") == "negative":
            continue
        keyword = str(item.get("keyword") or "").strip()
        key = (item.get("scene_pack_id"), keyword)
        if not keyword or key in seen:
            continue
        seen.add(key)
        signal = aggregate_keyword_heat_from_posts(keyword=keyword, posts=posts)
        await repository.upsert_keyword_heat_snapshot(
            {
                "vertical_id": None,
                "scene_pack_id": item.get("scene_pack_id"),
                "keyword": keyword,
                "platform": platform or item.get("platform") or "all",
                "snapshot_date": date.today(),
                "heat_score": signal["heat_score"],
                "growth_score": signal["heat_score"],
                "push_signal_score": signal["push_score"],
                "limit_signal_score": signal["cooldown_risk"],
                "platform_signal": signal["label"],
                "evidence": {
                    "evidence": signal["evidence"],
                    "sample_quality": signal["sample_quality"],
                    "sampling_advice": signal.get("sampling_advice"),
                },
            }
        )
        created += 1
    return {"created": created, "skipped": []}


async def _rebuild_competitor_composition_snapshots(repository, *, platform: str | None) -> dict[str, Any]:
    if not all(
        hasattr(repository, method)
        for method in (
            "list_competitor_accounts",
            "list_posts_by_creator",
            "list_entity_tags",
            "upsert_competitor_composition_snapshot",
        )
    ):
        return {"created": 0, "skipped": ["competitor_composition_methods_unavailable"]}
    from datetime import date

    created = 0
    competitors = await repository.list_competitor_accounts(enabled_only=True)
    for competitor in competitors:
        if platform and competitor.get("platform") != platform:
            continue
        posts = await repository.list_posts_by_creator(
            platform=competitor["platform"],
            creator_id=competitor["creator_id"],
            limit=DEFAULT_LATEST_LIMIT * 2,
        )
        tags = await repository.list_entity_tags(
            entity_type="creator",
            entity_id=competitor["creator_id"],
            platform=competitor["platform"],
            vertical_id=competitor.get("vertical_id"),
        )
        previous_snapshots = []
        if hasattr(repository, "list_competitor_composition_snapshots"):
            previous_snapshots = await repository.list_competitor_composition_snapshots(
                competitor_id=competitor["id"],
                limit=8,
            )
        snapshot = build_competitor_public_flow_snapshot(
            competitor=competitor,
            snapshot_date=date.today(),
            posts=posts,
            entity_tags=tags,
            previous_snapshots=previous_snapshots,
            keywords=[],
        )
        await repository.upsert_competitor_composition_snapshot(snapshot)
        created += 1
    return {"created": created, "skipped": []}


async def rebuild_account_profiles_from_posts(
    repository,
    *,
    job_id: int,
    platform: str | None = None,
    vertical_id: int | None = None,
    scene_pack_id: int | None = None,
) -> dict[str, Any]:
    if not all(
        hasattr(repository, method)
        for method in ("list_posts", "upsert_account_profile", "upsert_account_role")
    ):
        return {"skipped": True, "reason": "account_profile_methods_unavailable"}

    service = AccountProfileService(repository)
    posts = await repository.list_posts(job_id, limit=5000)
    upserted = 0
    skipped = 0
    for post in posts:
        if platform and post.get("platform") != platform:
            continue
        engagement = post.get("engagement_json") or {}
        author_id = engagement.get("author_id") or engagement.get("user_id")
        if not author_id:
            skipped += 1
            continue
        await service.upsert_from_post_author(
            {
                "platform": post["platform"],
                "author_id": str(author_id),
                "sec_account_id": engagement.get("sec_uid"),
                "display_name": engagement.get("nickname"),
                "bio": engagement.get("signature"),
                "source": "postprocess",
            },
            vertical_id=vertical_id,
            scene_pack_id=scene_pack_id,
            role="candidate_creator",
        )
        upserted += 1
    return {"skipped": False, "upserted": upserted, "missing_author": skipped}

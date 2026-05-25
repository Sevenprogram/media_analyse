from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from research.creator_metrics import (
    avg_engagement_rate_from_posts,
    engagement_total_from_post,
    hot_post_rate_from_posts,
)
from research.enums import PARSER_SOURCE_RULE
from research.realtime_creator_discovery import discover_realtime_creators


def parse_search_intent(
    *,
    raw_query: str,
    verticals: list[dict[str, Any]],
    tag_definitions: list[dict[str, Any]],
    selected_vertical_id: int | None = None,
) -> dict[str, Any]:
    query = raw_query.strip()
    detected_vertical_scores: Counter[int] = Counter()
    required_tags: list[int] = []
    optional_tags: list[int] = []

    for tag in tag_definitions:
        score = _tag_query_score(query, tag)
        if score <= 0:
            continue
        detected_vertical_scores[int(tag["vertical_id"])] += score
        if score >= 1:
            required_tags.append(int(tag["id"]))
        else:
            optional_tags.append(int(tag["id"]))

    if selected_vertical_id is not None:
        detected_verticals = [selected_vertical_id]
    else:
        detected_verticals = [
            vertical_id
            for vertical_id, _ in detected_vertical_scores.most_common()
        ]

    vertical_options = [
        vertical for vertical in verticals if int(vertical["id"]) in set(detected_verticals)
    ]
    needs_selection = selected_vertical_id is None and len(vertical_options) > 1
    if selected_vertical_id is not None:
        required_tags = [
            tag_id
            for tag_id in required_tags
            if _tag_by_id(tag_definitions, tag_id).get("vertical_id") == selected_vertical_id
        ]
        optional_tags = [
            tag_id
            for tag_id in optional_tags
            if _tag_by_id(tag_definitions, tag_id).get("vertical_id") == selected_vertical_id
        ]

    return {
        "raw_query": query,
        "detected_verticals": vertical_options,
        "selected_vertical_id": selected_vertical_id,
        "required_tags": sorted(set(required_tags)),
        "optional_tags": sorted(set(optional_tags) - set(required_tags)),
        "negative_tags": [],
        "confidence": 0.9 if required_tags else 0.4 if optional_tags else 0.0,
        "parser_source": PARSER_SOURCE_RULE,
        "needs_vertical_selection": needs_selection,
    }


def calculate_creator_match_score(
    *,
    required_tag_ids: list[int],
    optional_tag_ids: list[int],
    creator_profile: dict[str, Any],
    entity_tags: list[dict[str, Any]],
    recent_posts: list[dict[str, Any]] | None = None,
) -> float:
    tag_ids = [int(tag["tag_id"]) for tag in entity_tags]
    tag_counter = Counter(tag_ids)
    required = set(required_tag_ids)
    optional = set(optional_tag_ids)
    matched_required = required & set(tag_ids)
    required_coverage = len(matched_required) / len(required) if required else 1.0

    total_recent = max(1, int(creator_profile.get("recent_post_count_30d") or len(recent_posts or []) or 1))
    recent_frequency = min(1.0, sum(tag_counter[tag_id] for tag_id in required | optional) / total_recent)
    high_engagement = _high_engagement_component(entity_tags)
    profile_match = _profile_tag_component(creator_profile, required | optional)
    confidence_quality = (
        sum(float(tag.get("confidence") or 0) for tag in entity_tags) / max(1, len(entity_tags))
    )

    score = (
        required_coverage * 40
        + recent_frequency * 25
        + high_engagement * 15
        + profile_match * 10
        + confidence_quality * 10
    )
    return round(score, 4)


def score_creator_against_scene_packs(
    *,
    creator_profile: dict[str, Any],
    recent_posts: list[dict[str, Any]],
    scene_keywords: list[dict[str, Any]],
) -> dict[str, Any]:
    text = " ".join(
        str(value or "")
        for value in [
            creator_profile.get("display_name"),
            creator_profile.get("bio"),
            *[
                post.get("title") or post.get("content") or ""
                for post in recent_posts
            ],
        ]
    ).lower()
    primary_hits = []
    secondary_hits = []
    negative_hits = []
    score = 0.0
    for keyword in scene_keywords:
        term = str(keyword.get("keyword") or "").lower()
        if not term or term not in text:
            continue
        weight = float(keyword.get("weight") or 1)
        keyword_type = keyword.get("keyword_type")
        if keyword_type == "primary":
            primary_hits.append(keyword)
            score += 50 * weight
        elif keyword_type in {"secondary", "synonym", "platform_adapted"}:
            secondary_hits.append(keyword)
            score += 15 * weight
        elif keyword_type == "negative":
            negative_hits.append(keyword)
            score -= 30 * weight
    if not primary_hits:
        score = 0.0
    return {
        "match_score": round(max(0.0, min(100.0, score)), 4),
        "primary_hits": primary_hits,
        "secondary_hits": secondary_hits,
        "negative_hits": negative_hits,
    }


def aggregate_creator_profile(
    *,
    platform: str,
    creator_id: str,
    posts: list[dict[str, Any]],
    entity_tags: list[dict[str, Any]],
    base_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    recent_posts = [
        post for post in posts if _as_utc(post.get("publish_time") or now) >= cutoff
    ]
    tag_summary: dict[str, Any] = defaultdict(lambda: {"count": 0, "confidence_sum": 0.0})
    for tag in entity_tags:
        item = tag_summary[str(tag["tag_id"])]
        item["count"] += 1
        item["confidence_sum"] += float(tag.get("confidence") or 0)
    normalized_summary = {
        tag_id: {
            "count": data["count"],
            "avg_confidence": round(data["confidence_sum"] / max(1, data["count"]), 4),
        }
        for tag_id, data in tag_summary.items()
    }
    base_profile = base_profile or {}
    return {
        "platform": platform,
        "creator_id": creator_id,
        "display_name": base_profile.get("display_name"),
        "profile_url": base_profile.get("profile_url"),
        "bio": base_profile.get("bio"),
        "follower_count": base_profile.get("follower_count"),
        "following_count": base_profile.get("following_count"),
        "post_count": len(posts),
        "avg_engagement_rate": avg_engagement_rate_from_posts(posts, base_profile.get("follower_count")),
        "hot_post_rate": hot_post_rate_from_posts(posts),
        "recent_post_count_30d": len(recent_posts),
        "latest_snapshot_at": now,
        "tag_summary_json": normalized_summary,
    }


async def search_creators(repository, request: dict[str, Any]) -> dict[str, Any]:
    tag_definitions = await repository.list_tag_definitions(
        vertical_id=request.get("selected_vertical_id"),
        enabled_only=True,
    )
    verticals = await repository.list_verticals(enabled_only=True)
    required_tag_ids = request.get("required_tag_ids") or []
    optional_tag_ids = request.get("optional_tag_ids") or []
    intent = None
    if request.get("raw_query"):
        intent = parse_search_intent(
            raw_query=request["raw_query"],
            verticals=verticals,
            tag_definitions=tag_definitions,
            selected_vertical_id=request.get("selected_vertical_id"),
        )
        if intent["needs_vertical_selection"]:
            return {"intent": intent, "results": []}
        required_tag_ids = required_tag_ids or intent["required_tags"]
        optional_tag_ids = optional_tag_ids or intent["optional_tags"]

    diagnostics = {
        "profile_count": 0,
        "tag_definition_count": len(tag_definitions),
        "matched_tag_count": len(set(required_tag_ids + optional_tag_ids)),
        "fallback_used": False,
        "auto_rebuilt_profiles": 0,
        "guidance": "",
    }
    profiles = await repository.list_creator_profiles(
        platforms=request.get("platforms") or None,
        limit=None,
    )
    if not profiles:
        rebuild_platform = _single_platform(request.get("platforms") or None)
        rebuilt = await rebuild_creator_profiles(
            repository,
            platform=rebuild_platform,
        )
        diagnostics["auto_rebuilt_profiles"] = rebuilt["rebuilt_count"]
        profiles = rebuilt["profiles"] or await repository.list_creator_profiles(
            platforms=request.get("platforms") or None,
            limit=None,
        )
    diagnostics["profile_count"] = len(profiles)

    query_terms = _query_terms(request.get("raw_query") or "")
    text_required_terms = _query_terms_not_covered_by_tags(
        query_terms,
        tag_definitions,
        list(set(required_tag_ids + optional_tag_ids)),
    )
    should_use_text_fallback = bool(query_terms)
    tag_ids_filter = list(set(required_tag_ids + optional_tag_ids)) or None
    tags_by_creator: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    if tag_ids_filter:
        for current_platform in sorted({str(profile["platform"]) for profile in profiles}):
            platform_profiles = [
                str(profile["creator_id"])
                for profile in profiles
                if profile["platform"] == current_platform and _passes_profile_filters(profile, request)
            ]
            if hasattr(repository, "list_entity_tags_for_entities"):
                platform_tags = await repository.list_entity_tags_for_entities(
                    entity_type="creator",
                    entity_ids=platform_profiles,
                    platform=current_platform,
                    vertical_id=request.get("selected_vertical_id"),
                    tag_ids=tag_ids_filter,
                )
            else:
                platform_tags = await repository.list_entity_tags(
                    entity_type="creator",
                    platform=current_platform,
                    vertical_id=request.get("selected_vertical_id"),
                    tag_ids=tag_ids_filter,
                )
            for tag in platform_tags:
                tags_by_creator[(str(tag["platform"]), str(tag["entity_id"]))].append(tag)
    tag_filters_have_matches = bool(tags_by_creator)
    results = []
    for profile in profiles:
        if not _passes_profile_filters(profile, request):
            continue
        tags = tags_by_creator.get((str(profile["platform"]), str(profile["creator_id"])), [])
        if not tag_ids_filter:
            tags = await repository.list_entity_tags(
                entity_type="creator",
                entity_id=profile["creator_id"],
                platform=profile["platform"],
                vertical_id=request.get("selected_vertical_id"),
                tag_ids=None,
            )
        missing_required_tags = bool(required_tag_ids) and not set(required_tag_ids).issubset(
            {int(tag["tag_id"]) for tag in tags}
        )
        recent_posts = []
        fallback = {"score": 0.0, "evidence": [], "matched_terms": []}
        if should_use_text_fallback:
            recent_posts = await repository.list_posts_by_creator(
                platform=profile["platform"],
                creator_id=profile["creator_id"],
                limit=30,
            )
            fallback = _score_creator_text_fallback(
                profile=profile,
                posts=recent_posts,
                query_terms=text_required_terms or query_terms,
            )
            diagnostics["fallback_used"] = diagnostics["fallback_used"] or fallback["score"] > 0
        if missing_required_tags and fallback["score"] <= 0:
            continue
        if text_required_terms and not set(text_required_terms).issubset(set(fallback["matched_terms"])):
            continue
        tag_score = calculate_creator_match_score(
            required_tag_ids=required_tag_ids,
            optional_tag_ids=optional_tag_ids,
            creator_profile=profile,
            entity_tags=tags,
            recent_posts=recent_posts,
        ) if tags or required_tag_ids or optional_tag_ids else 0.0
        score = max(tag_score, fallback["score"])
        if tag_score and fallback["score"]:
            score = round(min(100.0, tag_score * 0.7 + fallback["score"] * 0.3), 4)
        if query_terms and not (required_tag_ids or optional_tag_ids) and score <= 0:
            continue
        result_item = {
            "platform": profile["platform"],
            "creator_id": profile["creator_id"],
            "display_name": profile.get("display_name"),
            "profile_url": profile.get("profile_url"),
            "follower_count": profile.get("follower_count"),
            "total_like_count": _profile_metric(profile, "total_like_count"),
            "total_collect_count": _profile_metric(profile, "total_collect_count"),
            "interaction_count": _profile_metric(profile, "interaction_count"),
            "recent_post_count_30d": profile.get("recent_post_count_30d") or 0,
            "avg_engagement_rate": profile.get("avg_engagement_rate"),
            "hot_post_rate": profile.get("hot_post_rate"),
            "match_score": score,
            "matched_tags": tags or [
                {"source": "query_text_fallback", "term": term}
                for term in fallback["matched_terms"]
            ],
            "evidence": [tag.get("evidence_json") or {} for tag in tags] or fallback["evidence"],
            "representative_posts": fallback["evidence"],
        }
        results.append(
            _with_source_metadata(
                result_item,
                source_type="local",
                labels=["Database"],
                realtime_unverified=False,
            )
        )
    results.sort(key=lambda item: item["match_score"], reverse=True)
    results = _dedupe_creator_results(results)
    realtime_diagnostics = _realtime_skipped_diagnostics()
    if request.get("include_realtime"):
        try:
            realtime = await discover_realtime_creators(repository, request)
            realtime_diagnostics = realtime["diagnostics"]
            results = _merge_creator_result_sources(results, realtime.get("results") or [])
        except Exception as exc:
            realtime_diagnostics = {
                **_realtime_skipped_diagnostics(),
                "enabled": True,
                "status": "failed",
                "platforms": request.get("platforms") or [],
                "error": str(exc),
            }
    diagnostics["guidance"] = _creator_search_guidance(
        profile_count=diagnostics["profile_count"],
        result_count=len(results),
        matched_tag_count=diagnostics["matched_tag_count"],
        fallback_used=diagnostics["fallback_used"],
    )
    limit = int(request.get("limit") or 50)
    final_results = _apply_realtime_result_quota(results, request, realtime_diagnostics, limit)
    selected_realtime = _count_realtime_results(final_results)
    requested_ratio = _requested_realtime_ratio(request) if request.get("include_realtime") else 0
    realtime_diagnostics = {
        **realtime_diagnostics,
        "requested_ratio": requested_ratio,
        "selected_count": selected_realtime,
        "selected_ratio": round((selected_realtime * 100) / len(final_results)) if final_results else 0,
    }
    return {
        "intent": intent,
        "diagnostics": diagnostics,
        "realtime": realtime_diagnostics,
        "progress": _complete_progress(request, realtime_diagnostics),
        "results": final_results,
    }


def _with_source_metadata(
    item: dict[str, Any],
    *,
    source_type: str,
    labels: list[str],
    realtime_unverified: bool,
) -> dict[str, Any]:
    return {
        **item,
        "source_type": source_type,
        "source_labels": labels,
        "realtime_unverified": realtime_unverified,
    }


def _realtime_skipped_diagnostics() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "skipped",
        "platforms": [],
        "unsupported_platforms": [],
        "created_profiles": 0,
        "created_candidates": 0,
        "requested_ratio": 0,
        "selected_count": 0,
        "selected_ratio": 0,
        "error": None,
    }


def _complete_progress(request: dict[str, Any], realtime_diagnostics: dict[str, Any]) -> dict[str, Any]:
    if request.get("include_realtime") and realtime_diagnostics.get("enabled"):
        persisted = int(realtime_diagnostics.get("persisted_creators") or realtime_diagnostics.get("created_candidates") or 0)
        limit = int(realtime_diagnostics.get("limit") or request.get("limit") or 50)
        return {
            "stage": "complete",
            "label": f"Complete · saved {persisted}/{limit} realtime creators",
            "percent": 100,
        }
    return {"stage": "complete", "label": "Complete", "percent": 100}


def _merge_creator_result_sources(
    local_results: list[dict[str, Any]],
    realtime_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for item in local_results:
        key = _creator_identity_key(item)
        index[key] = item
        merged.append(item)
    for realtime in realtime_results:
        key = _creator_identity_key(realtime)
        local = index.get(key)
        if local is None:
            merged.append(realtime)
            index[key] = realtime
            continue
        local.update(_fill_missing_profile_fields(local, realtime))
        local["source_type"] = "mixed"
        local["source_labels"] = ["Database", "Realtime"]
        local["realtime_unverified"] = False
        if not local.get("representative_posts") and realtime.get("representative_posts"):
            local["representative_posts"] = realtime["representative_posts"]
        if realtime.get("matched_tags"):
            local["matched_tags"] = (local.get("matched_tags") or []) + realtime["matched_tags"]
    merged.sort(key=lambda item: float(item.get("match_score") or 0), reverse=True)
    return _dedupe_creator_results(merged)


def _apply_realtime_result_quota(
    results: list[dict[str, Any]],
    request: dict[str, Any],
    realtime_diagnostics: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    limit = max(1, min(200, int(limit or 50)))
    if not request.get("include_realtime") or not realtime_diagnostics.get("enabled"):
        return results[:limit]
    realtime_ratio = _requested_realtime_ratio(request)
    realtime_quota = _requested_realtime_quota(limit, realtime_ratio)
    realtime_results = [item for item in results if _has_realtime_source(item)]
    local_results = [item for item in results if not _has_realtime_source(item)]
    if not realtime_results or realtime_quota <= 0:
        return results[:limit]
    selected_realtime = realtime_results[: min(realtime_quota, len(realtime_results))]
    selected_local = local_results[: max(0, limit - len(selected_realtime))]
    remaining = max(0, limit - len(selected_realtime) - len(selected_local))
    if remaining > 0:
        selected_realtime = selected_realtime + realtime_results[len(selected_realtime) : len(selected_realtime) + remaining]

    selected_keys = {
        _creator_identity_key(item)
        for item in [*selected_realtime, *selected_local]
    }
    final_results = [item for item in results if _creator_identity_key(item) in selected_keys]
    return final_results[:limit]


def _requested_realtime_ratio(request: dict[str, Any]) -> int:
    try:
        ratio = int(request.get("realtime_ratio") if request.get("realtime_ratio") is not None else 50)
    except (TypeError, ValueError):
        ratio = 50
    return max(0, min(100, ratio))


def _requested_realtime_quota(limit: int, realtime_ratio: int) -> int:
    if realtime_ratio <= 0:
        return 0
    return min(limit, max(1, (limit * realtime_ratio) // 100))


def _count_realtime_results(results: list[dict[str, Any]]) -> int:
    return sum(1 for item in results if _has_realtime_source(item))


def _has_realtime_source(item: dict[str, Any]) -> bool:
    if item.get("source_type") in {"realtime", "mixed"}:
        return True
    return "Realtime" in (item.get("source_labels") or [])


def _creator_identity_key(item: dict[str, Any]) -> str:
    platform = str(item.get("platform") or "")
    creator_id = str(item.get("creator_id") or "")
    if platform and creator_id:
        return f"id:{platform}:{creator_id}"
    profile_url = str(item.get("profile_url") or "").strip()
    if profile_url:
        return f"url:{profile_url}"
    display_name = str(item.get("display_name") or "").strip()
    return f"name:{platform}:{display_name}"


def _fill_missing_profile_fields(local: dict[str, Any], realtime: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "display_name",
        "profile_url",
        "bio",
        "follower_count",
        "recent_post_count_30d",
        "avg_engagement_rate",
        "hot_post_rate",
    )
    return {
        field: realtime[field]
        for field in fields
        if local.get(field) in (None, "", 0) and realtime.get(field) not in (None, "", 0)
    }


def _dedupe_creator_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        key = str(item.get("profile_url") or "").strip()
        if not key:
            display_name = str(item.get("display_name") or "").strip()
            if display_name and display_name != item.get("creator_id"):
                key = f"{item.get('platform')}:{display_name}"
        if not key:
            key = f"{item.get('platform')}:{item.get('creator_id')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


async def rebuild_creator_profiles(
    repository,
    *,
    job_id: int | None = None,
    platform: str | None = None,
    creator_id: str | None = None,
    analysis_version: str = "v1",
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    posts = await repository.list_all_posts(job_id=job_id, platform=platform)
    posts_by_creator: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        author_hash = post.get("author_hash")
        if not author_hash:
            continue
        if creator_id and author_hash != creator_id:
            continue
        posts_by_creator[(post["platform"], author_hash)].append(post)

    rebuilt = []
    total = len(posts_by_creator)
    if progress_callback:
        progress_callback({"status": "running", "total": total, "processed": 0, "rebuilt_count": 0})
    for (creator_platform, current_creator_id), creator_posts in posts_by_creator.items():
        existing_profile = await repository.get_creator_profile(creator_platform, current_creator_id)
        tags = await repository.list_entity_tags(
            entity_type="creator",
            entity_id=current_creator_id,
            platform=creator_platform,
        )
        post_tags = []
        for post in creator_posts:
            post_tags.extend(
                await repository.list_entity_tags(
                    entity_type="post",
                    entity_id=post["platform_post_id"],
                    platform=creator_platform,
                )
            )
        profile = aggregate_creator_profile(
            platform=creator_platform,
            creator_id=current_creator_id,
            posts=creator_posts,
            entity_tags=tags + post_tags,
            base_profile=_merge_profile_seed(
                existing_profile,
                _base_profile_from_posts(current_creator_id, creator_posts),
            ),
        )
        existing_summary = dict((existing_profile or {}).get("tag_summary_json") or {})
        profile["tag_summary_json"] = {
            **existing_summary,
            **profile["tag_summary_json"],
            "analysis_version": analysis_version,
        }
        rebuilt.append(await repository.upsert_creator_profile(profile))
        if progress_callback:
            progress_callback(
                {
                    "status": "running",
                    "total": total,
                    "processed": len(rebuilt),
                    "rebuilt_count": len(rebuilt),
                    "current_creator_id": current_creator_id,
                    "platform": creator_platform,
                }
            )

    return {
        "job_id": job_id,
        "platform": platform,
        "creator_id": creator_id,
        "rebuilt_count": len(rebuilt),
        "profiles": rebuilt,
    }


async def extract_creator_candidates_from_discovery_job(
    repository,
    *,
    job_id: int,
    pool_name: str | None = None,
) -> dict[str, Any]:
    job = await repository.get_job(job_id)
    if job is None:
        raise ValueError(f"Discovery job not found: {job_id}")
    rebuilt = await rebuild_creator_profiles(repository, job_id=job_id)
    platforms = job.get("platforms") or None
    profiles = rebuilt["profiles"] or await repository.list_creator_profiles(platforms=platforms)
    scene_keywords = await repository.list_scene_pack_keywords(enabled_only=True)
    if not scene_keywords:
        scene_keywords = [
            {
                "scene_pack_id": None,
                "keyword": keyword,
                "keyword_type": "primary",
                "weight": 1.0,
                "reason": "来自实时发现任务关键词",
            }
            for keyword in job.get("keywords") or []
        ]
    candidates = []
    target_pool = pool_name or f"discovery-{job_id}"
    for profile in profiles:
        if platforms and profile["platform"] not in platforms:
            continue
        recent_posts = await repository.list_posts_by_creator(
            platform=profile["platform"],
            creator_id=profile["creator_id"],
            limit=30,
        )
        score = score_creator_against_scene_packs(
            creator_profile=profile,
            recent_posts=recent_posts,
            scene_keywords=scene_keywords,
        )
        if score["match_score"] <= 0:
            continue
        vertical_id = _candidate_vertical_id(score["primary_hits"] or score["secondary_hits"])
        evidence = {
            "job_id": job_id,
            "primary_hits": [_keyword_evidence(item) for item in score["primary_hits"]],
            "secondary_hits": [_keyword_evidence(item) for item in score["secondary_hits"]],
            "negative_hits": [_keyword_evidence(item) for item in score["negative_hits"]],
            "representative_posts": [
                {
                    "platform_post_id": post.get("platform_post_id"),
                    "title": post.get("title"),
                    "content": (post.get("content") or "")[:160],
                    "publish_time": post.get("publish_time"),
                    "engagement": post.get("engagement_json") or {},
                }
                for post in recent_posts[:5]
            ],
        }
        candidate = await repository.upsert_creator_candidate(
            {
                "platform": profile["platform"],
                "creator_id": profile["creator_id"],
                "pool_name": target_pool,
                "vertical_id": vertical_id,
                "match_score": score["match_score"],
                "matched_tags_json": evidence["primary_hits"] + evidence["secondary_hits"],
                "evidence_json": evidence,
                "notes": "实时发现采集后自动抽取",
            }
        )
        candidates.append(_candidate_with_profile(candidate, profile))
    return {
        "job_id": job_id,
        "pool_name": target_pool,
        "rebuilt_profiles": rebuilt["rebuilt_count"],
        "candidate_count": len(candidates),
        "candidates": sorted(candidates, key=lambda item: item["match_score"], reverse=True),
    }


def export_creator_candidates_csv(candidates: list[dict[str, Any]]) -> str:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "platform",
            "display_name",
            "creator_id",
            "profile_url",
            "pool_name",
            "vertical_id",
            "match_score",
            "notes",
        ],
    )
    writer.writeheader()
    for item in candidates:
        writer.writerow(
            {
                "platform": item.get("platform"),
                "display_name": item.get("display_name"),
                "creator_id": item.get("creator_id"),
                "profile_url": item.get("profile_url"),
                "pool_name": item.get("pool_name"),
                "vertical_id": item.get("vertical_id"),
                "match_score": item.get("match_score"),
                "notes": item.get("notes"),
            }
        )
    return buffer.getvalue()


def _single_platform(platforms: list[str] | None) -> str | None:
    if not platforms or len(platforms) != 1:
        return None
    return platforms[0]


def _query_terms(raw_query: str) -> list[str]:
    terms: list[str] = []
    for token in re.split(r"[\s,，、+＋;；/|]+", raw_query.lower()):
        token = token.strip()
        if not token:
            continue
        if len(token) >= 2:
            terms.append(token)
        terms.extend(re.findall(r"[a-z0-9]{2,}", token))
    seen = set()
    unique_terms = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    return unique_terms


def _query_terms_not_covered_by_tags(
    query_terms: list[str],
    tag_definitions: list[dict[str, Any]],
    tag_ids: list[int],
) -> list[str]:
    if not query_terms or not tag_ids:
        return query_terms
    covered_terms: set[str] = set()
    wanted = {int(tag_id) for tag_id in tag_ids}
    for tag in tag_definitions:
        if int(tag.get("id") or 0) not in wanted:
            continue
        for value in [
            tag.get("tag_name"),
            *(tag.get("keywords") or []),
            *(tag.get("synonyms") or []),
        ]:
            normalized = str(value or "").lower().strip()
            if normalized:
                covered_terms.add(normalized)
                covered_terms.update(re.findall(r"[a-z0-9]{2,}", normalized))
    remaining = []
    for term in query_terms:
        if any(covered and (covered in term or term in covered) for covered in covered_terms):
            continue
        remaining.append(term)
    return remaining


def _score_creator_text_fallback(
    *,
    profile: dict[str, Any],
    posts: list[dict[str, Any]],
    query_terms: list[str],
) -> dict[str, Any]:
    if not query_terms:
        return {"score": 0.0, "matched_terms": [], "evidence": []}
    profile_text = _profile_search_text(profile)
    matched_terms = {
        term for term in query_terms if term and term in profile_text
    }
    evidence = []
    for post in posts:
        post_text = _post_search_text(post)
        post_terms = [term for term in query_terms if term and term in post_text]
        if not post_terms:
            continue
        matched_terms.update(post_terms)
        evidence.append(
            {
                "platform_post_id": post.get("platform_post_id"),
                "title": post.get("title"),
                "content": (post.get("content") or "")[:160],
                "publish_time": post.get("publish_time"),
                "matched_terms": post_terms,
                "engagement": post.get("engagement_json") or {},
            }
        )
    if not matched_terms:
        return {"score": 0.0, "matched_terms": [], "evidence": []}
    coverage = len(matched_terms) / max(1, len(query_terms))
    activity = min(1.0, len(evidence) / 5)
    engagement = min(1.0, sum(_engagement_total(post) for post in posts) / 500)
    score = coverage * 65 + activity * 20 + engagement * 15
    return {
        "score": round(min(100.0, score), 4),
        "matched_terms": sorted(matched_terms),
        "evidence": evidence[:5],
    }


def _profile_search_text(profile: dict[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in [
            profile.get("display_name"),
            profile.get("creator_id"),
            profile.get("bio"),
        ]
    ).lower()


def _profile_metric(profile: dict[str, Any], key: str) -> Any:
    metrics = (profile.get("tag_summary_json") or {}).get("profile_metrics") or {}
    return metrics.get(key)


def _post_search_text(post: dict[str, Any]) -> str:
    engagement = post.get("engagement_json") or {}
    return " ".join(
        str(value or "")
        for value in [
            post.get("title"),
            post.get("content"),
            engagement.get("source_keyword"),
            engagement.get("nickname"),
            engagement.get("desc"),
        ]
    ).lower()


def _base_profile_from_posts(creator_id: str, posts: list[dict[str, Any]]) -> dict[str, Any]:
    base_profile: dict[str, Any] = {"display_name": creator_id}
    for post in posts:
        engagement = post.get("engagement_json") or {}
        display_name = (
            engagement.get("nickname")
            or engagement.get("user_nickname")
            or engagement.get("author_name")
            or engagement.get("screen_name")
        )
        if _has_public_value(display_name):
            base_profile["display_name"] = str(display_name)
            break
    for post in posts:
        profile_url = _profile_url_from_post(post)
        if profile_url:
            base_profile["profile_url"] = profile_url
            break
    for post in posts:
        engagement = post.get("engagement_json") or {}
        follower_count = (
            engagement.get("follower_count")
            or engagement.get("followers_count")
            or engagement.get("fans")
        )
        if follower_count is not None:
            base_profile["follower_count"] = _to_int(follower_count)
            break
    return base_profile


def _candidate_with_profile(
    candidate: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    return {
        **candidate,
        "display_name": profile.get("display_name"),
        "profile_url": profile.get("profile_url"),
        "follower_count": profile.get("follower_count"),
        "recent_post_count_30d": profile.get("recent_post_count_30d") or 0,
        "avg_engagement_rate": profile.get("avg_engagement_rate"),
        "hot_post_rate": profile.get("hot_post_rate"),
    }


def _merge_profile_seed(
    existing_profile: dict[str, Any] | None,
    derived_profile: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing_profile or {})
    for key, value in derived_profile.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _profile_url_from_post(post: dict[str, Any]) -> str | None:
    engagement = post.get("engagement_json") or {}
    explicit_url = (
        engagement.get("profile_url")
        or engagement.get("user_url")
        or engagement.get("author_url")
    )
    if _has_public_value(explicit_url):
        return str(explicit_url)

    platform = post.get("platform")
    author_id = engagement.get("author_id") or engagement.get("user_id")
    if not _has_public_value(author_id):
        return None
    author_id = str(author_id)
    if platform == "xhs":
        return f"https://www.xiaohongshu.com/user/profile/{author_id}"
    if platform == "dy":
        sec_uid = engagement.get("sec_uid")
        if _has_public_value(sec_uid):
            return f"https://www.douyin.com/user/{sec_uid}"
    return None


def _has_public_value(value: Any) -> bool:
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"none", "null", "undefined"}


def _creator_search_guidance(
    *,
    profile_count: int,
    result_count: int,
    matched_tag_count: int,
    fallback_used: bool,
) -> str:
    if result_count:
        if fallback_used and not matched_tag_count:
            return "已使用本地内容文本匹配返回结果；初始化标签并运行打标后，匹配分会更稳定。"
        return "已基于本地达人画像和标签证据返回结果。"
    if not profile_count:
        return "本地还没有达人画像；请先完成关键词采集，或开启实时发现后等待完成并刷新。"
    if not matched_tag_count and not fallback_used:
        return "查询词没有命中标签或本地内容；请换关键词，或先在词库中加入对应标签。"
    return "已有达人画像，但当前筛选条件过窄；请放宽平台、粉丝或活跃度条件。"


def _tag_query_score(query: str, tag: dict[str, Any]) -> int:
    score = 0
    lowered = query.lower()
    tag_name = str(tag.get("tag_name") or "").lower()
    if tag_name and tag_name in lowered:
        score += 2
    for term in [*(tag.get("keywords") or []), *(tag.get("synonyms") or [])]:
        if term and str(term).lower() in lowered:
            score += 1
    for term in tag.get("negative_keywords") or []:
        if term and str(term).lower() in lowered:
            score = 0
    return score


def _tag_by_id(tag_definitions: list[dict[str, Any]], tag_id: int) -> dict[str, Any]:
    for tag in tag_definitions:
        if int(tag["id"]) == tag_id:
            return tag
    return {}


def _high_engagement_component(entity_tags: list[dict[str, Any]]) -> float:
    evidence_hits = 0
    for tag in entity_tags:
        evidence = tag.get("evidence_json") or {}
        if evidence.get("high_engagement") or evidence.get("post_engagement"):
            evidence_hits += 1
    return min(1.0, evidence_hits / max(1, len(entity_tags)))


def _profile_tag_component(creator_profile: dict[str, Any], tag_ids: set[int]) -> float:
    summary = creator_profile.get("tag_summary_json") or {}
    if not tag_ids:
        return 1.0
    matched = sum(1 for tag_id in tag_ids if str(tag_id) in summary)
    return matched / len(tag_ids)


def _passes_profile_filters(profile: dict[str, Any], request: dict[str, Any]) -> bool:
    follower_count = profile.get("follower_count")
    if request.get("follower_min") is not None and follower_count is not None:
        if follower_count < int(request["follower_min"]):
            return False
    if request.get("follower_max") is not None and follower_count is not None:
        if follower_count > int(request["follower_max"]):
            return False
    if request.get("recent_activity_min") is not None:
        if int(profile.get("recent_post_count_30d") or 0) < int(request["recent_activity_min"]):
            return False
    if request.get("engagement_rate_min") is not None:
        if float(profile.get("avg_engagement_rate") or 0) < float(request["engagement_rate_min"]):
            return False
    return True


def _avg_engagement_rate(posts: list[dict[str, Any]], follower_count: int | None) -> float | None:
    return avg_engagement_rate_from_posts(posts, follower_count)


def _hot_post_rate(posts: list[dict[str, Any]]) -> float | None:
    return hot_post_rate_from_posts(posts)


def _engagement_total(post: dict[str, Any]) -> int:
    return engagement_total_from_post(post)


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _keyword_evidence(keyword: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": keyword.get("keyword"),
        "keyword_type": keyword.get("keyword_type"),
        "scene_pack_id": keyword.get("scene_pack_id"),
        "weight": keyword.get("weight"),
        "reason": keyword.get("reason"),
    }


def _candidate_vertical_id(keywords: list[dict[str, Any]]) -> int | None:
    for keyword in keywords:
        scene_pack_id = keyword.get("scene_pack_id")
        if scene_pack_id is not None:
            return None
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

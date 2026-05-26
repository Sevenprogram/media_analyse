from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import json
import inspect
from typing import Any

import config
from research.creator_metrics import (
    avg_engagement_rate_from_posts,
    engagement_total_from_mapping,
    hot_post_rate_from_posts,
)
from media_platform.justoneapi.client import JustOneAPIClient, resolve_justone_api_key
from media_platform.tikhub.client import TikHubClient, resolve_tikhub_api_key
from media_platform.tikhub.mappers import get_mapper
from media_platform.tikhub.mappers.base import author, nested, pick


REALTIME_PLATFORMS = ("xhs", "dy")
TIKHUB_REALTIME_SOURCE = "tikhub_realtime"
JUSTONE_XHS_REALTIME_SOURCE = "justoneapi_xhs_realtime"
REALTIME_SOURCE = TIKHUB_REALTIME_SOURCE
JUSTONE_XHS_SEARCH_PATH = "/api/xiaohongshu-pgy/api/solar/cooperator/blogger/v2/v1"
JUSTONE_XHS_NOTES_RATE_PATH = "/api/xiaohongshu-pgy/api/solar/kol/dataV3/notesRate/v1"
JUSTONE_XHS_MAX_SEARCH_PAGES = 2
EXPANDED_SEARCH_MAX_PAGES = 5
USER_SEARCH_ENDPOINTS = {
    "xhs": {
        "method": "GET",
        "path": "/api/v1/xiaohongshu/app_v2/search_users",
        "json_body": False,
        "default_params": {"source": "explore_feed"},
        "page_param": "page",
        "cursor_param": "search_id",
        "cursor_initial": "",
        "max_pages": 2,
    },
    "dy": {
        "method": "POST",
        "path": "/api/v1/douyin/search/fetch_user_search_v2",
        "json_body": True,
        "default_params": {},
        "page_param": "",
        "cursor_param": "cursor",
        "cursor_initial": 0,
        "max_pages": 2,
    },
}
CREATOR_POST_ENDPOINTS = {
    "xhs": {
        "method": "GET",
        "path": "/api/v1/xiaohongshu/app_v2/get_user_posted_notes",
        "creator_param": "user_id",
        "cursor_param": "cursor",
    },
    "dy": {
        "method": "GET",
        "path": "/api/v1/douyin/web/fetch_user_post_videos",
        "creator_param": "sec_user_id",
        "cursor_param": "max_cursor",
    },
}
CREATOR_POST_ENRICHMENT_LIMIT = 30
CREATOR_POST_EXPANDED_ENRICHMENT_LIMIT = 120
CREATOR_POST_MAX_PAGES = 5


async def discover_realtime_creators(
    repository,
    request: dict[str, Any],
    *,
    client_factory: Callable[[], Any] = TikHubClient,
    justone_client_factory: Callable[[], Any] = JustOneAPIClient,
) -> dict[str, Any]:
    requested_platforms = [str(platform) for platform in request.get("platforms") or []]
    platforms = [
        platform
        for platform in (requested_platforms or list(REALTIME_PLATFORMS))
        if platform in REALTIME_PLATFORMS
    ]
    unsupported = [platform for platform in requested_platforms if platform not in REALTIME_PLATFORMS]
    keywords = _keywords_from_request(request)
    limit = _request_limit(request)
    diagnostics = _diagnostics(
        enabled=True,
        platforms=platforms,
        unsupported_platforms=unsupported,
        limit=limit,
    )
    if not platforms or not keywords:
        diagnostics["status"] = "skipped"
        return {"results": [], "diagnostics": diagnostics}

    initial_candidate_window = _candidate_window(limit)
    expanded_candidate_window = _expanded_candidate_window(limit)
    diagnostics.update(
        {
            "target_count": limit,
            "initial_candidate_window": initial_candidate_window,
            "expanded_candidate_window": expanded_candidate_window,
            "strict_matched_creators": 0,
            "expanded_strict_matched_creators": 0,
            "relaxed_matched_creators": 0,
            "completion_strategy": "strict",
            "relaxations": [],
        }
    )

    creators = await _collect_realtime_candidate_map(
        platforms=platforms,
        keywords=keywords,
        request=request,
        target_count=initial_candidate_window,
        diagnostics=diagnostics,
        client_factory=client_factory,
        justone_client_factory=justone_client_factory,
    )
    strict_selection = _select_realtime_creators(
        creators.values(),
        request=request,
        keywords=keywords,
        limit=limit,
        candidate_window=initial_candidate_window,
        allow_soft_relaxation=False,
    )
    strict_creators = strict_selection["eligible"]
    diagnostics["strict_matched_creators"] = len(strict_creators)
    selected_creators = strict_selection["selected"]

    if len(selected_creators) < limit and expanded_candidate_window > initial_candidate_window:
        diagnostics["completion_strategy"] = "expanded_strict"
        diagnostics["relaxations"].append("expanded_candidate_pool")
        expanded_creators = await _collect_realtime_candidate_map(
            platforms=platforms,
            keywords=keywords,
            request=request,
            target_count=expanded_candidate_window,
            diagnostics=diagnostics,
            client_factory=client_factory,
            justone_client_factory=justone_client_factory,
            max_search_pages=EXPANDED_SEARCH_MAX_PAGES,
        )
        for key, creator in expanded_creators.items():
            creators[key] = _merge_realtime_creator(creators.get(key), creator)
        expanded_strict_selection = _select_realtime_creators(
            creators.values(),
            request=request,
            keywords=keywords,
            limit=limit,
            candidate_window=expanded_candidate_window,
            allow_soft_relaxation=False,
        )
        strict_creators = expanded_strict_selection["eligible"]
        diagnostics["expanded_strict_matched_creators"] = len(strict_creators)
        selected_creators = expanded_strict_selection["selected"]
    else:
        diagnostics["expanded_strict_matched_creators"] = len(strict_creators)

    if len(selected_creators) < limit:
        relaxed_selection = _select_realtime_creators(
            creators.values(),
            request=request,
            keywords=keywords,
            limit=expanded_candidate_window,
            candidate_window=expanded_candidate_window,
            allow_soft_relaxation=True,
        )
        strict_keys = {_realtime_creator_key(creator) for creator in strict_creators}
        relaxed_creators = [
            creator
            for creator in relaxed_selection["eligible"]
            if _realtime_creator_key(creator) not in strict_keys
        ]
        if relaxed_creators:
            diagnostics["completion_strategy"] = "soft_relaxed"
            diagnostics["relaxed_matched_creators"] = len(relaxed_creators)
            selected_creators = [
                *strict_creators[:limit],
                *relaxed_creators[: max(0, limit - len(strict_creators))],
            ][:limit]

    selected_relaxations = sorted(
        {
            relaxation
            for creator in selected_creators
            for relaxation in (creator.get("filter_relaxations") or [])
        }
    )
    diagnostics["relaxations"] = sorted(set(diagnostics["relaxations"]) | set(selected_relaxations))
    diagnostics["matched_creators"] = len(strict_creators) + int(diagnostics["relaxed_matched_creators"] or 0)
    diagnostics["persisted_creators"] = len(selected_creators)

    results = []
    for creator in selected_creators:
        profile = await repository.upsert_creator_profile(_profile_payload(creator))
        candidate = await repository.upsert_creator_candidate(_candidate_payload(creator, request))
        diagnostics["created_profiles"] += 1 if profile else 0
        diagnostics["created_candidates"] += 1 if candidate else 0
        results.append(_result_payload(creator))

    diagnostics["status"] = _status(diagnostics["failed_platforms"], results)
    return {"results": results, "diagnostics": diagnostics}


async def probe_realtime_platforms(
    *,
    raw_query: str,
    platforms: list[str] | None = None,
    client_factory: Callable[[], Any] = TikHubClient,
    justone_client_factory: Callable[[], Any] = JustOneAPIClient,
) -> dict[str, Any]:
    requested_platforms = [str(platform) for platform in platforms or []]
    selected_platforms = [
        platform
        for platform in (requested_platforms or list(REALTIME_PLATFORMS))
        if platform in REALTIME_PLATFORMS
    ]
    unsupported = [
        platform for platform in requested_platforms if platform not in REALTIME_PLATFORMS
    ]
    keywords = _keywords_from_request({"raw_query": raw_query})
    keyword = keywords[0] if keywords else ""
    diagnostics = {
        "status": "skipped",
        "query": raw_query,
        "keyword": keyword,
        "platforms": selected_platforms,
        "unsupported_platforms": unsupported,
        "results": [],
    }
    if not selected_platforms or not keyword:
        return diagnostics

    for platform in selected_platforms:
        if platform == "xhs":
            if not _justone_enabled():
                diagnostics["results"].append(
                    _probe_platform_result(platform, False, 0, None, "ENABLE_JUSTONE_API is disabled")
                )
                continue
            if not resolve_justone_api_key():
                diagnostics["results"].append(
                    _probe_platform_result(platform, False, 0, None, "JUSTONE_API_KEY is not configured")
                )
                continue
            client = justone_client_factory()
            try:
                items = await _collect_justone_xhs_search_items(
                    client,
                    keyword=keyword,
                    target_count=1,
                    request={},
                )
                sample = _probe_sample_justone_xhs_creator(items[0], keyword) if items else None
                diagnostics["results"].append(
                    _probe_platform_result(platform, True, len(items), sample, None)
                )
            except Exception as exc:
                diagnostics["results"].append(
                    _probe_platform_result(platform, False, 0, None, str(exc))
                )
            finally:
                await _close_client(client)
            continue

        if not _tikhub_enabled():
            diagnostics["results"].append(
                _probe_platform_result(platform, False, 0, None, "ENABLE_TIKHUB is disabled")
            )
            continue
        if not resolve_tikhub_api_key():
            diagnostics["results"].append(
                _probe_platform_result(platform, False, 0, None, "TIKHUB_API_KEY is not configured")
            )
            continue
        client = client_factory()
        try:
            try:
                items = await _collect_user_search_items(
                    client,
                    platform=platform,
                    keyword=keyword,
                    target_count=1,
                )
                sample = _probe_sample_creator(platform, items[0], keyword) if items else None
                diagnostics["results"].append(
                    _probe_platform_result(platform, True, len(items), sample, None)
                )
            except Exception as exc:
                diagnostics["results"].append(
                    _probe_platform_result(platform, False, 0, None, str(exc))
                )
        finally:
            await _close_client(client)

    failures = [item for item in diagnostics["results"] if not item["ok"]]
    if not failures:
        diagnostics["status"] = "ok"
    elif len(failures) == len(diagnostics["results"]):
        diagnostics["status"] = "failed"
    else:
        diagnostics["status"] = "partial"
    return diagnostics


async def _call_search(client: Any, endpoint: Any, keyword: str) -> Any:
    payload = {**endpoint.default_params, endpoint.keyword_param: keyword}
    if endpoint.page_param and endpoint.page_param not in payload:
        payload[endpoint.page_param] = 1
    if endpoint.json_body:
        return await client.request(endpoint.method, endpoint.path, json=payload)
    return await client.request(endpoint.method, endpoint.path, params=payload)


async def _collect_realtime_candidate_map(
    *,
    platforms: list[str],
    keywords: list[str],
    request: dict[str, Any],
    target_count: int,
    diagnostics: dict[str, Any],
    client_factory: Callable[[], Any],
    justone_client_factory: Callable[[], Any],
    max_search_pages: int | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    creators: dict[tuple[str, str], dict[str, Any]] = {}
    if "xhs" in platforms:
        if not _justone_enabled():
            _mark_platform_failure(diagnostics, "xhs", "ENABLE_JUSTONE_API is disabled")
        elif not resolve_justone_api_key():
            _mark_platform_failure(diagnostics, "xhs", "JUSTONE_API_KEY is not configured")
        else:
            client = justone_client_factory()
            try:
                for creator in await _collect_justone_xhs_creators(
                    client,
                    request=request,
                    keywords=keywords,
                    target_count=target_count,
                    diagnostics=diagnostics,
                    max_search_pages=max_search_pages,
                ):
                    key = _realtime_creator_key(creator)
                    creators[key] = _merge_realtime_creator(creators.get(key), creator)
            except Exception as exc:
                _mark_platform_failure(diagnostics, "xhs", str(exc))
            finally:
                await _close_client(client)

    tikhub_platforms = [platform for platform in platforms if platform == "dy"]
    if tikhub_platforms:
        if not _tikhub_enabled():
            for platform in tikhub_platforms:
                _mark_platform_failure(diagnostics, platform, "ENABLE_TIKHUB is disabled")
        elif not resolve_tikhub_api_key():
            for platform in tikhub_platforms:
                _mark_platform_failure(diagnostics, platform, "TIKHUB_API_KEY is not configured")
        else:
            client = client_factory()
            try:
                for creator in await _collect_tikhub_creators(
                    client,
                    platforms=tikhub_platforms,
                    keywords=keywords,
                    target_count=target_count,
                    diagnostics=diagnostics,
                    max_search_pages=max_search_pages,
                ):
                    key = _realtime_creator_key(creator)
                    creators[key] = _merge_realtime_creator(creators.get(key), creator)
            finally:
                await _close_client(client)
    return creators


async def _collect_user_search_items(
    client: Any,
    *,
    platform: str,
    keyword: str,
    target_count: int,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    spec = USER_SEARCH_ENDPOINTS[platform]
    page = 1
    cursor = spec.get("cursor_initial", "")
    items: list[dict[str, Any]] = []
    page_limit = max_pages if max_pages is not None else int(spec["max_pages"])
    while page <= int(page_limit) and len(items) < target_count:
        payload = await _call_user_search(
            client,
            platform=platform,
            keyword=keyword,
            page=page,
            cursor=cursor,
        )
        page_items = _extract_items(payload)
        if not page_items:
            break
        items.extend(page_items)
        cursor = _next_search_cursor(payload)
        next_page = _next_search_page(platform, payload, page=page, cursor=cursor)
        if next_page is None:
            break
        page = next_page
    return items


async def _call_user_search(
    client: Any,
    *,
    platform: str,
    keyword: str,
    page: int,
    cursor: Any,
) -> Any:
    spec = USER_SEARCH_ENDPOINTS[platform]
    payload = {**spec.get("default_params", {}), "keyword": keyword}
    page_param = str(spec.get("page_param") or "")
    cursor_param = str(spec.get("cursor_param") or "")
    if page_param:
        payload[page_param] = page
    if cursor_param:
        payload[cursor_param] = _to_int(cursor) if platform == "dy" else str(cursor or "")
    if spec["json_body"]:
        return await client.request(spec["method"], spec["path"], json=payload)
    return await client.request(spec["method"], spec["path"], params=payload)


async def _collect_tikhub_creators(
    client: Any,
    *,
    platforms: list[str],
    keywords: list[str],
    target_count: int,
    diagnostics: dict[str, Any],
    max_search_pages: int | None = None,
) -> list[dict[str, Any]]:
    creators: dict[tuple[str, str], dict[str, Any]] = {}
    for platform in platforms:
        try:
            for keyword in keywords:
                for item in await _collect_user_search_items(
                    client,
                    platform=platform,
                    keyword=keyword,
                    target_count=target_count,
                    max_pages=max_search_pages,
                ):
                    normalized = _creator_from_user_search(platform, item, keyword)
                    if not normalized:
                        diagnostics["malformed_items"] += 1
                        continue
                    normalized["source"] = TIKHUB_REALTIME_SOURCE
                    key = (normalized["platform"], normalized["creator_id"])
                    creators[key] = _merge_realtime_creator(creators.get(key), normalized)
        except Exception as exc:
            _mark_platform_failure(diagnostics, platform, str(exc))

    shortlisted = sorted(
        creators.values(),
        key=lambda item: _score_creator(item, keywords),
        reverse=True,
    )[:target_count]
    for creator in shortlisted:
        try:
            await _enrich_creator_from_posts(client, creator)
        except Exception:
            diagnostics["failed_enrichments"] += 1
            continue
    return shortlisted


async def _collect_justone_xhs_creators(
    client: Any,
    *,
    request: dict[str, Any],
    keywords: list[str],
    target_count: int,
    diagnostics: dict[str, Any],
    max_search_pages: int | None = None,
) -> list[dict[str, Any]]:
    creators: dict[tuple[str, str], dict[str, Any]] = {}
    for keyword in keywords:
        for item in await _collect_justone_xhs_search_items(
            client,
            keyword=keyword,
            target_count=target_count,
            request=request,
            max_pages=max_search_pages,
        ):
            normalized = _creator_from_justone_xhs_search(item, keyword)
            if not normalized:
                diagnostics["malformed_items"] += 1
                continue
            key = (normalized["platform"], normalized["creator_id"])
            creators[key] = _merge_realtime_creator(creators.get(key), normalized)

    shortlisted = sorted(
        creators.values(),
        key=lambda item: _score_creator(item, keywords),
        reverse=True,
    )[:target_count]
    for creator in shortlisted:
        await _enrich_justone_xhs_creator(client, creator, diagnostics)
    return shortlisted


async def _collect_justone_xhs_search_items(
    client: Any,
    *,
    keyword: str,
    target_count: int,
    request: dict[str, Any],
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    page_limit = max_pages if max_pages is not None else JUSTONE_XHS_MAX_SEARCH_PAGES
    while page <= int(page_limit) and len(items) < target_count:
        payload = await client.request(
            "GET",
            JUSTONE_XHS_SEARCH_PATH,
            params=_justone_xhs_search_params(keyword, page=page, request=request),
        )
        page_items = _extract_justone_xhs_creator_items(payload)
        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) == 0 or len(items) >= target_count:
            break
        page += 1
    return items[:target_count]


def _justone_xhs_search_params(keyword: str, *, page: int, request: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {
        "searchType": "NOTE",
        "keyword": keyword,
        "page": page,
    }
    if request.get("follower_min") is not None:
        params["fansNumberLower"] = int(request["follower_min"])
    if request.get("follower_max") is not None:
        params["fansNumberUpper"] = int(request["follower_max"])
    return params


def _extract_justone_xhs_creator_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for path in (
        ("bloggers",),
        ("bloggerList",),
        ("kols",),
        ("kolList",),
        ("authorList",),
        ("userList",),
        ("items",),
        ("records",),
        ("list",),
        ("data", "bloggers"),
        ("data", "bloggerList"),
        ("data", "kols"),
        ("data", "kolList"),
        ("data", "items"),
        ("data", "records"),
        ("data", "list"),
    ):
        value = _value_at_path(payload, path)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return _extract_items(payload)


def _value_at_path(payload: Any, path: tuple[str, ...]) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _creator_from_justone_xhs_search(item: dict[str, Any], keyword: str) -> dict[str, Any] | None:
    raw_user = _justone_xhs_user_payload(item)
    creator_id = str(
        pick(
            raw_user,
            "userId",
            "user_id",
            "bloggerUserId",
            "blogger_user_id",
            "redId",
            "red_id",
            "id",
            default="",
        )
    ).strip()
    kol_id = str(pick(raw_user, "kolId", "kol_id", "bloggerId", "blogger_id", default="")).strip()
    if not creator_id:
        creator_id = kol_id
    if not creator_id:
        return None

    follower_count = _to_int_or_none(
        pick(
            raw_user,
            "fansNumber",
            "fansNum",
            "fansCount",
            "fans",
            "followerCount",
            "followersCount",
            "follower_count",
            default=_deep_pick(raw_user, "fansNumber", "fansNum", "fansCount", "followerCount"),
        )
    )
    display_name = str(
        pick(
            raw_user,
            "nickName",
            "nickname",
            "name",
            "userName",
            "bloggerName",
            "kolName",
            default=creator_id,
        )
    )
    bio = str(pick(raw_user, "desc", "description", "signature", "brief", "bio", default=""))
    return {
        "platform": "xhs",
        "creator_id": creator_id,
        "display_name": display_name,
        "profile_url": _profile_url("xhs", creator_id),
        "bio": bio,
        "follower_count": follower_count,
        "following_count": _to_int_or_none(pick(raw_user, "followingCount", "following_count", default=None)),
        "post_count": _to_int_or_none(pick(raw_user, "noteNumber", "noteCount", "notesCount", default=None)),
        "avg_engagement_rate": None,
        "hot_post_rate": None,
        "recent_post_count_30d": 0,
        "matched_keywords": [keyword],
        "representative_posts": [],
        "engagement_total": 0,
        "raw_item": item,
        "justone_kol_id": kol_id or None,
        "source": JUSTONE_XHS_REALTIME_SOURCE,
    }


def _justone_xhs_user_payload(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("blogger", "kol", "user", "author", "profile"):
        value = item.get(key)
        if isinstance(value, dict):
            return {**item, **value}
    return item


async def _enrich_justone_xhs_creator(
    client: Any,
    creator: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    user_id = str(creator.get("creator_id") or "").strip()
    if not user_id:
        return

    try:
        notes_rate = await client.request(
            "GET",
            JUSTONE_XHS_NOTES_RATE_PATH,
            params={
                "userId": user_id,
                "business": "DAILY_NOTE",
                "noteType": "PHOTO_TEXT_AND_VIDEO",
                "dateType": "DAY_30",
                "advertiseSwitch": "ALL",
            },
        )
        _merge_justone_xhs_notes_rate(creator, notes_rate)
    except Exception as exc:
        diagnostics["failed_enrichments"] += 1
        creator.setdefault("enrichment_errors", []).append(f"notesRate: {exc}")


def _merge_justone_xhs_notes_rate(creator: dict[str, Any], payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    note_number = _to_int_or_none(_deep_pick(payload, "noteNumber", "notesNumber", "noteCount"))
    notes = _extract_justone_xhs_notes(payload)
    representative_posts = _justone_xhs_representative_posts(notes)
    creator["recent_post_count_30d"] = note_number if note_number is not None else len(representative_posts)
    creator["post_count"] = max(int(creator.get("post_count") or 0), int(creator["recent_post_count_30d"] or 0))
    creator["representative_posts"] = representative_posts[:10]
    creator["engagement_total"] = sum(
        engagement_total_from_mapping(post.get("engagement")) for post in representative_posts
    )

    interaction_rate = _percent_to_ratio(_deep_pick(payload, "interactionRate", "engagementRate"))
    if interaction_rate is not None:
        creator["avg_engagement_rate"] = interaction_rate
    hot_rate = _percent_to_ratio(
        _deep_pick(payload, "thousandLikePercent", "hundredLikePercent", "viralRate", "hotPostRate")
    )
    if hot_rate is not None:
        creator["hot_post_rate"] = hot_rate


def _extract_justone_xhs_notes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for path in (("notes",), ("noteList",), ("items",), ("data", "notes"), ("data", "noteList")):
        value = _value_at_path(payload, path)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _justone_xhs_representative_posts(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    posts = []
    for note in notes:
        post_id = str(pick(note, "noteId", "note_id", "id", default="")).strip()
        title = str(pick(note, "title", "desc", "content", default="")).strip()
        like_count = _to_int(pick(note, "likeNum", "likeCount", "likedCount", default=0))
        collect_count = _to_int(pick(note, "collectNum", "collectCount", "collectedCount", default=0))
        comment_count = _to_int(pick(note, "commentNum", "commentCount", "commentsCount", default=0))
        share_count = _to_int(pick(note, "shareNum", "shareCount", "sharedCount", default=0))
        interaction_total = _to_int(pick(note, "interactionNum", "interactionCount", default=0))
        if interaction_total and not any((like_count, collect_count, comment_count, share_count)):
            like_count = interaction_total
        posts.append(
            {
                "platform": "xhs",
                "platform_post_id": post_id,
                "title": title,
                "content": title,
                "url": f"https://www.xiaohongshu.com/explore/{post_id}" if post_id else "",
                "publish_time": pick(note, "publishTime", "date", "time", default=None),
                "engagement": {
                    "liked_count": like_count,
                    "comment_count": comment_count,
                    "collected_count": collect_count,
                    "share_count": share_count,
                },
            }
        )
    return posts


def _probe_sample_justone_xhs_creator(item: dict[str, Any], keyword: str) -> dict[str, Any] | None:
    creator = _creator_from_justone_xhs_search(item, keyword)
    if not creator:
        return None
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "display_name": creator["display_name"],
        "profile_url": creator["profile_url"],
        "follower_count": creator["follower_count"],
    }


def _probe_platform_result(
    platform: str,
    ok: bool,
    item_count: int,
    sample_creator: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "platform": platform,
        "ok": ok,
        "item_count": item_count,
        "sample_creator": sample_creator,
        "error": error,
    }


def _keywords_from_request(request: dict[str, Any]) -> list[str]:
    raw = str(request.get("raw_query") or "").strip()
    if not raw:
        return []
    terms = [term.strip() for term in raw.replace("+", " ").replace(",", " ").split()]
    return [term for term in dict.fromkeys(terms) if term] or [raw]


def _request_limit(request: dict[str, Any]) -> int:
    try:
        limit = int(request.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    return max(1, min(200, limit))


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in (
        "items",
        "list",
        "users",
        "user_list",
        "business_data",
        "aweme_list",
        "notes",
        "videos",
        "data",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            items = _extract_items(value)
            if items:
                return items
    return []


def _creator_from_user_search(platform: str, item: dict[str, Any], keyword: str) -> dict[str, Any] | None:
    raw_user = _user_search_user(platform, item)
    creator_id = _creator_id(platform, raw_user)
    if not creator_id:
        return None

    follower_count = _follower_count(platform, raw_user)
    post_count = _post_count(raw_user)
    return {
        "platform": platform,
        "creator_id": creator_id,
        "display_name": _display_name(raw_user, creator_id),
        "profile_url": _profile_url(platform, creator_id),
        "bio": str(pick(raw_user, "desc", "description", "bio", "signature", default="")),
        "follower_count": follower_count,
        "following_count": _following_count(raw_user),
        "post_count": post_count,
        "recent_post_count_30d": 0,
        "avg_engagement_rate": None,
        "hot_post_rate": None,
        "matched_keywords": [keyword],
        "representative_posts": [],
        "engagement_total": 0,
        "raw_item": item,
    }


def _probe_sample_creator(platform: str, item: dict[str, Any], keyword: str) -> dict[str, Any] | None:
    creator = _creator_from_user_search(platform, item, keyword)
    if not creator:
        return None
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "display_name": creator["display_name"],
        "profile_url": creator["profile_url"],
        "follower_count": creator["follower_count"],
    }


def _user_search_user(platform: str, item: dict[str, Any]) -> dict[str, Any]:
    if platform == "xhs":
        return {
            "user_id": str(pick(item, "id", "user_id", "userId", "red_id", default="")).strip(),
            "nickname": str(pick(item, "name", "nickname", default="")).strip(),
            "desc": str(pick(item, "desc", "description", default="")).strip(),
            "image": str(pick(item, "image", "avatar", default="")).strip(),
            "followers_count": _xhs_follower_count_from_search(item),
        }
    user_info = _douyin_user_info(item)
    return {
        "sec_uid": str(
            pick(user_info, "sec_uid", "sec_user_id", "user_id", "uid", default="")
        ).strip(),
        "uid": str(pick(user_info, "uid", default="")).strip(),
        "nickname": str(pick(user_info, "nick_name", "nickname", "name", default="")).strip(),
        "signature": str(pick(user_info, "signature", "desc", "bio", default="")).strip(),
        "avatar": str(pick(user_info, "avatar_url", "avatar", default="")).strip(),
        "fans_cnt": _to_int_or_none(
            pick(user_info, "fans_cnt", "follower_count", "follower_count_str", default=None)
        ),
        "following_count": _to_int_or_none(
            pick(user_info, "favoriting_count", "following_count", default=None)
        ),
        "publish_cnt": _to_int_or_none(pick(user_info, "publish_cnt", "aweme_count", default=None)),
    }


def _raw_author(platform: str, item: dict[str, Any]) -> dict[str, Any]:
    if platform == "xhs" and isinstance(item.get("note"), dict):
        item = item["note"]
    if platform == "dy" and isinstance(item.get("aweme_info"), dict):
        item = item["aweme_info"]
    return author(item)


def _douyin_user_info(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data") if isinstance(item.get("data"), dict) else item
    raw_data = data.get("raw_data") if isinstance(data, dict) else None
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            raw_data = None
    if isinstance(raw_data, dict) and isinstance(raw_data.get("user_info"), dict):
        return raw_data["user_info"]
    if isinstance(data, dict) and isinstance(data.get("user_info"), dict):
        return data["user_info"]
    if isinstance(item.get("user_info"), dict):
        return item["user_info"]
    if isinstance(item.get("user"), dict):
        return item["user"]
    return item


def _mapped_author(platform: str, content: dict[str, Any]) -> dict[str, Any]:
    if platform == "xhs":
        return content.get("user") if isinstance(content.get("user"), dict) else {}
    return content.get("author") if isinstance(content.get("author"), dict) else {}


def _creator_id(platform: str, user: dict[str, Any]) -> str:
    if platform == "xhs":
        return str(pick(user, "user_id", "userId", "id", "userid", "red_id", default="")).strip()
    return str(
        pick(user, "sec_uid", "sec_user_id", "uid", "user_id", "id", default="")
    ).strip()


def _display_name(user: dict[str, Any], creator_id: str) -> str:
    return str(pick(user, "nickname", "nickName", "nick_name", "name", "unique_id", default=creator_id))


def _follower_count(platform: str, user: dict[str, Any]) -> int | None:
    if platform == "dy":
        value = pick(
            user,
            "fans",
            "fans_cnt",
            "followers_count",
            "follower_count",
            "max_follower_count",
            default=nested(user, "follow_info", "follower_count", default=None),
        )
    else:
        value = pick(
            user,
            "fans",
            "fans_cnt",
            "followers_count",
            "follower_count",
            default=pick(user, "sub_title", default=nested(user, "follow_info", "follower_count", default=None)),
        )
    return _to_int_or_none(value)


def _following_count(user: dict[str, Any]) -> int | None:
    return _to_int_or_none(
        pick(
            user,
            "follows",
            "following_count",
            "favoriting_count",
            default=nested(user, "follow_info", "following_count", default=None),
        )
    )


def _post_count(user: dict[str, Any]) -> int | None:
    return _to_int_or_none(
        pick(
            user,
            "notes_count",
            "note_count",
            "videos_count",
            "aweme_count",
            "publish_cnt",
            "posts_count",
            default=None,
        )
    )


def _representative_post(platform: str, content: dict[str, Any], keyword: str) -> dict[str, Any]:
    if platform == "xhs":
        post_id = str(pick(content, "note_id", "id", default=""))
        title = str(pick(content, "title", "desc", default=""))
        body = str(pick(content, "desc", "title", default=""))
        engagement = {
            "liked_count": _to_int(nested(content, "interact_info", "liked_count", default=0)),
            "comment_count": _to_int(nested(content, "interact_info", "comment_count", default=0)),
            "collected_count": _to_int(nested(content, "interact_info", "collected_count", default=0)),
            "share_count": _to_int(nested(content, "interact_info", "share_count", default=0)),
        }
        url = str(pick(content, "note_url", default=f"https://www.xiaohongshu.com/explore/{post_id}"))
    else:
        post_id = str(pick(content, "aweme_id", "id", default=""))
        title = str(pick(content, "desc", "title", default=""))
        body = title
        engagement = {
            "liked_count": _to_int(nested(content, "statistics", "digg_count", default=0)),
            "comment_count": _to_int(nested(content, "statistics", "comment_count", default=0)),
            "collected_count": _to_int(nested(content, "statistics", "collect_count", default=0)),
            "share_count": _to_int(nested(content, "statistics", "share_count", default=0)),
        }
        url = f"https://www.douyin.com/video/{post_id}" if post_id else ""
    return {
        "platform": platform,
        "platform_post_id": post_id,
        "title": title,
        "content": body,
        "url": url,
        "source_keyword": keyword,
        "engagement": engagement,
    }


async def _enrich_creator_from_posts(client: Any, creator: dict[str, Any]) -> None:
    endpoint = CREATOR_POST_ENDPOINTS[creator["platform"]]
    recent_posts: list[dict[str, Any]] = []
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
    cursor = ""
    page = 1
    while page <= CREATOR_POST_MAX_PAGES:
        payload = await client.request(
            endpoint["method"],
            endpoint["path"],
            params=_creator_post_params(
                creator["platform"],
                endpoint,
                creator["creator_id"],
                cursor=cursor,
                page=page,
            ),
        )
        items = _extract_items(payload)
        if not items:
            break

        stop_due_age = False
        for item in items:
            mapped = get_mapper(creator["platform"]).map_content(item, source_keyword="")
            if not isinstance(mapped, dict):
                continue
            timestamp = _publish_timestamp(creator["platform"], mapped)
            if timestamp is None:
                continue
            if timestamp < cutoff:
                stop_due_age = True
                break
            recent_posts.append(
                _representative_post(
                    creator["platform"],
                    mapped,
                    (creator.get("matched_keywords") or [""])[0],
                )
            )

        if stop_due_age:
            break

        cursor = _next_cursor(payload)
        if not cursor and items:
            cursor = _next_cursor(items[-1])
        if not cursor and not _has_more(payload):
            break
        page += 1

    creator["recent_post_count_30d"] = len(recent_posts)
    creator["representative_posts"] = recent_posts[:10]
    creator["engagement_total"] = sum(
        engagement_total_from_mapping(post.get("engagement")) for post in recent_posts
    )
    creator["avg_engagement_rate"] = avg_engagement_rate_from_posts(
        recent_posts,
        creator.get("follower_count"),
        engagement_fields=("engagement",),
    )
    creator["hot_post_rate"] = hot_post_rate_from_posts(
        recent_posts,
        engagement_fields=("engagement",),
    )


def _creator_post_params(
    platform: str,
    endpoint: Any,
    creator_id: str,
    *,
    cursor: str,
    page: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {endpoint["creator_param"]: creator_id}
    cursor_param = endpoint.get("cursor_param")
    if cursor_param:
        if platform == "dy":
            params[cursor_param] = _to_int(cursor)
        elif cursor:
            params[cursor_param] = cursor
    if platform == "dy" and "count" not in params:
        params["count"] = 20
    return params


def _publish_timestamp(platform: str, mapped: dict[str, Any]) -> int | None:
    raw_value = mapped.get("create_time") if platform == "dy" else mapped.get("time") or mapped.get("create_time")
    return _to_int_or_none(raw_value)


def _next_search_page(platform: str, payload: Any, *, page: int, cursor: str) -> int | None:
    if page >= int(USER_SEARCH_ENDPOINTS[platform]["max_pages"]):
        return None
    next_page = _to_int_or_none(payload.get("next_page") if isinstance(payload, dict) else None)
    if next_page and next_page > page:
        return next_page
    if platform == "xhs" and cursor:
        return page + 1
    if _has_more(payload) and cursor:
        return page + 1
    return None


def _next_search_cursor(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("search_id", "cursor", "next_cursor", "nextCursor", "max_cursor", "maxCursor"):
        value = data.get(key)
        if value not in (None, "", 0, "0"):
            return str(value)
    for value in data.values():
        if isinstance(value, dict):
            cursor = _next_search_cursor(value)
            if cursor:
                return cursor
    return ""


def _next_cursor(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in (
        "cursor",
        "next_cursor",
        "search_id",
        "lastCursor",
        "last_cursor",
        "max_id",
        "max_cursor",
        "maxCursor",
        "pcursor",
        "offset",
        "next",
    ):
        value = data.get(key)
        if value not in (None, "", 0, "0"):
            return str(value)
    for value in data.values():
        if isinstance(value, dict):
            cursor = _next_cursor(value)
            if cursor:
                return cursor
    return ""


def _has_more(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("has_more") or data.get("hasMore"):
        return True
    return any(_has_more(value) for value in data.values() if isinstance(value, dict))


def _realtime_creator_key(creator: dict[str, Any]) -> tuple[str, str]:
    return (str(creator.get("platform") or ""), str(creator.get("creator_id") or ""))


def _select_realtime_creators(
    creators: Any,
    *,
    request: dict[str, Any],
    keywords: list[str],
    limit: int,
    candidate_window: int,
    allow_soft_relaxation: bool,
) -> dict[str, list[dict[str, Any]]]:
    shortlisted = sorted(
        creators,
        key=lambda item: _score_creator(item, keywords),
        reverse=True,
    )[:candidate_window]

    eligible: list[dict[str, Any]] = []
    for creator in shortlisted:
        passes, relaxations = _filter_result(creator, request, allow_soft_relaxation=allow_soft_relaxation)
        if not passes:
            continue
        item = {**creator}
        item["filter_relaxations"] = relaxations
        item["quality_flags"] = _quality_flags(relaxations)
        score = _score_creator(item, keywords)
        if relaxations:
            score = max(0.0, score - _relaxation_penalty(relaxations))
        item["match_score"] = score
        eligible.append(item)

    eligible.sort(key=lambda item: item["match_score"], reverse=True)
    return {"eligible": eligible, "selected": eligible[:limit]}


def _filter_result(
    creator: dict[str, Any],
    request: dict[str, Any],
    *,
    allow_soft_relaxation: bool,
) -> tuple[bool, list[str]]:
    relaxations: list[str] = []
    follower_count = creator.get("follower_count")
    follower_min = request.get("follower_min")
    follower_max = request.get("follower_max")
    if follower_min is not None and (follower_count is None or int(follower_count) < int(follower_min)):
        return False, []
    if follower_max is not None and follower_count is not None and int(follower_count) > int(follower_max):
        return False, []

    recent_min = request.get("recent_activity_min")
    recent_count = int(creator.get("recent_post_count_30d") or 0)
    if recent_min is not None and recent_count < int(recent_min):
        if not allow_soft_relaxation or int(recent_min) > 1:
            return False, []
        relaxations.append("activity_pending_verification")

    engagement_min = request.get("engagement_rate_min")
    engagement_rate = creator.get("avg_engagement_rate")
    if engagement_min is not None:
        if engagement_rate in (None, ""):
            if not allow_soft_relaxation:
                return False, []
            relaxations.append("engagement_rate_missing")
        elif float(engagement_rate) < float(engagement_min):
            return False, []

    return True, sorted(set(relaxations))


def _quality_flags(relaxations: list[str]) -> list[str]:
    flags = []
    if "activity_pending_verification" in relaxations:
        flags.append("activity_pending_verification")
    if "engagement_rate_missing" in relaxations:
        flags.append("engagement_rate_missing")
    return flags


def _relaxation_penalty(relaxations: list[str]) -> float:
    penalty = 0.0
    if "activity_pending_verification" in relaxations:
        penalty += 8.0
    if "engagement_rate_missing" in relaxations:
        penalty += 6.0
    return penalty


def _dedupe_representative_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in posts:
        key = str(
            post.get("platform_post_id")
            or post.get("url")
            or f"{post.get('platform')}:{post.get('title')}:{post.get('content')}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(post)
    return deduped


def _merge_realtime_creator(
    existing: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    if existing is None:
        return current
    existing["matched_keywords"] = sorted(
        set(existing.get("matched_keywords") or []) | set(current.get("matched_keywords") or [])
    )
    existing["representative_posts"] = _dedupe_representative_posts(
        (existing.get("representative_posts") or []) + current.get("representative_posts", [])
    )
    existing["recent_post_count_30d"] = max(
        int(existing.get("recent_post_count_30d") or 0),
        int(current.get("recent_post_count_30d") or 0),
    )
    existing["engagement_total"] = int(existing.get("engagement_total") or 0) + int(
        current.get("engagement_total") or 0
    )
    for field in ("display_name", "profile_url", "bio", "follower_count", "following_count", "post_count"):
        if existing.get(field) in (None, "", 0) and current.get(field) not in (None, "", 0):
            existing[field] = current[field]
    existing["avg_engagement_rate"] = avg_engagement_rate_from_posts(
        existing.get("representative_posts") or [],
        existing.get("follower_count"),
        engagement_fields=("engagement",),
    )
    existing["hot_post_rate"] = hot_post_rate_from_posts(
        existing.get("representative_posts") or [],
        engagement_fields=("engagement",),
    )
    return existing


def _score_creator(creator: dict[str, Any], keywords: list[str]) -> float:
    text = " ".join(
        str(value or "")
        for value in [
            creator.get("display_name"),
            creator.get("bio"),
            *[
                f"{post.get('title') or ''} {post.get('content') or ''}"
                for post in creator.get("representative_posts") or []
            ],
        ]
    ).lower()
    matched = [keyword for keyword in keywords if keyword.lower() in text]
    keyword_score = 40.0 * (len(matched) / max(1, len(keywords)))
    engagement_score = min(25.0, int(creator.get("engagement_total") or 0) / 20)
    follower_score = min(20.0, int(creator.get("follower_count") or 0) / 500)
    activity_score = min(15.0, int(creator.get("recent_post_count_30d") or 0) * 3)
    return round(min(100.0, keyword_score + engagement_score + follower_score + activity_score), 4)


def _passes_request_filters(creator: dict[str, Any], request: dict[str, Any]) -> bool:
    return _filter_result(creator, request, allow_soft_relaxation=False)[0]


def _profile_payload(creator: dict[str, Any]) -> dict[str, Any]:
    source = _creator_source(creator)
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "display_name": creator.get("display_name"),
        "profile_url": creator.get("profile_url"),
        "bio": creator.get("bio"),
        "follower_count": creator.get("follower_count"),
        "following_count": creator.get("following_count"),
        "post_count": creator.get("post_count"),
        "avg_engagement_rate": creator.get("avg_engagement_rate"),
        "hot_post_rate": creator.get("hot_post_rate"),
        "recent_post_count_30d": creator.get("recent_post_count_30d") or 0,
        "latest_snapshot_at": datetime.now(timezone.utc),
        "tag_summary_json": {
            "source": source,
            "matched_keywords": creator.get("matched_keywords") or [],
            "filter_relaxations": creator.get("filter_relaxations") or [],
            "quality_flags": creator.get("quality_flags") or [],
        },
    }


def _candidate_payload(creator: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    evidence = _evidence_payload(creator)
    project_id = request.get("project_id")
    pool_name = f"project:{project_id}:realtime" if project_id else "realtime"
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "pool_name": pool_name,
        "vertical_id": request.get("selected_vertical_id"),
        "match_score": creator.get("match_score"),
        "matched_tags_json": _matched_tags(creator),
        "evidence_json": evidence,
        "notes": _candidate_note(creator),
    }


def _result_payload(creator: dict[str, Any]) -> dict[str, Any]:
    evidence = _evidence_payload(creator)
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "display_name": creator.get("display_name"),
        "profile_url": creator.get("profile_url"),
        "bio": creator.get("bio"),
        "follower_count": creator.get("follower_count"),
        "recent_post_count_30d": creator.get("recent_post_count_30d") or 0,
        "avg_engagement_rate": creator.get("avg_engagement_rate"),
        "hot_post_rate": creator.get("hot_post_rate"),
        "match_score": creator.get("match_score"),
        "matched_tags": _matched_tags(creator),
        "evidence": [evidence],
        "representative_posts": creator.get("representative_posts") or [],
        "filter_relaxations": creator.get("filter_relaxations") or [],
        "quality_flags": creator.get("quality_flags") or [],
        "source_type": "realtime",
        "source_labels": ["Realtime"],
        "realtime_unverified": True,
    }


def _matched_tags(creator: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"source": _creator_source(creator), "keyword": keyword}
        for keyword in creator.get("matched_keywords") or []
    ]


def _evidence_payload(creator: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": _creator_source(creator),
        "profile_metrics": {
            "follower_count": creator.get("follower_count"),
            "following_count": creator.get("following_count"),
            "post_count": creator.get("post_count"),
            "avg_engagement_rate": creator.get("avg_engagement_rate"),
            "hot_post_rate": creator.get("hot_post_rate"),
        },
        "matched_keywords": creator.get("matched_keywords") or [],
        "representative_posts": creator.get("representative_posts") or [],
        "recent_post_count_30d": creator.get("recent_post_count_30d") or 0,
        "filter_relaxations": creator.get("filter_relaxations") or [],
        "quality_flags": creator.get("quality_flags") or [],
    }


def _creator_source(creator: dict[str, Any]) -> str:
    return str(creator.get("source") or REALTIME_SOURCE)


def _candidate_note(creator: dict[str, Any]) -> str:
    if _creator_source(creator) == JUSTONE_XHS_REALTIME_SOURCE:
        return "Imported from JustOneAPI Xiaohongshu realtime creator discovery"
    return "Imported from TikHub realtime creator discovery"


def _profile_url(platform: str, creator_id: str) -> str:
    if platform == "xhs":
        return f"https://www.xiaohongshu.com/user/profile/{creator_id}"
    return f"https://www.douyin.com/user/{creator_id}"


def _candidate_window(limit: int) -> int:
    requested = max(10, int(limit or 10) * 2)
    return min(requested, CREATOR_POST_ENRICHMENT_LIMIT)


def _expanded_candidate_window(limit: int) -> int:
    requested = max(_candidate_window(limit), int(limit or 10) * 8)
    return min(requested, CREATOR_POST_EXPANDED_ENRICHMENT_LIMIT)


def _tikhub_enabled() -> bool:
    return bool(getattr(config, "ENABLE_TIKHUB", False))


def _justone_enabled() -> bool:
    return bool(getattr(config, "ENABLE_JUSTONE_API", False))


def _xhs_follower_count_from_search(item: dict[str, Any]) -> int | None:
    return _to_int_or_none(pick(item, "sub_title", "subtitle", "fans", default=None))


def _to_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return _to_int(value)


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    import re

    text = str(value).strip().replace(",", "").replace("粉丝", "").replace(" ", "")
    multiplier = 1
    lowered = text.lower()
    if "万" in text or lowered.endswith("w"):
        multiplier = 10000
        text = text.replace("万", "")
        if lowered.endswith("w"):
            text = text[:-1]
    elif lowered.endswith("m"):
        multiplier = 1000000
        text = text[:-1]
    elif lowered.endswith("k"):
        multiplier = 1000
        text = text[:-1]

    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 0
    return int(float(match.group(0)) * multiplier)


def _percent_to_ratio(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().replace("%", "")
    else:
        normalized = value
    try:
        number = float(normalized)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return round(number / 100, 6)


def _deep_pick(payload: Any, *keys: str) -> Any:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value
        for value in payload.values():
            found = _deep_pick(value, *keys)
            if found not in (None, ""):
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _deep_pick(item, *keys)
            if found not in (None, ""):
                return found
    return None


def _mark_platform_failure(diagnostics: dict[str, Any], platform: str, message: str) -> None:
    if platform not in diagnostics["failed_platforms"]:
        diagnostics["failed_platforms"].append(platform)
    diagnostics["error"] = message


def _status(failed_platforms: list[str], results: list[dict[str, Any]]) -> str:
    if failed_platforms and results:
        return "partial"
    if failed_platforms:
        return "failed"
    return "ok"


def _diagnostics(
    *,
    enabled: bool,
    platforms: list[str],
    unsupported_platforms: list[str],
    limit: int,
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "status": "ok",
        "platforms": platforms,
        "unsupported_platforms": unsupported_platforms,
        "limit": limit,
        "matched_creators": 0,
        "persisted_creators": 0,
        "created_profiles": 0,
        "created_candidates": 0,
        "malformed_items": 0,
        "failed_enrichments": 0,
        "failed_platforms": [],
        "error": None,
    }


async def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result

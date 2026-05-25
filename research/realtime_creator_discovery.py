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
from media_platform.tikhub.client import TikHubClient, resolve_tikhub_api_key
from media_platform.tikhub.mappers import get_mapper
from media_platform.tikhub.mappers.base import author, nested, pick


REALTIME_PLATFORMS = ("xhs", "dy")
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
REALTIME_SOURCE = "tikhub_realtime"
CREATOR_POST_ENRICHMENT_LIMIT = 30
CREATOR_POST_MAX_PAGES = 5


async def discover_realtime_creators(
    repository,
    request: dict[str, Any],
    *,
    client_factory: Callable[[], Any] = TikHubClient,
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
    if not _tikhub_enabled():
        diagnostics["status"] = "skipped"
        diagnostics["reason"] = "ENABLE_TIKHUB is disabled"
        return {"results": [], "diagnostics": diagnostics}
    if not resolve_tikhub_api_key():
        diagnostics["status"] = "skipped"
        diagnostics["reason"] = "TIKHUB_API_KEY is not configured"
        return {"results": [], "diagnostics": diagnostics}
    if not platforms or not keywords:
        diagnostics["status"] = "skipped"
        return {"results": [], "diagnostics": diagnostics}

    client = client_factory()
    creators: dict[tuple[str, str], dict[str, Any]] = {}
    candidate_window = _candidate_window(limit)
    try:
        for platform in platforms:
            try:
                for keyword in keywords:
                    for item in await _collect_user_search_items(
                        client,
                        platform=platform,
                        keyword=keyword,
                        target_count=candidate_window,
                    ):
                        normalized = _creator_from_user_search(platform, item, keyword)
                        if not normalized:
                            diagnostics["malformed_items"] += 1
                            continue
                        key = (normalized["platform"], normalized["creator_id"])
                        creators[key] = _merge_realtime_creator(creators.get(key), normalized)
            except Exception as exc:
                diagnostics["failed_platforms"].append(platform)
                diagnostics["error"] = str(exc)

        shortlisted = sorted(
            creators.values(),
            key=lambda item: _score_creator(item, keywords),
            reverse=True,
        )[:candidate_window]
        for creator in shortlisted:
            try:
                await _enrich_creator_from_posts(client, creator)
            except Exception:
                continue
    finally:
        await _close_client(client)

    scored_creators = []
    for creator in shortlisted:
        if not _passes_request_filters(creator, request):
            continue
        creator["match_score"] = _score_creator(creator, keywords)
        scored_creators.append(creator)

    scored_creators.sort(key=lambda item: item["match_score"], reverse=True)
    limited_creators = scored_creators[:limit]
    diagnostics["matched_creators"] = len(scored_creators)
    diagnostics["persisted_creators"] = len(limited_creators)

    results = []
    for creator in limited_creators:
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
    if not _tikhub_enabled():
        diagnostics["reason"] = "ENABLE_TIKHUB is disabled"
        return diagnostics
    if not resolve_tikhub_api_key():
        diagnostics["reason"] = "TIKHUB_API_KEY is not configured"
        return diagnostics
    if not selected_platforms or not keyword:
        return diagnostics

    client = client_factory()
    try:
        for platform in selected_platforms:
            try:
                items = await _collect_user_search_items(
                    client,
                    platform=platform,
                    keyword=keyword,
                    target_count=1,
                )
                sample = _probe_sample_creator(platform, items[0], keyword) if items else None
                diagnostics["results"].append(
                    {
                        "platform": platform,
                        "ok": True,
                        "item_count": len(items),
                        "sample_creator": sample,
                        "error": None,
                    }
                )
            except Exception as exc:
                diagnostics["results"].append(
                    {
                        "platform": platform,
                        "ok": False,
                        "item_count": 0,
                        "sample_creator": None,
                        "error": str(exc),
                    }
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


async def _collect_user_search_items(
    client: Any,
    *,
    platform: str,
    keyword: str,
    target_count: int,
) -> list[dict[str, Any]]:
    spec = USER_SEARCH_ENDPOINTS[platform]
    page = 1
    cursor = spec.get("cursor_initial", "")
    items: list[dict[str, Any]] = []
    while page <= int(spec["max_pages"]) and len(items) < target_count:
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


def _merge_realtime_creator(
    existing: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    if existing is None:
        return current
    existing["matched_keywords"] = sorted(
        set(existing.get("matched_keywords") or []) | set(current.get("matched_keywords") or [])
    )
    existing["representative_posts"] = (
        existing.get("representative_posts") or []
    ) + current.get("representative_posts", [])
    existing["recent_post_count_30d"] = max(
        int(existing.get("recent_post_count_30d") or 0),
        len(existing["representative_posts"]),
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
    follower_count = creator.get("follower_count")
    follower_min = request.get("follower_min")
    follower_max = request.get("follower_max")
    if follower_min is not None and (follower_count is None or int(follower_count) < int(follower_min)):
        return False
    if follower_max is not None and follower_count is not None and int(follower_count) > int(follower_max):
        return False
    recent_min = request.get("recent_activity_min")
    if recent_min is not None and int(creator.get("recent_post_count_30d") or 0) < int(recent_min):
        return False
    engagement_min = request.get("engagement_rate_min")
    if engagement_min is not None and float(creator.get("avg_engagement_rate") or 0) < float(engagement_min):
        return False
    return True


def _profile_payload(creator: dict[str, Any]) -> dict[str, Any]:
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
            "source": REALTIME_SOURCE,
            "matched_keywords": creator.get("matched_keywords") or [],
        },
    }


def _candidate_payload(creator: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    evidence = _evidence_payload(creator)
    return {
        "platform": creator["platform"],
        "creator_id": creator["creator_id"],
        "pool_name": "realtime",
        "vertical_id": request.get("selected_vertical_id"),
        "match_score": creator.get("match_score"),
        "matched_tags_json": _matched_tags(creator),
        "evidence_json": evidence,
        "notes": "Imported from TikHub realtime creator discovery",
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
        "source_type": "realtime",
        "source_labels": ["Realtime"],
        "realtime_unverified": True,
    }


def _matched_tags(creator: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"source": REALTIME_SOURCE, "keyword": keyword}
        for keyword in creator.get("matched_keywords") or []
    ]


def _evidence_payload(creator: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": REALTIME_SOURCE,
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
    }


def _profile_url(platform: str, creator_id: str) -> str:
    if platform == "xhs":
        return f"https://www.xiaohongshu.com/user/profile/{creator_id}"
    return f"https://www.douyin.com/user/{creator_id}"


def _candidate_window(limit: int) -> int:
    requested = max(10, int(limit or 10) * 2)
    return min(requested, CREATOR_POST_ENRICHMENT_LIMIT)


def _tikhub_enabled() -> bool:
    return bool(getattr(config, "ENABLE_TIKHUB", False))


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

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
import inspect
from typing import Any

from media_platform.tikhub.client import TikHubClient
from media_platform.tikhub.endpoints import Capability, get_endpoint
from media_platform.tikhub.mappers import get_mapper
from media_platform.tikhub.mappers.base import author, nested, pick


REALTIME_PLATFORMS = ("xhs", "dy")


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
    diagnostics = _diagnostics(
        enabled=True,
        platforms=platforms,
        unsupported_platforms=unsupported,
    )
    if not platforms or not keywords:
        diagnostics["status"] = "skipped"
        return {"results": [], "diagnostics": diagnostics}

    client = client_factory()
    creators: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        for platform in platforms:
            try:
                endpoint = get_endpoint(platform, Capability.SEARCH)
                for keyword in keywords:
                    payload = await _call_search(client, endpoint, keyword)
                    for item in _extract_items(payload):
                        normalized = _creator_from_content(platform, item, keyword)
                        if not normalized:
                            diagnostics["malformed_items"] += 1
                            continue
                        key = (normalized["platform"], normalized["creator_id"])
                        creators[key] = _merge_realtime_creator(creators.get(key), normalized)
            except Exception as exc:
                diagnostics["failed_platforms"].append(platform)
                diagnostics["error"] = str(exc)
    finally:
        await _close_client(client)

    results = []
    for creator in creators.values():
        if not _passes_request_filters(creator, request):
            continue
        creator["match_score"] = _score_creator(creator, keywords)
        profile = await repository.upsert_creator_profile(_profile_payload(creator))
        candidate = await repository.upsert_creator_candidate(_candidate_payload(creator, request))
        diagnostics["created_profiles"] += 1 if profile else 0
        diagnostics["created_candidates"] += 1 if candidate else 0
        results.append(_result_payload(creator))

    results.sort(key=lambda item: item["match_score"], reverse=True)
    diagnostics["status"] = _status(diagnostics["failed_platforms"], results)
    return {"results": results[: int(request.get("limit") or 50)], "diagnostics": diagnostics}


async def _call_search(client: Any, endpoint: Any, keyword: str) -> Any:
    payload = {**endpoint.default_params, endpoint.keyword_param: keyword}
    if endpoint.json_body:
        return await client.request(endpoint.method, endpoint.path, json=payload)
    return await client.request(endpoint.method, endpoint.path, params=payload)


def _keywords_from_request(request: dict[str, Any]) -> list[str]:
    raw = str(request.get("raw_query") or "").strip()
    if not raw:
        return []
    terms = [term.strip() for term in raw.replace("+", " ").replace(",", " ").split()]
    return [term for term in dict.fromkeys(terms) if term] or [raw]


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("items", "list", "aweme_list", "notes", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            items = _extract_items(value)
            if items:
                return items
    return []


def _creator_from_content(platform: str, item: dict[str, Any], keyword: str) -> dict[str, Any] | None:
    raw_item = item
    content = get_mapper(platform).map_content(item, source_keyword=keyword)
    if not isinstance(content, dict):
        return None
    raw_user = _raw_author(platform, raw_item)
    mapped_user = _mapped_author(platform, content)
    user = {**mapped_user, **raw_user}
    creator_id = _creator_id(platform, user)
    if not creator_id:
        return None

    representative_post = _representative_post(platform, content, keyword)
    follower_count = _follower_count(platform, user)
    engagement_total = _engagement_total(representative_post["engagement"])
    return {
        "platform": platform,
        "creator_id": creator_id,
        "display_name": _display_name(user, creator_id),
        "profile_url": _profile_url(platform, creator_id),
        "bio": str(pick(user, "desc", "description", "bio", "signature", default="")),
        "follower_count": follower_count,
        "following_count": _following_count(user),
        "post_count": _post_count(user),
        "recent_post_count_30d": 1,
        "avg_engagement_rate": _engagement_rate(engagement_total, follower_count),
        "hot_post_rate": 1.0 if engagement_total >= 1000 else 0.0,
        "matched_keywords": [keyword],
        "representative_posts": [representative_post],
        "engagement_total": engagement_total,
        "raw_item": raw_item,
    }


def _raw_author(platform: str, item: dict[str, Any]) -> dict[str, Any]:
    if platform == "xhs" and isinstance(item.get("note"), dict):
        item = item["note"]
    if platform == "dy" and isinstance(item.get("aweme_info"), dict):
        item = item["aweme_info"]
    return author(item)


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
            default=nested(user, "follow_info", "follower_count", default=None),
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
    existing["avg_engagement_rate"] = _engagement_rate(
        existing["engagement_total"], existing.get("follower_count")
    )
    existing["hot_post_rate"] = _hot_post_rate(existing.get("representative_posts") or [])
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
            "source": "tikhub_realtime",
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
        {"source": "tikhub_realtime", "keyword": keyword}
        for keyword in creator.get("matched_keywords") or []
    ]


def _evidence_payload(creator: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "tikhub_realtime",
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


def _engagement_total(engagement: dict[str, Any]) -> int:
    return sum(_to_int(value) for value in engagement.values())


def _engagement_rate(engagement_total: int, follower_count: Any) -> float | None:
    followers = _to_int(follower_count)
    if followers <= 0:
        return None
    return round(engagement_total / followers, 6)


def _hot_post_rate(posts: list[dict[str, Any]]) -> float:
    if not posts:
        return 0.0
    hot_posts = [
        post for post in posts if _engagement_total(post.get("engagement") or {}) >= 1000
    ]
    return round(len(hot_posts) / len(posts), 4)


def _to_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return _to_int(value)


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith(("k", "K")):
        multiplier = 1000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


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
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "status": "ok",
        "platforms": platforms,
        "unsupported_platforms": unsupported_platforms,
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

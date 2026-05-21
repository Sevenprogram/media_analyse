import re
from datetime import datetime, timezone
from typing import Any

from media_platform.tikhub.client import TikHubClient
from media_platform.tikhub.mappers import get_mapper
from media_platform.tikhub.mappers.base import author
from store import douyin as douyin_store
from store import xhs as xhs_store

PROFILE_ENDPOINTS = {
    "xhs": ("GET", "/api/v1/xiaohongshu/app_v2/get_user_info", "user_id"),
    "dy": ("GET", "/api/v1/douyin/web/fetch_user_profile_by_uid", "uid"),
}


async def enrich_creator_metrics_from_tikhub(
    repository,
    creators: list[dict[str, Any]],
    *,
    client: TikHubClient | None = None,
) -> dict[str, Any]:
    owned_client = client is None
    client = client or TikHubClient()
    enriched = []
    failed = []
    try:
        for creator in creators:
            try:
                enriched.append(await _enrich_one(repository, client, creator))
            except Exception as exc:
                failed.append(
                    {
                        "platform": creator.get("platform"),
                        "creator_id": creator.get("creator_id"),
                        "profile_url": creator.get("profile_url"),
                        "error": str(exc),
                    }
                )
    finally:
        if owned_client:
            await client.close()
    return {"enriched_count": len(enriched), "failed_count": len(failed), "enriched": enriched, "failed": failed}


async def _enrich_one(repository, client: TikHubClient, creator: dict[str, Any]) -> dict[str, Any]:
    platform = str(creator["platform"])
    native_id = native_creator_id(platform, creator)
    if not native_id:
        raise ValueError("missing native creator id; profile_url is required")

    method, path, param = PROFILE_ENDPOINTS[platform]
    data = await client.request(
        method,
        path,
        params={param: native_id},
    )
    creator_payload = _extract_creator_payload(data)
    mapped = get_mapper(platform).map_creator(creator_payload)
    metrics = _creator_metrics(platform, mapped)
    if platform == "dy" and not metrics.get("total_like_count"):
        fallback_metrics = await _fetch_dy_search_metrics(client, creator, native_id, metrics)
        if fallback_metrics:
            _apply_dy_metric_overrides(mapped, fallback_metrics)
            metrics = {**metrics, **{key: value for key, value in fallback_metrics.items() if value not in (None, "")}}
    await _save_platform_creator(platform, native_id, mapped)

    existing = await repository.get_creator_profile(platform, creator["creator_id"])
    tag_summary = dict((existing or {}).get("tag_summary_json") or {})
    tag_summary["profile_metrics"] = {
        "source": "tikhub_creator",
        "native_creator_id": native_id,
        "total_like_count": metrics.get("total_like_count"),
        "total_collect_count": metrics.get("total_collect_count"),
        "interaction_count": metrics.get("interaction_count"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = {
        "platform": platform,
        "creator_id": creator["creator_id"],
        "display_name": metrics.get("display_name") or creator.get("display_name"),
        "profile_url": creator.get("profile_url") or _profile_url(platform, native_id),
        "bio": metrics.get("bio"),
        "follower_count": metrics.get("follower_count"),
        "following_count": metrics.get("following_count"),
        "post_count": metrics.get("post_count") or (existing or {}).get("post_count"),
        "avg_engagement_rate": (existing or {}).get("avg_engagement_rate"),
        "hot_post_rate": (existing or {}).get("hot_post_rate"),
        "recent_post_count_30d": (existing or {}).get("recent_post_count_30d"),
        "latest_snapshot_at": datetime.now(timezone.utc),
        "tag_summary_json": tag_summary,
    }
    updated = await repository.upsert_creator_profile(payload)
    return {**updated, **tag_summary["profile_metrics"]}


def native_creator_id(platform: str, creator: dict[str, Any]) -> str:
    profile_url = str(creator.get("profile_url") or "")
    if platform == "xhs":
        match = re.search(r"/user/profile/([^/?#]+)", profile_url)
        return match.group(1) if match else ""
    if platform == "dy":
        uid = _dy_uid_from_creator(creator)
        if uid:
            return uid
        match = re.search(r"/user/([^/?#]+)", profile_url)
        if match:
            return match.group(1)
        evidence = creator.get("evidence") or []
        for item in evidence if isinstance(evidence, list) else []:
            engagement = item.get("engagement") if isinstance(item, dict) else {}
            if isinstance(engagement, dict) and engagement.get("sec_uid"):
                return str(engagement["sec_uid"])
    return ""


def _dy_uid_from_creator(creator: dict[str, Any]) -> str:
    for key in ("evidence", "representative_posts"):
        value = creator.get(key) or []
        for item in value if isinstance(value, list) else []:
            if not isinstance(item, dict):
                continue
            engagement = item.get("engagement") or {}
            if isinstance(engagement, dict) and engagement.get("author_id"):
                return str(engagement["author_id"])
    return ""


async def _fetch_dy_search_metrics(
    client: TikHubClient,
    creator: dict[str, Any],
    native_id: str,
    current_metrics: dict[str, Any],
) -> dict[str, Any]:
    keyword = str(current_metrics.get("display_name") or creator.get("display_name") or "").strip()
    if not keyword:
        return {}
    data = await client.request(
        "POST",
        "/api/v1/douyin/search/fetch_user_search_v2",
        json={"keyword": keyword, "page": 1, "cursor": 0, "count": 10},
    )
    sec_uid = _dy_sec_uid_from_creator(creator)
    candidate = _find_dy_search_user(data, native_id=native_id, sec_uid=sec_uid, display_name=keyword)
    if not candidate:
        return {}
    return {
        "display_name": candidate.get("nickname") or candidate.get("nick_name") or keyword,
        "follower_count": _to_int(candidate.get("fans_cnt") or candidate.get("follower_count")),
        "following_count": _to_int(candidate.get("favoriting_count") or candidate.get("following_count")),
        "post_count": _to_int(candidate.get("publish_cnt") or candidate.get("aweme_count")),
        "total_like_count": _to_int(candidate.get("like_cnt") or candidate.get("total_favorited")),
        "interaction_count": _to_int(candidate.get("like_cnt") or candidate.get("total_favorited")),
    }


def _dy_sec_uid_from_creator(creator: dict[str, Any]) -> str:
    profile_url = str(creator.get("profile_url") or "")
    match = re.search(r"/user/([^/?#]+)", profile_url)
    if match:
        return match.group(1)
    evidence = creator.get("evidence") or []
    for item in evidence if isinstance(evidence, list) else []:
        engagement = item.get("engagement") if isinstance(item, dict) else {}
        if isinstance(engagement, dict) and engagement.get("sec_uid"):
            return str(engagement["sec_uid"])
    return ""


def _find_dy_search_user(data: Any, *, native_id: str, sec_uid: str, display_name: str) -> dict[str, Any]:
    for item in _iter_dy_search_users(data):
        user = item.get("user_info") if isinstance(item.get("user_info"), dict) else item
        if not isinstance(user, dict):
            continue
        values = {
            str(user.get("uid") or ""),
            str(user.get("user_id") or ""),
            str(user.get("sec_uid") or ""),
        }
        nickname = str(user.get("nickname") or user.get("nick_name") or "")
        if native_id in values or (sec_uid and sec_uid in values) or nickname == display_name:
            return user
    return {}


def _iter_dy_search_users(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("user_list", "data", "list", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _iter_dy_search_users(value)
            if nested:
                return nested
    return []


def _apply_dy_metric_overrides(mapped: dict[str, Any], metrics: dict[str, Any]) -> None:
    user = mapped.setdefault("user", {})
    if metrics.get("display_name"):
        user["nickname"] = metrics["display_name"]
    if metrics.get("follower_count") is not None:
        user["max_follower_count"] = metrics["follower_count"]
    if metrics.get("following_count") is not None:
        user["following_count"] = metrics["following_count"]
    if metrics.get("post_count") is not None:
        user["aweme_count"] = metrics["post_count"]
    if metrics.get("total_like_count") is not None:
        user["total_favorited"] = metrics["total_like_count"]


def _extract_creator_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    for key in ("user", "author", "creator", "profile", "user_info", "author_info"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    if isinstance(data.get("data"), dict):
        return _extract_creator_payload(data["data"])
    for key in ("items", "aweme_list", "notes", "list", "data"):
        value = data.get(key)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                note = first.get("note") if isinstance(first.get("note"), dict) else first
                return author(note) or note
        if isinstance(value, dict):
            nested = _extract_creator_payload(value)
            if nested:
                return nested
    return data


async def _save_platform_creator(platform: str, native_id: str, mapped: dict[str, Any]) -> None:
    if platform == "xhs":
        await xhs_store.save_creator(native_id, mapped)
    elif platform == "dy":
        await douyin_store.save_creator(native_id, mapped)


def _creator_metrics(platform: str, mapped: dict[str, Any]) -> dict[str, Any]:
    if platform == "xhs":
        basic = mapped.get("basicInfo") or {}
        interactions = {
            item.get("type"): item.get("count")
            for item in mapped.get("interactions") or []
            if isinstance(item, dict)
        }
        return {
            "display_name": basic.get("nickname"),
            "bio": basic.get("desc"),
            "follower_count": _to_int(interactions.get("fans")),
            "following_count": _to_int(interactions.get("follows")),
            "post_count": _to_int(interactions.get("notes")),
            "total_like_count": _to_int(interactions.get("liked") or interactions.get("interaction")),
            "interaction_count": _to_int(interactions.get("interaction")),
            "total_collect_count": _to_int(interactions.get("collected")),
        }
    user = mapped.get("user") or {}
    return {
        "display_name": user.get("nickname"),
        "bio": user.get("signature"),
        "follower_count": _to_int(user.get("max_follower_count")),
        "following_count": _to_int(user.get("following_count")),
        "post_count": _to_int(user.get("aweme_count")),
        "total_like_count": _to_int(user.get("total_favorited")),
        "interaction_count": _to_int(user.get("total_favorited")),
        "total_collect_count": _to_int(user.get("collect_count")),
    }


def _profile_url(platform: str, native_id: str) -> str:
    if platform == "xhs":
        return f"https://www.xiaohongshu.com/user/profile/{native_id}"
    if platform == "dy":
        return f"https://www.douyin.com/user/{native_id}"
    return ""


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None

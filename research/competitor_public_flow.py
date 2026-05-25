from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from research.competitors import build_competitor_composition_snapshot


DEFAULT_LATEST_LIMIT = 50
DEFAULT_MONITOR_INTERVAL_MINUTES = 24 * 60


def build_competitor_public_flow_snapshot(
    *,
    competitor: dict[str, Any],
    posts: list[dict[str, Any]],
    keywords: list[str],
    entity_tags: list[dict[str, Any]] | None = None,
    previous_snapshots: list[dict[str, Any]] | None = None,
    snapshot_date: date | None = None,
    latest_limit: int = DEFAULT_LATEST_LIMIT,
) -> dict[str, Any]:
    latest_posts = _dedupe_posts(posts)[:latest_limit]
    previous_snapshots = previous_snapshots or []
    previous_public_flow = _previous_public_flow(previous_snapshots)
    previous_posts = previous_public_flow.get("posts_by_id") or {}
    current_posts = {
        _post_id(post): _post_public_metrics(post)
        for post in latest_posts
        if _post_id(post)
    }
    cumulative = _sum_metrics(current_posts.values())
    delta_by_post = {
        post_id: _subtract_metrics(metrics, previous_posts.get(post_id, {}))
        for post_id, metrics in current_posts.items()
    }
    delta = _sum_metrics(delta_by_post.values())
    base_snapshot = build_competitor_composition_snapshot(
        competitor_account_id=int(competitor["id"]),
        snapshot_date=snapshot_date or date.today(),
        platform=competitor["platform"],
        posts=latest_posts,
        entity_tags=entity_tags or [],
        keywords=keywords,
    )
    public_flow = {
        "latest_limit": latest_limit,
        "deduped_post_count": len(latest_posts),
        "cumulative": cumulative,
        "delta": delta,
        "posts_by_id": current_posts,
        "delta_by_post": delta_by_post,
        "top_delta_posts": _top_delta_posts(latest_posts, delta_by_post),
    }
    anomalies = detect_public_flow_anomalies(
        current_snapshot=base_snapshot,
        public_flow=public_flow,
        previous_snapshots=previous_snapshots,
    )
    base_snapshot["total_flow_count"] = cumulative["total_interaction"]
    base_snapshot["evidence"] = {
        **base_snapshot.get("evidence", {}),
        "public_flow": public_flow,
        "anomalies": anomalies,
    }
    return base_snapshot


def detect_public_flow_anomalies(
    *,
    current_snapshot: dict[str, Any],
    public_flow: dict[str, Any],
    previous_snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    delta_total = int((public_flow.get("delta") or {}).get("total_interaction") or 0)
    previous_deltas = [
        int(((snapshot.get("evidence") or {}).get("public_flow") or {}).get("delta", {}).get("total_interaction") or 0)
        for snapshot in previous_snapshots[:7]
    ]
    previous_positive = [value for value in previous_deltas if value > 0]
    baseline = sum(previous_positive) / len(previous_positive) if previous_positive else 0
    if baseline > 0 and delta_total >= max(100, baseline * 2):
        anomalies.append(
            {
                "type": "interaction_spike",
                "severity": "high",
                "title": "interaction spike",
                "reason": f"New public interactions {delta_total}, above 2x recent average {baseline:.1f}.",
            }
        )

    keyword_anomaly = _keyword_shift_anomaly(current_snapshot, previous_snapshots)
    if keyword_anomaly:
        anomalies.append(keyword_anomaly)

    top_delta_posts = public_flow.get("top_delta_posts") or []
    if top_delta_posts and int(top_delta_posts[0].get("delta_total") or 0) >= 100:
        anomalies.append(
            {
                "type": "new_hot_post",
                "severity": "high",
                "title": "new hot post",
                "reason": f"Post {top_delta_posts[0].get('platform_post_id')} gained {top_delta_posts[0].get('delta_total')} public interactions.",
                "post": top_delta_posts[0],
            }
        )
    return anomalies


async def create_competitor_monitor_jobs(
    repository,
    *,
    interval_minutes: int = DEFAULT_MONITOR_INTERVAL_MINUTES,
    latest_limit: int = DEFAULT_LATEST_LIMIT,
) -> dict[str, Any]:
    competitors = await repository.list_competitor_accounts(enabled_only=True)
    existing_jobs = await repository.list_jobs() if hasattr(repository, "list_jobs") else []
    jobs = []
    for competitor in competitors:
        payload = _monitor_job_payload(
            competitor,
            interval_minutes=interval_minutes,
            latest_limit=latest_limit,
        )
        existing = next((job for job in existing_jobs if job.get("topic") == payload["topic"]), None)
        if existing and hasattr(repository, "update_job"):
            job = await repository.update_job(existing["id"], payload)
        else:
            job = await repository.create_job(payload)
        jobs.append(job)
    return {
        "created_or_updated": len(jobs),
        "jobs": jobs,
        "interval_minutes": interval_minutes,
        "latest_limit": latest_limit,
    }


async def get_competitor_monitor_job(
    repository,
    competitor_id: int,
) -> dict[str, Any] | None:
    jobs = await repository.list_jobs() if hasattr(repository, "list_jobs") else []
    topic = f"competitor_public_flow:{competitor_id}"
    return next((job for job in jobs if job.get("topic") == topic), None)


async def create_or_update_competitor_monitor_job(
    repository,
    competitor: dict[str, Any],
    *,
    schedule_enabled: bool,
    interval_minutes: int | None = DEFAULT_MONITOR_INTERVAL_MINUTES,
    latest_limit: int = DEFAULT_LATEST_LIMIT,
) -> dict[str, Any]:
    existing = await get_competitor_monitor_job(repository, int(competitor["id"]))
    if existing and hasattr(repository, "update_job"):
        payload = {
            "schedule_enabled": schedule_enabled,
            "schedule_interval_minutes": interval_minutes if schedule_enabled else None,
            "status": existing.get("status") or "pending",
        }
        return await repository.update_job(existing["id"], payload)

    payload = _monitor_job_payload(
        competitor,
        interval_minutes=interval_minutes or DEFAULT_MONITOR_INTERVAL_MINUTES,
        latest_limit=latest_limit,
    )
    payload["schedule_enabled"] = schedule_enabled
    payload["schedule_interval_minutes"] = interval_minutes if schedule_enabled else None
    return await repository.create_job(payload)


async def create_competitor_fetch_now_job(
    repository,
    competitor: dict[str, Any],
    *,
    latest_limit: int = DEFAULT_LATEST_LIMIT,
    days_back: int | None = None,
) -> dict[str, Any]:
    payload = _monitor_job_payload(
        competitor,
        interval_minutes=DEFAULT_MONITOR_INTERVAL_MINUTES,
        latest_limit=latest_limit,
    )
    if days_back:
        today = date.today()
        payload["start_date"] = today - timedelta(days=days_back - 1)
        payload["end_date"] = today
    payload.update(
        {
            "name": f"{competitor.get('display_name') or competitor['creator_id']} - fetch now",
            "topic": f"competitor_public_flow_now:{competitor['id']}:{date.today().isoformat()}",
            "schedule_enabled": False,
            "schedule_interval_minutes": None,
        }
    )
    return await repository.create_job(payload)


def _monitor_job_payload(
    competitor: dict[str, Any],
    *,
    interval_minutes: int,
    latest_limit: int,
) -> dict[str, Any]:
    today = date.today()
    return {
        "name": f"{competitor.get('display_name') or competitor['creator_id']} - competitor public flow",
        "topic": f"competitor_public_flow:{competitor['id']}",
        "platforms": [competitor["platform"]],
        "collection_mode": "creator",
        "keywords": [],
        "target_ids": [],
        "creator_ids": [competitor["creator_id"]],
        "start_date": today,
        "end_date": today + timedelta(days=365),
        "status": "pending",
        "comment_policy": {
            "enable_comments": False,
            "enable_sub_comments": False,
            "max_posts_per_job": latest_limit,
        },
        "raw_record_mode": "minimal",
        "anonymize_authors": True,
        "schedule_enabled": True,
        "schedule_interval_minutes": interval_minutes,
    }


def _dedupe_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for post in posts:
        keys = [key for key in (_post_dedupe_id_key(post), _post_content_signature(post)) if key]
        if not keys:
            keys = [_fallback_post_id(post)]
        if any(key in seen for key in keys):
            continue
        seen.update(keys)
        result.append(post)
    return result


def _post_dedupe_id_key(post: dict[str, Any]) -> str:
    post_id = _post_id(post)
    return f"id:{post_id}" if post_id else ""


def _post_id(post: dict[str, Any]) -> str:
    return str(post.get("platform_post_id") or post.get("content_id") or post.get("id") or "")


def _post_content_signature(post: dict[str, Any]) -> str:
    title = " ".join(str(post.get("title") or post.get("content") or "").split())
    publish_time = str(post.get("publish_time") or "").strip()
    if not title or not publish_time:
        return ""
    engagement = post.get("engagement_json") or post.get("engagement") or {}
    author = str(
        post.get("author_hash")
        or post.get("creator_id")
        or engagement.get("platform_author_id")
        or engagement.get("author_id")
        or engagement.get("user_id")
        or ""
    ).strip()
    platform = str(post.get("platform") or "").strip()
    return f"sig:{platform}|{author}|{title}|{publish_time[:16]}"


def _fallback_post_id(post: dict[str, Any]) -> str:
    return "|".join(
        str(value or "")
        for value in [
            post.get("platform"),
            post.get("author_hash") or post.get("creator_id"),
            post.get("title") or post.get("content"),
            post.get("publish_time"),
        ]
    )


def _post_public_metrics(post: dict[str, Any]) -> dict[str, int]:
    return {
        "like": _metric(post, "liked_count") + _metric(post, "like_count"),
        "comment": _metric(post, "comment_count") + _metric(post, "comments_count"),
        "share": _metric(post, "share_count") + _metric(post, "shared_count"),
        "collect": _metric(post, "collected_count") + _metric(post, "favorite_count"),
        "total_interaction": _metric(post, "liked_count")
        + _metric(post, "like_count")
        + _metric(post, "comment_count")
        + _metric(post, "comments_count")
        + _metric(post, "share_count")
        + _metric(post, "shared_count")
        + _metric(post, "collected_count")
        + _metric(post, "favorite_count"),
    }


def _metric(post: dict[str, Any], key: str) -> int:
    engagement = post.get("engagement_json") or post.get("engagement") or {}
    try:
        return int(engagement.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _sum_metrics(items) -> dict[str, int]:
    total = Counter({key: 0 for key in ("like", "comment", "share", "collect", "total_interaction")})
    for item in items:
        for key in ("like", "comment", "share", "collect", "total_interaction"):
            total[key] += max(0, int(item.get(key) or 0))
    return dict(total)


def _subtract_metrics(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    return {
        key: max(0, int(current.get(key) or 0) - int(previous.get(key) or 0))
        for key in ("like", "comment", "share", "collect", "total_interaction")
    }


def _top_delta_posts(posts: list[dict[str, Any]], delta_by_post: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    by_id = {_post_id(post): post for post in posts}
    rows = []
    for post_id, delta in delta_by_post.items():
        post = by_id.get(post_id, {})
        if not _post_is_ranking_eligible(post):
            continue
        rows.append(
            {
                "platform_post_id": post_id,
                "title": post.get("title"),
                "url": post.get("url"),
                "author_verified": bool(post.get("author_verified")),
                "has_valid_url": bool(post.get("has_valid_url")),
                "link_status": _post_link_status(post),
                "delta_total": int(delta.get("total_interaction") or 0),
                "delta": delta,
            }
        )
    return sorted(rows, key=lambda item: item["delta_total"], reverse=True)[:10]


def _post_is_ranking_eligible(post: dict[str, Any]) -> bool:
    return bool(post.get("author_verified"))


def _post_link_status(post: dict[str, Any]) -> str:
    if post.get("has_valid_url"):
        return "ok"
    if not post.get("author_verified"):
        return "author_mismatch"
    engagement = post.get("engagement_json") or {}
    if post.get("platform") == "xhs" and not str(engagement.get("xsec_token") or "").strip():
        return "missing_xsec_token"
    return "invalid_platform_url"


def _previous_public_flow(previous_snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    for snapshot in previous_snapshots:
        public_flow = (snapshot.get("evidence") or {}).get("public_flow")
        if public_flow:
            return public_flow
    return {}


def _keyword_shift_anomaly(
    current_snapshot: dict[str, Any],
    previous_snapshots: list[dict[str, Any]],
) -> dict[str, Any] | None:
    current_distribution = current_snapshot.get("keyword_distribution") or {}
    if not current_distribution:
        return None
    top_keyword, top_count = max(current_distribution.items(), key=lambda item: int(item[1] or 0))
    current_total = sum(int(value or 0) for value in current_distribution.values())
    if current_total <= 0:
        return None
    current_ratio = int(top_count or 0) / current_total
    previous_counts = [
        int((snapshot.get("keyword_distribution") or {}).get(top_keyword) or 0)
        for snapshot in previous_snapshots[:7]
    ]
    previous_avg = sum(previous_counts) / len(previous_counts) if previous_counts else 0
    if int(top_count or 0) >= 2 and current_ratio >= 0.4 and int(top_count or 0) >= max(2, previous_avg * 2):
        return {
            "type": "keyword_shift",
            "severity": "medium",
            "title": "keyword shift",
            "reason": f"Keyword '{top_keyword}' now accounts for {current_ratio:.0%}, above recent average {previous_avg:.1f}.",
            "keyword": top_keyword,
        }
    return None

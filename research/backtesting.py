from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from research.keyword_heat import aggregate_keyword_heat_from_posts


def date_range(start_date: date, end_date: date) -> list[date]:
    days = (end_date - start_date).days
    return [start_date + timedelta(days=offset) for offset in range(days + 1)]


async def run_backtest(repository: Any, backtest: dict[str, Any]) -> dict[str, Any]:
    start_at = datetime.combine(backtest["start_date"], time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(backtest["end_date"], time.max, tzinfo=timezone.utc)
    platforms = list(backtest.get("platforms") or [])
    keywords = [item.strip() for item in backtest.get("keywords") or [] if item.strip()]

    posts = []
    for platform in platforms or [None]:
        posts.extend(
            await repository.list_all_posts(
                platform=platform,
                start_at=start_at,
                end_at=end_at,
                limit=20000,
            )
        )

    posts = _dedupe_posts(posts)
    matched_posts = [
        post for post in posts if any(_keyword_in_post(keyword, post) for keyword in keywords)
    ]
    replay_dates = date_range(backtest["start_date"], backtest["end_date"])
    if not backtest.get("replay_daily", True):
        replay_dates = [backtest["end_date"]]

    daily = [
        _build_daily_row(
            replay_date=replay_date,
            keywords=keywords,
            platforms=platforms,
            posts=matched_posts,
        )
        for replay_date in replay_dates
    ]
    latest = daily[-1] if daily else {}
    report = {
        "backtest_id": backtest["id"],
        "scenario": backtest["scenario"],
        "keywords": keywords,
        "platforms": platforms,
        "window": {
            "start_date": backtest["start_date"].isoformat(),
            "end_date": backtest["end_date"].isoformat(),
            "days": len(replay_dates),
        },
        "sample": _sample_summary(posts=posts, matched_posts=matched_posts, daily=daily),
        "daily": daily,
        "latest_keywords": latest.get("keywords", []),
        "platform_summary": _platform_summary(matched_posts),
        "calibration_notes": _calibration_notes(daily),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "supplemental": {
            "use_tikhub_backfill": bool(backtest.get("use_tikhub_backfill")),
            "research_job_id": backtest.get("research_job_id"),
        },
    }
    return report


def _build_daily_row(
    *,
    replay_date: date,
    keywords: list[str],
    platforms: list[str],
    posts: list[dict[str, Any]],
) -> dict[str, Any]:
    now = datetime.combine(replay_date, time.max, tzinfo=timezone.utc)
    visible_posts = [
        post
        for post in posts
        if _as_utc(post.get("publish_time") or post.get("created_at") or now) <= now
    ]
    keyword_rows = []
    for keyword in keywords:
        keyword_posts = [post for post in visible_posts if _keyword_in_post(keyword, post)]
        signal = aggregate_keyword_heat_from_posts(keyword=keyword, posts=keyword_posts, now=now)
        keyword_rows.append(
            {
                "keyword": keyword,
                "label": signal["label"],
                "heat_score": signal["heat_score"],
                "push_score": signal["push_score"],
                "cooldown_risk": signal["cooldown_risk"],
                "confidence": signal["confidence"],
                "sample_quality": signal.get("sample_quality") or {},
                "sample_count": len(keyword_posts),
                "evidence": signal["evidence"],
            }
        )
    total_sample = len(visible_posts)
    avg_heat = round(
        sum(float(item["heat_score"]) for item in keyword_rows) / max(1, len(keyword_rows)),
        2,
    )
    labels = Counter(item["label"] for item in keyword_rows)
    return {
        "date": replay_date.isoformat(),
        "sample_count": total_sample,
        "platforms": platforms,
        "avg_heat_score": avg_heat,
        "dominant_label": labels.most_common(1)[0][0] if labels else "insufficient_data",
        "keywords": keyword_rows,
    }


def _sample_summary(
    *,
    posts: list[dict[str, Any]],
    matched_posts: list[dict[str, Any]],
    daily: list[dict[str, Any]],
) -> dict[str, Any]:
    latest_count = int(daily[-1]["sample_count"]) if daily else 0
    if latest_count >= 100:
        status = "enough"
    elif latest_count >= 30:
        status = "limited"
    else:
        status = "insufficient"
    return {
        "status": status,
        "total_posts": len(posts),
        "matched_posts": len(matched_posts),
        "latest_visible_posts": latest_count,
    }


def _platform_summary(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(post.get("platform") or "unknown") for post in posts)
    return [
        {"platform": platform, "sample_count": count}
        for platform, count in counts.most_common()
    ]


def _calibration_notes(daily: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    if not daily or int(daily[-1].get("sample_count") or 0) < 30:
        notes.append("样本不足 30 条，推流/限流标签只能作为线索，不能作为确定结论。")
    labels = [row.get("dominant_label") for row in daily]
    if len(set(labels[-3:])) > 1:
        notes.append("最近 3 个回放日标签波动较大，建议提高样本阈值或分平台查看。")
    scores = [float(row.get("avg_heat_score") or 0) for row in daily]
    if len(scores) >= 2 and abs(scores[-1] - scores[0]) >= 40:
        notes.append("窗口首尾热度变化超过 40 分，建议复核是否存在活动、投放或平台事件。")
    if not notes:
        notes.append("当前回测信号较稳定，可进入真实连续监控验证。")
    return notes


def _keyword_in_post(keyword: str, post: dict[str, Any]) -> bool:
    engagement = post.get("engagement_json") or post.get("engagement") or {}
    text = " ".join(
        [
            str(post.get("title") or ""),
            str(post.get("content") or ""),
            str(engagement.get("source_keyword") or ""),
            str(engagement.get("tag_list") or ""),
        ]
    ).lower()
    return keyword.lower() in text


def _dedupe_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for post in posts:
        key = (str(post.get("platform") or ""), str(post.get("platform_post_id") or post.get("id")))
        if key in seen:
            continue
        seen.add(key)
        result.append(post)
    return result


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

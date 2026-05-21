from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from typing import Any

from research.ai_provider import OpenAICompatibleProvider


async def run_ai_insight_analysis(
    repository: Any,
    *,
    provider_config_id: int | None = None,
    platforms: list[str] | None = None,
    vertical_id: int | None = None,
    scene_pack_id: int | None = None,
    window_days: int = 7,
) -> dict[str, Any]:
    provider_config = await _resolve_provider(repository, provider_config_id)
    input_summary = await build_ai_insight_input(
        repository,
        platforms=platforms or ["xhs", "dy"],
        vertical_id=vertical_id,
        scene_pack_id=scene_pack_id,
        window_days=window_days,
    )
    run = await repository.create_ai_insight_run(
        {
            "provider_config_id": provider_config["id"],
            "vertical_id": vertical_id,
            "scene_pack_id": scene_pack_id,
            "platforms": platforms or ["xhs", "dy"],
            "window_days": window_days,
            "status": "running",
            "input_summary": _json_safe(input_summary),
            "model": provider_config["model"],
        }
    )
    try:
        provider = OpenAICompatibleProvider(
            base_url=provider_config["base_url"],
            api_key=provider_config["api_key"],
            model=provider_config["model"],
            timeout=provider_config.get("timeout") or 60,
        )
        output = _normalize_ai_output(
            await provider.complete_json(
                prompt=build_ai_insight_prompt(input_summary),
                params={
                    "temperature": 0.35,
                    "max_tokens": 2800,
                    **(provider_config.get("default_params") or {}),
                },
            )
        )
        hotspots = await repository.create_ai_hotspots(run["id"], _json_safe(output["hotspots"]))
        topics = await repository.create_ai_topic_ideas(run["id"], _json_safe(output["topic_ideas"]))
        updated = await repository.update_ai_insight_run(
            run["id"],
            {
                "status": "completed",
                "output": _json_safe(output),
                "error_message": None,
            },
        )
        return {
            "run": updated,
            "hotspots": hotspots,
            "topic_ideas": topics,
            "platform_strategy": output.get("platform_strategy") or {},
            "risk_notes": output.get("risk_notes") or [],
        }
    except Exception as exc:
        fallback = build_rule_based_ai_insight_fallback(input_summary)
        hotspots = await repository.create_ai_hotspots(run["id"], _json_safe(fallback["hotspots"]))
        topics = await repository.create_ai_topic_ideas(run["id"], _json_safe(fallback["topic_ideas"]))
        updated = await repository.update_ai_insight_run(
            run["id"],
            {
                "status": "fallback",
                "output": _json_safe(fallback),
                "error_message": f"{type(exc).__name__}: {exc}",
            },
        )
        return {
            "run": updated,
            "hotspots": hotspots,
            "topic_ideas": topics,
            "platform_strategy": fallback.get("platform_strategy") or {},
            "risk_notes": fallback.get("risk_notes") or [],
        }


async def build_ai_insight_input(
    repository: Any,
    *,
    platforms: list[str],
    vertical_id: int | None,
    scene_pack_id: int | None,
    window_days: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start_at = datetime.combine((now - timedelta(days=window_days - 1)).date(), time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
    posts: list[dict[str, Any]] = []
    for platform in platforms:
        posts.extend(
            await repository.list_all_posts(
                platform=platform,
                start_at=start_at,
                end_at=end_at,
                limit=3000,
            )
        )
    posts = _dedupe_posts(posts)
    backtests = await repository.list_backtests(limit=8)
    latest_backtests = [
        _compact_backtest(item)
        for item in backtests
        if item.get("report")
    ][:4]
    platform_counts = Counter(str(post.get("platform") or "unknown") for post in posts)
    keyword_counts = _keyword_counts(posts)
    top_posts = sorted(posts, key=_engagement_total, reverse=True)[:20]
    return {
        "window": {
            "days": window_days,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
        "scope": {
            "platforms": platforms,
            "vertical_id": vertical_id,
            "scene_pack_id": scene_pack_id,
        },
        "sample": {
            "total_posts": len(posts),
            "platform_counts": dict(platform_counts),
            "keyword_counts": keyword_counts,
        },
        "latest_backtests": latest_backtests,
        "top_posts": [_compact_post(item) for item in top_posts],
    }


def build_ai_insight_prompt(input_summary: dict[str, Any]) -> str:
    schema = {
        "executive_summary": "string, 120 Chinese characters max",
        "hotspots": [
            {
                "name": "热点名称",
                "platform": "xhs|dy|all",
                "heat_level": "high|watch|experimental",
                "confidence": "high|medium|low",
                "reason": "必须基于证据解释",
                "evidence_refs": {"keywords": ["..."], "post_titles": ["..."], "sample_count": 0},
                "platform_strategy": {"xhs": "小红书建议", "dy": "抖音建议"},
                "risk_notes": ["风险"],
            }
        ],
        "topic_ideas": [
            {
                "title": "选题标题",
                "platform": "xhs|dy",
                "target_audience": "目标人群",
                "keywords": ["关键词"],
                "content_angle": "内容角度",
                "outline": ["开头", "主体", "结尾"],
                "reason": "为什么现在值得做",
                "evidence_refs": {"keywords": ["..."], "post_titles": ["..."]},
                "risk_notes": ["风险"],
                "expected_effect": "预期效果",
            }
        ],
        "platform_strategy": {"xhs": "策略", "dy": "策略"},
        "risk_notes": ["全局风险"],
    }
    return (
        "你是社交媒体增长情报分析师，只能基于给定数据做分析，不能编造外部事实。\n"
        "任务：分析最近热点，并直接给出可执行的新选题。热点和选题会自动入库，所以必须严格、保守、可解释。\n"
        "硬性要求：\n"
        "1. 所有热点必须绑定 evidence_refs，至少包含关键词或帖子标题。\n"
        "2. 不要声称平台已经确定推流/限流，只能说疑似升温、降温或需要观察。\n"
        "3. 小红书选题偏经验、避坑、清单、情绪共鸣、家长视角；抖音选题偏强结论、冲突、规则变化、案例拆解。\n"
        "4. 每个平台至少给 3 个选题，总选题 6-10 个；热点 3-6 个。\n"
        "5. 选题必须包含目标人群、关键词、内容角度、结构、推荐理由、风险。\n"
        "6. 如果样本不足，要降低 confidence，并在 risk_notes 说明。\n"
        "7. 只返回 JSON，不要 Markdown，不要解释 JSON 之外的文字。\n"
        f"输出 JSON schema 示例：{json.dumps(schema, ensure_ascii=False)}\n"
        f"输入数据：{json.dumps(input_summary, ensure_ascii=False, default=str)}"
    )


def build_rule_based_ai_insight_fallback(input_summary: dict[str, Any]) -> dict[str, Any]:
    keyword_counts = input_summary.get("sample", {}).get("keyword_counts") or {}
    sorted_keywords = sorted(keyword_counts.items(), key=lambda item: int(item[1] or 0), reverse=True)
    top_keywords = [item[0] for item in sorted_keywords[:5]]
    hotspots = [
        {
            "name": keyword,
            "platform": "all",
            "heat_level": "watch",
            "confidence": "medium" if count >= 100 else "low",
            "reason": f"近 7 天样本中「{keyword}」出现 {count} 次，适合进入选题观察池。",
            "evidence_refs": {"keywords": [keyword], "sample_count": count},
            "platform_strategy": {
                "xhs": "用经验、避坑、清单角度测试。",
                "dy": "用强结论、冲突和案例拆解角度测试。",
            },
            "risk_notes": ["这是规则降级结果，未经过 AI 深度归纳。"],
        }
        for keyword, count in sorted_keywords[:5]
    ]
    topic_ideas = []
    for platform in ["xhs", "dy"]:
        for keyword in top_keywords[:4]:
            topic_ideas.append(
                {
                    "title": _fallback_title(platform, keyword),
                    "platform": platform,
                    "target_audience": "K12 教育家长 / 单亲妈妈 / 升学规划人群",
                    "keywords": [keyword],
                    "content_angle": "基于高频关键词做场景化内容测试",
                    "outline": ["抛出痛点", "给出具体场景", "提供 3 个可执行建议", "引导评论补充"],
                    "reason": f"「{keyword}」在当前样本中出现频率靠前，适合先做低成本内容测试。",
                    "evidence_refs": {"keywords": [keyword]},
                    "risk_notes": ["规则生成选题，需要人工看标题语气是否过度焦虑。"],
                    "expected_effect": "验证关键词点击和互动反馈。",
                }
            )
    return {
        "executive_summary": "AI 调用失败，已用规则生成热点和选题，适合作为临时观察建议。",
        "hotspots": hotspots,
        "topic_ideas": topic_ideas,
        "platform_strategy": {
            "xhs": "优先测试经验、避坑、清单和情绪共鸣内容。",
            "dy": "优先测试强结论、冲突、规则变化和案例拆解内容。",
        },
        "risk_notes": ["当前为规则降级输出，请在 Provider 恢复后重新运行 AI 分析。"],
    }


async def _resolve_provider(repository: Any, provider_config_id: int | None) -> dict[str, Any]:
    if provider_config_id:
        provider = await repository.get_ai_provider(provider_config_id, include_secret=True)
        if provider:
            return provider
        raise ValueError("AI provider config not found")
    providers = await repository.list_ai_providers()
    enabled = [item for item in providers if item.get("enabled") and item.get("api_key_set")]
    preferred = next((item for item in enabled if "4router" in str(item.get("name") or "").lower()), None)
    selected = preferred or (enabled[0] if enabled else None)
    if selected is None:
        raise ValueError("No enabled AI provider with API key is configured")
    provider = await repository.get_ai_provider(selected["id"], include_secret=True)
    if provider is None:
        raise ValueError("AI provider config not found")
    return provider


def _normalize_ai_output(output: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise ValueError("AI output must be a JSON object")
    hotspots = output.get("hotspots")
    ideas = output.get("topic_ideas")
    if not isinstance(hotspots, list) or not isinstance(ideas, list):
        raise ValueError("AI output must include hotspots and topic_ideas arrays")
    return {
        "executive_summary": str(output.get("executive_summary") or ""),
        "hotspots": [_normalize_hotspot(item) for item in hotspots[:8] if isinstance(item, dict)],
        "topic_ideas": [_normalize_topic(item) for item in ideas[:12] if isinstance(item, dict)],
        "platform_strategy": output.get("platform_strategy") if isinstance(output.get("platform_strategy"), dict) else {},
        "risk_notes": output.get("risk_notes") if isinstance(output.get("risk_notes"), list) else [],
    }


def _normalize_hotspot(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("name") or "未命名热点"),
        "platform": _platform(item.get("platform")),
        "heat_level": str(item.get("heat_level") or "watch"),
        "confidence": _confidence(item.get("confidence")),
        "reason": str(item.get("reason") or "AI 未提供理由"),
        "evidence": item.get("evidence_refs") or item.get("evidence") or {},
        "platform_strategy": item.get("platform_strategy") if isinstance(item.get("platform_strategy"), dict) else {},
        "risk_notes": item.get("risk_notes") if isinstance(item.get("risk_notes"), list) else [],
    }


def _normalize_topic(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(item.get("title") or "未命名选题"),
        "platform": _platform(item.get("platform"), default="xhs"),
        "target_audience": item.get("target_audience"),
        "keywords": item.get("keywords") if isinstance(item.get("keywords"), list) else [],
        "content_angle": item.get("content_angle") or item.get("angle"),
        "outline": item.get("outline") if isinstance(item.get("outline"), list) else [],
        "reason": str(item.get("reason") or "AI 未提供理由"),
        "evidence": item.get("evidence_refs") or item.get("evidence") or {},
        "risk_notes": item.get("risk_notes") if isinstance(item.get("risk_notes"), list) else [],
        "expected_effect": item.get("expected_effect"),
        "status": "active",
    }


def _platform(value: Any, *, default: str = "all") -> str:
    text = str(value or default).lower()
    return text if text in {"all", "xhs", "dy", "wb", "bili", "zhihu"} else default


def _confidence(value: Any) -> str:
    text = str(value or "low").lower()
    return text if text in {"high", "medium", "low"} else "low"


def _keyword_counts(posts: list[dict[str, Any]]) -> dict[str, int]:
    keywords = ["K12教育", "单亲妈妈", "家庭教育", "教育规划", "小升初", "暑假班", "新东方", "学而思"]
    result: dict[str, int] = {}
    for keyword in keywords:
        result[keyword] = sum(1 for post in posts if keyword.lower() in _post_text(post))
    return result


def _compact_backtest(item: dict[str, Any]) -> dict[str, Any]:
    report = item.get("report") or {}
    latest = report.get("latest_keywords") or []
    return {
        "id": item.get("id"),
        "scenario": item.get("scenario"),
        "sample": report.get("sample") or {},
        "platform_summary": report.get("platform_summary") or [],
        "latest_keywords": [
            {
                "keyword": row.get("keyword"),
                "label": row.get("label"),
                "heat_score": row.get("heat_score"),
                "confidence": row.get("confidence"),
                "sample_count": row.get("sample_count"),
            }
            for row in latest[:8]
        ],
    }


def _compact_post(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": item.get("platform"),
        "title": item.get("title"),
        "source_keyword": (item.get("engagement_json") or {}).get("source_keyword"),
        "publish_time": item.get("publish_time"),
        "engagement": _engagement_total(item),
    }


def _engagement_total(post: dict[str, Any]) -> int:
    engagement = post.get("engagement_json") or {}
    total = 0
    for key in ("liked_count", "like_count", "comment_count", "share_count", "collected_count"):
        try:
            total += int(engagement.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _post_text(post: dict[str, Any]) -> str:
    engagement = post.get("engagement_json") or {}
    return " ".join(
        [
            str(post.get("title") or ""),
            str(post.get("content") or ""),
            str(engagement.get("source_keyword") or ""),
            str(engagement.get("tag_list") or ""),
        ]
    ).lower()


def _dedupe_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for post in posts:
        key = (str(post.get("platform") or ""), str(post.get("platform_post_id") or post.get("id")))
        if key in seen:
            continue
        seen.add(key)
        result.append(post)
    return result


def _fallback_title(platform: str, keyword: str) -> str:
    if platform == "dy":
        return f"{keyword}正在变热？3个信号判断现在要不要跟"
    return f"{keyword}相关内容怎么做？给家长看的3个真实场景"


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))

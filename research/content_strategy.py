from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any


PLATFORM_ALIASES = {
    "all": None,
    "douyin": "dy",
    "dy": "dy",
    "xhs": "xhs",
    "xiaohongshu": "xhs",
    "bili": "bili",
    "bilibili": "bili",
    "video": "video",
    "wb": "wb",
    "weibo": "wb",
}

PLATFORM_LABELS = {
    "dy": "抖音",
    "xhs": "小红书",
    "bili": "B站",
    "wb": "微博",
    "weibo": "微博",
    "video": "视频号",
    "ks": "快手",
    "zhihu": "知乎",
    "tieba": "贴吧",
    None: "全部平台",
}

GOAL_LABELS = {
    "conversion": "获客转化",
    "engagement": "种草互动",
    "awareness": "品牌声量",
}

RISK_LABELS = {
    "small_sample_spike": "小样本异常升温",
    "single_platform_signal": "单平台信号",
    "stale_data": "数据过旧",
    "overheated_competition": "竞争过热",
    "missing_execution_parameters": "执行参数缺失",
    "high_cost": "执行成本偏高",
}

PAIN_RULES = [
    ("选择困难", ["怎么选", "推荐", "哪个好", "避坑", "清单", "攻略", "挑选", "选择"]),
    ("安全顾虑", ["风险", "副作用", "踩坑", "危害", "敏感", "过敏", "焦虑", "不要", "注意"]),
    ("成本价格", ["价格", "多少钱", "预算", "省钱", "性价比", "贵", "便宜", "成本"]),
    ("效果验证", ["测评", "对比", "效果", "真实", "结果", "案例", "复盘", "体验"]),
    ("新手入门", ["新手", "入门", "第一周", "基础", "教程", "步骤", "小白", "0-6"]),
]

FRAMEWORK_RULES = [
    ("避坑清单型", ["避坑", "不要", "踩坑", "误区", "注意"], ["风险拆解", "清单", "低成本验证"]),
    ("对比测评型", ["测评", "对比", "横评", "区别", "怎么选"], ["测评", "对比", "决策辅助"]),
    ("案例拆解型", ["案例", "复盘", "真实", "过程", "全过程"], ["案例", "过程", "信任建立"]),
    ("步骤教程型", ["步骤", "教程", "方法", "指南", "攻略"], ["教程", "可执行", "收藏"]),
    ("情绪共鸣型", ["焦虑", "后悔", "崩溃", "终于", "普通人"], ["共鸣", "痛点", "评论互动"]),
]

PAIN_COLORS = ["#0f8f85", "#2cbaa7", "#86d2c6", "#d9c089", "#bed3d8", "#dfe8e5"]
MIX_COLORS = ["#0f8f85", "#2d9fd6", "#f59d48", "#9ac9be", "#ef7d57"]
TRAFFIC_COLORS = ["#0f8f85", "#ff7d66", "#efc261", "#58a6ff", "#7cb6cc", "#dfe8e5"]
DISPLAY_NUMBER_PATTERN = re.compile(r"^\s*\d+(?:[\.,]\d+)?\s*(?:[kKwW万])?\s*$")


def normalize_strategy_filters(
    *,
    platform: str | None,
    time_range: str,
    goal: str,
    audience: str,
    stage: str,
) -> dict[str, Any]:
    normalized_platform = PLATFORM_ALIASES.get(str(platform or "all"), platform)
    window_days = {"7d": 7, "30d": 30, "90d": 90}.get(str(time_range or "30d"), 30)
    summary = {
        "platform": normalized_platform,
        "platform_label": PLATFORM_LABELS.get(normalized_platform, str(normalized_platform or "全部平台")),
        "range": time_range if time_range in {"7d", "30d", "90d"} else "30d",
        "window_days": window_days,
        "goal": goal if goal in GOAL_LABELS else "conversion",
        "goal_label": GOAL_LABELS.get(goal, GOAL_LABELS["conversion"]),
        "audience": audience or "all",
        "stage": stage or "boost",
    }
    return summary


def build_content_strategy_summary(
    *,
    filters: dict[str, Any],
    dashboard: dict[str, Any],
    posts: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    ai_insights: dict[str, Any],
    ai_topic_ideas: list[dict[str, Any]],
    ai_strategy_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    posts = _dedupe_posts(posts)
    opportunities = list(dashboard.get("opportunities") or [])
    top_opportunities = list(dashboard.get("top_opportunities") or opportunities[:5])
    watchlist = list(dashboard.get("watchlist") or [])
    diagnostics = list(dashboard.get("diagnostics") or [])
    keyword_trends = _build_keyword_trends(keyword_heat_snapshots, opportunities, posts)
    suggestions = _build_suggestions(
        ai_topic_ideas=ai_topic_ideas,
        opportunities=top_opportunities + watchlist,
        keyword_trends=keyword_trends,
        filters=filters,
    )
    frameworks = _build_frameworks(posts, opportunities)
    competitor_samples = _build_competitor_samples(competitor_compositions, opportunities)
    pain_distribution = _build_pain_distribution(posts, suggestions, opportunities)
    risks = _build_risks(
        dashboard=dashboard,
        opportunities=opportunities + watchlist,
        content_snapshots=content_snapshots,
        ai_insights=ai_insights,
    )
    weekly_mix = _build_weekly_mix(filters, suggestions, frameworks)
    traffic_share = _build_traffic_share(posts, content_snapshots, competitor_compositions)
    evidence_pack = _build_evidence_pack(
        suggestions=suggestions,
        keyword_trends=keyword_trends,
        competitor_samples=competitor_samples,
        posts=posts,
        risks=risks,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    latest_at = _latest_timestamp(
        keyword_heat_snapshots + content_snapshots + competitor_compositions + posts
    ) or generated_at
    decision = dashboard.get("decision") or {}
    summary = {
        "generated_at": generated_at,
        "filters": filters,
        "hero": {
            "headline": decision.get("headline") or "当前样本不足，建议先补充采集后再形成策略判断。",
            "sample_summary": decision.get("sample_summary") or "暂无可用样本摘要。",
            "confidence": decision.get("confidence") or "low",
            "updated_at": latest_at,
            "evidence_count": int(decision.get("evidence_count") or len(evidence_pack["items"])),
        },
        "ai_status": {
            "enabled": bool((ai_insights.get("run") or {}).get("id") or ai_topic_ideas),
            "source": "latest_ai_topic_ideas" if ai_topic_ideas else "deterministic_rules",
            "run": ai_insights.get("run"),
        },
        "metrics": _build_metrics(
            opportunities=opportunities,
            keyword_trends=keyword_trends,
            content_snapshots=content_snapshots,
        ),
        "pain_distribution": pain_distribution,
        "keyword_trends": keyword_trends,
        "frameworks": frameworks,
        "suggestions": suggestions,
        "competitor_samples": competitor_samples,
        "risks": risks,
        "weekly_mix": weekly_mix,
        "traffic_share": traffic_share,
        "evidence_pack": evidence_pack,
        "diagnostics": diagnostics,
    }
    summary["strategy_note"] = ""
    summary["section_sources"] = _default_section_sources()
    if ai_strategy_summary:
        _apply_ai_strategy_summary(summary, ai_strategy_summary)
    return summary


def build_content_strategy_ai_input(
    *,
    filters: dict[str, Any],
    project_record: dict[str, Any],
    keyword_rows: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    base_summary: dict[str, Any],
) -> dict[str, Any]:
    scoped_posts = _dedupe_posts(posts)
    top_posts = sorted(
        scoped_posts,
        key=lambda item: _engagement_total(item.get("engagement_json") or {}),
        reverse=True,
    )[:12]
    keyword_snapshot_rows = [
        {
            "keyword": str(item.get("keyword") or ""),
            "platform": item.get("platform"),
            "heat_score": float(item.get("heat_score") or 0),
            "growth_score": float(item.get("growth_score") or 0),
        }
        for item in keyword_heat_snapshots[:10]
    ]
    tracking_rows = [
        {
            "platform": item.get("platform"),
            "snapshot_date": item.get("snapshot_date"),
            "total_content_count": int(item.get("total_content_count") or 0),
            "hot_post_rate": float(item.get("hot_post_rate") or 0),
        }
        for item in content_snapshots[:8]
    ]
    competitor_rows = [
        {
            "platform": item.get("platform_key") or item.get("platform"),
            "title": item.get("title"),
            "interaction": item.get("interaction"),
        }
        for item in (base_summary.get("competitor_samples") or [])[:8]
    ]
    return {
        "filters": filters,
        "project": {
            "id": project_record.get("id"),
            "name": project_record.get("name"),
            "platforms": project_record.get("platforms") or [],
            "keywords": _collect_active_keywords(keyword_rows),
            "primary_goal": project_record.get("primary_goal"),
        },
        "sample": {
            "post_count": len(scoped_posts),
            "platform_counts": dict(Counter(str(post.get("platform") or "unknown") for post in scoped_posts)),
            "top_posts": [
                {
                    "platform": post.get("platform"),
                    "title": _truncate_text(post.get("title") or post.get("content") or "", limit=96),
                    "engagement": _format_number(_engagement_total(post.get("engagement_json") or {})),
                    "publish_time": _timestamp_string(post.get("publish_time")),
                }
                for post in top_posts
            ],
            "keyword_snapshots": keyword_snapshot_rows,
            "content_tracking": tracking_rows,
            "competitor_samples": competitor_rows,
            "competitor_snapshots": [
                {
                    "platform": item.get("platform"),
                    "total_flow_count": int(item.get("total_flow_count") or 0),
                }
                for item in competitor_compositions[:8]
            ],
        },
        "baseline_summary": _compact_json(
            {
                "hero": base_summary.get("hero") or {},
                "keyword_trends": (base_summary.get("keyword_trends") or [])[:10],
                "frameworks": (base_summary.get("frameworks") or [])[:8],
                "suggestions": (base_summary.get("suggestions") or [])[:12],
                "risks": (base_summary.get("risks") or [])[:8],
                "weekly_mix": (base_summary.get("weekly_mix") or [])[:6],
            },
            limit=14000,
        ),
    }


CONTENT_STRATEGY_AI_SECTIONS = (
    "overview",
    "keyword_trends",
    "frameworks",
    "suggestions",
    "risks",
    "weekly_mix",
)


def build_content_strategy_ai_prompt(input_summary: dict[str, Any]) -> str:
    schema = {
        "executive_summary": "string",
        "hotspots": [
            {
                "name": "string",
                "platform": "xhs|dy|all",
                "heat_level": "high|watch|experimental",
                "confidence": "high|medium|low",
                "reason": "string",
                "evidence_refs": {"keywords": ["string"], "post_titles": ["string"], "sample_count": 0},
                "platform_strategy": {"xhs": "string", "dy": "string"},
                "risk_notes": ["string"],
            }
        ],
        "topic_ideas": [
            {
                "title": "string",
                "platform": "xhs|dy|all",
                "target_audience": "string",
                "keywords": ["string"],
                "content_angle": "string",
                "outline": ["string"],
                "reason": "string",
                "evidence_refs": {"keywords": ["string"], "post_titles": ["string"]},
                "risk_notes": ["string"],
                "expected_effect": "string",
            }
        ],
        "platform_strategy": {"xhs": "string", "dy": "string"},
        "risk_notes": ["string"],
        "content_strategy": {
            "strategy_note": "string",
            "hero": {"headline": "string", "sample_summary": "string", "confidence": "low|medium|high"},
            "keyword_trends": [{"keyword": "string", "platform": "xhs|dy|all", "heat": "string", "score": 0, "direction": "up|down"}],
            "frameworks": [{"title": "string", "tags": ["string"], "posts": 0, "interactions": "string", "leads": 0}],
            "suggestions": [
                {
                    "title": "string",
                    "audience": "string",
                    "chance": 0,
                    "risk": "low|medium|high",
                    "direction": "string",
                    "platform": "xhs|dy|all",
                    "keywords": ["string"],
                    "outline": ["string"],
                    "reason": "string",
                    "risk_notes": ["string"],
                }
            ],
            "risks": [{"title": "string", "detail": "string", "level": "low|medium|high", "count": 0}],
            "weekly_mix": [{"label": "string", "percent": 0, "pieces": 0, "exposure": "string", "leads": 0}],
        },
    }
    return (
        "You are a senior social content strategist. Use only the provided evidence and baseline summary. "
        "All user-facing text fields must be written in Simplified Chinese. "
        "Do not invent external facts, unsupported metrics, or platform policy changes.\n"
        "Rules:\n"
        "1. Return JSON only.\n"
        "2. Reuse baseline quantitative values when possible instead of inventing precise counts.\n"
        "3. Keep recommendations conservative, evidence-bound, and execution-oriented.\n"
        "4. If evidence is weak, lower confidence and explain the limitation in strategy_note or risk_notes.\n"
        "5. keyword_trends 5-10 rows, frameworks 3-6 rows, suggestions 6-12 rows, risks 3-6 rows, weekly_mix 4-6 rows.\n"
        "   keyword_trends must be unique by keyword + platform. Do not repeat the same keyword for the same platform.\n"
        "6. weekly_mix percentages should sum close to 100.\n"
        f"Output schema: {json.dumps(schema, ensure_ascii=False)}\n"
        f"Input: {json.dumps(input_summary, ensure_ascii=False, default=str)}"
    )


def build_content_strategy_ai_section_prompt(input_summary: dict[str, Any], section: str) -> str:
    if section not in CONTENT_STRATEGY_AI_SECTIONS:
        raise ValueError(f"Unsupported content strategy AI section: {section}")
    schema = _content_strategy_ai_section_schema(section)
    rules = [
        "Return JSON only.",
        "Use only the provided evidence and baseline summary.",
        "All user-facing text fields must be written in Simplified Chinese.",
        "Do not invent external facts, unsupported metrics, or platform policy changes.",
        "Reuse baseline quantitative values when possible instead of inventing precise counts.",
    ]
    if section == "keyword_trends":
        rules.append("keyword_trends must be unique by keyword + platform. Return 5-10 rows.")
    elif section == "frameworks":
        rules.append("Return 3-6 reusable content frameworks.")
    elif section == "suggestions":
        rules.append("Return 6-12 execution-ready suggestions. Keep high-opportunity baseline candidates visible.")
    elif section == "risks":
        rules.append("Return 3-6 evidence-bound risk rows.")
    elif section == "weekly_mix":
        rules.append("Return 4-6 rows. Percentages should sum close to 100.")
    else:
        rules.append("Return a short strategy_note and hero only. Keep this section concise.")
    compact_input = _content_strategy_ai_section_input(input_summary, section)
    return (
        "You are a senior social content strategist.\n"
        f"Requested section: {section}\n"
        f"Rules:\n- " + "\n- ".join(rules) + "\n"
        f"Output schema: {json.dumps(schema, ensure_ascii=False)}\n"
        f"Input: {json.dumps(compact_input, ensure_ascii=False, default=str)}"
    )


def normalize_content_strategy_ai_section(
    output: dict[str, Any],
    *,
    section: str,
    fallback_summary: dict[str, Any],
) -> dict[str, Any]:
    if section not in CONTENT_STRATEGY_AI_SECTIONS:
        raise ValueError(f"Unsupported content strategy AI section: {section}")
    if not isinstance(output, dict):
        raise ValueError("AI strategy section output must be a JSON object")
    strategy = output.get("content_strategy")
    if not isinstance(strategy, dict):
        raise ValueError("AI strategy section output must include content_strategy")
    if section == "overview":
        result: dict[str, Any] = {}
        strategy_note = str(strategy.get("strategy_note") or output.get("executive_summary") or "").strip()
        if strategy_note:
            result["strategy_note"] = strategy_note
        hero = _normalize_ai_hero(strategy.get("hero"), fallback_summary.get("hero") or {})
        if hero.get("headline") or hero.get("sample_summary"):
            result["hero"] = hero
        return result
    if section == "keyword_trends":
        rows = _normalize_ai_keyword_trends(strategy.get("keyword_trends"), fallback_summary.get("keyword_trends") or [])
        return {"keyword_trends": rows} if rows else {}
    if section == "frameworks":
        rows = _normalize_ai_frameworks(strategy.get("frameworks"), fallback_summary.get("frameworks") or [])
        return {"frameworks": rows} if rows else {}
    if section == "suggestions":
        rows = _normalize_ai_suggestions(strategy.get("suggestions"), fallback_summary.get("suggestions") or [])
        return {"suggestions": rows} if rows else {}
    if section == "risks":
        rows = _normalize_ai_risks(strategy.get("risks"), fallback_summary.get("risks") or [])
        return {"risks": rows} if rows else {}
    rows = _normalize_ai_weekly_mix(strategy.get("weekly_mix"), fallback_summary.get("weekly_mix") or [])
    return {"weekly_mix": rows} if rows else {}


def _content_strategy_ai_section_schema(section: str) -> dict[str, Any]:
    content_schema: dict[str, Any]
    if section == "overview":
        content_schema = {
            "strategy_note": "string",
            "hero": {"headline": "string", "sample_summary": "string", "confidence": "low|medium|high"},
        }
    elif section == "keyword_trends":
        content_schema = {
            "keyword_trends": [
                {"keyword": "string", "platform": "xhs|dy|all", "heat": "string", "score": 0, "direction": "up|down"}
            ]
        }
    elif section == "frameworks":
        content_schema = {
            "frameworks": [{"title": "string", "tags": ["string"], "posts": 0, "interactions": "string", "leads": 0}]
        }
    elif section == "suggestions":
        content_schema = {
            "suggestions": [
                {
                    "title": "string",
                    "audience": "string",
                    "chance": 0,
                    "risk": "low|medium|high",
                    "direction": "string",
                    "platform": "xhs|dy|all",
                    "keywords": ["string"],
                    "outline": ["string"],
                    "reason": "string",
                    "risk_notes": ["string"],
                }
            ]
        }
    elif section == "risks":
        content_schema = {"risks": [{"title": "string", "detail": "string", "level": "low|medium|high", "count": 0}]}
    else:
        content_schema = {"weekly_mix": [{"label": "string", "percent": 0, "pieces": 0, "exposure": "string", "leads": 0}]}
    return {
        "executive_summary": "string",
        "platform_strategy": {"xhs": "string", "dy": "string"},
        "risk_notes": ["string"],
        "content_strategy": content_schema,
    }


def _content_strategy_ai_section_input(input_summary: dict[str, Any], section: str) -> dict[str, Any]:
    baseline = input_summary.get("baseline_summary") if isinstance(input_summary.get("baseline_summary"), dict) else {}
    baseline_keys = {
        "overview": ("hero",),
        "keyword_trends": ("keyword_trends",),
        "frameworks": ("frameworks",),
        "suggestions": ("suggestions", "keyword_trends"),
        "risks": ("risks", "hero"),
        "weekly_mix": ("weekly_mix", "suggestions", "frameworks"),
    }[section]
    compact_baseline = {key: baseline.get(key) for key in baseline_keys if key in baseline}
    sample = input_summary.get("sample") if isinstance(input_summary.get("sample"), dict) else {}
    compact_sample = {
        "post_count": sample.get("post_count"),
        "platform_counts": sample.get("platform_counts"),
        "top_posts": (sample.get("top_posts") or [])[:8],
        "keyword_snapshots": (sample.get("keyword_snapshots") or [])[:8],
        "content_tracking": (sample.get("content_tracking") or [])[:8],
        "competitor_samples": (sample.get("competitor_samples") or [])[:8],
        "competitor_snapshots": (sample.get("competitor_snapshots") or [])[:6],
    }
    return {
        "filters": input_summary.get("filters") or {},
        "project": input_summary.get("project") or {},
        "sample": compact_sample,
        "baseline_summary": compact_baseline,
    }


def normalize_content_strategy_ai_summary(
    output: dict[str, Any],
    *,
    fallback_summary: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise ValueError("AI strategy output must be a JSON object")
    strategy = output.get("content_strategy")
    if not isinstance(strategy, dict):
        raise ValueError("AI strategy output must include content_strategy")
    return {
        "strategy_note": str(strategy.get("strategy_note") or output.get("executive_summary") or "").strip(),
        "hero": _normalize_ai_hero(strategy.get("hero"), fallback_summary.get("hero") or {}),
        "keyword_trends": _normalize_ai_keyword_trends(
            strategy.get("keyword_trends"),
            fallback_summary.get("keyword_trends") or [],
        ),
        "frameworks": _normalize_ai_frameworks(
            strategy.get("frameworks"),
            fallback_summary.get("frameworks") or [],
        ),
        "suggestions": _normalize_ai_suggestions(
            strategy.get("suggestions"),
            fallback_summary.get("suggestions") or [],
        ),
        "risks": _normalize_ai_risks(
            strategy.get("risks"),
            fallback_summary.get("risks") or [],
        ),
        "weekly_mix": _normalize_ai_weekly_mix(
            strategy.get("weekly_mix"),
            fallback_summary.get("weekly_mix") or [],
        ),
    }


def build_content_strategy_ai_fallback(
    fallback_summary: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    return {
        "strategy_note": f"AI 暂不可用，当前展示规则托底策略。原因：{reason}",
        "hero": dict(fallback_summary.get("hero") or {}),
        "keyword_trends": list(fallback_summary.get("keyword_trends") or []),
        "frameworks": list(fallback_summary.get("frameworks") or []),
        "suggestions": list(fallback_summary.get("suggestions") or []),
        "risks": list(fallback_summary.get("risks") or []),
        "weekly_mix": list(fallback_summary.get("weekly_mix") or []),
    }


def _apply_ai_strategy_summary(summary: dict[str, Any], ai_strategy_summary: dict[str, Any]) -> None:
    section_sources = dict(summary.get("section_sources") or _default_section_sources())
    strategy_note = str(ai_strategy_summary.get("strategy_note") or "").strip()
    if strategy_note:
        summary["strategy_note"] = strategy_note

    hero = ai_strategy_summary.get("hero") if isinstance(ai_strategy_summary.get("hero"), dict) else {}
    if hero.get("headline") or hero.get("sample_summary"):
        hero_updates = {
            key: value
            for key, value in hero.items()
            if value not in (None, "") and value != [] and value != {}
        }
        summary["hero"] = {
            **summary.get("hero", {}),
            **hero_updates,
        }
        section_sources["hero"] = "ai"

    for key in ("keyword_trends", "frameworks", "suggestions", "risks", "weekly_mix"):
        rows = ai_strategy_summary.get(key)
        if isinstance(rows, list) and rows:
            if key == "keyword_trends":
                rows = _dedupe_keyword_trends(rows)
            if key == "suggestions":
                summary[key] = _merge_ai_suggestions_with_fallback(
                    ai_rows=rows,
                    fallback_rows=summary.get("suggestions") or [],
                )
            elif key == "frameworks":
                normalized_frameworks = _normalize_ai_frameworks(
                    rows,
                    summary.get("frameworks") or [],
                )
                if not normalized_frameworks:
                    continue
                summary[key] = normalized_frameworks
            else:
                summary[key] = rows
            section_sources[key] = "ai"

    summary["section_sources"] = section_sources


def _merge_ai_suggestions_with_fallback(
    *,
    ai_rows: list[dict[str, Any]],
    fallback_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ai_unique = _unique_suggestions(ai_rows)
    ai_keys = {_suggestion_key(row) for row in ai_unique}
    protected_fallback = [
        row
        for row in _unique_suggestions(fallback_rows)
        if _is_high_value_suggestion(row)
        and _suggestion_key(row) not in ai_keys
    ]
    protected_keys = {_suggestion_key(row) for row in protected_fallback}
    fallback_other = [
        row
        for row in _unique_suggestions(fallback_rows)
        if _suggestion_key(row) not in ai_keys
        and _suggestion_key(row) not in protected_keys
    ]

    ai_limit = max(0, 12 - len(protected_fallback))
    merged = [*ai_unique[:ai_limit], *protected_fallback]
    seen = {_suggestion_key(row) for row in merged}
    for row in fallback_other:
        key = _suggestion_key(row)
        if key in seen:
            continue
        merged.append(row)
        seen.add(key)
        if len(merged) >= 12:
            break
    return merged[:12]


def _unique_suggestions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _suggestion_key(row)
        if not key[1]:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _suggestion_key(row: dict[str, Any]) -> tuple[str, str]:
    platform = str(row.get("platform") or "").strip()
    title_value = row.get("match_title") or row.get("title")
    title = " ".join(str(title_value or "").split()).lower()
    return platform, title


def _is_high_value_suggestion(row: dict[str, Any]) -> bool:
    if str(row.get("id") or "").startswith("keyword-trend:"):
        return False
    return _bounded_number(row.get("chance"), 0, minimum=0.0, maximum=100.0) >= 75


def _limit_suggestions_preserving_high_value(
    rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    protected = [row for row in rows if _is_high_value_suggestion(row)]
    protected_keys = {_suggestion_key(row) for row in protected}
    others = [row for row in rows if _suggestion_key(row) not in protected_keys]
    return [*protected[:limit], *others[: max(0, limit - len(protected))]][:limit]


def build_content_strategy_draft_prompt(
    *,
    kind: str,
    payload: dict[str, Any],
    context: dict[str, Any],
    filters: dict[str, Any],
) -> str:
    schema = {
        "title": "string",
        "summary": "string",
        "sections": [{"heading": "string", "items": ["string"]}],
        "body": "string",
        "checklist": ["string"],
        "risk_notes": ["string"],
    }
    compact_context = {
        "kind": kind,
        "filters": filters,
        "payload": payload,
        "context": _compact_json(context, limit=6000),
    }
    return (
        "你是内容增长策略负责人。只能基于输入证据生成策略草稿，不要编造外部平台事实。\n"
        "任务类型：copy=生成单条内容文案，weekly_plan=生成本周内容计划，topic_pack=生成选题包，"
        "framework=把框架改成可执行模板，evidence_summary=总结证据集。\n"
        "要求：\n"
        "1. 只返回 JSON，不要 Markdown。\n"
        "2. 输出必须包含 title、summary、sections、body、checklist、risk_notes。\n"
        "3. 所有建议都要能从输入的标题、关键词、证据样本或风险中推出。\n"
        "4. 如果证据不足，在 risk_notes 里说明，并把 checklist 的第一步设为补样本。\n"
        "5. 文案语气克制，不使用绝对化、恐吓式、医疗功效承诺或虚假背书。\n"
        f"JSON schema 示例：{json.dumps(schema, ensure_ascii=False)}\n"
        f"输入证据：{json.dumps(compact_context, ensure_ascii=False, default=str)}"
    )


def normalize_strategy_draft_output(output: dict[str, Any], *, source_payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(output, dict):
        return build_strategy_draft_fallback(source_payload, reason="AI 返回不是 JSON 对象")
    sections = []
    raw_sections = output.get("sections") if isinstance(output.get("sections"), list) else []
    for item in raw_sections[:8]:
        if not isinstance(item, dict):
            continue
        sections.append(
            {
                "heading": str(item.get("heading") or item.get("title") or "执行段落"),
                "items": _string_list(item.get("items") or item.get("points"))[:8],
            }
        )
    return {
        "title": str(output.get("title") or source_payload.get("title") or "策略草稿"),
        "summary": str(output.get("summary") or ""),
        "sections": sections,
        "body": str(output.get("body") or ""),
        "checklist": _string_list(output.get("checklist"))[:10],
        "risk_notes": _string_list(output.get("risk_notes"))[:8],
        "source_payload": source_payload,
    }


def build_strategy_draft_fallback(source_payload: dict[str, Any], *, reason: str) -> dict[str, Any]:
    title = str(source_payload.get("title") or source_payload.get("name") or "策略草稿")
    keywords = _string_list(source_payload.get("keywords"))[:5]
    if not keywords and source_payload.get("keyword"):
        keywords = [str(source_payload["keyword"])]
    return {
        "title": title,
        "summary": "AI 暂不可用，已按当前证据生成规则草稿。",
        "sections": [
            {
                "heading": "核心角度",
                "items": [
                    f"围绕「{title}」做低成本内容测试。",
                    f"关键词优先使用：{'、'.join(keywords) if keywords else '当前选题标题中的高频词'}。",
                ],
            },
            {
                "heading": "执行结构",
                "items": ["开头直接抛痛点", "中段给出 3 个可执行判断", "结尾引导评论补充场景"],
            },
        ],
        "body": f"{title}\n\n1. 先说明目标人群遇到的具体问题。\n2. 给出可验证的观察点或清单。\n3. 附上风险提醒，避免绝对化表达。",
        "checklist": ["补充 5-10 条同类样本", "检查标题是否过度焦虑", "发布后观察收藏、评论和私信意图"],
        "risk_notes": [reason, "这是规则降级草稿，需要人工复核。"],
        "source_payload": source_payload,
    }


def _default_section_sources() -> dict[str, str]:
    return {
        "hero": "rules",
        "keyword_trends": "rules",
        "frameworks": "rules",
        "suggestions": "rules",
        "risks": "rules",
        "weekly_mix": "rules",
    }


def _collect_active_keywords(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for row in rows:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword or row.get("status") != "active" or row.get("keyword_type") == "excluded":
            continue
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(keyword)
    return keywords


def _normalize_ai_hero(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {}
    return {
        "headline": str(item.get("headline") or fallback.get("headline") or "").strip(),
        "sample_summary": str(item.get("sample_summary") or fallback.get("sample_summary") or "").strip(),
        "confidence": _normalize_confidence(item.get("confidence"), fallback.get("confidence")),
    }


def _normalize_ai_keyword_trends(value: Any, fallback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _list_of_dicts(value)
    if not rows:
        return []
    fallback_by_key = {
        (str(item.get("keyword") or "").strip().lower(), str(item.get("platform") or "").strip()): item
        for item in fallback_rows
    }
    normalized = []
    for index, item in enumerate(rows[:10], start=1):
        keyword = str(item.get("keyword") or "").strip()
        if not keyword:
            continue
        platform = _normalize_ai_platform(item.get("platform"))
        fallback = fallback_by_key.get((keyword.lower(), platform or "")) or fallback_by_key.get((keyword.lower(), ""))
        score = _bounded_number(item.get("score"), (fallback or {}).get("score"), minimum=0.0, maximum=100.0)
        direction = _normalize_direction(item.get("direction"), fallback=(fallback or {}).get("direction"))
        normalized.append(
            {
                "rank": index,
                "keyword": keyword,
                "platform": platform,
                "platform_label": PLATFORM_LABELS.get(platform, platform or "鍏ㄩ儴骞冲彴"),
                "heat": str(item.get("heat") or (fallback or {}).get("heat") or _format_score(score)),
                "score": round(score, 1),
                "direction": direction,
                "points": (fallback or {}).get("points") or _trend_points(score, 8 if direction == "up" else -6),
                "evidence": (fallback or {}).get("evidence") or {},
            }
        )
    return _dedupe_keyword_trends(normalized)


def _dedupe_keyword_trends(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        platform = _normalize_ai_platform(row.get("platform"))
        key = (keyword.lower(), platform or "")
        candidate = {**row, "keyword": keyword, "platform": platform}
        if key not in best_by_key:
            best_by_key[key] = candidate
            order.append(key)
            continue
        current_score = _bounded_number(best_by_key[key].get("score"), 0, minimum=0.0, maximum=100.0)
        next_score = _bounded_number(candidate.get("score"), 0, minimum=0.0, maximum=100.0)
        if next_score > current_score:
            best_by_key[key] = candidate
    deduped = [best_by_key[key] for key in order]
    deduped.sort(key=lambda item: _bounded_number(item.get("score"), 0, minimum=0.0, maximum=100.0), reverse=True)
    for index, item in enumerate(deduped, start=1):
        item["rank"] = index
        item["platform_label"] = PLATFORM_LABELS.get(item.get("platform"), item.get("platform") or "全部平台")
    return deduped


def _normalize_ai_frameworks(value: Any, fallback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _list_of_dicts(value)
    if not rows:
        return []
    fallback_by_title = {
        str(item.get("title") or "").strip().lower(): item
        for item in fallback_rows
        if str(item.get("title") or "").strip()
    }
    normalized = []
    for item in rows:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        fallback = fallback_by_title.get(title.lower())
        posts = _safe_int(item.get("posts"), fallback=(fallback or {}).get("posts"), minimum=1)
        interactions = _framework_interactions_display(
            item.get("interactions"),
            fallback=(fallback or {}).get("interactions"),
            posts=posts,
        )
        normalized.append(
            {
                "title": title,
                "tags": _string_list(item.get("tags"))[:4] or list((fallback or {}).get("tags") or []),
                "posts": posts,
                "interactions": interactions,
                "leads": _safe_int(item.get("leads"), fallback=(fallback or {}).get("leads"), minimum=0),
                "samples": (fallback or {}).get("samples") or [],
            }
        )
    normalized.sort(key=_framework_sort_key, reverse=True)
    return normalized[:8]


def _normalize_ai_suggestions(value: Any, fallback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _list_of_dicts(value)
    if not rows:
        return []
    fallback_by_title = {
        str(item.get("title") or "").strip().lower(): item
        for item in fallback_rows
        if str(item.get("title") or "").strip()
    }
    normalized = []
    for index, item in enumerate(rows[:12], start=1):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        fallback = fallback_by_title.get(title.lower())
        normalized.append(
            {
                "id": str(item.get("id") or (fallback or {}).get("id") or f"ai-suggestion:{index}"),
                "title": title,
                "audience": str(item.get("audience") or (fallback or {}).get("audience") or "泛目标人群"),
                "chance": round(_bounded_number(item.get("chance"), (fallback or {}).get("chance"), minimum=0.0, maximum=100.0), 1),
                "risk": _normalize_ai_risk_label(item.get("risk"), fallback=(fallback or {}).get("risk")),
                "direction": str(item.get("direction") or item.get("reason") or (fallback or {}).get("direction") or "AI 策略判断"),
                "platform": _normalize_ai_platform(item.get("platform") or (fallback or {}).get("platform")),
                "keywords": _string_list(item.get("keywords"))[:6] or list((fallback or {}).get("keywords") or []),
                "outline": _string_list(item.get("outline"))[:6] or list((fallback or {}).get("outline") or []),
                "reason": str(item.get("reason") or (fallback or {}).get("reason") or ""),
                "evidence": (fallback or {}).get("evidence") or {},
                "samples": (fallback or {}).get("samples") or [],
                "source": "ai",
                "risk_notes": _string_list(item.get("risk_notes"))[:6] or list((fallback or {}).get("risk_notes") or []),
            }
        )
    return normalized


def _normalize_ai_risks(value: Any, fallback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _list_of_dicts(value)
    if not rows:
        return []
    fallback_by_title = {
        str(item.get("title") or "").strip().lower(): item
        for item in fallback_rows
        if str(item.get("title") or "").strip()
    }
    normalized = []
    for item in rows[:8]:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        fallback = fallback_by_title.get(title.lower())
        normalized.append(
            {
                "title": title,
                "detail": str(item.get("detail") or (fallback or {}).get("detail") or ""),
                "level": _normalize_ai_risk_label(item.get("level"), fallback=(fallback or {}).get("level")),
                "count": _safe_int(item.get("count"), fallback=(fallback or {}).get("count"), minimum=1),
            }
        )
    return normalized


def _normalize_ai_weekly_mix(value: Any, fallback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _list_of_dicts(value)
    if not rows:
        return []
    total_pieces = max(1, sum(_safe_int(item.get("pieces"), minimum=0) for item in fallback_rows) or 12)
    total_leads = max(1, sum(_safe_int(item.get("leads"), minimum=0) for item in fallback_rows) or 72)
    leads_per_piece = max(1.0, total_leads / total_pieces)
    normalized = []
    for index, item in enumerate(rows[:6]):
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        percent = _bounded_number(item.get("percent"), fallback=0.0, minimum=1.0, maximum=100.0)
        pieces = _safe_int(item.get("pieces"), fallback=round(total_pieces * percent / 100), minimum=1)
        leads = _safe_int(item.get("leads"), fallback=round(pieces * leads_per_piece), minimum=1)
        exposure_raw = item.get("exposure")
        exposure = (
            str(exposure_raw).strip()
            if exposure_raw not in {None, ""}
            else _format_number(pieces * 420)
        )
        normalized.append(
            {
                "label": label,
                "percent": percent,
                "pieces": pieces,
                "exposure": exposure,
                "leads": leads,
                "color": str(item.get("color") or MIX_COLORS[index % len(MIX_COLORS)]),
            }
        )
    return _rebalance_weekly_mix(normalized)


def _rebalance_weekly_mix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    total = sum(float(item.get("percent") or 0) for item in rows) or 1.0
    normalized = []
    for index, item in enumerate(rows):
        percent = round(float(item.get("percent") or 0) / total * 100, 1)
        normalized.append({**item, "percent": percent, "color": item.get("color") or MIX_COLORS[index % len(MIX_COLORS)]})
    drift = round(100.0 - sum(float(item["percent"]) for item in normalized), 1)
    if normalized:
        normalized[0]["percent"] = round(float(normalized[0]["percent"]) + drift, 1)
    return normalized


def _normalize_ai_risk_label(value: Any, *, fallback: Any = None) -> str:
    text = str(value or fallback or "").strip().lower()
    if "high" in text or "楂?" in text:
        return _risk_level(risk_notes=[], risk_tags=["high_cost"])
    if "medium" in text or "mid" in text or "涓?" in text:
        return _risk_level(risk_notes=["note"], risk_tags=[])
    if "low" in text or "浣?" in text:
        return _risk_level(risk_notes=[], risk_tags=[])
    return str(fallback or _risk_level(risk_notes=[], risk_tags=[]))


def _normalize_confidence(value: Any, fallback: Any = None) -> str:
    text = str(value or fallback or "").strip().lower()
    if text in {"low", "medium", "high"}:
        return text
    if "high" in text:
        return "high"
    if "medium" in text or "mid" in text:
        return "medium"
    return "low"


def _normalize_direction(value: Any, *, fallback: Any = None) -> str:
    text = str(value or fallback or "").strip().lower()
    return "down" if text == "down" else "up"


def _normalize_ai_platform(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"", "all", "none", "null"}:
        return None
    return PLATFORM_ALIASES.get(text, text)


def _bounded_number(value: Any, fallback: Any, *, minimum: float, maximum: float) -> float:
    for candidate in (value, fallback):
        try:
            number = float(candidate)
            return max(minimum, min(maximum, number))
        except (TypeError, ValueError):
            continue
    return minimum


def _safe_int(value: Any, *, fallback: Any = 0, minimum: int = 0) -> int:
    for candidate in (value, fallback):
        try:
            return max(minimum, int(round(float(candidate))))
        except (TypeError, ValueError):
            continue
    return minimum


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _build_metrics(
    *,
    opportunities: list[dict[str, Any]],
    keyword_trends: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    high_opportunity = len([item for item in opportunities if float(item.get("score") or 0) >= 75])
    high_interaction = len([item for item in opportunities if float(item.get("trend_7d") or 0) >= 50])
    low_competition = len(
        [
            item
            for item in opportunities
            if float((item.get("score_breakdown") or {}).get("competition_gap") or 0) >= 70
        ]
    )
    trending = len([item for item in keyword_trends if item.get("direction") == "up"])
    sample_count = sum(int(item.get("total_content_count") or 0) for item in content_snapshots)
    return [
        {
            "label": "高机会",
            "value": str(high_opportunity),
            "hint": "机会值超过 75，可进入执行评估",
            "accent": "danger",
            "key": "high_opportunity",
        },
        {
            "label": "高互动",
            "value": str(high_interaction),
            "hint": "近周期互动或热度信号较强",
            "accent": "orange",
            "key": "high_interaction",
        },
        {
            "label": "低竞争",
            "value": str(low_competition),
            "hint": "供给缺口较明显，适合测试差异化",
            "accent": "green",
            "key": "low_competition",
        },
        {
            "label": "趋势上升",
            "value": str(trending),
            "hint": f"已纳入 {sample_count} 条内容样本辅助判断",
            "accent": "teal",
            "key": "trending_up",
        },
    ]


def _build_pain_distribution(
    posts: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    texts = [_post_text(post) for post in posts]
    texts.extend(str(item.get("title") or "") for item in suggestions)
    texts.extend(str(item.get("display_title") or item.get("name") or "") for item in opportunities)
    counts: Counter[str] = Counter()
    for text in texts:
        lowered = text.lower()
        matched = False
        for label, terms in PAIN_RULES:
            if any(term.lower() in lowered for term in terms):
                counts[label] += 1
                matched = True
        if not matched and text.strip():
            counts["其他"] += 1
    if not counts:
        counts["其他"] = 1
    total = sum(counts.values()) or 1
    rows = []
    ordered_labels = [label for label, _ in PAIN_RULES] + ["其他"]
    for index, label in enumerate(ordered_labels):
        count = counts.get(label, 0)
        if count <= 0:
            continue
        rows.append(
            {
                "label": label,
                "value": round(count / total * 100, 1),
                "count": count,
                "color": PAIN_COLORS[index % len(PAIN_COLORS)],
            }
        )
    return rows


def _build_keyword_trends(
    snapshots: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for snapshot in snapshots:
        keyword = str(snapshot.get("keyword") or "").strip()
        if not keyword:
            continue
        platform = snapshot.get("platform")
        key = (keyword, platform)
        if key in seen:
            continue
        seen.add(key)
        heat = float(snapshot.get("heat_score") or 0)
        growth = float(snapshot.get("growth_score") or 0)
        score = round(min(100.0, heat * 0.65 + growth * 0.35), 1)
        rows.append(
            {
                "rank": 0,
                "keyword": keyword,
                "platform": platform,
                "platform_label": PLATFORM_LABELS.get(platform, platform or "全部平台"),
                "heat": _format_score(heat),
                "score": score,
                "direction": "up" if growth >= 0 else "down",
                "points": _trend_points(score, growth),
                "evidence": snapshot.get("evidence") or {},
            }
        )
    if len(rows) < 5:
        rows.extend(_keyword_rows_from_opportunities(opportunities, seen))
    if len(rows) < 5:
        rows.extend(_keyword_rows_from_posts(posts, seen))
    rows.sort(key=lambda item: float(item["score"]), reverse=True)
    for index, row in enumerate(rows[:10], start=1):
        row["rank"] = index
    return rows[:10]


def _build_suggestions(
    *,
    ai_topic_ideas: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    keyword_trends: list[dict[str, Any]],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for idea in ai_topic_ideas:
        if not _platform_matches(idea.get("platform"), filters.get("platform")):
            continue
        title = str(idea.get("title") or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        risk_notes = _string_list(idea.get("risk_notes"))
        rows.append(
            {
                "id": f"ai-topic:{idea.get('id') or len(rows) + 1}",
                "title": title,
                "audience": idea.get("target_audience") or _audience_label(filters.get("audience")),
                "chance": _chance_from_confidence(idea.get("confidence"), base=82),
                "risk": _risk_level(risk_notes=risk_notes, risk_tags=[]),
                "direction": idea.get("content_angle") or idea.get("reason") or "AI 选题建议",
                "platform": idea.get("platform"),
                "keywords": _string_list(idea.get("keywords")),
                "outline": _string_list(idea.get("outline")),
                "reason": idea.get("reason") or "",
                "evidence": idea.get("evidence") or {},
                "source": "ai",
                "risk_notes": risk_notes,
            }
        )
    for opportunity in opportunities:
        title = str(opportunity.get("display_title") or opportunity.get("name") or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        payload = opportunity.get("payload") or {}
        keywords = _string_list(payload.get("keywords"))
        if payload.get("keyword") and not keywords:
            keywords = [str(payload["keyword"])]
        rows.append(
            {
                "id": opportunity.get("id") or f"opportunity:{len(rows) + 1}",
                "title": _topic_title_from_opportunity(title, opportunity.get("type")),
                "match_title": title,
                "audience": _audience_label(filters.get("audience")),
                "chance": round(float(opportunity.get("score") or 0), 1),
                "risk": _risk_level(risk_notes=[], risk_tags=opportunity.get("risk_tags") or []),
                "direction": opportunity.get("reason") or "机会评分生成",
                "platform": opportunity.get("platform"),
                "keywords": keywords,
                "outline": ["痛点开场", "证据拆解", "给出可执行建议", "评论引导"],
                "reason": opportunity.get("reason") or "",
                "evidence": (opportunity.get("detail") or {}).get("evidence") or {},
                "samples": opportunity.get("samples") or [],
                "source": "rules",
                "risk_notes": [RISK_LABELS.get(tag, tag) for tag in opportunity.get("risk_tags") or []],
            }
        )
    for trend in keyword_trends:
        title = f"{trend['keyword']}怎么做？3 个信号判断是否值得跟"
        if title in seen_titles:
            continue
        seen_titles.add(title)
        rows.append(
            {
                "id": f"keyword-trend:{trend['keyword']}",
                "title": title,
                "audience": _audience_label(filters.get("audience")),
                "chance": trend["score"],
                "risk": "低风险" if trend["score"] >= 70 else "中风险",
                "direction": "关键词趋势生成",
                "platform": trend.get("platform"),
                "keywords": [trend["keyword"]],
                "outline": ["先讲判断标准", "再拆当前样本信号", "最后给出测试动作"],
                "reason": f"关键词热度分 {trend['score']}，适合做小样本测试。",
                "evidence": trend.get("evidence") or {},
                "source": "rules",
                "risk_notes": [],
            }
        )
    rows.sort(key=lambda item: float(item.get("chance") or 0), reverse=True)
    return _limit_suggestions_preserving_high_value(rows, 12)


def _build_frameworks(posts: list[dict[str, Any]], opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    samples = []
    for post in posts:
        samples.append(
            {
                "title": post.get("title") or post.get("content") or "未命名内容",
                "engagement": _engagement_total(post.get("engagement_json") or {}),
                "platform": post.get("platform"),
                "url": post.get("url"),
            }
        )
    for opportunity in opportunities:
        for sample in opportunity.get("samples") or []:
            samples.append(
                {
                    "title": sample.get("title") or sample.get("body") or opportunity.get("display_title"),
                    "engagement": _engagement_total(sample.get("engagement") or {}),
                    "platform": sample.get("platform") or opportunity.get("platform"),
                    "url": sample.get("url"),
                }
            )
    for sample in samples:
        framework, tags = _classify_framework(str(sample.get("title") or ""))
        bucket = buckets.setdefault(
            framework,
            {
                "title": framework,
                "tags": tags,
                "posts": 0,
                "interactions": [],
                "leads": 0,
                "samples": [],
            },
        )
        engagement = int(sample.get("engagement") or 0)
        bucket["posts"] += 1
        bucket["interactions"].append(engagement)
        bucket["leads"] += max(0, round(engagement * 0.06))
        if len(bucket["samples"]) < 3:
            bucket["samples"].append(sample)
    rows = []
    for bucket in buckets.values():
        median_interaction = _median_number(bucket["interactions"])
        rows.append(
            {
                "title": bucket["title"],
                "tags": bucket["tags"],
                "posts": bucket["posts"],
                "interactions": _format_number(median_interaction),
                "leads": bucket["leads"],
                "samples": bucket["samples"],
            }
        )
    rows.sort(key=_framework_sort_key, reverse=True)
    return rows[:8]


def _build_competitor_samples(
    competitor_compositions: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in competitor_compositions:
        evidence = item.get("evidence") or {}
        top_posts = evidence.get("top_posts") if isinstance(evidence, dict) else None
        if not isinstance(top_posts, list):
            top_posts = []
        for post in top_posts[:4]:
            if not isinstance(post, dict):
                continue
            rows.append(_competitor_sample_row(post, item))
    for opportunity in opportunities:
        if opportunity.get("type") != "competitor":
            continue
        for sample in opportunity.get("samples") or []:
            rows.append(_competitor_sample_row(sample, opportunity))
    unique = []
    seen: set[str] = set()
    for row in rows:
        key = row.get("url") or f"{row.get('platform')}:{row.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    unique.sort(key=lambda item: _parse_display_number(item["interaction"]), reverse=True)
    return unique[:10]


def _build_risks(
    *,
    dashboard: dict[str, Any],
    opportunities: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
    ai_insights: dict[str, Any],
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    details: dict[str, str] = {}
    for item in opportunities:
        for tag in item.get("risk_tags") or []:
            label = RISK_LABELS.get(tag, str(tag))
            counts[label] += 1
            details.setdefault(label, _risk_detail(tag))
    for diagnostic in dashboard.get("diagnostics") or []:
        title = str(diagnostic.get("title") or "诊断提醒")
        counts[title] += 1
        details.setdefault(title, str(diagnostic.get("body") or "需要复核当前数据质量。"))
    for snapshot in content_snapshots:
        if float(snapshot.get("hot_post_rate") or 0) >= 0.45:
            counts["同质化风险"] += 1
            details.setdefault("同质化风险", "高互动内容集中在少数表达方式，建议增加案例差异化。")
    for note in _string_list(ai_insights.get("risk_notes")):
        counts[note] += 1
        details.setdefault(note, "来自最新 AI 洞察的风险提示。")
    if not counts:
        counts["样本覆盖风险"] = 1
        details["样本覆盖风险"] = "当前证据样本有限，建议先补齐平台和时间窗样本。"
    rows = []
    for title, count in counts.most_common(8):
        rows.append(
            {
                "title": title,
                "detail": details.get(title) or "需要人工复核后再执行。",
                "level": "高风险" if count >= 3 else "中风险",
                "count": int(count),
            }
        )
    return rows


def _build_weekly_mix(
    filters: dict[str, Any],
    suggestions: list[dict[str, Any]],
    frameworks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    goal = filters.get("goal")
    if goal == "awareness":
        base = [("话题内容", 34), ("观点内容", 26), ("案例内容", 22), ("转化内容", 10), ("复盘内容", 8)]
    elif goal == "engagement":
        base = [("痛点内容", 32), ("互动内容", 28), ("测评内容", 18), ("案例内容", 14), ("转化内容", 8)]
    else:
        base = [("痛点内容", 36), ("科普内容", 24), ("案例内容", 18), ("测评内容", 12), ("转化内容", 10)]
    suggested_total = max(8, min(24, len(suggestions) + len(frameworks) + 6))
    rows = []
    for index, (label, percent) in enumerate(base):
        pieces = max(1, round(suggested_total * percent / 100))
        rows.append(
            {
                "label": label,
                "percent": percent,
                "pieces": pieces,
                "exposure": _format_number(pieces * 420),
                "leads": max(1, round(pieces * (16 if goal == "conversion" else 9))),
                "color": MIX_COLORS[index % len(MIX_COLORS)],
            }
        )
    return rows


def _build_traffic_share(
    posts: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    traffic: Counter[str] = Counter()
    for post in posts:
        platform = post.get("platform") or "unknown"
        value = max(1, _engagement_total(post.get("engagement_json") or {}))
        counts[platform] += 1
        traffic[platform] += value
    for snapshot in content_snapshots:
        platform = snapshot.get("platform") or "unknown"
        value = int(snapshot.get("total_content_count") or 0)
        counts[platform] += value
        traffic[platform] += max(value * 20, 0)
    for snapshot in competitor_compositions:
        platform = snapshot.get("platform") or "unknown"
        value = int(snapshot.get("total_flow_count") or 0)
        counts[platform] += value
        traffic[platform] += max(value, 0)
    if not traffic:
        traffic["unknown"] = 1
    total = sum(traffic.values()) or 1
    rows = []
    for index, (platform, value) in enumerate(traffic.most_common(6)):
        percent = round(value / total * 100, 1)
        rows.append(
            {
                "platform": PLATFORM_LABELS.get(platform, platform),
                "platform_key": platform,
                "percent": percent,
                "traffic": _format_number(value),
                "sample_count": int(counts.get(platform) or 0),
                "color": TRAFFIC_COLORS[index % len(TRAFFIC_COLORS)],
            }
        )
    estimated_exposure = sum(traffic.values())
    return {
        "estimated_exposure": _format_number(estimated_exposure),
        "estimated_leads": max(0, round(estimated_exposure * 0.028)),
        "estimated_orders": max(0, round(estimated_exposure * 0.002)),
        "rows": rows,
    }


def _build_evidence_pack(
    *,
    suggestions: list[dict[str, Any]],
    keyword_trends: list[dict[str, Any]],
    competitor_samples: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> dict[str, Any]:
    items = []
    for suggestion in suggestions[:6]:
        items.append(
            {
                "type": "suggestion",
                "title": suggestion["title"],
                "platform": suggestion.get("platform"),
                "reason": suggestion.get("reason") or suggestion.get("direction"),
                "payload": suggestion,
            }
        )
    for trend in keyword_trends[:6]:
        items.append(
            {
                "type": "keyword",
                "title": trend["keyword"],
                "platform": trend.get("platform"),
                "reason": f"机会值 {trend['score']}，方向 {trend['direction']}",
                "payload": trend,
            }
        )
    for sample in competitor_samples[:6]:
        items.append(
            {
                "type": "competitor_sample",
                "title": sample["title"],
                "platform": sample.get("platform"),
                "reason": f"互动 {sample.get('interaction')}",
                "payload": sample,
            }
        )
    for post in sorted(posts, key=lambda item: _engagement_total(item.get("engagement_json") or {}), reverse=True)[:6]:
        items.append(
            {
                "type": "post_sample",
                "title": post.get("title") or post.get("content") or str(post.get("platform_post_id") or "内容样本"),
                "platform": post.get("platform"),
                "reason": f"互动 {_format_number(_engagement_total(post.get('engagement_json') or {}))}",
                "payload": {
                    "url": post.get("url"),
                    "publish_time": post.get("publish_time"),
                    "engagement": post.get("engagement_json") or {},
                },
            }
        )
    return {"items": items[:24], "risks": risks[:6], "total": len(items)}


def _keyword_rows_from_opportunities(
    opportunities: list[dict[str, Any]],
    seen: set[tuple[str, str | None]],
) -> list[dict[str, Any]]:
    rows = []
    for item in opportunities:
        if item.get("type") != "keyword":
            continue
        keyword = str(item.get("name") or item.get("display_title") or "").strip()
        platform = item.get("platform")
        key = (keyword, platform)
        if not keyword or key in seen:
            continue
        seen.add(key)
        score = round(float(item.get("score") or 0), 1)
        change = float(item.get("change_24h") or item.get("trend_7d") or 0)
        rows.append(
            {
                "rank": 0,
                "keyword": keyword,
                "platform": platform,
                "platform_label": PLATFORM_LABELS.get(platform, platform or "全部平台"),
                "heat": _format_score(score),
                "score": score,
                "direction": "up" if change >= 0 else "down",
                "points": _trend_points(score, change),
                "evidence": (item.get("detail") or {}).get("evidence") or {},
            }
        )
    return rows


def _keyword_rows_from_posts(
    posts: list[dict[str, Any]],
    seen: set[tuple[str, str | None]],
) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str | None]] = Counter()
    for post in posts:
        engagement = post.get("engagement_json") or {}
        candidates = _string_list(engagement.get("source_keyword"))
        if not candidates:
            candidates = [term for term, _ in PAIN_RULES if term in _post_text(post)]
        for keyword in candidates:
            key = (keyword, post.get("platform"))
            if key not in seen:
                counter[key] += 1
    rows = []
    for (keyword, platform), count in counter.most_common(8):
        seen.add((keyword, platform))
        score = min(100.0, 35 + count * 8)
        rows.append(
            {
                "rank": 0,
                "keyword": keyword,
                "platform": platform,
                "platform_label": PLATFORM_LABELS.get(platform, platform or "全部平台"),
                "heat": _format_score(score),
                "score": round(score, 1),
                "direction": "up",
                "points": _trend_points(score, count),
                "evidence": {"sample_count": count},
            }
        )
    return rows


def _classify_framework(title: str) -> tuple[str, list[str]]:
    lowered = title.lower()
    for label, terms, tags in FRAMEWORK_RULES:
        if any(term.lower() in lowered for term in terms):
            return label, tags
    return "问题解决型", ["痛点", "方法", "泛用模板"]


def _competitor_sample_row(sample: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    platform = sample.get("platform") or source.get("platform")
    engagement = sample.get("engagement") or sample.get("engagement_json") or {}
    total = _engagement_total(engagement)
    title = sample.get("title") or sample.get("body") or sample.get("text") or source.get("display_title") or "未命名样本"
    return {
        "platform": PLATFORM_LABELS.get(platform, platform or "未知平台"),
        "platform_key": platform,
        "badge": _platform_badge(platform),
        "title": str(title),
        "interaction": _format_number(total),
        "likes": _format_number(_first_number(engagement, ["like_count", "liked_count", "likes", "digg_count"])),
        "comments": _format_number(_first_number(engagement, ["comment_count", "comments"])),
        "favorites": _format_number(_first_number(engagement, ["collect_count", "favorite_count", "favorites"])),
        "url": sample.get("url") or source.get("target_url"),
        "publish_time": sample.get("publish_time"),
    }


def _topic_title_from_opportunity(title: str, opportunity_type: str | None) -> str:
    if opportunity_type == "keyword":
        return f"{title}怎么做？3 个内容角度快速测试"
    if opportunity_type == "competitor":
        return f"拆解「{title}」近期高互动内容打法"
    if opportunity_type == "creator":
        return f"参考「{title}」的人群表达做一次低成本测试"
    return title


def _risk_detail(tag: str) -> str:
    return {
        "small_sample_spike": "热度来自少量样本，先补样本再放大执行。",
        "single_platform_signal": "信号集中在单一平台，跨平台可迁移性需要验证。",
        "stale_data": "样本更新时间较早，建议刷新后再判断。",
        "overheated_competition": "同类供给较多，需要从案例、场景或人群切口做差异化。",
        "missing_execution_parameters": "缺少链接、关键词或采集参数，执行前需要补齐。",
        "high_cost": "可能带来较高采集或投放成本，建议先小样本验证。",
    }.get(tag, "需要人工复核后再执行。")


def _risk_level(*, risk_notes: list[str], risk_tags: list[str]) -> str:
    if any(tag in {"high_cost", "overheated_competition", "missing_execution_parameters"} for tag in risk_tags):
        return "高风险"
    if len(risk_notes) >= 2 or risk_tags:
        return "中风险"
    return "低风险"


def _chance_from_confidence(value: Any, *, base: int) -> int:
    text = str(value or "").lower()
    if text == "high":
        return min(96, base + 10)
    if text == "low":
        return max(55, base - 18)
    return base


def _audience_label(value: Any) -> str:
    return {
        "moms": "宝妈 / 家长",
        "pet": "新手养宠",
        "ingredient": "成分党",
        "all": "泛目标人群",
    }.get(str(value or "all"), str(value or "泛目标人群"))


def _platform_matches(item_platform: Any, selected_platform: Any) -> bool:
    selected = PLATFORM_ALIASES.get(str(selected_platform or "all"), selected_platform)
    item = PLATFORM_ALIASES.get(str(item_platform or "all"), item_platform)
    return selected in {None, "all"} or item in {selected, "all", None}


def _platform_badge(platform: Any) -> str:
    return {
        "dy": "dy",
        "xhs": "xh",
        "bili": "bi",
        "wb": "wb",
        "weibo": "wb",
    }.get(str(platform or ""), "ot")


def _trend_points(score: float, growth: float) -> list[float]:
    base = max(4.0, min(80.0, float(score) * 0.55))
    slope = max(-8.0, min(12.0, float(growth) / 10.0))
    return [round(max(1.0, min(100.0, base + slope * index + ((index % 3) - 1) * 2)), 1) for index in range(8)]


def _format_score(value: float) -> str:
    return f"{round(float(value), 1)}"


def _format_number(value: float | int) -> str:
    number = float(value or 0)
    if number >= 10000:
        return f"{round(number / 10000, 1)}w"
    if number >= 1000:
        return f"{round(number / 1000, 1)}k"
    return str(int(round(number)))


def _median_number(values: list[int | float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value or 0) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _framework_interactions_display(value: Any, *, fallback: Any, posts: int) -> str:
    for candidate in (value, fallback):
        if _is_display_number(candidate):
            return _format_number(_parse_display_number(candidate))
    return _format_number(max(0, posts) * 320)


def _framework_sort_key(item: dict[str, Any]) -> tuple[float, int, int]:
    return (
        _parse_display_number(item.get("interactions")),
        _safe_int(item.get("posts"), minimum=0),
        _safe_int(item.get("leads"), minimum=0),
    )


def _is_display_number(value: Any) -> bool:
    return bool(DISPLAY_NUMBER_PATTERN.match(str(value or "").strip()))


def _parse_display_number(value: Any) -> float:
    text = str(value or "0").strip().lower().replace(",", "")
    multiplier = 1.0
    if text.endswith("w") or text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    elif text.endswith("k"):
        multiplier = 1000.0
        text = text[:-1]
    text = text.strip()
    try:
        return float(text) * multiplier
    except ValueError:
        return 0.0


def _first_number(data: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        try:
            value = float(data.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value:
            return value
    return 0.0


def _engagement_total(engagement: dict[str, Any]) -> int:
    total = 0
    for key in (
        "like_count",
        "liked_count",
        "likes",
        "digg_count",
        "comment_count",
        "comments",
        "share_count",
        "shares",
        "collect_count",
        "favorite_count",
        "favorites",
        "play_count",
        "view_count",
    ):
        try:
            total += int(float(engagement.get(key) or 0))
        except (TypeError, ValueError):
            continue
    return total


def _post_text(post: dict[str, Any]) -> str:
    engagement = post.get("engagement_json") or {}
    values = [
        post.get("title"),
        post.get("content"),
        engagement.get("source_keyword"),
        engagement.get("tag_list"),
    ]
    return " ".join(str(value) for value in values if value).lower()


def _dedupe_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen: set[tuple[str, str]] = set()
    for post in posts:
        key = (str(post.get("platform") or ""), str(post.get("platform_post_id") or post.get("id") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(post)
    return result


def _latest_timestamp(items: list[dict[str, Any]]) -> str | None:
    values = []
    for item in items:
        for key in ("updated_at", "created_at", "snapshot_date", "publish_time"):
            value = item.get(key)
            if value:
                values.append(_timestamp_string(value))
                break
    values = [value for value in values if value]
    return max(values) if values else None


def _timestamp_string(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None and str(item).strip()]
    return []


def _truncate_text(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _compact_json(value: Any, *, limit: int) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return value
    return {"truncated_json": text[:limit], "truncated": True}

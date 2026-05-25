from __future__ import annotations

import asyncio
import os
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from typing import Any

from research.ai_insights import (
    _compact_post,
    _dedupe_posts,
    _engagement_total,
    _json_safe,
    _post_text,
    build_rule_based_ai_insight_fallback,
)
from research.ai_provider import OpenAICompatibleProvider
from research.content_strategy import (
    CONTENT_STRATEGY_AI_SECTIONS,
    build_content_strategy_ai_fallback,
    build_content_strategy_ai_input,
    build_content_strategy_ai_section_prompt,
    normalize_content_strategy_ai_section,
)


STATE_KEY_PREFIX = "research:content-strategy:project"


def content_strategy_state_key(project_id: int) -> str:
    return f"{STATE_KEY_PREFIX}:{project_id}:state"


def normalize_content_strategy_state(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    scheduled_refresh = raw.get("scheduled_refresh") if isinstance(raw.get("scheduled_refresh"), dict) else {}
    manual_analysis = raw.get("manual_analysis") if isinstance(raw.get("manual_analysis"), dict) else {}
    ai_insights = raw.get("ai_insights") if isinstance(raw.get("ai_insights"), dict) else {}
    return {
        "scheduled_refresh": {
            "status": str(scheduled_refresh.get("status") or "idle"),
            "trigger": str(scheduled_refresh.get("trigger") or ""),
            "last_started_at": scheduled_refresh.get("last_started_at"),
            "last_completed_at": scheduled_refresh.get("last_completed_at"),
            "last_collection_completed_at": scheduled_refresh.get("last_collection_completed_at"),
            "last_collection_job_id": scheduled_refresh.get("last_collection_job_id"),
            "last_error": scheduled_refresh.get("last_error"),
        },
        "manual_analysis": {
            "last_refreshed_at": manual_analysis.get("last_refreshed_at"),
        },
        "ai_insights": {
            "mode": str(ai_insights.get("mode") or "none"),
            "status": str(ai_insights.get("status") or "idle"),
            "generated_at": ai_insights.get("generated_at"),
            "provider": ai_insights.get("provider") if isinstance(ai_insights.get("provider"), dict) else None,
            "executive_summary": str(ai_insights.get("executive_summary") or ""),
            "platform_strategy": ai_insights.get("platform_strategy")
            if isinstance(ai_insights.get("platform_strategy"), dict)
            else {},
            "hotspots": ai_insights.get("hotspots") if isinstance(ai_insights.get("hotspots"), list) else [],
            "topic_ideas": ai_insights.get("topic_ideas") if isinstance(ai_insights.get("topic_ideas"), list) else [],
            "risk_notes": ai_insights.get("risk_notes") if isinstance(ai_insights.get("risk_notes"), list) else [],
            "strategy_summary": ai_insights.get("strategy_summary")
            if isinstance(ai_insights.get("strategy_summary"), dict)
            else {},
            "strategy_summary_source": str(ai_insights.get("strategy_summary_source") or "none"),
            "section_statuses": ai_insights.get("section_statuses")
            if isinstance(ai_insights.get("section_statuses"), dict)
            else {},
            "error": ai_insights.get("error"),
            "input_summary": ai_insights.get("input_summary")
            if isinstance(ai_insights.get("input_summary"), dict)
            else {},
        },
    }


async def load_project_content_strategy_state(
    repository: Any,
    project_id: int,
) -> dict[str, Any]:
    setting = await repository.get_global_setting(content_strategy_state_key(project_id))
    state = normalize_content_strategy_state((setting or {}).get("value"))
    state["_updated_at"] = (setting or {}).get("updated_at")
    return state


async def save_project_content_strategy_state(
    repository: Any,
    project_id: int,
    state: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_content_strategy_state(state)
    saved = await repository.upsert_global_setting(content_strategy_state_key(project_id), normalized)
    result = normalize_content_strategy_state(saved.get("value"))
    result["_updated_at"] = saved.get("updated_at")
    return result


def collect_active_project_keywords(keyword_rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for row in keyword_rows:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword or row.get("status") != "active" or row.get("keyword_type") == "excluded":
            continue
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(keyword)
    return keywords


def refresh_interval_minutes(project_record: dict[str, Any]) -> int | None:
    cadence = str(project_record.get("refresh_cadence") or "off")
    if cadence == "daily":
        return 1440
    if cadence == "three_days":
        return 4320
    if cadence == "weekly":
        return 10080
    if cadence == "custom_hours":
        return int(project_record.get("custom_interval_value") or 1) * 60
    if cadence == "custom_days":
        return int(project_record.get("custom_interval_value") or 1) * 1440
    return None


def build_project_content_strategy_ai_input(
    *,
    project_record: dict[str, Any],
    keyword_rows: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    window_days: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start_at = datetime.combine(
        (now - timedelta(days=max(window_days, 1) - 1)).date(),
        time.min,
        tzinfo=timezone.utc,
    )
    end_at = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
    scoped_posts = _dedupe_posts(
        [
            post
            for post in posts
            if _post_in_window(post, start_at=start_at, end_at=end_at)
        ]
    )
    project_keywords = collect_active_project_keywords(keyword_rows)
    platform_counts = Counter(str(post.get("platform") or "unknown") for post in scoped_posts)
    keyword_counts = {
        keyword: sum(1 for post in scoped_posts if keyword.lower() in _post_text(post))
        for keyword in project_keywords[:20]
    }
    top_posts = sorted(scoped_posts, key=_engagement_total, reverse=True)[:20]
    return {
        "window": {
            "days": window_days,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
        "scope": {
            "project_id": project_record.get("id"),
            "project_name": project_record.get("name"),
            "platforms": project_record.get("platforms") or [],
            "keywords": project_keywords,
        },
        "sample": {
            "total_posts": len(scoped_posts),
            "platform_counts": dict(platform_counts),
            "keyword_counts": keyword_counts,
        },
        "latest_backtests": [],
        "top_posts": [_compact_post(item) for item in top_posts],
    }


async def generate_project_content_strategy_ai_bundle(
    repository: Any,
    *,
    project_record: dict[str, Any],
    keyword_rows: list[dict[str, Any]],
    posts: list[dict[str, Any]],
    provider_config_id: int | None = None,
    window_days: int = 7,
    filters: dict[str, Any] | None = None,
    keyword_heat_snapshots: list[dict[str, Any]] | None = None,
    content_snapshots: list[dict[str, Any]] | None = None,
    competitor_compositions: list[dict[str, Any]] | None = None,
    base_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback_summary = base_summary if isinstance(base_summary, dict) else {}
    project_input_summary = build_project_content_strategy_ai_input(
        project_record=project_record,
        keyword_rows=keyword_rows,
        posts=posts,
        window_days=window_days,
    )
    strategy_input_summary = build_content_strategy_ai_input(
        filters=filters
        or {
            "platform": None,
            "platform_label": "全部平台",
            "range": f"{window_days}d",
            "window_days": window_days,
            "goal": "conversion",
            "goal_label": "获客转化",
            "audience": "all",
            "stage": "boost",
        },
        project_record=project_record,
        keyword_rows=keyword_rows,
        posts=posts,
        keyword_heat_snapshots=list(keyword_heat_snapshots or []),
        content_snapshots=list(content_snapshots or []),
        competitor_compositions=list(competitor_compositions or []),
        base_summary=fallback_summary,
    )
    try:
        provider_config = await _resolve_provider(repository, provider_config_id)
    except Exception as exc:
        fallback = build_rule_based_ai_insight_fallback(project_input_summary)
        strategy_summary = build_content_strategy_ai_fallback(
            fallback_summary,
            reason=f"{type(exc).__name__}: {exc}",
        )
        return {
            "mode": "fallback",
            "status": "fallback",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": None,
            "executive_summary": fallback.get("executive_summary") or "",
            "platform_strategy": fallback.get("platform_strategy") or {},
            "hotspots": _json_safe(fallback.get("hotspots") or []),
            "topic_ideas": _json_safe(fallback.get("topic_ideas") or []),
            "risk_notes": _json_safe(fallback.get("risk_notes") or []),
            "strategy_summary": _json_safe(strategy_summary),
            "strategy_summary_source": "fallback",
            "section_statuses": {},
            "error": f"{type(exc).__name__}: {exc}",
            "input_summary": _json_safe(strategy_input_summary),
        }
    provider_info = {
        "name": provider_config.get("name"),
        "model": provider_config.get("model"),
    }
    provider = OpenAICompatibleProvider(
        base_url=provider_config["base_url"],
        api_key=provider_config["api_key"],
        model=provider_config["model"],
        timeout=provider_config.get("timeout") or 60,
    )
    section_results = await _generate_content_strategy_sections(
        provider,
        provider_config=provider_config,
        strategy_input_summary=strategy_input_summary,
        fallback_summary=fallback_summary,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    strategy_summary: dict[str, Any] = {}
    section_statuses: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    overview_output: dict[str, Any] = {}
    completed_sections: list[str] = []

    for result in section_results:
        section = str(result["section"])
        section_statuses[section] = {
            "status": result["status"],
            "source": "ai" if result["status"] == "completed" else "rules",
            "generated_at": generated_at if result["status"] == "completed" else None,
            "error": result.get("error"),
        }
        if result["status"] == "completed":
            completed_sections.append(section)
            strategy_summary.update(result.get("strategy_fragment") or {})
            if section == "overview":
                overview_output = result.get("output") or {}
        elif result.get("error"):
            errors.append(f"{section}: {result['error']}")

    if not completed_sections:
        fallback = build_rule_based_ai_insight_fallback(project_input_summary)
        strategy_summary = build_content_strategy_ai_fallback(
            fallback_summary,
            reason="; ".join(errors) or "AI sections returned no usable output",
        )
        return {
            "mode": "fallback",
            "status": "fallback",
            "generated_at": generated_at,
            "provider": provider_info,
            "executive_summary": fallback.get("executive_summary") or "",
            "platform_strategy": fallback.get("platform_strategy") or {},
            "hotspots": _json_safe(fallback.get("hotspots") or []),
            "topic_ideas": _json_safe(fallback.get("topic_ideas") or []),
            "risk_notes": _json_safe(fallback.get("risk_notes") or []),
            "strategy_summary": _json_safe(strategy_summary),
            "strategy_summary_source": "fallback",
            "section_statuses": _json_safe(section_statuses),
            "error": "; ".join(errors) or "AI sections returned no usable output",
            "input_summary": _json_safe(strategy_input_summary),
        }

    all_sections_completed = len(completed_sections) == len(CONTENT_STRATEGY_AI_SECTIONS)
    status = "completed" if all_sections_completed else "partial"
    strategy_summary_source = "ai" if all_sections_completed else "partial_ai"
    fallback = build_rule_based_ai_insight_fallback(project_input_summary)
    return {
        "mode": "ai",
        "status": status,
        "generated_at": generated_at,
        "provider": provider_info,
        "executive_summary": overview_output.get("executive_summary") or fallback.get("executive_summary") or "",
        "platform_strategy": overview_output.get("platform_strategy") or fallback.get("platform_strategy") or {},
        "hotspots": _json_safe(overview_output.get("hotspots") or []),
        "topic_ideas": _json_safe(overview_output.get("topic_ideas") or []),
        "risk_notes": _json_safe(overview_output.get("risk_notes") or fallback.get("risk_notes") or []),
        "strategy_summary": _json_safe(strategy_summary),
        "strategy_summary_source": strategy_summary_source,
        "section_statuses": _json_safe(section_statuses),
        "error": "; ".join(errors) if errors else None,
        "input_summary": _json_safe(strategy_input_summary),
    }


async def _generate_content_strategy_sections(
    provider: OpenAICompatibleProvider,
    *,
    provider_config: dict[str, Any],
    strategy_input_summary: dict[str, Any],
    fallback_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    concurrency = _content_strategy_ai_concurrency()
    semaphore = asyncio.Semaphore(concurrency)

    async def run_section(section: str) -> dict[str, Any]:
        async with semaphore:
            try:
                raw_output = await provider.complete_json(
                    prompt=build_content_strategy_ai_section_prompt(strategy_input_summary, section),
                    params=_content_strategy_section_params(provider_config, section),
                )
                output = _normalize_content_strategy_section_output(raw_output)
                strategy_fragment = normalize_content_strategy_ai_section(
                    raw_output,
                    section=section,
                    fallback_summary=fallback_summary,
                )
                if not strategy_fragment:
                    raise ValueError("AI section returned no usable content_strategy fields")
                return {
                    "section": section,
                    "status": "completed",
                    "output": output,
                    "strategy_fragment": strategy_fragment,
                    "error": None,
                }
            except Exception as exc:
                return {
                    "section": section,
                    "status": "fallback",
                    "output": {},
                    "strategy_fragment": {},
                    "error": f"{type(exc).__name__}: {exc}",
                }

    return await asyncio.gather(*(run_section(section) for section in CONTENT_STRATEGY_AI_SECTIONS))


def _normalize_content_strategy_section_output(output: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise ValueError("AI output must be a JSON object")
    return {
        "executive_summary": str(output.get("executive_summary") or ""),
        "hotspots": output.get("hotspots") if isinstance(output.get("hotspots"), list) else [],
        "topic_ideas": output.get("topic_ideas") if isinstance(output.get("topic_ideas"), list) else [],
        "platform_strategy": output.get("platform_strategy") if isinstance(output.get("platform_strategy"), dict) else {},
        "risk_notes": output.get("risk_notes") if isinstance(output.get("risk_notes"), list) else [],
    }


def _content_strategy_ai_concurrency() -> int:
    raw = os.getenv("AI_GATEWAY_CONTENT_STRATEGY_MAX_CONCURRENCY") or os.getenv("AI_GATEWAY_MAX_CONCURRENCY") or "2"
    try:
        return max(1, min(4, int(raw)))
    except ValueError:
        return 2


def _content_strategy_section_params(provider_config: dict[str, Any], section: str) -> dict[str, Any]:
    base = dict(provider_config.get("default_params") or {})
    section_default = int(os.getenv("AI_GATEWAY_CONTENT_STRATEGY_SECTION_MAX_TOKENS", "900"))
    max_tokens_by_section = {
        "overview": min(section_default, 700),
        "keyword_trends": min(section_default, 800),
        "frameworks": min(section_default, 900),
        "suggestions": max(section_default, 1100),
        "risks": min(section_default, 800),
        "weekly_mix": min(section_default, 800),
    }
    base.update(
        {
            "temperature": 0.25 if section in {"overview", "risks"} else 0.35,
            "max_tokens": max_tokens_by_section.get(section, section_default),
        }
    )
    return base


async def _resolve_provider(repository: Any, provider_config_id: int | None) -> dict[str, Any]:
    env_api_key = os.getenv("AI_GATEWAY_API_KEY")
    if env_api_key:
        return {
            "id": None,
            "name": os.getenv("AI_GATEWAY_NAME", "AI Gateway"),
            "base_url": os.getenv("AI_GATEWAY_BASE_URL", "https://4router.net/v1"),
            "api_key": env_api_key,
            "model": os.getenv("AI_GATEWAY_MODEL", "gpt-5.4-mini"),
            "timeout": int(os.getenv("AI_GATEWAY_CONTENT_STRATEGY_TIMEOUT", os.getenv("AI_GATEWAY_TIMEOUT", "60"))),
            "default_params": {
                "temperature": float(os.getenv("AI_GATEWAY_TEMPERATURE", "0.2")),
                "max_tokens": int(
                    os.getenv(
                        "AI_GATEWAY_CONTENT_STRATEGY_MAX_TOKENS",
                        os.getenv("AI_GATEWAY_MAX_TOKENS", "2800"),
                    )
                ),
            },
        }
    if provider_config_id:
        provider = await repository.get_ai_provider(provider_config_id, include_secret=True)
        if provider is None:
            raise ValueError("AI provider config not found")
        return provider
    providers = await repository.list_ai_providers()
    enabled = [item for item in providers if item.get("enabled") and item.get("api_key_set")]
    selected = enabled[0] if enabled else None
    if selected is None:
        raise ValueError("No enabled AI provider with API key is configured")
    provider = await repository.get_ai_provider(selected["id"], include_secret=True)
    if provider is None:
        raise ValueError("AI provider config not found")
    return provider


def _post_in_window(
    post: dict[str, Any],
    *,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    publish_time = post.get("publish_time")
    if isinstance(publish_time, datetime):
        candidate = publish_time if publish_time.tzinfo else publish_time.replace(tzinfo=timezone.utc)
        return start_at <= candidate.astimezone(timezone.utc) <= end_at
    return True

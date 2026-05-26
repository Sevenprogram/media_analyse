from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import config  # noqa: F401 - loads .env.example/.env into os.environ
from research.ai_provider import OpenAICompatibleProvider
from research.dashboard import build_dashboard_summary
from research.growth_projects import project_key_for_job


TODAY_INTELLIGENCE_SETTING_KEY = "reports:today-intelligence:latest"
DEFAULT_MAX_AGE_MINUTES = 120


ProviderFactory = Callable[..., OpenAICompatibleProvider]


async def get_latest_today_intelligence(
    repository: Any,
    *,
    platform: str | None = None,
    project_id: str | None = None,
    project_record: dict[str, Any] | None = None,
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
) -> dict[str, Any] | None:
    setting = await repository.get_global_setting(
        _setting_key(platform=platform, project_id=project_id, project_record=project_record)
    )
    value = (setting or {}).get("value") or {}
    if not value:
        return None
    if not _is_fresh(value.get("generated_at"), max_age_minutes=max_age_minutes):
        stale = dict(value)
        stale["status"] = "stale"
        stale["ai_status"] = _ai_status(stale)
        return stale
    value["ai_status"] = _ai_status(value)
    return value


async def run_today_intelligence_analysis(
    repository: Any,
    *,
    platform: str | None = None,
    project_id: str | None = None,
    project_record: dict[str, Any] | None = None,
    force: bool = False,
    provider_factory: ProviderFactory | None = None,
) -> dict[str, Any]:
    del force
    bundle = await build_today_intelligence_input(
        repository,
        platform=platform,
        project_id=project_id,
        project_record=project_record,
    )
    provider_config: dict[str, Any] | None = None
    provider_info: dict[str, Any] | None = None
    generated_at = datetime.now(timezone.utc)
    expires_at = generated_at + timedelta(minutes=DEFAULT_MAX_AGE_MINUTES)

    try:
        provider_config = await _resolve_provider(repository)
        provider_info = {
            "name": provider_config.get("name") or "AI Gateway",
            "model": provider_config.get("model"),
        }
        factory = provider_factory or OpenAICompatibleProvider
        provider = factory(
            base_url=provider_config["base_url"],
            api_key=provider_config["api_key"],
            model=provider_config["model"],
            timeout=int(provider_config.get("timeout") or 60),
        )
        raw_output = await provider.complete_json(
            prompt=build_today_intelligence_prompt(bundle["input_summary"]),
            params={
                "temperature": 0.2,
                "max_tokens": int(
                    (provider_config.get("default_params") or {}).get("max_tokens")
                    or os.getenv("AI_GATEWAY_MAX_TOKENS", "1200")
                ),
                **(provider_config.get("default_params") or {}),
            },
        )
        normalized = _normalize_ai_output(raw_output, bundle=bundle)
        result = _result_payload(
            status="completed",
            source="ai",
            generated_at=generated_at,
            expires_at=expires_at,
            provider=provider_info,
            output=normalized,
            bundle=bundle,
            error=None,
        )
    except Exception as exc:
        fallback = build_rule_based_today_intelligence_fallback(
            bundle["input_summary"],
            reason=f"{type(exc).__name__}: {exc}",
        )
        result = _result_payload(
            status="fallback",
            source="rules",
            generated_at=generated_at,
            expires_at=expires_at,
            provider=provider_info,
            output=fallback,
            bundle=bundle,
            error=f"{type(exc).__name__}: {exc}",
        )

    result["ai_status"] = _ai_status(result)
    await repository.upsert_global_setting(
        _setting_key(platform=platform, project_id=project_id, project_record=project_record),
        result,
    )
    return result


async def build_today_intelligence_input(
    repository: Any,
    *,
    platform: str | None = None,
    project_id: str | None = None,
    project_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project = _compact_project(project_id=project_id, project_record=project_record)
    jobs = (
        await _project_jobs(repository, project_id=project_id, project_record=project_record)
        if project
        else await _maybe_call(repository, "list_jobs", default=[])
    )
    project_keywords = (
        await _project_keywords(repository, project_record=project_record)
        if project
        else set()
    )
    if project and not project_keywords:
        project_keywords = _keywords_from_jobs(jobs)
    project_platforms = _project_platforms(
        project_record=project_record,
        jobs=jobs,
        platform=platform,
    )
    creator_candidates = await _project_creator_candidates(
        repository,
        project_record=project_record if project else None,
        project_keywords=project_keywords,
        project_platforms=project_platforms,
        platform=platform,
    )
    keyword_heat_snapshots = await _maybe_call(
        repository,
        "list_keyword_heat_snapshots",
        platform=platform,
        limit=100 if project else 50,
        default=[],
    )
    keyword_heat_snapshots = _filter_keyword_heat_snapshots(
        keyword_heat_snapshots,
        project_keywords=project_keywords,
        project_platforms=project_platforms,
        platform=platform,
    )
    competitor_compositions = await _maybe_call(
        repository,
        "list_competitor_composition_snapshots",
        platform=platform,
        limit=50,
        default=[],
    )
    if project:
        competitor_compositions = await _project_competitor_compositions(
            repository,
            project_record=project_record,
            platform=platform,
            fallback=competitor_compositions,
        )
    content_snapshots = await _maybe_call(
        repository,
        "list_content_tracking_snapshots",
        platform=platform,
        limit=50,
        default=[],
    )
    if project:
        content_snapshots = _filter_content_snapshots(
            content_snapshots,
            project_keywords=project_keywords,
            project_platforms=project_platforms,
            platform=platform,
        )
    monitor_pools = await _maybe_call(
        repository,
        "list_monitor_pools",
        enabled_only=True,
        default=[],
    )
    if project:
        monitor_pools = _filter_monitor_pools(
            monitor_pools,
            jobs=jobs,
            project_record=project_record,
        )
    feedback = await _maybe_call(
        repository,
        "list_opportunity_feedback",
        limit=500,
        default=[],
    )
    database_stats = (
        await _project_database_stats(repository, jobs=jobs)
        if project
        else await _maybe_call(
            repository,
            "get_database_collection_stats",
            default=_empty_database_stats(),
        )
    )
    dashboard = build_dashboard_summary(
        jobs=jobs,
        creator_candidates=creator_candidates,
        keyword_heat_snapshots=keyword_heat_snapshots,
        competitor_compositions=competitor_compositions,
        content_snapshots=content_snapshots,
        monitor_pools=monitor_pools,
        platform=platform,
        feedback=feedback,
    )
    input_summary = _compact_input_summary(
        dashboard=dashboard,
        database_stats=database_stats,
        jobs=jobs,
        platform=platform,
        project=project,
    )
    return {
        "project": project,
        "dashboard": dashboard,
        "database_stats": database_stats,
        "input_summary": input_summary,
    }


def build_today_intelligence_prompt(input_summary: dict[str, Any]) -> str:
    schema = {
        "executive_summary": "120字以内中文总结",
        "actions": [
            {
                "id": "action id",
                "title": "行动标题",
                "reason": "基于证据解释为什么今天要做",
                "priority_explanation": "优先级解释",
                "target_type": "collection|content|creator|competitor|keyword|system",
                "action": "retry_task|collect_more|open_opportunity|contact_creator|create_tracker|review_risk|view_detail",
                "payload": {},
                "evidence_refs": ["evidence id"],
                "risk_notes": ["风险"],
            }
        ],
        "opportunity_explanations": [
            {
                "opportunity_id": "必须来自输入 opportunities[].id",
                "why_now": "为什么现在值得做",
                "suggested_angle": "内容或运营角度",
                "execution_advice": "下一步动作建议",
                "risk_notes": ["风险"],
                "evidence_refs": ["evidence id"],
            }
        ],
        "risk_explanations": [
            {
                "risk_id": "必须来自输入 risks[].id",
                "business_impact": "业务影响",
                "recommended_action": "处理建议",
                "evidence_refs": ["evidence id"],
            }
        ],
        "sample_quality_explanation": {
            "summary": "样本质量解释",
            "coverage_gap": "覆盖缺口",
            "collection_advice": "补采建议",
        },
        "data_bias_notes": ["数据偏向说明"],
        "assumptions": ["分析假设"],
    }
    return (
        "你是社交媒体增长情报分析师。只能基于输入数据分析，不能编造外部事实。\n"
        "今日情报默认由 AI 生成，但事实、数量、风险等级和机会基础分都来自输入，不允许改写。\n"
        "硬性要求：\n"
        "1. 所有 opportunity_id 必须来自输入 opportunities[].id。\n"
        "2. 所有 risk_id 必须来自输入 risks[].id。\n"
        "3. 不要声称平台确定推流或限流，只能说疑似、观察或影响可信度。\n"
        "4. 样本不足时必须降低语气，优先建议补采。\n"
        "5. 输出 JSON，不要 Markdown，不要 JSON 之外的解释。\n"
        f"输出 JSON schema 示例：{json.dumps(schema, ensure_ascii=False)}\n"
        f"输入数据：{json.dumps(input_summary, ensure_ascii=False, default=str)}"
    )


def build_rule_based_today_intelligence_fallback(
    input_summary: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    actions = input_summary.get("rule_actions") or []
    opportunities = input_summary.get("opportunities") or []
    risks = input_summary.get("risks") or []
    sample_quality = input_summary.get("sample_quality") or {}
    top_opportunity = opportunities[0] if opportunities else None
    executive_summary = (
        f"AI 分析不可用，已使用规则结果。优先处理「{actions[0]['title']}」。"
        if actions
        else "AI 分析不可用，当前样本不足，建议先完成采集后再生成今日情报。"
    )
    if top_opportunity:
        executive_summary += f" 今日最强机会为「{top_opportunity.get('title')}」。"
    return {
        "executive_summary": executive_summary,
        "actions": [
            {
                "id": item.get("id") or f"rule-action-{index}",
                "title": item.get("title") or "处理今日任务",
                "reason": item.get("reason") or "来自规则降级结果。",
                "priority_explanation": item.get("bucket") or "规则优先级",
                "target_type": item.get("target_type") or "system",
                "action": item.get("action") or "view_detail",
                "payload": item.get("payload") or {},
                "evidence_refs": item.get("evidence_refs") or [],
                "risk_notes": ["AI 分析失败，当前为规则降级建议。"],
            }
            for index, item in enumerate(actions[:6])
        ],
        "opportunity_explanations": [
            {
                "opportunity_id": item.get("id"),
                "why_now": item.get("reason") or "规则识别到该机会的基础分靠前。",
                "suggested_angle": "先复核证据，再进入内容排期或达人跟进。",
                "execution_advice": "打开机会详情查看样本和风险。",
                "risk_notes": item.get("risk_tags") or [],
                "evidence_refs": item.get("evidence_refs") or [],
            }
            for item in opportunities[:8]
            if item.get("id")
        ],
        "risk_explanations": [
            {
                "risk_id": item.get("id"),
                "business_impact": item.get("body") or item.get("title") or "该风险会影响判断可信度。",
                "recommended_action": item.get("action") or "先查看任务或补采样本。",
                "evidence_refs": item.get("evidence_refs") or [],
            }
            for item in risks[:6]
            if item.get("id")
        ],
        "sample_quality_explanation": {
            "summary": sample_quality.get("summary") or "样本质量由规则计算。",
            "coverage_gap": sample_quality.get("coverage_gap") or "平台覆盖不足时请补采。",
            "collection_advice": sample_quality.get("collection_advice") or "优先补齐低覆盖平台和近 3 天样本。",
        },
        "data_bias_notes": ["这是规则降级输出。", *input_summary.get("data_bias_notes", [])],
        "assumptions": [reason],
    }


def _normalize_ai_output(raw: dict[str, Any], *, bundle: dict[str, Any]) -> dict[str, Any]:
    fallback = build_rule_based_today_intelligence_fallback(
        bundle["input_summary"],
        reason="AI output normalization fallback",
    )
    output = raw if isinstance(raw, dict) else {}
    return {
        "executive_summary": _string(output.get("executive_summary"))
        or fallback["executive_summary"],
        "actions": _list(output.get("actions")) or fallback["actions"],
        "opportunity_explanations": _filter_opportunity_explanations(
            _list(output.get("opportunity_explanations")),
            bundle["input_summary"],
        )
        or fallback["opportunity_explanations"],
        "risk_explanations": _filter_risk_explanations(
            _list(output.get("risk_explanations")),
            bundle["input_summary"],
        )
        or fallback["risk_explanations"],
        "sample_quality_explanation": _dict(output.get("sample_quality_explanation"))
        or fallback["sample_quality_explanation"],
        "data_bias_notes": [str(item) for item in _list(output.get("data_bias_notes"))],
        "assumptions": [str(item) for item in _list(output.get("assumptions"))],
    }


def _result_payload(
    *,
    status: str,
    source: str,
    generated_at: datetime,
    expires_at: datetime,
    provider: dict[str, Any] | None,
    output: dict[str, Any],
    bundle: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "source": source,
        "project_id": (bundle.get("project") or {}).get("id"),
        "project": bundle.get("project"),
        "generated_at": generated_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "error": error,
        "provider": provider,
        "executive_summary": output.get("executive_summary") or "",
        "actions": output.get("actions") or [],
        "opportunity_explanations": output.get("opportunity_explanations") or [],
        "risk_explanations": output.get("risk_explanations") or [],
        "sample_quality_explanation": output.get("sample_quality_explanation") or {},
        "data_bias_notes": output.get("data_bias_notes") or [],
        "assumptions": output.get("assumptions") or [],
        "input_summary": bundle.get("input_summary") or {},
        "dashboard": bundle.get("dashboard") or {},
        "database_stats": bundle.get("database_stats") or _empty_database_stats(),
    }


def _compact_input_summary(
    *,
    dashboard: dict[str, Any],
    database_stats: dict[str, Any],
    jobs: list[dict[str, Any]],
    platform: str | None,
    project: dict[str, Any] | None = None,
) -> dict[str, Any]:
    opportunities = [
        _compact_opportunity(item)
        for item in (dashboard.get("opportunities") or dashboard.get("top_opportunities") or [])[:8]
    ]
    rule_actions = _compact_actions(dashboard.get("actions") or {})
    risks = _compact_risks(dashboard)
    sample_quality = _sample_quality(database_stats=database_stats, dashboard=dashboard)
    return {
        "window": "近 3 天真实采集数据 + 7d 机会评分窗口",
        "platform": platform,
        "scope": "project" if project else "global",
        "project": project,
        "generated_input_at": datetime.now(timezone.utc).isoformat(),
        "decision": dashboard.get("decision") or {},
        "monitoring": dashboard.get("monitoring") or {},
        "jobs": _compact_jobs(jobs),
        "rule_actions": rule_actions,
        "opportunities": opportunities,
        "risks": risks,
        "sample_quality": sample_quality,
        "database_stats": _compact_database_stats(database_stats),
        "data_bias_notes": _data_bias_notes(database_stats),
    }


def _compact_project(
    *,
    project_id: str | None,
    project_record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not project_id and not project_record:
        return None
    resolved_id = str((project_record or {}).get("id") or project_id or "").strip()
    name = str((project_record or {}).get("name") or project_id or "").strip()
    return {
        "id": resolved_id,
        "requested_id": project_id,
        "name": name,
        "primary_goal": (project_record or {}).get("primary_goal"),
        "platforms": (project_record or {}).get("platforms") or [],
        "scene_pack_id": (project_record or {}).get("scene_pack_id"),
        "sample_status": (project_record or {}).get("sample_status"),
        "recommended_action": (project_record or {}).get("recommended_action"),
    }


async def _project_jobs(
    repository: Any,
    *,
    project_id: str | None,
    project_record: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    keys = _project_keys(project_id=project_id, project_record=project_record)
    direct_jobs = await _maybe_call(repository, "list_jobs_for_project", sorted(keys), default=[])
    all_jobs = await _maybe_call(repository, "list_jobs", default=[])
    normalized_keys = {_slug_project_key(key) for key in keys}
    project_tokens: set[str] = set()
    for key in keys:
        project_tokens.update(_project_semantic_tokens(key))
    seen_ids = {int(job["id"]) for job in direct_jobs if job.get("id") is not None}
    related_jobs = [
        job
        for job in all_jobs
        if job.get("id") is not None
        and int(job["id"]) not in seen_ids
        and (
            _slug_project_key(project_key_for_job(job)) in normalized_keys
            or _is_semantic_project_job(project_tokens, job)
        )
    ]
    return [*direct_jobs, *related_jobs]


def _project_keys(
    *,
    project_id: str | None,
    project_record: dict[str, Any] | None,
) -> set[str]:
    keys = {
        str(project_id or ""),
        str((project_record or {}).get("id") or ""),
        str((project_record or {}).get("name") or ""),
        _slug_project_key((project_record or {}).get("name")),
    }
    return {key for key in keys if key}


async def _project_keywords(
    repository: Any,
    *,
    project_record: dict[str, Any] | None,
) -> set[str]:
    if not project_record or not project_record.get("id"):
        return set()
    rows = await _maybe_call(
        repository,
        "list_growth_project_keywords",
        int(project_record["id"]),
        default=[],
    )
    return {
        str(item.get("keyword") or "").strip()
        for item in rows
        if str(item.get("keyword") or "").strip()
        and str(item.get("keyword_type") or "").lower() not in {"negative", "excluded"}
        and str(item.get("status") or "active").lower() != "excluded"
    }


def _project_platforms(
    *,
    project_record: dict[str, Any] | None,
    jobs: list[dict[str, Any]],
    platform: str | None,
) -> set[str]:
    if platform:
        return {platform}
    platforms = {
        str(item or "").strip()
        for item in ((project_record or {}).get("platforms") or [])
        if str(item or "").strip()
    }
    for job in jobs:
        platforms.update(
            str(item or "").strip()
            for item in (job.get("platforms") or [])
            if str(item or "").strip()
        )
    return platforms


def _keywords_from_jobs(jobs: list[dict[str, Any]]) -> set[str]:
    keywords: set[str] = set()
    for job in jobs:
        keywords.update(
            str(item or "").strip()
            for item in (job.get("keywords") or [])
            if str(item or "").strip()
        )
    return keywords


def _filter_keyword_heat_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    project_keywords: set[str],
    project_platforms: set[str],
    platform: str | None,
) -> list[dict[str, Any]]:
    if not project_keywords and not project_platforms:
        return snapshots
    result = []
    for item in snapshots:
        item_platform = str(item.get("platform") or "").strip()
        if platform and item_platform != platform:
            continue
        if project_platforms and item_platform and item_platform not in project_platforms:
            continue
        keyword = str(item.get("keyword") or "").strip()
        if project_keywords and keyword not in project_keywords:
            continue
        result.append(item)
    return result[:50]


async def _project_creator_candidates(
    repository: Any,
    *,
    project_record: dict[str, Any] | None,
    project_keywords: set[str],
    project_platforms: set[str],
    platform: str | None,
) -> list[dict[str, Any]]:
    if project_record and project_record.get("id"):
        project_pool = await _maybe_call(
            repository,
            "list_creator_candidates",
            pool_name=f"project:{project_record['id']}:realtime",
            platform=platform,
            default=[],
        )
        if project_pool:
            return await _enrich_creator_candidates(repository, project_pool)

    candidates = await _maybe_call(
        repository,
        "list_creator_candidates",
        platform=platform,
        default=[],
    )
    if project_record:
        candidates = _filter_creator_candidates(
            candidates,
            project_keywords=project_keywords,
            project_platforms=project_platforms,
            platform=platform,
        )
    return await _enrich_creator_candidates(repository, candidates)


def _filter_creator_candidates(
    candidates: list[dict[str, Any]],
    *,
    project_keywords: set[str],
    project_platforms: set[str],
    platform: str | None,
) -> list[dict[str, Any]]:
    if not project_keywords:
        return []
    result = []
    for item in candidates:
        item_platform = str(item.get("platform") or "").strip()
        if platform and item_platform != platform:
            continue
        if project_platforms and item_platform and item_platform not in project_platforms:
            continue
        if _candidate_matches_keywords(item, project_keywords):
            result.append(item)
    return result[:50]


def _candidate_matches_keywords(item: dict[str, Any], project_keywords: set[str]) -> bool:
    haystack = " ".join(_candidate_text_values(item)).lower()
    if not haystack:
        return False
    for keyword in project_keywords:
        keyword_text = str(keyword or "").strip().lower()
        if keyword_text and keyword_text in haystack:
            return True
    return False


def _candidate_text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, dict):
        values: list[str] = []
        for key, item in value.items():
            if key in {"creator_id", "profile_url", "target_url"}:
                continue
            values.extend(_candidate_text_values(item))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_candidate_text_values(item))
        return values
    return []


async def _enrich_creator_candidates(
    repository: Any,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []
    for item in candidates:
        next_item = dict(item)
        creator_id = str(next_item.get("creator_id") or "").strip()
        profile = await _maybe_call(
            repository,
            "get_creator_profile",
            next_item.get("platform"),
            creator_id,
            default=None,
        )
        if isinstance(profile, dict):
            _merge_creator_profile_fields(next_item, profile, creator_id=creator_id)
        display_name = _public_creator_name(next_item, creator_id)
        if display_name:
            next_item["display_name"] = display_name
        enriched.append(next_item)
    return enriched


def _merge_creator_profile_fields(
    target: dict[str, Any],
    profile: dict[str, Any],
    *,
    creator_id: str,
) -> None:
    for key in (
        "display_name",
        "nickname",
        "profile_url",
        "bio",
        "follower_count",
        "following_count",
        "post_count",
        "avg_engagement_rate",
        "hot_post_rate",
        "recent_post_count_30d",
        "latest_snapshot_at",
    ):
        value = profile.get(key)
        if value not in (None, "") and not (
            key in {"display_name", "nickname"} and str(value).strip() == creator_id
        ):
            target[key] = value


def _public_creator_name(item: dict[str, Any], creator_id: str) -> str | None:
    for key in ("display_name", "nickname", "nick_name", "name"):
        value = str(item.get(key) or "").strip()
        if value and value != creator_id:
            return value
    return None


async def _project_competitor_compositions(
    repository: Any,
    *,
    project_record: dict[str, Any] | None,
    platform: str | None,
    fallback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not project_record or not project_record.get("id"):
        return []
    accounts = await _maybe_call(
        repository,
        "list_competitor_accounts",
        enabled_only=True,
        monitor_type="competitor",
        project_id=int(project_record["id"]),
        default=[],
    )
    if not accounts:
        return []
    snapshots: list[dict[str, Any]] = []
    for account in accounts[:12]:
        rows = await _maybe_call(
            repository,
            "list_competitor_composition_snapshots",
            competitor_id=account.get("id"),
            platform=platform,
            limit=5,
            default=[],
        )
        snapshots.extend(rows)
    return snapshots or fallback[:0]


def _filter_content_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    project_keywords: set[str],
    project_platforms: set[str],
    platform: str | None,
) -> list[dict[str, Any]]:
    result = []
    for item in snapshots:
        item_platform = str(item.get("platform") or "").strip()
        if platform and item_platform != platform:
            continue
        if project_platforms and item_platform and item_platform not in project_platforms:
            continue
        distribution = item.get("keyword_distribution") or item.get("keyword_distribution_json") or {}
        if project_keywords and isinstance(distribution, dict):
            if not (set(map(str, distribution.keys())) & project_keywords):
                continue
        result.append(item)
    return result[:50]


def _filter_monitor_pools(
    pools: list[dict[str, Any]],
    *,
    jobs: list[dict[str, Any]],
    project_record: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    job_ids = {int(job["id"]) for job in jobs if job.get("id") is not None}
    scene_pack_id = (project_record or {}).get("scene_pack_id")
    result = []
    for item in pools:
        if item.get("research_job_id") in job_ids:
            result.append(item)
            continue
        scene_ids = item.get("scene_pack_ids") or []
        if scene_pack_id and (item.get("scene_pack_id") == scene_pack_id or scene_pack_id in scene_ids):
            result.append(item)
    return result


async def _project_database_stats(repository: Any, *, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    job_ids = [int(job["id"]) for job in jobs if job.get("id") is not None]
    if not job_ids:
        return _empty_database_stats()
    stats_by_job = await _maybe_call(repository, "get_job_stats_many", job_ids, default={})
    posts = comments = raw_records = creators = 0
    post_platforms: dict[str, int] = {}
    comment_platforms: dict[str, int] = {}
    for stats in (stats_by_job or {}).values():
        posts += int(stats.get("posts") or 0)
        comments += int(stats.get("comments") or 0)
        raw_records += int(stats.get("raw_records") or 0)
        creators += int(stats.get("authors") or stats.get("creators") or 0)
        by_platform = stats.get("by_platform") or {}
        _merge_platform_counts(post_platforms, by_platform.get("posts") or {})
        _merge_platform_counts(comment_platforms, by_platform.get("comments") or {})
    return {
        "total_collected": posts + comments + raw_records,
        "research_posts": posts,
        "research_comments": comments,
        "raw_records": raw_records,
        "creator_profiles": creators,
        "entity_tags": 0,
        "creator_candidates": 0,
        "by_platform": {
            "posts": post_platforms,
            "comments": comment_platforms,
            "raw_records": {},
        },
        "raw_platform_tables": {},
        "raw_platform_totals": {},
    }


def _merge_platform_counts(target: dict[str, int], source: dict[str, Any]) -> None:
    for key, value in source.items():
        target[str(key)] = int(target.get(str(key), 0)) + int(value or 0)


def _slug_project_key(value: object) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    return "".join(
        ch if ch.isalnum() or ch == "_" or ("\u4e00" <= ch <= "\u9fff") else "_"
        for ch in raw
    ).strip("_")


_PROJECT_TOKEN_STOPWORDS = {"collection", "initial", "project", "research", "topic"}


def _project_semantic_tokens(value: object) -> set[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return set()
    tokens = set(re.findall(r"[a-z0-9]+", raw))
    if "education" in raw or "\u6559\u80b2" in raw:
        tokens.update({"education", "\u6559\u80b2"})
    if "summer" in raw or "\u6691" in raw:
        tokens.add("summer")
    return {
        token
        for token in tokens
        if len(token) > 1 and token not in _PROJECT_TOKEN_STOPWORDS
    }


def _job_semantic_tokens(job: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for value in (job.get("topic"), project_key_for_job(job)):
        tokens.update(_project_semantic_tokens(value))
    return tokens


def _is_semantic_project_job(project_tokens: set[str], job: dict[str, Any]) -> bool:
    if not project_tokens:
        return False
    job_tokens = _job_semantic_tokens(job)
    project_digits = {token for token in project_tokens if token.isdigit()}
    job_digits = {token for token in job_tokens if token.isdigit()}
    if project_digits and (
        not project_digits.issubset(job_digits)
        or bool(job_digits - project_digits)
    ):
        return False
    return len(project_tokens & job_tokens) >= 2


def _compact_actions(actions: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for bucket, rows in (
        ("立即处理", actions.get("do_now") or []),
        ("今日观察", actions.get("watch_today") or []),
        ("暂缓", actions.get("defer") or []),
    ):
        for index, item in enumerate(rows):
            if not isinstance(item, dict):
                continue
            result.append(
                {
                    "id": f"{bucket}:{index}:{item.get('title')}",
                    "bucket": bucket,
                    "title": item.get("title"),
                    "reason": item.get("reason"),
                    "target_type": item.get("target_type"),
                    "action": item.get("action"),
                    "payload": item.get("payload") or {},
                }
            )
    return result


def _compact_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    sample_scope = item.get("sample_scope") or {}
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "title": item.get("display_title") or item.get("name"),
        "platform": item.get("platform"),
        "score": item.get("score"),
        "confidence": item.get("confidence"),
        "reason": item.get("reason"),
        "risk_tags": item.get("risk_tags") or [],
        "evidence_summary": item.get("evidence_summary") or [],
        "evidence_refs": [sample.get("title") for sample in (item.get("samples") or [])[:3] if isinstance(sample, dict)],
        "sample_count": sample_scope.get("sample_count"),
        "sample_platforms": sample_scope.get("platforms") or [],
        "last_updated_at": sample_scope.get("last_updated_at"),
        "payload": item.get("payload") or {},
    }


def _compact_risks(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    decision = dashboard.get("decision") or {}
    for index, note in enumerate(decision.get("risk_notes") or []):
        risks.append(
            {
                "id": f"decision-risk-{index}",
                "title": "决策风险",
                "body": str(note),
                "action": "review_sample_quality",
            }
        )
    for item in dashboard.get("diagnostics") or []:
        if not isinstance(item, dict):
            continue
        risks.append(
            {
                "id": f"diagnostic-{item.get('code') or len(risks)}",
                "title": item.get("title"),
                "body": item.get("body"),
                "action": item.get("action") or "view_detail",
            }
        )
    monitoring = dashboard.get("monitoring") or {}
    if int(monitoring.get("failed_jobs") or monitoring.get("errors") or 0) > 0:
        risks.append(
            {
                "id": "monitoring-failed-jobs",
                "title": "采集任务失败",
                "body": f"{monitoring.get('failed_jobs') or monitoring.get('errors')} 个任务失败，可能影响今日判断。",
                "action": "view_jobs",
            }
        )
    return risks


def _sample_quality(*, database_stats: dict[str, Any], dashboard: dict[str, Any]) -> dict[str, Any]:
    posts = int(database_stats.get("research_posts") or 0)
    comments = int(database_stats.get("research_comments") or 0)
    raw_records = int(database_stats.get("raw_records") or 0)
    platform_counts = (database_stats.get("by_platform") or {}).get("posts") or {}
    platform_count = len([value for value in platform_counts.values() if int(value or 0) > 0])
    decision = dashboard.get("decision") or {}
    if posts >= 100 and platform_count >= 2:
        grade = "high"
    elif posts >= 40 or raw_records >= 100:
        grade = "medium"
    elif posts > 0 or raw_records > 0:
        grade = "low"
    else:
        grade = "insufficient"
    coverage_gap = "平台覆盖充足" if platform_count >= 2 else "平台覆盖偏单一，建议补采至少一个平台。"
    if grade == "insufficient":
        collection_advice = "先完成首轮项目采集，再生成强行动建议。"
    elif grade == "low":
        collection_advice = "先补齐近 3 天内容样本，再执行机会动作。"
    else:
        collection_advice = "可进入机会复核，同时继续补齐低覆盖平台。"
    actual_summary = f"标准化项目样本 {posts} 条，评论 {comments} 条，raw {raw_records} 条。"
    summary = actual_summary if grade == "insufficient" else (decision.get("sample_summary") or actual_summary)
    return {
        "grade": grade,
        "posts": posts,
        "comments": comments,
        "raw_records": raw_records,
        "platform_count": platform_count,
        "summary": decision.get("sample_summary") or f"标准内容样本 {posts} 条，评论 {comments} 条，raw {raw_records} 条。",
        "summary": summary,
        "coverage_gap": coverage_gap,
        "collection_advice": collection_advice,
    }


def _compact_database_stats(database_stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_collected": database_stats.get("total_collected") or 0,
        "research_posts": database_stats.get("research_posts") or 0,
        "research_comments": database_stats.get("research_comments") or 0,
        "raw_records": database_stats.get("raw_records") or 0,
        "creator_profiles": database_stats.get("creator_profiles") or 0,
        "creator_candidates": database_stats.get("creator_candidates") or 0,
        "by_platform": database_stats.get("by_platform") or {},
    }


def _compact_jobs(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for job in jobs:
        status = str(job.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "total": len(jobs),
        "status_counts": counts,
        "recent": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "platforms": item.get("platforms") or [],
            }
            for item in jobs[:8]
        ],
    }


def _data_bias_notes(database_stats: dict[str, Any]) -> list[str]:
    platform_counts = ((database_stats.get("by_platform") or {}).get("posts") or {})
    if not platform_counts:
        return ["暂无标准化平台样本，当前结论需要先补采。"]
    total = sum(int(value or 0) for value in platform_counts.values())
    if total <= 0:
        return ["暂无标准化平台样本，当前结论需要先补采。"]
    top_platform, top_count = max(platform_counts.items(), key=lambda item: int(item[1] or 0))
    if int(top_count or 0) / total >= 0.75:
        return [f"样本明显偏向 {top_platform}，跨平台结论需要谨慎。"]
    return []


async def _resolve_provider(repository: Any) -> dict[str, Any]:
    env_api_key = os.getenv("AI_GATEWAY_API_KEY")
    if env_api_key:
        return {
            "name": os.getenv("AI_GATEWAY_NAME", "AI Gateway"),
            "base_url": os.getenv("AI_GATEWAY_BASE_URL", "https://4router.net/v1"),
            "api_key": env_api_key,
            "model": os.getenv("AI_GATEWAY_MODEL", "gpt-5.4-mini"),
            "timeout": int(os.getenv("AI_GATEWAY_TIMEOUT", "60")),
            "default_params": {
                "temperature": float(os.getenv("AI_GATEWAY_TEMPERATURE", "0.2")),
                "max_tokens": int(os.getenv("AI_GATEWAY_MAX_TOKENS", "1200")),
            },
        }
    providers = await _maybe_call(repository, "list_ai_providers", default=[])
    enabled = [item for item in providers if item.get("enabled") and item.get("api_key_set")]
    selected = next((item for item in enabled if "gateway" in str(item.get("name") or "").lower()), None)
    selected = selected or (enabled[0] if enabled else None)
    if selected is None:
        raise ValueError("AI_GATEWAY_API_KEY is not configured and no enabled AI provider exists")
    provider = await repository.get_ai_provider(selected["id"], include_secret=True)
    if provider is None:
        raise ValueError("AI provider config not found")
    return provider


async def _maybe_call(obj: Any, method: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    func = getattr(obj, method, None)
    if func is None:
        return default
    try:
        return await func(*args, **kwargs)
    except TypeError:
        return await func(*args)
    except Exception:
        return default


def _filter_opportunity_explanations(items: list[Any], input_summary: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = {item.get("id") for item in input_summary.get("opportunities") or []}
    result = []
    for item in items:
        if not isinstance(item, dict) or item.get("opportunity_id") not in allowed:
            continue
        result.append(item)
    return result


def _filter_risk_explanations(items: list[Any], input_summary: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = {item.get("id") for item in input_summary.get("risks") or []}
    result = []
    for item in items:
        if not isinstance(item, dict) or item.get("risk_id") not in allowed:
            continue
        result.append(item)
    return result


def _ai_status(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": value.get("status") or "missing",
        "source": value.get("source") or "none",
        "generated_at": value.get("generated_at"),
        "expires_at": value.get("expires_at"),
        "provider": value.get("provider"),
        "error": value.get("error"),
    }


def _is_fresh(value: Any, *, max_age_minutes: int) -> bool:
    parsed = _parse_datetime(value)
    if parsed is None:
        return False
    return datetime.now(timezone.utc) - parsed <= timedelta(minutes=max_age_minutes)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _setting_key(
    *,
    platform: str | None,
    project_id: str | None = None,
    project_record: dict[str, Any] | None = None,
) -> str:
    scope_id = str((project_record or {}).get("id") or project_id or "").strip()
    key = (
        f"{TODAY_INTELLIGENCE_SETTING_KEY}:project:{scope_id}"
        if scope_id
        else TODAY_INTELLIGENCE_SETTING_KEY
    )
    return f"{key}:platform:{platform}" if platform else key


def _empty_database_stats() -> dict[str, Any]:
    return {
        "total_collected": 0,
        "research_posts": 0,
        "research_comments": 0,
        "raw_records": 0,
        "creator_profiles": 0,
        "entity_tags": 0,
        "creator_candidates": 0,
        "by_platform": {"posts": {}, "comments": {}, "raw_records": {}},
        "raw_platform_tables": {},
        "raw_platform_totals": {},
    }


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}

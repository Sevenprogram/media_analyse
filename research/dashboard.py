from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


SCORING_WEIGHTS = {
    "heat_growth": 0.35,
    "sample_confidence": 0.25,
    "competition_gap": 0.2,
    "actionability": 0.2,
}

RISK_SMALL_SAMPLE_SPIKE = "small_sample_spike"
RISK_SINGLE_PLATFORM_SIGNAL = "single_platform_signal"
RISK_STALE_DATA = "stale_data"
RISK_OVERHEATED_COMPETITION = "overheated_competition"
RISK_MISSING_EXECUTION_PARAMETERS = "missing_execution_parameters"
RISK_HIGH_COST = "high_cost"


def build_dashboard_summary(
    *,
    jobs: list[dict[str, Any]],
    creator_candidates: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
    monitor_pools: list[dict[str, Any]],
    platform: str | None,
    feedback: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    opportunities = _build_opportunities(
        creator_candidates=creator_candidates,
        keyword_heat_snapshots=keyword_heat_snapshots,
        competitor_compositions=competitor_compositions,
        content_snapshots=content_snapshots,
    )
    opportunities, watchlist, ignored_opportunities = _apply_feedback_and_split(
        opportunities=opportunities,
        feedback=feedback or [],
    )
    monitoring = _build_monitoring(
        jobs=jobs,
        monitor_pools=monitor_pools,
        keyword_heat_snapshots=keyword_heat_snapshots,
        competitor_compositions=competitor_compositions,
        content_snapshots=content_snapshots,
    )
    diagnostics = _build_diagnostics(
        opportunities=opportunities,
        watchlist=watchlist,
        ignored_opportunities=ignored_opportunities,
        monitoring=monitoring,
    )
    type_decisions = _build_type_decisions(
        opportunities=opportunities,
        watchlist=watchlist,
        monitoring=monitoring,
        platform=platform,
    )
    type_diagnostics = _build_type_diagnostics(
        opportunities=opportunities,
        watchlist=watchlist,
    )
    decision = _build_decision(
        opportunities=opportunities,
        watchlist=watchlist,
        monitoring=monitoring,
        platform=platform,
    )
    top_opportunities = opportunities[:5]
    return {
        "decision": decision,
        "actions": _build_actions(opportunities=top_opportunities, decision=decision),
        "monitoring": monitoring,
        "opportunities": opportunities,
        "top_opportunities": top_opportunities,
        "watchlist": watchlist,
        "ignored_opportunities": ignored_opportunities,
        "diagnostics": diagnostics,
        "type_decisions": type_decisions,
        "type_diagnostics": type_diagnostics,
        "scoring_profile": {"weights": SCORING_WEIGHTS, "window": "7d_plus_24h"},
    }


def _build_monitoring(
    *,
    jobs: list[dict[str, Any]],
    monitor_pools: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for item in jobs:
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    running_jobs = status_counts.get("running", 0)
    errors = sum(status_counts.get(status, 0) for status in ("failed", "error"))
    today_collected = sum(int(item.get("total_content_count") or 0) for item in content_snapshots)
    today_collected += sum(int(item.get("total_flow_count") or 0) for item in competitor_compositions)
    realtime_jobs = sum(
        1
        for item in jobs
        if item.get("collection_mode") == "search" and item.get("status") == "running"
    )
    last_updated_at = _latest_timestamp(
        keyword_heat_snapshots + competitor_compositions + content_snapshots
    )
    return {
        "running_jobs": running_jobs,
        "pending_jobs": status_counts.get("pending", 0),
        "completed_jobs": status_counts.get("completed", 0),
        "failed_jobs": errors,
        "job_status_counts": status_counts,
        "today_collected": today_collected,
        "errors": errors,
        "monitor_pools": len(monitor_pools),
        "realtime_jobs": realtime_jobs,
        "last_updated_at": last_updated_at,
    }


def _build_decision(
    *,
    opportunities: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    monitoring: dict[str, Any],
    platform: str | None,
) -> dict[str, Any]:
    del monitoring
    evidence_count = sum(int(item.get("evidence_count") or 0) for item in opportunities + watchlist)
    if not opportunities:
        return {
            "headline": "当前样本不足，建议先执行一次实时发现形成首批样本。",
            "confidence": "low",
            "sample_status": "insufficient",
            "sample_summary": "24h 与 7d 样本不足，暂不输出确定性判断。",
            "risk_notes": ["样本不足，暂不输出确定性推荐。"],
            "evidence_count": evidence_count,
        }

    top = opportunities[0]
    sample_status = "enough" if evidence_count >= 3 else "limited"
    confidence = "high" if top["score"] >= 85 and evidence_count >= 6 else "medium"
    platform_text = f"{platform} 平台" if platform else "当前平台"
    return {
        "headline": f"{platform_text}今日优先关注「{top['display_title']}」，{top['reason']}",
        "confidence": confidence,
        "sample_status": sample_status,
        "sample_summary": f"已形成 {len(opportunities)} 条机会线索，证据 {evidence_count} 条。",
        "risk_notes": [] if sample_status == "enough" else ["证据样本偏少，建议先观察样本覆盖和更新时间。"],
        "evidence_count": evidence_count,
    }


def _build_actions(
    *,
    opportunities: list[dict[str, Any]],
    decision: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    if not opportunities:
        return {
            "do_now": [
                {
                    "title": "补充一轮实时发现样本",
                    "reason": "当前样本不足，先采集关键词、内容、达人样本后再判断机会。",
                    "target_type": "keyword",
                    "action": "search_now",
                    "payload": {"keywords": ["K12教育", "单亲妈妈"]},
                }
            ],
            "watch_today": [],
            "defer": [
                {
                    "title": "暂缓生成增长报告",
                    "reason": decision["sample_summary"],
                    "target_type": "report",
                    "action": "view_detail",
                    "payload": {},
                }
            ],
        }

    do_now = [
        {
            "title": f"跟进 {item['display_title']}",
            "reason": item["reason"],
            "target_type": item["type"],
            "action": _last_action_kind(item),
            "payload": item["payload"],
        }
        for item in opportunities[:2]
    ]
    watch_today = [
        {
            "title": f"观察 {item['display_title']}",
            "reason": item["reason"],
            "target_type": item["type"],
            "action": "view_detail",
            "payload": item["payload"],
        }
        for item in opportunities[2:5]
    ]
    return {"do_now": do_now, "watch_today": watch_today, "defer": []}


def _build_type_decisions(
    *,
    opportunities: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    monitoring: dict[str, Any],
    platform: str | None,
) -> dict[str, dict[str, Any]]:
    return {
        opportunity_type: _build_single_type_decision(
            opportunities=[item for item in opportunities if item.get("type") == opportunity_type],
            watchlist=[item for item in watchlist if item.get("type") == opportunity_type],
            platform=platform,
            opportunity_type=opportunity_type,
        )
        for opportunity_type in ("keyword", "content", "creator", "competitor")
    }


def _build_type_diagnostics(
    *,
    opportunities: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    labels = {
        "keyword": "关键词",
        "content": "内容",
        "creator": "达人",
        "competitor": "友商动作",
    }
    diagnostics: dict[str, list[dict[str, Any]]] = {}
    for opportunity_type, label in labels.items():
        type_opportunities = [item for item in opportunities if item.get("type") == opportunity_type]
        type_watchlist = [item for item in watchlist if item.get("type") == opportunity_type]
        entries: list[dict[str, Any]] = []
        if not type_opportunities and not type_watchlist:
            entries.append(
                {
                    "code": f"no_{opportunity_type}_opportunities",
                    "title": f"暂无{label}机会",
                    "body": f"当前还没有可展示的{label}样本；请先完成采集或刷新快照。",
                }
            )
        if type_watchlist:
            entries.append(
                {
                    "code": f"{opportunity_type}_watchlist_low_confidence",
                    "title": f"{label}存在待补证据项",
                    "body": f"{len(type_watchlist)} 条{label}机会因样本少、证据不足或数据过旧进入观察池。",
                }
            )
        diagnostics[opportunity_type] = entries
    return diagnostics


def _build_single_type_decision(
    *,
    opportunities: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    platform: str | None,
    opportunity_type: str,
) -> dict[str, Any]:
    labels = {
        "keyword": "关键词",
        "content": "内容",
        "creator": "达人",
        "competitor": "友商动作",
    }
    label = labels.get(opportunity_type, "机会")
    ranked = opportunities or watchlist
    evidence_count = sum(int(item.get("evidence_count") or 0) for item in ranked)
    if not ranked:
        return {
            "headline": f"当前暂无可判断的{label}机会。",
            "confidence": "low",
            "sample_status": "insufficient",
            "sample_summary": f"还没有形成{label}样本，请先采集或重建对应快照。",
            "risk_notes": [f"{label}样本不足，暂不输出确定性推荐。"],
            "evidence_count": 0,
        }

    top = ranked[0]
    sample_count = int((top.get("sample_scope") or {}).get("sample_count") or 0)
    sample_status = "enough" if opportunities and evidence_count >= 3 and sample_count >= 10 else "limited"
    confidence = "high" if top.get("confidence") == "high" else "medium" if opportunities else "low"
    platform_text = f"{platform} 平台" if platform else "当前平台"
    return {
        "headline": f"{platform_text}{label}优先关注「{top.get('display_title') or top.get('name')}」。",
        "confidence": confidence,
        "sample_status": sample_status,
        "sample_summary": f"{label}共 {len(ranked)} 条线索，证据 {evidence_count} 条。",
        "risk_notes": [] if sample_status == "enough" else [f"{label}证据仍偏少，建议先补样本再执行。"],
        "evidence_count": evidence_count,
    }


def _build_opportunities(
    *,
    creator_candidates: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items = []
    items.extend(_creator_opportunity(item) for item in creator_candidates)
    items.extend(_keyword_opportunity(item) for item in keyword_heat_snapshots)
    items.extend(_competitor_opportunity(item) for item in competitor_compositions)
    items.extend(_content_opportunity(item) for item in content_snapshots)
    items = _dedupe_opportunities(items)
    items.sort(key=lambda item: item["score"], reverse=True)
    return items


def _dedupe_opportunities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for item in items:
        key = _opportunity_dedupe_key(item)
        if key not in deduped:
            deduped[key] = item
            order.append(key)
            continue
        deduped[key] = _merge_opportunity(deduped[key], item)
    return [deduped[key] for key in order]


def _opportunity_dedupe_key(item: dict[str, Any]) -> tuple[str, str]:
    opportunity_type = str(item.get("type") or "")
    if opportunity_type == "keyword":
        keyword = _normalize_dedupe_text(
            ((item.get("payload") or {}).get("keyword") if isinstance(item.get("payload"), dict) else None)
            or item.get("display_title")
            or item.get("name")
            or item.get("id")
        )
        if keyword:
            return ("keyword", keyword)
    return (opportunity_type or "unknown", str(item.get("id") or id(item)))


def _merge_opportunity(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    winner, other = (
        (incoming, existing)
        if float(incoming.get("score") or 0) > float(existing.get("score") or 0)
        else (existing, incoming)
    )
    merged = dict(winner)
    existing_platforms = _opportunity_platforms(existing)
    incoming_platforms = _opportunity_platforms(incoming)
    platforms = _unique_strings([*existing_platforms, *incoming_platforms])
    source_ids = _unique_strings(
        [
            *((existing.get("payload") or {}).get("source_opportunity_ids") or []),
            *((incoming.get("payload") or {}).get("source_opportunity_ids") or []),
            existing.get("id"),
            incoming.get("id"),
        ]
    )
    sample_scope = dict(merged.get("sample_scope") or {})
    sample_scope["platforms"] = platforms
    sample_scope["sample_count"] = _merged_sample_count(existing, incoming)
    sample_scope["last_updated_at"] = _latest_timestamp_values(
        [
            (existing.get("sample_scope") or {}).get("last_updated_at"),
            (incoming.get("sample_scope") or {}).get("last_updated_at"),
        ]
    )
    samples = _dedupe_samples([*(existing.get("samples") or []), *(incoming.get("samples") or [])])
    evidence_summary = _unique_strings(
        [*(existing.get("evidence_summary") or []), *(incoming.get("evidence_summary") or [])]
    )
    risk_tags = _unique_strings([*(existing.get("risk_tags") or []), *(incoming.get("risk_tags") or [])])
    if len(platforms) > 1:
        risk_tags = [tag for tag in risk_tags if tag != RISK_SINGLE_PLATFORM_SIGNAL]
    payload = dict(merged.get("payload") or {})
    payload["platforms"] = platforms
    payload["source_opportunity_ids"] = source_ids
    if merged.get("type") == "keyword" and len(platforms) > 1:
        payload["merged_platform_signal"] = True
    merged["payload"] = payload
    merged["sample_scope"] = sample_scope
    merged["samples"] = samples
    merged["risk_tags"] = risk_tags
    merged["evidence_summary"] = evidence_summary or merged.get("evidence_summary") or []
    merged["evidence_count"] = max(
        int(existing.get("evidence_count") or 0),
        int(incoming.get("evidence_count") or 0),
        len(samples),
    )
    merged["confidence"] = _confidence(
        float(merged.get("score") or 0),
        int(merged.get("evidence_count") or 0),
        int(sample_scope.get("sample_count") or 0),
    )
    detail = dict(merged.get("detail") or {})
    detail["summary"] = merged["evidence_summary"]
    merged["detail"] = detail
    if merged.get("type") == "keyword" and len(platforms) > 1:
        merged["display_subtitle"] = f"{' / '.join(_label_platform(platform) for platform in platforms)}关键词 · 样本 {sample_scope['sample_count']}"
        merged["reason"] = _append_sentence_once(
            str(merged.get("reason") or other.get("reason") or ""),
            "已合并多个平台的同名话题信号。",
        )
    return merged


def _opportunity_platforms(item: dict[str, Any]) -> list[str]:
    sample_scope = item.get("sample_scope") or {}
    platforms = sample_scope.get("platforms")
    if isinstance(platforms, list) and platforms:
        return _unique_strings(platforms)
    platform = item.get("platform") or (item.get("payload") or {}).get("platform")
    return [str(platform)] if platform else []


def _merged_sample_count(existing: dict[str, Any], incoming: dict[str, Any]) -> int:
    existing_count = int((existing.get("sample_scope") or {}).get("sample_count") or 0)
    incoming_count = int((incoming.get("sample_scope") or {}).get("sample_count") or 0)
    existing_platforms = set(_opportunity_platforms(existing))
    incoming_platforms = set(_opportunity_platforms(incoming))
    if existing_platforms and incoming_platforms and existing_platforms.isdisjoint(incoming_platforms):
        return existing_count + incoming_count
    return max(existing_count, incoming_count)


def _dedupe_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        key = _normalize_dedupe_text(
            sample.get("url")
            or sample.get("source_url")
            or sample.get("platform_post_id")
            or f"{sample.get('platform')}:{sample.get('title')}"
        )
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(sample)
    return result[:12]


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _normalize_dedupe_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _append_sentence_once(text: str, sentence: str) -> str:
    text = str(text or "").strip()
    sentence = str(sentence or "").strip()
    if not sentence or sentence in text:
        return text
    return f"{text} {sentence}".strip()


def _latest_timestamp_values(values: list[Any]) -> str | None:
    parsed_values = [_parse_datetime(value) for value in values if value]
    parsed_values = [value for value in parsed_values if value is not None]
    if parsed_values:
        return max(parsed_values).isoformat()
    for value in values:
        if value:
            return str(value)
    return None


def _creator_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    creator_id = str(item.get("creator_id") or "")
    name = item.get("display_name") or creator_id or "未命名达人"
    platform = item.get("platform")
    evidence = item.get("evidence") or []
    evidence_count = _evidence_count(evidence)
    sample_count = _sample_count(item, evidence, default=int(item.get("recent_post_count_30d") or 30))
    platforms = _platforms(item)
    stale = _is_stale(item)
    breakdown = {
        "heat_growth": _clamp(float(item.get("match_score") or 0) * 0.7 + float(item.get("hot_post_rate") or 0) * 30),
        "sample_confidence": _sample_confidence_score(sample_count, platforms, stale),
        "competition_gap": _clamp(70 + (100 - float(item.get("match_score") or 0)) * 0.1),
        "actionability": _clamp(65 + float(item.get("recent_post_count_30d") or 0) * 1.5),
    }
    payload = {
        "platform": platform,
        "creator_id": creator_id,
        "display_name": name,
        "profile_url": _creator_profile_url(platform, creator_id, item),
    }
    summary = [f"匹配分 {round(float(item.get('match_score') or 0), 1)}，近 30 天内容 {sample_count} 条。"]
    return _standard_opportunity(
        opportunity_id=f"creator:{platform}:{creator_id}",
        opportunity_type="creator",
        name=name,
        display_title=name,
        display_subtitle=f"{_label_platform(platform)}达人 · {creator_id}" if creator_id else f"{_label_platform(platform)}达人",
        target_url=payload["profile_url"],
        platform=platform,
        breakdown=breakdown,
        risk_tags=_risk_tags(
            item=item,
            sample_count=sample_count,
            platforms=platforms,
            stale=stale,
            heat_growth=breakdown["heat_growth"],
            competition_gap=breakdown["competition_gap"],
            actionability=breakdown["actionability"],
        ),
        evidence_summary=summary,
        sample_count=sample_count,
        platforms=platforms,
        last_updated_at=_last_updated_at(item),
        change_24h=0.0,
        trend_7d=float(item.get("recent_post_count_30d") or 0),
        evidence=evidence,
        evidence_count=evidence_count,
        payload=payload,
        reason="主词匹配较高且近期持续发布，适合优先复核并加入监控。",
        samples=_samples_from_evidence(evidence, default_type="creator", platform=platform),
    )


def _keyword_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    keyword = item.get("keyword") or item.get("tag_name") or str(item.get("tag_id") or "关键词机会")
    platform = item.get("platform")
    evidence = item.get("evidence") or {}
    evidence_count = _evidence_count(evidence)
    sample_count = _sample_count(item, evidence, default=30)
    platforms = _platforms(item)
    stale = _is_stale(item)
    heat_score = float(item.get("heat_score") or 0)
    growth_score = float(item.get("growth_score") or 0)
    breakdown = {
        "heat_growth": _clamp(heat_score * 0.65 + growth_score * 0.35),
        "sample_confidence": _sample_confidence_score(sample_count, platforms, stale),
        "competition_gap": _competition_gap_score(item, default=75.0),
        "actionability": _keyword_actionability(item),
    }
    payload = {"platform": platform, "keyword": keyword}
    summary = [f"热度 {round(heat_score, 1)}，24h 增长 {round(growth_score, 1)}，平台信号 {item.get('platform_signal') or 'normal'}。"]
    return _standard_opportunity(
        opportunity_id=f"keyword:{platform}:{keyword}",
        opportunity_type="keyword",
        name=keyword,
        display_title=str(keyword),
        display_subtitle=f"{_label_platform(platform)}关键词 · 样本 {sample_count}",
        target_url=None,
        platform=platform,
        breakdown=breakdown,
        risk_tags=_risk_tags(
            item=item,
            sample_count=sample_count,
            platforms=platforms,
            stale=stale,
            heat_growth=breakdown["heat_growth"],
            competition_gap=breakdown["competition_gap"],
            actionability=breakdown["actionability"],
        ),
        evidence_summary=summary,
        sample_count=sample_count,
        platforms=platforms,
        last_updated_at=_last_updated_at(item),
        change_24h=growth_score,
        trend_7d=heat_score,
        evidence=evidence,
        evidence_count=evidence_count,
        payload=payload,
        reason=f"热度分 {round(heat_score, 1)}，增长分 {round(growth_score, 1)}，值得马上补样本验证。",
        samples=_samples_from_evidence(evidence, default_type="post", platform=platform),
    )


def _competitor_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    platform = item.get("platform")
    name = item.get("display_name") or item.get("competitor_name") or f"友商 #{item.get('competitor_id')}"
    evidence = item.get("evidence") or {}
    top_posts = evidence.get("top_posts") or [] if isinstance(evidence, dict) else []
    evidence_count = len(top_posts) or _evidence_count(evidence)
    sample_count = _sample_count(item, evidence, default=int(item.get("total_flow_count") or 30))
    platforms = _platforms(item)
    stale = _is_stale(item)
    total_flow_count = float(item.get("total_flow_count") or 0)
    hot_post_rate = float(item.get("hot_post_rate") or 0)
    breakdown = {
        "heat_growth": _clamp(total_flow_count / 100 + hot_post_rate * 60),
        "sample_confidence": _sample_confidence_score(sample_count, platforms, stale),
        "competition_gap": _competition_gap_score(item, default=max(15.0, 85.0 - hot_post_rate * 80)),
        "actionability": _clamp(55 + evidence_count * 12),
    }
    payload = {"platform": platform, "competitor_id": item.get("competitor_id")}
    summary = [f"友商内容流量 {int(total_flow_count)}，高互动率 {round(hot_post_rate * 100, 1)}%。"]
    return _standard_opportunity(
        opportunity_id=f"competitor:{platform}:{item.get('competitor_id')}",
        opportunity_type="competitor",
        name=name,
        display_title=str(name),
        display_subtitle=f"{_label_platform(platform)}友商动作",
        target_url=None,
        platform=platform,
        breakdown=breakdown,
        risk_tags=_risk_tags(
            item=item,
            sample_count=sample_count,
            platforms=platforms,
            stale=stale,
            heat_growth=breakdown["heat_growth"],
            competition_gap=breakdown["competition_gap"],
            actionability=breakdown["actionability"],
        ),
        evidence_summary=summary,
        sample_count=sample_count,
        platforms=platforms,
        last_updated_at=_last_updated_at(item),
        change_24h=total_flow_count,
        trend_7d=hot_post_rate * 100,
        evidence=evidence,
        evidence_count=evidence_count,
        payload=payload,
        reason="友商近期内容供给和互动较集中，适合拆解选题与发布节奏。",
        samples=_samples_from_evidence(top_posts or evidence, default_type="competitor", platform=platform),
    )


def _content_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    platform = item.get("platform")
    evidence = item.get("evidence") or {}
    top_posts = evidence.get("top_posts") or [] if isinstance(evidence, dict) else []
    first_post = top_posts[0] if top_posts and isinstance(top_posts[0], dict) else {}
    name = (
        first_post.get("title")
        or item.get("title")
        or item.get("tracker_name")
        or f"内容机会 #{item.get('tracker_id')}"
    )
    keywords = item.get("keyword_distribution") or {}
    evidence_count = len(top_posts) or _evidence_count(keywords)
    sample_count = _sample_count(item, evidence, default=int(item.get("total_content_count") or 30))
    platforms = _platforms(item)
    stale = _is_stale(item)
    total_content_count = float(item.get("total_content_count") or 0)
    hot_post_rate = float(item.get("hot_post_rate") or 0)
    breakdown = {
        "heat_growth": _clamp(total_content_count * 1.5 + hot_post_rate * 50),
        "sample_confidence": _sample_confidence_score(sample_count, platforms, stale),
        "competition_gap": _competition_gap_score(item, default=72.0),
        "actionability": _clamp(60 + min(len(keywords), 10) * 3 + evidence_count * 5),
    }
    payload = {
        "platform": platform,
        "tracker_id": item.get("tracker_id"),
        "keywords": list(keywords.keys())[:5] if isinstance(keywords, dict) else [],
    }
    summary = [f"同类内容 {int(total_content_count)} 条，高互动率 {round(hot_post_rate * 100, 1)}%。"]
    return _standard_opportunity(
        opportunity_id=f"content:{platform}:{item.get('tracker_id')}",
        opportunity_type="content",
        name=name,
        display_title=str(name),
        display_subtitle=f"{_label_platform(platform)}内容 · 样本 {sample_count}",
        target_url=first_post.get("url"),
        platform=platform,
        breakdown=breakdown,
        risk_tags=_risk_tags(
            item=item,
            sample_count=sample_count,
            platforms=platforms,
            stale=stale,
            heat_growth=breakdown["heat_growth"],
            competition_gap=breakdown["competition_gap"],
            actionability=breakdown["actionability"],
        ),
        evidence_summary=summary,
        sample_count=sample_count,
        platforms=platforms,
        last_updated_at=_last_updated_at(item),
        change_24h=total_content_count,
        trend_7d=hot_post_rate * 100,
        evidence=evidence,
        evidence_count=evidence_count,
        payload=payload,
        reason="同类优质内容供给不足且关键词可执行，适合快速复刻内容角度。",
        samples=_samples_from_evidence(top_posts, default_type="content", platform=platform),
    )


def _standard_opportunity(
    *,
    opportunity_id: str,
    opportunity_type: str,
    name: str,
    display_title: str,
    display_subtitle: str,
    target_url: str | None,
    platform: str | None,
    breakdown: dict[str, float],
    risk_tags: list[str],
    evidence_summary: list[str],
    sample_count: int,
    platforms: list[str],
    last_updated_at: str | None,
    change_24h: float,
    trend_7d: float,
    evidence: Any,
    evidence_count: int,
    payload: dict[str, Any],
    reason: str,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    score = _weighted_score(breakdown)
    payload = {**payload, "display_title": display_title, "target_url": target_url}
    return {
        "id": opportunity_id,
        "type": opportunity_type,
        "name": name,
        "display_title": display_title,
        "display_subtitle": display_subtitle,
        "target_url": target_url,
        "platform": platform,
        "score": score,
        "score_breakdown": breakdown,
        "risk_tags": risk_tags,
        "evidence_summary": evidence_summary,
        "sample_scope": {
            "window": "7d",
            "platforms": platforms,
            "sample_count": sample_count,
            "last_updated_at": last_updated_at,
        },
        "trend": {
            "change_24h": change_24h,
            "points_7d": [],
            "points_14d": [],
            "points_30d": [],
        },
        "actions": [
            {"kind": "view_evidence", "label": "查看证据", "risk": "low", "payload": payload},
            {"kind": "prefill_collection_task", "label": "预填采集任务", "risk": "high", "payload": payload},
        ],
        "samples": samples,
        "detail": {
            "summary": evidence_summary,
            "trend_30d": [],
            "evidence": evidence,
        },
        "change_24h": change_24h,
        "trend_7d": trend_7d,
        "confidence": _confidence(score, evidence_count, sample_count),
        "reason": reason,
        "evidence_count": evidence_count,
        "payload": payload,
    }


def _apply_feedback_and_split(
    *,
    opportunities: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    latest_feedback = _latest_feedback_by_opportunity(feedback)
    top_candidates: list[dict[str, Any]] = []
    watchlist: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []

    for item in opportunities:
        item = dict(item)
        state = latest_feedback.get(item["id"])
        if state:
            item["feedback_state"] = state.get("feedback")

        if state and state.get("feedback") == "false_positive":
            ignored.append(item)
            continue

        if state and state.get("feedback") == "watch":
            watchlist.append(item)
            continue

        if state and state.get("feedback") == "valid":
            item["feedback_state"] = "valid"

        if _is_watchlist_item(item):
            watchlist.append(item)
        else:
            top_candidates.append(item)

    top_candidates.sort(key=lambda item: item["score"], reverse=True)
    watchlist.sort(key=lambda item: item["score"], reverse=True)
    return top_candidates, watchlist, ignored


def _latest_feedback_by_opportunity(feedback: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in feedback:
        opportunity_id = item.get("opportunity_id")
        if opportunity_id and opportunity_id not in result:
            result[opportunity_id] = item
    return result


def _is_watchlist_item(item: dict[str, Any]) -> bool:
    sample_count = int((item.get("sample_scope") or {}).get("sample_count") or 0)
    return sample_count < 10 or RISK_SMALL_SAMPLE_SPIKE in (item.get("risk_tags") or [])


def _build_diagnostics(
    *,
    opportunities: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    ignored_opportunities: list[dict[str, Any]],
    monitoring: dict[str, Any],
) -> list[dict[str, Any]]:
    diagnostics = []
    if not opportunities and not watchlist:
        diagnostics.append(
            {
                "code": "no_data",
                "title": "暂无可排序机会",
                "body": "缺少标准化样本，系统只展示诊断，不生成假结论。",
            }
        )
    if watchlist:
        diagnostics.append(
            {
                "code": "watchlist_low_confidence",
                "title": "观察池存在低可信机会",
                "body": f"{len(watchlist)} 条机会因小样本、平台单一或数据过旧进入观察池。",
            }
        )
    if ignored_opportunities:
        diagnostics.append(
            {
                "code": "feedback_ignored",
                "title": "已按反馈移除误判机会",
                "body": f"{len(ignored_opportunities)} 条机会被标记为误判，不再影响当前榜单。",
            }
        )
    if monitoring.get("errors"):
        diagnostics.append(
            {
                "code": "collection_errors",
                "title": "采集链路存在失败任务",
                "body": f"{monitoring['errors']} 个任务失败，需要先查看任务日志。",
                "action": "view_jobs",
            }
        )
    return diagnostics


def _weighted_score(breakdown: dict[str, float]) -> float:
    return round(
        breakdown["heat_growth"] * SCORING_WEIGHTS["heat_growth"]
        + breakdown["sample_confidence"] * SCORING_WEIGHTS["sample_confidence"]
        + breakdown["competition_gap"] * SCORING_WEIGHTS["competition_gap"]
        + breakdown["actionability"] * SCORING_WEIGHTS["actionability"],
        2,
    )


def _sample_confidence_score(sample_count: int, platforms: list[str], stale: bool) -> float:
    if stale:
        return 30.0
    if sample_count >= 100 and len(set(platforms)) >= 2:
        return 95.0
    if sample_count >= 100:
        return 80.0
    if sample_count >= 30:
        return 65.0
    if sample_count >= 10:
        return 40.0
    return 20.0


def _risk_tags(
    *,
    item: dict[str, Any],
    sample_count: int,
    platforms: list[str],
    stale: bool,
    heat_growth: float,
    competition_gap: float,
    actionability: float,
) -> list[str]:
    tags = []
    if sample_count < 10 and heat_growth >= 80:
        tags.append(RISK_SMALL_SAMPLE_SPIKE)
    if len(set(platforms)) <= 1:
        tags.append(RISK_SINGLE_PLATFORM_SIGNAL)
    if stale:
        tags.append(RISK_STALE_DATA)
    if competition_gap <= 30:
        tags.append(RISK_OVERHEATED_COMPETITION)
    if actionability < 50 or item.get("missing_execution_parameters"):
        tags.append(RISK_MISSING_EXECUTION_PARAMETERS)
    if item.get("cost_level") == "high" or float(item.get("estimated_cost") or 0) >= 1000:
        tags.append(RISK_HIGH_COST)
    return tags


def _sample_count(item: dict[str, Any], evidence: Any, *, default: int) -> int:
    for key in ("sample_count", "total_content_count", "total_flow_count", "recent_post_count_30d"):
        if key in item and item.get(key) is not None:
            return max(0, int(float(item.get(key) or 0)))
    return max(default, _evidence_count(evidence))


def _platforms(item: dict[str, Any]) -> list[str]:
    platforms = item.get("platforms")
    if isinstance(platforms, list) and platforms:
        return [str(value) for value in platforms if value]
    platform = item.get("platform")
    return [str(platform)] if platform else []


def _competition_gap_score(item: dict[str, Any], *, default: float) -> float:
    if item.get("competition_gap") is not None:
        return _clamp(float(item["competition_gap"]))
    if item.get("supply_gap_score") is not None:
        return _clamp(float(item["supply_gap_score"]))
    if item.get("competition_score") is not None:
        return _clamp(100 - float(item["competition_score"]))
    return _clamp(default)


def _keyword_actionability(item: dict[str, Any]) -> float:
    score = 70.0
    if item.get("keyword") or item.get("tag_name"):
        score += 10
    if item.get("platform"):
        score += 5
    if item.get("scene_pack_id") or item.get("vertical_id"):
        score += 5
    return _clamp(score)


def _is_stale(item: dict[str, Any]) -> bool:
    value = item.get("snapshot_date") or item.get("created_at") or item.get("updated_at")
    parsed = _parse_datetime(value)
    if parsed is None:
        return False
    return (datetime.now(timezone.utc) - parsed).days > 14


def _last_updated_at(item: dict[str, Any]) -> str | None:
    value = item.get("updated_at") or item.get("created_at") or item.get("snapshot_date")
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _samples_from_evidence(
    evidence: Any,
    *,
    default_type: str,
    platform: str | None,
) -> list[dict[str, Any]]:
    if isinstance(evidence, dict):
        if isinstance(evidence.get("samples"), list):
            source = evidence["samples"]
        elif isinstance(evidence.get("top_posts"), list):
            source = evidence["top_posts"]
        elif isinstance(evidence.get("items"), list):
            source = evidence["items"]
        else:
            source = []
    elif isinstance(evidence, list):
        source = evidence
    else:
        source = []

    samples = []
    for item in source[:10]:
        if isinstance(item, dict):
            engagement = item.get("engagement") or item.get("engagement_json") or {}
            samples.append(
                {
                    "type": item.get("type") or default_type,
                    "title": item.get("title") or item.get("text") or item.get("platform_post_id"),
                    "body": item.get("body") or item.get("content"),
                    "platform": item.get("platform") or platform,
                    "url": item.get("url") or _post_url(item.get("platform") or platform, item.get("platform_post_id")),
                    "publish_time": item.get("publish_time"),
                    "engagement": engagement,
                    "matched_terms": item.get("matched_terms") or [],
                    "raw_ref": item,
                }
            )
        else:
            samples.append(
                {
                    "type": default_type,
                    "title": str(item),
                    "body": None,
                    "platform": platform,
                    "url": None,
                    "publish_time": None,
                    "engagement": {},
                    "matched_terms": [],
                    "raw_ref": {"value": item},
                }
            )
    return samples


def _creator_profile_url(platform: str | None, creator_id: str, item: dict[str, Any]) -> str | None:
    explicit = item.get("profile_url") or item.get("url")
    if explicit:
        return str(explicit)
    if not creator_id:
        return None
    if platform == "xhs":
        return f"https://www.xiaohongshu.com/user/profile/{creator_id.removeprefix('xhs_')}"
    if platform == "dy":
        return f"https://www.douyin.com/user/{creator_id}"
    if platform in {"wb", "weibo"}:
        return f"https://weibo.com/u/{creator_id}"
    if platform == "bili":
        return f"https://space.bilibili.com/{creator_id}"
    return None


def _post_url(platform: str | None, post_id: Any) -> str | None:
    if not post_id:
        return None
    post_id = str(post_id)
    if platform == "xhs":
        return f"https://www.xiaohongshu.com/explore/{post_id}"
    if platform == "dy":
        return f"https://www.douyin.com/video/{post_id}"
    if platform in {"wb", "weibo"}:
        return f"https://weibo.com/detail/{post_id}"
    if platform == "bili":
        return f"https://www.bilibili.com/video/{post_id}"
    return None


def _label_platform(platform: str | None) -> str:
    return {
        "xhs": "小红书",
        "dy": "抖音",
        "ks": "快手",
        "bili": "B站",
        "wb": "微博",
        "weibo": "微博",
        "tieba": "贴吧",
        "zhihu": "知乎",
    }.get(platform or "", platform or "未知平台")


def _last_action_kind(item: dict[str, Any]) -> str:
    actions = item.get("actions") or []
    if not actions:
        return "view_detail"
    action = actions[-1]
    if isinstance(action, dict):
        return str(action.get("kind") or "view_detail")
    return str(action)


def _confidence(score: float, evidence_count: int, sample_count: int) -> str:
    if score >= 85 and evidence_count >= 3 and sample_count >= 100:
        return "high"
    if score >= 60 or evidence_count >= 1 or sample_count >= 30:
        return "medium"
    return "low"


def _evidence_count(evidence: Any) -> int:
    if isinstance(evidence, list):
        return len(evidence)
    if isinstance(evidence, dict):
        if isinstance(evidence.get("items"), list):
            return len(evidence["items"])
        if isinstance(evidence.get("evidence"), list):
            return len(evidence["evidence"])
        if isinstance(evidence.get("top_posts"), list):
            return len(evidence["top_posts"])
        if isinstance(evidence.get("samples"), list):
            return len(evidence["samples"])
        return len(evidence)
    return 0


def _latest_timestamp(items: list[dict[str, Any]]) -> str | None:
    values = [
        item.get("updated_at") or item.get("created_at") or item.get("snapshot_date")
        for item in items
        if item.get("updated_at") or item.get("created_at") or item.get("snapshot_date")
    ]
    if not values:
        return None
    latest = max(str(value) for value in values)
    return latest or datetime.now(timezone.utc).isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 2)

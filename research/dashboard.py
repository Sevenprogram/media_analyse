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
        "opportunities": top_opportunities,
        "top_opportunities": top_opportunities,
        "watchlist": watchlist[:3],
        "ignored_opportunities": ignored_opportunities,
        "diagnostics": diagnostics,
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
    running_jobs = sum(1 for item in jobs if item.get("status") == "running")
    errors = sum(1 for item in jobs if item.get("status") in {"failed", "error"})
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
            "risk_notes": ["样本不足，暂不输出确定性推流判断。"],
            "evidence_count": evidence_count,
        }

    top = opportunities[0]
    sample_status = "enough" if evidence_count >= 3 else "limited"
    confidence = "high" if top["score"] >= 85 and evidence_count >= 6 else "medium"
    platform_text = f"{platform} 骞冲彴" if platform else "褰撳墠骞冲彴"
    return {
        "headline": f"{platform_text}浠婃棩浼樺厛鍏虫敞銆{top['name']}銆嶏紝{top['reason']}",
        "confidence": confidence,
        "sample_status": sample_status,
        "sample_summary": f"宸插舰鎴?{len(opportunities)} 鏉℃満浼氱嚎绱紝璇佹嵁 {evidence_count} 鏉°€?",
        "risk_notes": [] if sample_status == "enough" else ["璇佹嵁鏁伴噺鏈夐檺锛屾墽琛屽墠寤鸿鏌ョ湅璇︽儏銆?"],
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
                    "title": "鎵ц涓€娆″疄鏃跺彂鐜?",
                    "reason": "褰撳墠鏍锋湰涓嶈冻锛岄渶瑕佸厛閲囬泦鍏抽敭璇嶅拰杈句汉鍩虹鏁版嵁銆?",
                    "target_type": "keyword",
                    "action": "search_now",
                    "payload": {"keywords": ["K12鏁欒偛", "鍗曚翰濡堝"]},
                }
            ],
            "watch_today": [],
            "defer": [
                {
                    "title": "鏆傜紦纭畾鎬ф姇鏀惧垽鏂?",
                    "reason": decision["sample_summary"],
                    "target_type": "report",
                    "action": "view_detail",
                    "payload": {},
                }
            ],
        }

    do_now = [
        {
            "title": f"澶勭悊 {item['name']}",
            "reason": item["reason"],
            "target_type": item["type"],
            "action": _last_action_kind(item),
            "payload": item["payload"],
        }
        for item in opportunities[:2]
    ]
    watch_today = [
        {
            "title": f"瑙傚療 {item['name']}",
            "reason": item["reason"],
            "target_type": item["type"],
            "action": "view_detail",
            "payload": item["payload"],
        }
        for item in opportunities[2:5]
    ]
    return {"do_now": do_now, "watch_today": watch_today, "defer": []}


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
    items.sort(key=lambda item: item["score"], reverse=True)
    return items[:20]


def _creator_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    name = item.get("display_name") or item.get("creator_id") or "鏈懡鍚嶈揪浜?"
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
    payload = {"platform": platform, "creator_id": item.get("creator_id"), "display_name": name}
    summary = [f"鍖归厤鍒?{item.get('match_score', 0)}銆?"]
    return _standard_opportunity(
        opportunity_id=f"creator:{platform}:{item.get('creator_id')}",
        opportunity_type="creator",
        name=name,
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
        reason="涓昏瘝鍖归厤杈冮珮涓旇繎鏈熸寔缁彂甯栵紝閫傚悎浼樺厛澶嶆牳骞跺姞鍏ョ洃鎺с€?",
        samples=_samples_from_evidence(evidence, default_type="creator", platform=platform),
    )


def _keyword_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    keyword = item.get("keyword") or item.get("tag_name") or str(item.get("tag_id") or "鍏抽敭璇?")
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
    summary = [f"骞冲彴淇″彿锛歿{item.get('platform_signal') or 'normal'}銆?"]
    return _standard_opportunity(
        opportunity_id=f"keyword:{platform}:{keyword}",
        opportunity_type="keyword",
        name=keyword,
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
        reason=f"鐑害鍒?{round(heat_score, 1)}锛屽钩鍙颁俊鍙蜂负 {item.get('platform_signal') or 'normal'}銆?",
        samples=_samples_from_evidence(evidence, default_type="post", platform=platform),
    )


def _competitor_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    platform = item.get("platform")
    name = f"鍙嬪晢 #{item.get('competitor_id')}"
    evidence = item.get("evidence") or {}
    top_posts = evidence.get("top_posts") or [] if isinstance(evidence, dict) else []
    evidence_count = len(top_posts)
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
    summary = [f"鎬讳簰鍔?{item.get('total_flow_count', 0)}锛岀垎娆剧巼 {item.get('hot_post_rate', 0)}銆?"]
    return _standard_opportunity(
        opportunity_id=f"competitor:{platform}:{item.get('competitor_id')}",
        opportunity_type="competitor",
        name=name,
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
        reason="鍙嬪晢娴侀噺缁勬垚鍑虹幇鍙鐩樻牱鏈紝寤鸿鏌ョ湅鍏抽敭璇嶅拰鐖嗘鍐呭缁撴瀯銆?",
        samples=_samples_from_evidence(top_posts, default_type="competitor", platform=platform),
    )


def _content_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    platform = item.get("platform")
    name = f"鍐呭杩借釜 #{item.get('tracker_id')}"
    evidence = item.get("evidence") or {}
    top_posts = evidence.get("top_posts") or [] if isinstance(evidence, dict) else []
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
    summary = [f"鍖归厤鍐呭 {item.get('total_content_count', 0)} 鏉°€?"]
    return _standard_opportunity(
        opportunity_id=f"content:{platform}:{item.get('tracker_id')}",
        opportunity_type="content",
        name=name,
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
        reason="鍚岀被鍐呭宸叉湁鍙瀵熸牱鏈紝閫傚悎缁х画杩借釜鍏抽敭璇嶅懡涓拰鐖嗘缁撴瀯銆?",
        samples=_samples_from_evidence(top_posts, default_type="content", platform=platform),
    )


def _standard_opportunity(
    *,
    opportunity_id: str,
    opportunity_type: str,
    name: str,
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
    return {
        "id": opportunity_id,
        "type": opportunity_type,
        "name": name,
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
            {"kind": "view_evidence", "label": "鏌ョ湅璇佹嵁", "risk": "low", "payload": payload},
            {"kind": "prefill_collection_task", "label": "棰勫～閲囬泦浠诲姟", "risk": "high", "payload": payload},
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
                "title": "鏆傛棤鏈轰細鍒ゆ柇",
                "body": "鍏堥噰闆嗘牱鏈悗鍐嶇敓鎴愭満浼氭銆?",
            }
        )
    if watchlist:
        diagnostics.append(
            {
                "code": "watchlist_low_confidence",
                "title": "鏈変綆淇″績鏈轰細",
                "body": f"{len(watchlist)} 鏉℃満浼氶渶瑕佹洿澶氭牱鏈墠鑳芥帓鍏ヤ紭鍏堢骇銆?",
            }
        )
    if ignored_opportunities:
        diagnostics.append(
            {
                "code": "feedback_ignored",
                "title": "宸插簲鐢ㄥ弽棣?",
                "body": f"{len(ignored_opportunities)} 鏉¤鏍囪涓鸿垽骞剁Щ鍑洪灞忔帓鍚嶃€?",
            }
        )
    if monitoring.get("errors"):
        diagnostics.append(
            {
                "code": "collection_errors",
                "title": "閲囬泦浠诲姟寮傚父",
                "body": f"{monitoring['errors']} 涓换鍔″浜庡け璐ユ垨寮傚父鐘舵€併€?",
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
            samples.append(
                {
                    "type": item.get("type") or default_type,
                    "title": item.get("title") or item.get("text"),
                    "body": item.get("body") or item.get("content"),
                    "platform": item.get("platform") or platform,
                    "url": item.get("url"),
                    "publish_time": item.get("publish_time"),
                    "engagement": item.get("engagement") or item.get("engagement_json") or {},
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
        item.get("created_at") or item.get("snapshot_date")
        for item in items
        if item.get("created_at") or item.get("snapshot_date")
    ]
    if not values:
        return None
    latest = max(str(value) for value in values)
    return latest or datetime.now(timezone.utc).isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 2)

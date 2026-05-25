from typing import Any

from research.competitors import calculate_keyword_opportunities


def build_growth_report(
    *,
    vertical_id: int | None,
    platform: str | None,
    creator_candidates: list[dict[str, Any]],
    creator_profiles: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    tag_definitions: list[dict[str, Any]],
    entity_tags: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]] | None = None,
    content_snapshots: list[dict[str, Any]] | None = None,
    keyword_heat_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    filtered_candidates = [
        item
        for item in creator_candidates
        if (vertical_id is None or item.get("vertical_id") == vertical_id)
        and (platform is None or item.get("platform") == platform)
    ]
    filtered_competitors = [
        item
        for item in competitors
        if (vertical_id is None or item.get("vertical_id") == vertical_id)
        and (platform is None or item.get("platform") == platform)
    ]
    opportunities = calculate_keyword_opportunities(
        vertical_id=vertical_id or 0,
        tag_definitions=tag_definitions,
        entity_tags=entity_tags,
        creator_profiles=creator_profiles,
        snapshots=snapshots,
        platform=platform,
    )
    if not opportunities and keyword_heat_snapshots:
        opportunities = [
            {
                "vertical_id": vertical_id or 0,
                "platform": item.get("platform"),
                "tag_id": index + 1,
                "tag_name": item.get("keyword") or f"keyword-{index + 1}",
                "heat_score": float(item.get("heat_score") or 0),
                "growth_score": float(item.get("growth_score") or 0),
                "competition_score": 0.0,
                "supply_gap_score": float(item.get("growth_score") or 0),
                "platform_signal": item.get("platform_signal") or "normal",
                "evidence": item.get("evidence") or {},
            }
            for index, item in enumerate(keyword_heat_snapshots)
        ]
    boss_report = build_boss_report(
        vertical_id=vertical_id,
        platform=platform,
        creator_candidates=filtered_candidates,
        competitors=filtered_competitors,
        keyword_opportunities=opportunities,
        competitor_compositions=competitor_compositions or [],
        content_snapshots=content_snapshots or [],
        keyword_heat_snapshots=keyword_heat_snapshots or [],
    )

    return {
        "title": "增长情报报告",
        "vertical_id": vertical_id,
        "platform": platform,
        "summary": boss_report["summary"],
        "metrics": {
            "candidate_creators": len(filtered_candidates),
            "creator_profiles": len(creator_profiles),
            "competitors": len(filtered_competitors),
            "snapshots": len(snapshots),
            "keyword_opportunities": len(opportunities),
            "competitor_compositions": len(competitor_compositions or []),
        },
        "top_creators": filtered_candidates[:10],
        "top_opportunities": opportunities[:10],
        "competitors": filtered_competitors[:10],
        "boss_report": boss_report,
        "evidence": boss_report["evidence"],
        "recommended_actions": boss_report["recommended_actions"],
    }


def build_boss_report(
    *,
    vertical_id: int | None,
    platform: str | None,
    creator_candidates: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
    keyword_opportunities: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    content_snapshots: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    top_creator = _first_sorted(creator_candidates, "match_score")
    top_opportunity = _first_sorted(keyword_opportunities, "supply_gap_score")
    top_competitor_snapshot = _first_sorted(competitor_compositions, "total_flow_count")
    top_heat = _first_sorted(keyword_heat_snapshots, "heat_score")

    summary: list[str] = []
    if top_creator:
        summary.append(
            f"达人筛选已形成候选池，最高匹配分 {top_creator.get('match_score', 0)}，"
            f"建议优先复核 {top_creator.get('display_name') or top_creator.get('creator_id') or '高分达人'}。"
        )
    if top_opportunity:
        summary.append(
            f"关键词机会集中在「{top_opportunity.get('tag_name') or top_opportunity.get('tag_id')}」，"
            f"平台信号为 {top_opportunity.get('platform_signal')}。"
        )
    if top_competitor_snapshot:
        summary.append(
            f"友商流量已拆分为关键词、内容类型、发布时间和爆款率，"
            f"最高单日互动量 {top_competitor_snapshot.get('total_flow_count', 0)}。"
        )
    if top_heat:
        summary.append(
            f"关键词「{top_heat.get('keyword')}」当前热度分 {top_heat.get('heat_score', 0)}，"
            f"推流判断为 {top_heat.get('platform_signal')}。"
        )
    if not summary:
        summary.append("当前报告样本不足，建议先完成关键词配置、实时发现和友商每日监控。")

    return {
        "vertical_id": vertical_id,
        "platform": platform,
        "summary": summary,
        "sections": {
            "creator_discovery": {
                "title": "达人筛选",
                "count": len(creator_candidates),
                "top_items": creator_candidates[:10],
            },
            "content_tracking": {
                "title": "内容追踪",
                "count": len(content_snapshots),
                "top_items": content_snapshots[:10],
            },
            "keyword_heat": {
                "title": "关键词热度",
                "count": len(keyword_heat_snapshots),
                "top_items": keyword_heat_snapshots[:10],
            },
            "competitor_flow": {
                "title": "友商流量组成",
                "count": len(competitor_compositions),
                "top_items": competitor_compositions[:10],
            },
        },
        "evidence": _report_evidence(
            opportunities=keyword_opportunities,
            competitor_compositions=competitor_compositions,
            keyword_heat_snapshots=keyword_heat_snapshots,
        ),
        "recommended_actions": _recommended_actions(
            candidates=creator_candidates,
            competitors=competitors,
            opportunities=keyword_opportunities,
            compositions=competitor_compositions,
        ),
    }


def _recommended_actions(
    *,
    candidates: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    compositions: list[dict[str, Any]],
) -> list[str]:
    actions = []
    if opportunities:
        actions.append("优先围绕高机会关键词建立内容测试组，并连续观察 3-7 天推流变化。")
    if candidates:
        actions.append("从候选达人池选择高匹配、低风险账号加入监控池，并立即爬取主页内容。")
    if competitors and compositions:
        actions.append("复盘友商高爆款日期的关键词、发布时间和内容类型组合，沉淀为场景包规则。")
    elif competitors:
        actions.append("已配置友商账号，下一步需要执行组成快照重建，补齐每日流量结构。")
    if not actions:
        actions.append("先初始化赛道、场景包和平台能力，再执行一次实时发现形成首批样本。")
    return actions


def _report_evidence(
    *,
    opportunities: list[dict[str, Any]],
    competitor_compositions: list[dict[str, Any]],
    keyword_heat_snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence = [
        {
            "source": "keyword_opportunities",
            "label": item.get("tag_name") or item.get("tag_id"),
            "data": item.get("evidence") or {},
        }
        for item in opportunities[:6]
    ]
    evidence.extend(
        {
            "source": "competitor_composition",
            "label": item.get("platform"),
            "data": {
                "total_flow_count": item.get("total_flow_count", 0),
                "hot_post_rate": item.get("hot_post_rate", 0),
                "keyword_distribution": item.get("keyword_distribution") or {},
                "content_type_distribution": item.get("content_type_distribution") or {},
                "publish_time_distribution": item.get("publish_time_distribution") or {},
                "interaction_structure": item.get("interaction_structure") or {},
            },
        }
        for item in competitor_compositions[:6]
    )
    evidence.extend(
        {
            "source": "keyword_heat",
            "label": item.get("keyword"),
            "data": item.get("evidence") or {},
        }
        for item in keyword_heat_snapshots[:6]
    )
    return evidence


def _first_sorted(items: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    if not items:
        return None
    return sorted(items, key=lambda item: float(item.get(key) or 0), reverse=True)[0]

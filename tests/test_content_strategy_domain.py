from __future__ import annotations

from datetime import datetime, timezone

from research.content_strategy import (
    _build_frameworks,
    _normalize_ai_frameworks,
    build_content_strategy_summary,
    build_strategy_draft_fallback,
    normalize_strategy_draft_output,
    normalize_strategy_filters,
)


def test_build_content_strategy_summary_combines_ai_topics_and_local_evidence() -> None:
    filters = normalize_strategy_filters(
        platform="xhs",
        time_range="30d",
        goal="conversion",
        audience="moms",
        stage="boost",
    )
    dashboard = {
        "decision": {
            "headline": "优先关注猫粮测评",
            "confidence": "medium",
            "sample_summary": "已形成 2 条机会线索。",
            "evidence_count": 4,
        },
        "opportunities": [
            {
                "id": "keyword:xhs:猫粮测评",
                "type": "keyword",
                "name": "猫粮测评",
                "display_title": "猫粮测评",
                "platform": "xhs",
                "score": 78,
                "trend_7d": 64,
                "change_24h": 12,
                "risk_tags": ["single_platform_signal"],
                "score_breakdown": {"competition_gap": 82},
                "payload": {"keyword": "猫粮测评"},
                "reason": "热度和增长分较高。",
                "samples": [
                    {
                        "title": "猫粮测评不要踩坑",
                        "platform": "xhs",
                        "engagement": {"like_count": 120, "comment_count": 15},
                    }
                ],
                "detail": {"evidence": {"sample_count": 3}},
            }
        ],
        "top_opportunities": [],
        "watchlist": [],
        "diagnostics": [],
    }
    posts = [
        {
            "id": 1,
            "platform": "xhs",
            "platform_post_id": "p1",
            "title": "新手猫粮怎么选，真实测评避坑",
            "content": "价格、效果和安全风险都要看。",
            "url": "https://example.com/p1",
            "publish_time": datetime.now(timezone.utc),
            "engagement_json": {"like_count": 100, "comment_count": 20, "source_keyword": "猫粮测评"},
        }
    ]
    result = build_content_strategy_summary(
        filters=filters,
        dashboard=dashboard,
        posts=posts,
        keyword_heat_snapshots=[
            {
                "keyword": "猫粮测评",
                "platform": "xhs",
                "heat_score": 86,
                "growth_score": 32,
                "evidence": {"items": ["local evidence"]},
            }
        ],
        content_snapshots=[
            {"platform": "xhs", "total_content_count": 12, "hot_post_rate": 0.5}
        ],
        competitor_compositions=[
            {
                "platform": "xhs",
                "total_flow_count": 240,
                "evidence": {
                    "top_posts": [
                        {
                            "platform": "xhs",
                            "title": "同行猫粮测评爆文",
                            "engagement": {"like_count": 80, "comment_count": 10},
                        }
                    ]
                },
            }
        ],
        ai_insights={"run": {"id": 1}, "risk_notes": ["标题不要过度焦虑"]},
        ai_topic_ideas=[
            {
                "id": 7,
                "title": "猫粮测评怎么做才不踩坑",
                "platform": "xhs",
                "target_audience": "新手猫家长",
                "keywords": ["猫粮测评"],
                "content_angle": "测评避坑",
                "risk_notes": [],
            }
        ],
    )

    assert result["filters"]["platform"] == "xhs"
    assert result["ai_status"]["source"] == "latest_ai_topic_ideas"
    assert [item["key"] for item in result["metrics"]] == [
        "high_opportunity",
        "high_interaction",
        "low_competition",
        "trending_up",
    ]
    assert result["suggestions"][0]["title"] == "猫粮测评怎么做才不踩坑"
    assert result["keyword_trends"][0]["keyword"] == "猫粮测评"
    assert result["frameworks"]
    assert result["competitor_samples"][0]["title"] == "同行猫粮测评爆文"
    assert any(item["title"] == "同质化风险" for item in result["risks"])
    assert result["traffic_share"]["estimated_leads"] > 0
    assert result["evidence_pack"]["total"] > 0


def test_build_content_strategy_summary_prefers_sample_pain_distribution_from_post_fingerprints() -> None:
    filters = normalize_strategy_filters(
        platform="xhs",
        time_range="30d",
        goal="conversion",
        audience="parents",
        stage="boost",
    )
    result = build_content_strategy_summary(
        filters=filters,
        dashboard={
            "decision": {},
            "opportunities": [],
            "top_opportunities": [],
            "watchlist": [],
            "diagnostics": [],
        },
        posts=[
            {
                "id": "post-1",
                "platform": "xhs",
                "title": "孩子提分焦虑越来越重怎么办",
                "content": "成绩落后和提分压力一直压着家长。",
                "engagement_json": {},
            },
            {
                "id": "post-2",
                "platform": "xhs",
                "title": "英语启蒙到底怎么做",
                "content": "英语启蒙和自然拼读怎么安排更稳。",
                "engagement_json": {},
            },
            {
                "id": "post-3",
                "platform": "xhs",
                "title": "小升初择校规划要提前多久",
                "content": "择校规划这件事别拖到最后。",
                "engagement_json": {},
            },
            {
                "id": "post-4",
                "platform": "xhs",
                "title": "提分焦虑不是孩子懒",
                "content": "家长先别把提分问题简单归因。",
                "engagement_json": {},
            },
        ],
        keyword_heat_snapshots=[],
        content_snapshots=[],
        competitor_compositions=[],
        ai_insights={},
        ai_topic_ideas=[],
    )

    assert result["section_sources"]["pain_distribution"] == "sample"
    assert result["pain_distribution"][0]["label"] == "提分焦虑"
    assert result["pain_distribution"][0]["count"] == 2
    assert sum(item["count"] for item in result["pain_distribution"]) == 4


def test_build_content_strategy_summary_falls_back_to_rules_when_no_specific_pain_samples_exist() -> None:
    filters = normalize_strategy_filters(
        platform="xhs",
        time_range="30d",
        goal="conversion",
        audience="parents",
        stage="boost",
    )
    result = build_content_strategy_summary(
        filters=filters,
        dashboard={
            "decision": {},
            "opportunities": [],
            "top_opportunities": [],
            "watchlist": [],
            "diagnostics": [],
        },
        posts=[
            {
                "id": "generic-post",
                "platform": "xhs",
                "title": "普通内容记录",
                "content": "今天分享一个学习流程和执行笔记。",
                "engagement_json": {},
            }
        ],
        keyword_heat_snapshots=[],
        content_snapshots=[],
        competitor_compositions=[],
        ai_insights={},
        ai_topic_ideas=[
            {
                "id": 1,
                "title": "新手怎么选课程更省钱",
                "platform": "xhs",
                "target_audience": "家长",
                "keywords": ["选课"],
                "content_angle": "入门决策",
                "risk_notes": [],
            }
        ],
    )

    assert result["section_sources"]["pain_distribution"] == "rules"
    assert any(item["label"] == "选择困难" for item in result["pain_distribution"])


def test_build_content_strategy_summary_exposes_risk_evidence_for_low_hot_post_rate() -> None:
    filters = normalize_strategy_filters(
        platform="xhs",
        time_range="30d",
        goal="conversion",
        audience="parents",
        stage="boost",
    )
    result = build_content_strategy_summary(
        filters=filters,
        dashboard={
            "decision": {},
            "opportunities": [],
            "top_opportunities": [],
            "watchlist": [],
            "diagnostics": [],
        },
        posts=[],
        keyword_heat_snapshots=[],
        content_snapshots=[
            {
                "platform": "xhs",
                "total_content_count": 40,
                "hot_post_rate": 0.0,
                "evidence": {"hot_content": []},
            }
        ],
        competitor_compositions=[],
        ai_insights={},
        ai_topic_ideas=[],
    )

    row = next(item for item in result["risks"] if item["title"] == "内容扩散效率不足")
    assert row["evidence"]["sources"] == ["content_tracking"]
    assert "热帖率 0 / 40" in row["evidence"]["metric_summary"]
    assert any("样本 40 条" in note for note in row["evidence"]["notes"])


def test_content_frameworks_sort_by_median_interaction() -> None:
    posts = [
        {
            "title": f"避坑清单 low sample {index}",
            "engagement_json": {"like_count": 100},
        }
        for index in range(5)
    ] + [
        {
            "title": "测评 high sample a",
            "engagement_json": {"like_count": 1000},
        },
        {
            "title": "测评 high sample b",
            "engagement_json": {"like_count": 1200},
        },
    ]

    frameworks = _build_frameworks(posts, opportunities=[])

    assert frameworks[0]["title"] == "对比测评型"
    assert frameworks[0]["interactions"] == "1.1k"
    assert frameworks[1]["title"] == "避坑清单型"
    assert frameworks[1]["interactions"] == "100"


def test_ai_frameworks_do_not_treat_copy_as_interaction_metric() -> None:
    frameworks = _normalize_ai_frameworks(
        [
            {
                "title": "Question framework",
                "tags": ["search"],
                "posts": 18,
                "interactions": "Suitable for search traffic and comment consultation copy.",
                "leads": 0,
            },
            {
                "title": "Proof framework",
                "tags": ["proof"],
                "posts": 4,
                "interactions": "2.4k",
                "leads": 2,
            },
        ],
        fallback_rows=[
            {
                "title": "Question framework",
                "tags": ["fallback"],
                "posts": 18,
                "interactions": "1.2k",
                "leads": 1,
                "samples": [],
            }
        ],
    )

    assert [item["title"] for item in frameworks] == ["Proof framework", "Question framework"]
    assert frameworks[0]["interactions"] == "2.4k"
    assert frameworks[1]["interactions"] == "1.2k"


def test_strategy_draft_normalization_and_fallback_are_stable() -> None:
    payload = {"title": "猫粮测评", "keywords": ["猫粮", "测评"]}
    normalized = normalize_strategy_draft_output(
        {
            "title": "猫粮测评文案",
            "summary": "用本地证据生成。",
            "sections": [{"heading": "结构", "items": ["痛点", "证据", "行动"]}],
            "body": "正文",
            "checklist": ["复核风险"],
            "risk_notes": ["避免绝对化"],
        },
        source_payload=payload,
    )
    fallback = build_strategy_draft_fallback(payload, reason="AI unavailable")

    assert normalized["title"] == "猫粮测评文案"
    assert normalized["sections"][0]["items"] == ["痛点", "证据", "行动"]
    assert fallback["source_payload"] == payload
    assert "AI unavailable" in fallback["risk_notes"]


def test_build_content_strategy_summary_prefers_ai_strategy_sections_when_present() -> None:
    filters = normalize_strategy_filters(
        platform="xhs",
        time_range="30d",
        goal="conversion",
        audience="all",
        stage="boost",
    )
    result = build_content_strategy_summary(
        filters=filters,
        dashboard={
            "decision": {
                "headline": "规则头部判断",
                "sample_summary": "规则样本摘要",
                "confidence": "low",
                "evidence_count": 2,
            },
            "opportunities": [],
            "top_opportunities": [],
            "watchlist": [],
            "diagnostics": [],
        },
        posts=[],
        keyword_heat_snapshots=[],
        content_snapshots=[],
        competitor_compositions=[],
        ai_insights={"run": {"id": "ai-run-1"}, "risk_notes": []},
        ai_topic_ideas=[],
        ai_strategy_summary={
            "strategy_note": "AI 建议先做家长决策路径，再补高风险边界说明。",
            "hero": {
                "headline": "AI 判断：先做暑假规划决策内容",
                "sample_summary": "AI 汇总了项目样本和关键词快照。",
                "confidence": "high",
            },
            "keyword_trends": [
                {
                    "rank": 1,
                    "keyword": "暑假规划",
                    "platform": "xhs",
                    "platform_label": "小红书",
                    "heat": "88",
                    "score": 88,
                    "direction": "up",
                    "points": [42, 51, 56, 63, 70],
                    "evidence": {"sample_count": 6},
                }
            ],
            "frameworks": [
                {
                    "title": "AI 决策路径型",
                    "tags": ["决策", "清单"],
                    "posts": 12,
                    "interactions": "2.4k",
                    "leads": 38,
                    "samples": [],
                }
            ],
            "suggestions": [
                {
                    "id": "ai-suggestion:1",
                    "title": "暑假规划别先报班，先把 K12 目标定清楚",
                    "audience": "K12 家长",
                    "chance": 86,
                    "risk": "中风险",
                    "direction": "AI 策略判断",
                    "platform": "xhs",
                    "keywords": ["暑假规划", "K12"],
                    "outline": ["先定目标", "再定预算", "最后排课"],
                    "reason": "AI 根据项目样本判断家长决策链路更值得先做。",
                    "evidence": {"sample_count": 4},
                    "samples": [],
                    "source": "ai",
                    "risk_notes": ["避免结果承诺"],
                }
            ],
            "risks": [
                {
                    "title": "标题焦虑过强",
                    "detail": "AI 判断当前标题容易过度放大焦虑，需要收紧措辞。",
                    "level": "中风险",
                    "count": 2,
                }
            ],
            "weekly_mix": [
                {
                    "label": "决策内容",
                    "percent": 42,
                    "pieces": 5,
                    "exposure": "2.1k",
                    "leads": 21,
                    "color": "#0f8f85",
                },
                {
                    "label": "案例内容",
                    "percent": 33,
                    "pieces": 4,
                    "exposure": "1.8k",
                    "leads": 15,
                    "color": "#2d9fd6",
                },
                {
                    "label": "复盘内容",
                    "percent": 25,
                    "pieces": 3,
                    "exposure": "1.2k",
                    "leads": 8,
                    "color": "#f59d48",
                },
            ],
        },
    )

    assert result["hero"]["headline"] == "AI 判断：先做暑假规划决策内容"
    assert result["strategy_note"] == "AI 建议先做家长决策路径，再补高风险边界说明。"
    assert result["suggestions"][0]["source"] == "ai"
    assert result["frameworks"][0]["title"] == "AI 决策路径型"
    assert result["section_sources"]["hero"] == "ai"
    assert result["section_sources"]["weekly_mix"] == "ai"


def test_ai_strategy_suggestions_do_not_hide_high_opportunity_candidates() -> None:
    filters = normalize_strategy_filters(
        platform="xhs",
        time_range="30d",
        goal="conversion",
        audience="all",
        stage="boost",
    )
    opportunities = [
        {
            "id": f"keyword:xhs:教育培训:{index}",
            "type": "keyword",
            "name": f"教育培训场景 {index}",
            "display_title": f"教育培训场景 {index}",
            "platform": "xhs",
            "score": 82 - index,
            "trend_7d": 55,
            "score_breakdown": {"competition_gap": 72},
            "payload": {"keyword": f"教育培训 {index}"},
            "reason": "项目机会评分超过执行阈值。",
            "risk_tags": [],
            "samples": [],
            "detail": {"evidence": {"sample_count": 3}},
        }
        for index in range(7)
    ]

    result = build_content_strategy_summary(
        filters=filters,
        dashboard={
            "decision": {
                "headline": "规则头部判断",
                "sample_summary": "规则样本摘要",
                "confidence": "medium",
                "evidence_count": 7,
            },
            "opportunities": opportunities,
            "top_opportunities": opportunities,
            "watchlist": [],
            "diagnostics": [],
        },
        posts=[],
        keyword_heat_snapshots=[],
        content_snapshots=[],
        competitor_compositions=[],
        ai_insights={"run": {"id": "ai-run-2"}, "risk_notes": []},
        ai_topic_ideas=[],
        ai_strategy_summary={
            "suggestions": [
                {
                    "id": "ai-suggestion:1",
                    "title": "教育培训场景 0",
                    "audience": "泛目标人群",
                    "chance": 86,
                    "risk": "低风险",
                    "direction": "AI 策略判断",
                    "platform": "xhs",
                    "keywords": ["教育培训 0"],
                    "outline": ["拆场景", "给证据", "做测试"],
                    "reason": "AI 优先增强该候选。",
                    "source": "ai",
                    "risk_notes": [],
                },
                {
                    "id": "ai-suggestion:2",
                    "title": "教育培训场景 1",
                    "audience": "泛目标人群",
                    "chance": 84,
                    "risk": "低风险",
                    "direction": "AI 策略判断",
                    "platform": "xhs",
                    "keywords": ["教育培训 1"],
                    "outline": ["拆场景", "给证据", "做测试"],
                    "reason": "AI 优先增强该候选。",
                    "source": "ai",
                    "risk_notes": [],
                },
            ]
        },
    )

    high_opportunity_metric = next(item for item in result["metrics"] if item["key"] == "high_opportunity")
    high_opportunity_suggestions = [
        item
        for item in result["suggestions"]
        if float(item.get("chance") or 0) >= 75
        and not str(item.get("id") or "").startswith("keyword-trend:")
    ]

    assert high_opportunity_metric["value"] == "7"
    assert len(high_opportunity_suggestions) == 7
    assert result["suggestions"][0]["source"] == "ai"


def test_ai_strategy_suggestion_limit_preserves_high_opportunity_fallbacks() -> None:
    filters = normalize_strategy_filters(
        platform="xhs",
        time_range="30d",
        goal="conversion",
        audience="all",
        stage="boost",
    )
    opportunities = [
        {
            "id": f"keyword:xhs:training:{index}",
            "type": "keyword",
            "name": f"Training Scenario {index}",
            "display_title": f"Training Scenario {index}",
            "platform": "xhs",
            "score": 82 - index,
            "trend_7d": 55,
            "score_breakdown": {"competition_gap": 72},
            "payload": {"keyword": f"training {index}"},
            "reason": "Rule opportunity score is above execution threshold.",
            "risk_tags": [],
            "samples": [],
            "detail": {"evidence": {"sample_count": 3}},
        }
        for index in range(7)
    ]
    ai_suggestions = [
        {
            "id": f"ai-suggestion:{index}",
            "title": f"AI narrow idea {index}",
            "audience": "general audience",
            "chance": 50,
            "risk": "low",
            "direction": "AI-only candidate",
            "platform": "xhs",
            "keywords": [f"ai keyword {index}"],
            "outline": ["scene", "evidence", "test"],
            "reason": "AI returned a full list without the rule opportunities.",
            "source": "ai",
            "risk_notes": [],
        }
        for index in range(12)
    ]

    result = build_content_strategy_summary(
        filters=filters,
        dashboard={
            "decision": {
                "headline": "Rule headline",
                "sample_summary": "Rule sample summary",
                "confidence": "medium",
                "evidence_count": 7,
            },
            "opportunities": opportunities,
            "top_opportunities": opportunities,
            "watchlist": [],
            "diagnostics": [],
        },
        posts=[],
        keyword_heat_snapshots=[],
        content_snapshots=[],
        competitor_compositions=[],
        ai_insights={"run": {"id": "ai-run-3"}, "risk_notes": []},
        ai_topic_ideas=[],
        ai_strategy_summary={"suggestions": ai_suggestions},
    )

    high_opportunity_suggestions = [
        item for item in result["suggestions"] if float(item.get("chance") or 0) >= 75
    ]

    assert len(result["suggestions"]) == 12
    assert len(high_opportunity_suggestions) == 7
    assert result["suggestions"][0]["source"] == "ai"
    assert any(item.get("match_title") == "Training Scenario 6" for item in high_opportunity_suggestions)


def test_content_strategy_ai_keyword_trends_are_unique_by_keyword_and_platform() -> None:
    filters = normalize_strategy_filters(
        platform="all",
        time_range="30d",
        goal="conversion",
        audience="all",
        stage="boost",
    )
    result = build_content_strategy_summary(
        filters=filters,
        dashboard={
            "decision": {},
            "opportunities": [],
            "top_opportunities": [],
            "watchlist": [],
            "diagnostics": [],
        },
        posts=[],
        keyword_heat_snapshots=[],
        content_snapshots=[],
        competitor_compositions=[],
        ai_insights={"run": {"id": "ai-run-duplicates"}, "risk_notes": []},
        ai_topic_ideas=[],
        ai_strategy_summary={
            "keyword_trends": [
                {"keyword": "教育培训", "platform": None, "heat": "100", "score": 100, "direction": "up"},
                {"keyword": "教育培训", "platform": None, "heat": "100", "score": 100, "direction": "up"},
                {"keyword": "升学规划", "platform": "xhs", "heat": "75", "score": 75, "direction": "up"},
                {"keyword": "升学规划", "platform": "xhs", "heat": "50", "score": 50, "direction": "up"},
                {"keyword": "择校", "platform": None, "heat": "中", "score": 0, "direction": "up"},
            ],
        },
    )

    trend_keys = [(item["keyword"], item.get("platform")) for item in result["keyword_trends"]]
    assert trend_keys == [("教育培训", None), ("升学规划", "xhs"), ("择校", None)]
    assert result["keyword_trends"][0]["rank"] == 1
    assert result["keyword_trends"][1]["rank"] == 2
    assert result["keyword_trends"][1]["score"] == 75
    assert result["section_sources"]["keyword_trends"] == "ai"

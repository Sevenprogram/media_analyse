from research.dashboard import build_dashboard_summary


def test_dashboard_summary_returns_conservative_empty_state():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform=None,
    )

    assert summary["decision"]["sample_status"] == "insufficient"
    assert summary["decision"]["confidence"] == "low"
    assert "样本不足" in summary["decision"]["headline"]
    assert summary["actions"]["do_now"][0]["action"] == "search_now"
    assert summary["opportunities"] == []


def test_dashboard_summary_ranks_balanced_opportunities():
    summary = build_dashboard_summary(
        jobs=[{"id": 1, "status": "running", "collection_mode": "search"}],
        creator_candidates=[
            {
                "platform": "xhs",
                "creator_id": "creator-1",
                "display_name": "K12妈妈号",
                "match_score": 92,
                "recent_post_count_30d": 12,
                "hot_post_rate": 0.3,
                "evidence": [{"text": "主词命中"}],
            }
        ],
        keyword_heat_snapshots=[
            {
                "keyword": "K12教育",
                "platform": "xhs",
                "heat_score": 88,
                "growth_score": 20,
                "platform_signal": "boosting",
                "evidence": {"items": ["24h 内容量上升"]},
            }
        ],
        competitor_compositions=[
            {
                "competitor_id": 2,
                "platform": "xhs",
                "total_flow_count": 5000,
                "hot_post_rate": 0.4,
                "keyword_distribution": {"升学规划": 6},
                "evidence": {"top_posts": [{"title": "升学规划爆款"}]},
            }
        ],
        content_snapshots=[
            {
                "tracker_id": 3,
                "platform": "xhs",
                "total_content_count": 30,
                "hot_post_rate": 0.25,
                "keyword_distribution": {"单亲妈妈": 8},
                "evidence": {"top_posts": [{"title": "陪读焦虑"}]},
            }
        ],
        monitor_pools=[{"id": 1, "name": "K12达人池"}],
        platform="xhs",
    )

    assert summary["decision"]["sample_status"] == "enough"
    assert summary["monitoring"]["running_jobs"] == 1
    assert summary["monitoring"]["monitor_pools"] == 1
    assert len(summary["opportunities"]) == 4
    assert summary["opportunities"][0]["score"] >= summary["opportunities"][-1]["score"]
    assert all(item["reason"] for item in summary["opportunities"])


def test_dashboard_summary_returns_standard_decision_contract():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[
            {
                "keyword": "K12教育",
                "platform": "xhs",
                "heat_score": 90,
                "growth_score": 40,
                "platform_signal": "boosting",
                "sample_count": 128,
                "snapshot_date": "2026-05-21",
                "evidence": {"items": ["24h 讨论上升"]},
            }
        ],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform="xhs",
    )

    assert summary["scoring_profile"]["weights"] == {
        "heat_growth": 0.35,
        "sample_confidence": 0.25,
        "competition_gap": 0.2,
        "actionability": 0.2,
    }
    assert summary["scoring_profile"]["window"] == "7d_plus_24h"
    assert len(summary["top_opportunities"]) == 1
    opportunity = summary["top_opportunities"][0]
    assert set(opportunity["score_breakdown"]) == {
        "heat_growth",
        "sample_confidence",
        "competition_gap",
        "actionability",
    }
    assert opportunity["sample_scope"]["sample_count"] == 128
    assert "risk_tags" in opportunity
    assert "samples" in opportunity
    assert "display_title" in opportunity
    assert "target_url" in opportunity
    assert summary["opportunities"] == summary["top_opportunities"]


def test_low_sample_spike_goes_to_watchlist_not_first():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[
            {
                "keyword": "small-sample-spike",
                "platform": "xhs",
                "heat_score": 99,
                "growth_score": 95,
                "sample_count": 5,
                "snapshot_date": "2026-05-21",
                "evidence": {"items": ["low sample spike"]},
            },
            {
                "keyword": "stable-opportunity",
                "platform": "xhs",
                "heat_score": 82,
                "growth_score": 30,
                "sample_count": 150,
                "snapshot_date": "2026-05-21",
                "evidence": {"items": ["stable growth"]},
            },
        ],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform="xhs",
    )

    assert summary["top_opportunities"][0]["name"] == "stable-opportunity"
    watch_names = [item["name"] for item in summary["watchlist"]]
    assert "small-sample-spike" in watch_names
    spike = next(item for item in summary["watchlist"] if item["name"] == "small-sample-spike")
    assert "small_sample_spike" in spike["risk_tags"]


def test_feedback_moves_false_positive_out_of_top_opportunities():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[
            {
                "keyword": "false-positive",
                "platform": "xhs",
                "heat_score": 95,
                "growth_score": 45,
                "sample_count": 130,
                "evidence": {"items": ["x"]},
            },
            {
                "keyword": "keep",
                "platform": "xhs",
                "heat_score": 80,
                "growth_score": 30,
                "sample_count": 130,
                "evidence": {"items": ["y"]},
            },
        ],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform="xhs",
        feedback=[
            {"opportunity_id": "keyword:xhs:false-positive", "feedback": "false_positive"},
        ],
    )

    assert all(item["name"] != "false-positive" for item in summary["top_opportunities"])
    assert any(item["name"] == "false-positive" for item in summary["ignored_opportunities"])


def test_dashboard_summary_keeps_full_opportunity_pool_beyond_top_five():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[
            {
                "platform": "xhs",
                "creator_id": f"creator-{index}",
                "display_name": f"creator-{index}",
                "match_score": 90 - index,
                "recent_post_count_30d": 30,
                "evidence": [{"text": "match"}],
            }
            for index in range(6)
        ],
        keyword_heat_snapshots=[
            {
                "keyword": "long-tail-keyword",
                "platform": "xhs",
                "heat_score": 50,
                "growth_score": 10,
                "sample_count": 30,
                "evidence": {"items": ["keyword evidence"]},
            }
        ],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform="xhs",
    )

    assert len(summary["top_opportunities"]) == 5
    assert len(summary["opportunities"]) == 7
    assert any(item["type"] == "keyword" for item in summary["opportunities"])


def test_dashboard_summary_exposes_type_decisions_and_competitor_watchlist():
    summary = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[],
        competitor_compositions=[
            {
                "competitor_id": 1,
                "platform": "xhs",
                "display_name": "竞品账号",
                "total_flow_count": 0,
                "hot_post_rate": 0.0,
                "sample_count": 0,
                "evidence": {"items": ["已配置友商账号，但还没有公开流量快照"]},
            }
        ],
        content_snapshots=[],
        monitor_pools=[],
        platform="xhs",
    )

    assert any(item["type"] == "competitor" for item in summary["watchlist"])
    assert summary["type_decisions"]["competitor"]["sample_status"] == "limited"
    assert summary["type_decisions"]["keyword"]["sample_status"] == "insufficient"
    assert summary["type_diagnostics"]["competitor"]
    assert summary["type_diagnostics"]["keyword"][0]["code"] == "no_keyword_opportunities"

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.dashboard import build_dashboard_summary


def _keyword_snapshot(
    keyword: str,
    *,
    platform: str,
    heat_score: float,
    growth_score: float,
    sample_count: int = 30,
) -> dict:
    return {
        "keyword": keyword,
        "platform": platform,
        "heat_score": heat_score,
        "growth_score": growth_score,
        "sample_count": sample_count,
        "evidence": {
            "samples": [
                {
                    "platform": platform,
                    "title": f"{platform} {keyword}",
                    "url": f"https://example.test/{platform}/{keyword}",
                }
            ]
        },
    }


def test_dashboard_deduplicates_keyword_opportunities_by_topic() -> None:
    dashboard = build_dashboard_summary(
        jobs=[],
        creator_candidates=[],
        keyword_heat_snapshots=[
            _keyword_snapshot("study plan", platform="xhs", heat_score=75, growth_score=75),
            _keyword_snapshot("study plan", platform="dy", heat_score=50, growth_score=50),
            _keyword_snapshot("study plan", platform="dy", heat_score=50, growth_score=50),
            _keyword_snapshot("family education", platform="xhs", heat_score=40, growth_score=30),
        ],
        competitor_compositions=[],
        content_snapshots=[],
        monitor_pools=[],
        platform=None,
    )

    opportunities = dashboard["opportunities"]
    study_plan = [item for item in opportunities if item["display_title"] == "study plan"]

    assert len(study_plan) == 1
    assert len(opportunities) == 2
    assert study_plan[0]["id"] == "keyword:xhs:study plan"
    assert set(study_plan[0]["payload"]["platforms"]) == {"xhs", "dy"}
    assert set(study_plan[0]["payload"]["source_opportunity_ids"]) == {
        "keyword:xhs:study plan",
        "keyword:dy:study plan",
    }
    assert study_plan[0]["reason"].count("已合并多个平台的同名话题信号。") == 1
    assert "single_platform_signal" not in study_plan[0]["risk_tags"]

from datetime import datetime, timezone

from research.charts import build_chart_summary


def test_build_chart_summary_includes_core_dashboard_series():
    posts = [
        {
            "platform": "wb",
            "publish_time": datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
            "engagement_json": {"source_keyword": "政策"},
        }
    ]
    comments = [
        {
            "platform": "wb",
            "publish_time": datetime(2026, 1, 1, 13, tzinfo=timezone.utc),
        }
    ]
    ai_results = [{"result_json": {"sentiment": "positive", "topic_tags": ["治理"]}}]

    summary = build_chart_summary(posts=posts, comments=comments, ai_results=ai_results)

    assert summary["platform_counts"] == [{"platform": "wb", "posts": 1, "comments": 1}]
    assert summary["keyword_ranking"] == [{"keyword": "政策", "count": 1}]
    assert summary["sentiment_distribution"] == [{"name": "positive", "value": 1}]
    assert summary["topic_tag_ranking"] == [{"name": "治理", "value": 1}]

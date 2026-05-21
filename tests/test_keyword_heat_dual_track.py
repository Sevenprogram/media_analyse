from research.keyword_heat import build_keyword_heat_signal


def test_keyword_heat_returns_rule_ai_and_conflict():
    result = build_keyword_heat_signal(
        keyword="K12教育",
        platform="dy",
        metrics={
            "volume_24h": 30,
            "volume_7d_avg": 10,
            "volume_30d_avg": 8,
            "engagement_24h": 5000,
            "hot_post_rate": 0.4,
            "creator_participation": 12,
            "platform_coverage": 2,
        },
        ai_judgment={
            "label": "normal",
            "confidence": 0.7,
            "explanation": "AI sees stable topic",
        },
    )

    assert result["rule"]["label"] == "boosting"
    assert result["ai"]["label"] == "normal"
    assert result["conflict"] is True
    assert result["label"] == "boosting"
    assert result["evidence"]

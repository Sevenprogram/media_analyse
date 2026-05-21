from research.content_fingerprint import analyze_posts_for_tracking, build_content_fingerprint


def test_build_content_fingerprint_extracts_text_signals():
    result = build_content_fingerprint(
        {
            "title": "单亲妈妈分享小学英语启蒙经验",
            "content": "孩子英语基础差，靠自然拼读和每日陪读提分。",
            "engagement_json": {"liked_count": 200, "comment_count": 20},
        }
    )

    assert result["audience"] == "单亲妈妈"
    assert result["pain_point"] == "提分焦虑"
    assert result["content_type"] == "经验分享"
    assert result["confidence"] > 0.7


def test_analyze_posts_for_tracking_keeps_platform_and_post_id():
    result = analyze_posts_for_tracking(
        [{"platform": "xhs", "platform_post_id": "p1", "title": "K12英语启蒙"}]
    )

    assert result[0]["platform"] == "xhs"
    assert result[0]["platform_post_id"] == "p1"
    assert "fingerprint" in result[0]

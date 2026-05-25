from __future__ import annotations

import re
from collections import Counter
from typing import Any


AUDIENCE_TERMS = {
    "单亲妈妈": ["单亲", "一个人带娃", "离异妈妈", "陪读妈妈"],
    "小学家长": ["小学", "小升初", "一年级", "二年级", "三年级", "四年级", "五年级", "六年级"],
    "宝妈": ["宝妈", "妈妈", "宝爸", "家长"],
}
PAIN_TERMS = {
    "提分焦虑": ["提分", "成绩", "落后", "焦虑", "跟不上"],
    "英语启蒙": ["英语启蒙", "英语", "自然拼读", "单词"],
    "择校规划": ["择校", "升学", "小升初", "规划"],
}
CONTENT_TYPE_TERMS = {
    "经验分享": ["经验", "分享", "我是怎么", "复盘"],
    "避坑": ["避坑", "不要", "千万", "踩坑"],
    "测评": ["测评", "对比", "实测"],
    "案例": ["案例", "真实", "故事"],
}
CONVERSION_TERMS = ["课程", "咨询", "训练营", "资料", "私信", "领取", "报名"]


def build_content_fingerprint(post: dict[str, Any]) -> dict[str, Any]:
    text = _post_text(post)
    audience = _first_match(text, AUDIENCE_TERMS) or "泛家长"
    pain_point = _first_match(text, PAIN_TERMS) or "未明确痛点"
    content_type = _first_match(text, CONTENT_TYPE_TERMS) or post.get("content_type") or "内容样本"
    conversion_intent = "转化线索" if any(term in text for term in CONVERSION_TERMS) else "弱转化"
    topic_terms = _top_terms(text)
    topic = " / ".join(topic_terms[:3]) if topic_terms else (post.get("title") or "未提取主题")
    confidence = _confidence(text=text, audience=audience, pain_point=pain_point)
    return {
        "audience": audience,
        "pain_point": pain_point,
        "topic": topic,
        "content_type": content_type,
        "conversion_intent": conversion_intent,
        "summary": _summary(post, audience, pain_point, content_type),
        "confidence": confidence,
        "evidence": {
            "title": post.get("title"),
            "matched_text": text[:240],
            "engagement_total": _engagement_total(post),
        },
    }


def analyze_posts_for_tracking(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "platform": post.get("platform"),
            "platform_post_id": post.get("platform_post_id") or post.get("content_id"),
            "fingerprint": build_content_fingerprint(post),
        }
        for post in posts
    ]


def _post_text(post: dict[str, Any]) -> str:
    engagement = post.get("engagement_json") or post.get("engagement") or {}
    return " ".join(
        str(value or "")
        for value in [
            post.get("title"),
            post.get("content"),
            post.get("text_content"),
            engagement.get("source_keyword"),
            engagement.get("tag_list"),
            engagement.get("desc"),
        ]
    )


def _first_match(text: str, groups: dict[str, list[str]]) -> str | None:
    lowered = text.lower()
    for label, terms in groups.items():
        if any(term.lower() in lowered for term in terms):
            return label
    return None


def _top_terms(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}", text)
    stop = {"这个", "一个", "就是", "我们", "孩子", "家长", "分享"}
    counts = Counter(token for token in tokens if token not in stop)
    return [term for term, _ in counts.most_common(5)]


def _summary(post: dict[str, Any], audience: str, pain_point: str, content_type: str) -> str:
    title = str(post.get("title") or post.get("content") or post.get("text_content") or "").strip()
    title = title[:48] if title else "无标题内容"
    return f"{audience}围绕{pain_point}的{content_type}：{title}"


def _confidence(*, text: str, audience: str, pain_point: str) -> float:
    score = 0.35
    if audience != "泛家长":
        score += 0.25
    if pain_point != "未明确痛点":
        score += 0.25
    if len(text) >= 80:
        score += 0.15
    return round(min(score, 1.0), 4)


def _engagement_total(post: dict[str, Any]) -> int:
    engagement = post.get("engagement_json") or post.get("engagement") or {}
    total = 0
    for key in ("liked_count", "like_count", "comment_count", "comments_count", "share_count", "collected_count"):
        try:
            total += int(engagement.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return total

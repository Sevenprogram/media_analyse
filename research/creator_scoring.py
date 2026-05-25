from typing import Any


def score_creator_candidate(
    profile: dict[str, Any],
    posts: list[dict[str, Any]],
    keywords: list[dict[str, Any]],
) -> dict[str, Any]:
    blocks = [
        {
            "post_id": post.get("platform_post_id") or post.get("id"),
            "url": post.get("url"),
            "text": f"{post.get('title') or ''}\n{post.get('content') or ''}",
            "engagement": post.get("engagement_json") or {},
        }
        for post in posts
    ]
    matched: dict[str, list[str]] = {
        "primary": [],
        "secondary": [],
        "platform_adapted": [],
        "synonym": [],
        "negative": [],
    }
    evidence: list[dict[str, Any]] = []

    for keyword in keywords:
        term = str(keyword.get("keyword") or "").strip()
        if not term:
            continue
        key_type = str(keyword.get("keyword_type") or "secondary")
        for block in blocks:
            if term.lower() not in block["text"].lower():
                continue
            matched.setdefault(key_type, []).append(term)
            evidence.append(
                {
                    "keyword": term,
                    "keyword_type": key_type,
                    "post_id": block["post_id"],
                    "url": block["url"],
                    "context": block["text"][:180],
                    "engagement": block["engagement"],
                }
            )
            break

    if not matched["primary"]:
        return {
            "eligible": False,
            "score": 0.0,
            "labels": ["主词未命中"],
            "matched_keywords": _dedupe_matches(matched),
            "evidence": evidence,
        }

    score = 35.0
    score += min(len(set(matched.get("secondary", []))) * 10.0, 20.0)
    score += min(len(set(matched.get("synonym", []))) * 6.0, 12.0)
    score += min(len(set(matched.get("platform_adapted", []))) * 5.0, 10.0)
    score += min(float(profile.get("recent_post_count_30d") or len(posts) or 0) * 2.0, 10.0)
    score += min(float(profile.get("avg_engagement_rate") or 0) * 100.0, 15.0)
    score -= min(len(set(matched.get("negative", []))) * 15.0, 30.0)
    score = round(max(0.0, min(100.0, score)), 2)

    labels = ["高匹配" if score >= 80 else "可跟进" if score >= 60 else "低优先级"]
    if matched.get("negative"):
        labels.append("存在排除词风险")

    return {
        "eligible": score >= 60 and not matched.get("negative"),
        "score": score,
        "labels": labels,
        "matched_keywords": _dedupe_matches(matched),
        "evidence": evidence,
    }


def _dedupe_matches(matched: dict[str, list[str]]) -> dict[str, list[str]]:
    return {key: sorted(set(values)) for key, values in matched.items()}

from collections import Counter
from typing import Any


def extract_content_keywords(
    *, text: str, scene_keywords: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    lowered = text.lower()
    results = []
    for keyword in scene_keywords:
        term = str(keyword.get("keyword") or "").strip()
        if not term or term.lower() not in lowered:
            continue
        index = lowered.find(term.lower())
        results.append(
            {
                "keyword": term,
                "keyword_type": keyword.get("keyword_type"),
                "scene_pack_id": keyword.get("scene_pack_id"),
                "platform": keyword.get("platform"),
                "confidence": _keyword_confidence(str(keyword.get("keyword_type") or "")),
                "evidence_text": _context(text, term),
                "reason": keyword.get("reason") or "",
                "query_variants": [term],
                "position": index,
            }
        )
    results.sort(key=lambda item: (-item["confidence"], item["position"]))
    return results


def search_similar_content(
    *, keywords: list[str], posts: list[dict[str, Any]], limit: int = 50
) -> list[dict[str, Any]]:
    candidates = []
    for post in posts:
        engagement = post.get("engagement_json") or {}
        text = _join_text(
            post.get("title"),
            post.get("content"),
            engagement.get("source_keyword"),
            engagement.get("tag_list"),
        )
        hits = _keyword_hits(text, keywords)
        if not hits:
            continue
        score = _similarity_score(hits, [], keywords) + min(15, _post_engagement(post) / 20)
        candidates.append(
            {
                "platform": post["platform"],
                "platform_post_id": post["platform_post_id"],
                "author_id": post.get("author_hash"),
                "title": post.get("title") or post.get("content") or post["platform_post_id"],
                "url": post.get("url"),
                "publish_time": post.get("publish_time"),
                "similarity_score": round(min(100.0, score), 2),
                "matched_keywords": hits,
                "engagement": post.get("engagement_json") or {},
                "evidence": {
                    "source": "local",
                    "snippets": [hit["context"] for hit in hits],
                },
            }
        )
    return sorted(candidates, key=lambda item: item["similarity_score"], reverse=True)[:limit]


def build_tracker_analysis(
    *, tracker: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    platform_counts = Counter(item["platform"] for item in candidates)
    keyword_counts = Counter()
    for item in candidates:
        for hit in item.get("matched_keywords") or []:
            keyword_counts[hit["term"]] += hit["count"]
    return {
        "tracker_id": tracker["id"],
        "summary": {
            "total_candidates": len(candidates),
            "platforms": dict(platform_counts),
            "top_keywords": [
                {"name": key, "value": value}
                for key, value in keyword_counts.most_common(10)
            ],
        },
        "hot_content": candidates[:10],
        "evidence": [item.get("evidence") for item in candidates[:20]],
    }


def analyze_content_tracking(
    *,
    query: str,
    posts: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    entity_tags: list[dict[str, Any]],
    tag_definitions: list[dict[str, Any]],
    limit: int = 30,
) -> dict[str, Any]:
    terms = _query_terms(query)
    tags_by_id = {int(tag["id"]): tag for tag in tag_definitions}
    tags_by_entity: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for tag in entity_tags:
        key = (tag["entity_type"], tag["platform"], tag["entity_id"])
        tags_by_entity.setdefault(key, []).append(tag)

    post_results = []
    for post in posts:
        engagement = post.get("engagement_json") or {}
        text = _join_text(
            post.get("title"),
            post.get("content"),
            engagement.get("source_keyword"),
            engagement.get("tag_list"),
        )
        hits = _keyword_hits(text, terms)
        post_tags = tags_by_entity.get(("post", post["platform"], post["platform_post_id"]), [])
        tag_hits = [
            {
                "tag_id": tag["tag_id"],
                "tag_name": tags_by_id.get(int(tag["tag_id"]), {}).get("tag_name"),
                "confidence": tag.get("confidence"),
            }
            for tag in post_tags
        ]
        if not hits and not tag_hits:
            continue
        post_results.append(
            {
                "platform": post["platform"],
                "post_id": post["platform_post_id"],
                "title": post.get("title") or post.get("content") or post["platform_post_id"],
                "author_hash": post.get("author_hash"),
                "url": post.get("url"),
                "publish_time": post.get("publish_time"),
                "engagement": post.get("engagement_json") or {},
                "keyword_hits": hits,
                "tag_hits": tag_hits,
                "similarity_score": _similarity_score(hits, post_tags, terms),
                "tracking_markers": _tracking_markers(text, hits),
            }
        )

    comment_results = []
    for comment in comments:
        hits = _keyword_hits(comment.get("content") or "", terms)
        if not hits:
            continue
        comment_results.append(
            {
                "platform": comment["platform"],
                "comment_id": comment["platform_comment_id"],
                "post_id": comment.get("platform_post_id"),
                "content": comment.get("content"),
                "keyword_hits": hits,
                "like_count": comment.get("like_count") or 0,
            }
        )

    post_results.sort(key=lambda item: item["similarity_score"], reverse=True)
    trend_terms = Counter()
    for item in post_results:
        for hit in item["keyword_hits"]:
            trend_terms[hit["term"]] += hit["count"]
        for tag in item["tag_hits"]:
            if tag["tag_name"]:
                trend_terms[str(tag["tag_name"])] += 1

    return {
        "query": query,
        "summary": {
            "matched_posts": len(post_results),
            "matched_comments": len(comment_results),
            "tracked_keywords": len(terms),
            "top_terms": [{"name": name, "value": value} for name, value in trend_terms.most_common(12)],
        },
        "content": post_results[:limit],
        "comments": comment_results[:limit],
        "insights": _content_insights(post_results, comment_results, trend_terms),
    }


def _query_terms(query: str) -> list[str]:
    normalized = query.replace("+", " ").replace("，", " ").replace(",", " ")
    return [item.strip() for item in normalized.split() if item.strip()]


def _keyword_hits(text: str, terms: list[str]) -> list[dict[str, Any]]:
    lowered = text.lower()
    hits = []
    for term in terms:
        count = lowered.count(term.lower())
        if count:
            hits.append({"term": term, "count": count, "context": _context(text, term)})
    return hits


def _similarity_score(hits: list[dict[str, Any]], tags: list[dict[str, Any]], terms: list[str]) -> float:
    keyword_component = min(60.0, sum(hit["count"] for hit in hits) * 20.0)
    tag_component = min(40.0, len(tags) * 10.0)
    coverage_component = 0.0
    if terms:
        coverage_component = len({hit["term"] for hit in hits}) / len(terms) * 20.0
    return round(min(100.0, keyword_component + tag_component + coverage_component), 2)


def _tracking_markers(text: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    length = max(1, len(text))
    markers = []
    for hit in hits:
        index = text.lower().find(hit["term"].lower())
        if index >= 0:
            markers.append(
                {
                    "term": hit["term"],
                    "position_percent": round(index / length * 100, 2),
                    "source": "text",
                }
            )
    return markers


def _content_insights(
    posts: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    trend_terms: Counter,
) -> list[str]:
    insights = []
    if posts:
        insights.append(f"找到 {len(posts)} 条同类内容，可按相似度加入追踪池。")
    if comments:
        insights.append(f"评论区命中 {len(comments)} 条关键词线索，适合继续看购买意图和负反馈。")
    if trend_terms:
        top = trend_terms.most_common(1)[0][0]
        insights.append(f"当前最高频信号是「{top}」，建议作为二级筛选条件。")
    if not insights:
        insights.append("当前样本中未发现稳定关键词信号，建议扩大时间窗或补充同义词。")
    return insights


def _join_text(*values: Any) -> str:
    return " ".join(str(value) for value in values if value)


def _context(text: str, term: str, width: int = 36) -> str:
    index = text.lower().find(term.lower())
    if index < 0:
        return text[: width * 2]
    start = max(0, index - width)
    end = min(len(text), index + len(term) + width)
    return text[start:end]


def _keyword_confidence(keyword_type: str) -> float:
    return {
        "primary": 0.95,
        "secondary": 0.8,
        "synonym": 0.72,
        "platform_adapted": 0.7,
        "negative": 0.9,
    }.get(keyword_type, 0.5)


def _post_engagement(post: dict[str, Any]) -> int:
    engagement = post.get("engagement_json") or {}
    return sum(
        int(engagement.get(key) or 0)
        for key in (
            "liked_count",
            "like_count",
            "comment_count",
            "comments_count",
            "share_count",
            "collected_count",
        )
    )

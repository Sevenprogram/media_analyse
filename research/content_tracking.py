import json
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


def build_content_keyword_ai_prompt(
    *,
    title: str | None,
    text: str,
    platform: str | None,
) -> str:
    schema = {
        "keywords": [
            {
                "keyword": "string",
                "keyword_type": "primary|secondary|synonym|negative",
                "confidence": 0.0,
                "evidence_text": "string",
                "reason": "string",
                "query_variants": ["string"],
            }
        ]
    }
    evidence = {
        "title": title or "",
        "text": text[:4000],
        "platform": platform,
    }
    return (
        "你是内容增长研究员。请从输入内容中提取适合后续内容跟踪和平台搜索的关键词。\n"
        "要求：\n"
        "1. 只返回 JSON，不要 Markdown。\n"
        "2. primary 放最值得直接追踪的核心词，secondary 放相关扩展词，synonym 放同义/表达变体，negative 放太泛或容易误伤的噪声词。\n"
        "3. 关键词要适合直接用于小红书、抖音等平台搜索。\n"
        "4. evidence_text 必须来自标题或正文，不要编造外部事实。\n"
        "5. 最多返回 12 个关键词，按追踪价值排序。\n"
        f"输出 JSON schema 示例：{json.dumps(schema, ensure_ascii=False)}\n"
        f"输入内容：{json.dumps(evidence, ensure_ascii=False)}"
    )


def normalize_content_keyword_ai_output(output: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(output, dict):
        return []
    rows = output.get("keywords")
    if not isinstance(rows, list):
        rows = output.get("items")
    normalized = []
    for index, item in enumerate(_list_of_dicts(rows)):
        keyword = str(item.get("keyword") or item.get("term") or "").strip()
        if not keyword:
            continue
        keyword_type = str(item.get("keyword_type") or item.get("type") or "secondary").lower()
        if keyword_type not in {"primary", "secondary", "synonym", "negative"}:
            keyword_type = "secondary"
        confidence = _float_between(item.get("confidence"), default=_keyword_confidence(keyword_type))
        variants = _string_list(item.get("query_variants") or item.get("variants"))
        if not variants:
            variants = [keyword]
        normalized.append(
            {
                "keyword": keyword,
                "keyword_type": keyword_type,
                "scene_pack_id": item.get("scene_pack_id"),
                "platform": item.get("platform"),
                "confidence": confidence,
                "evidence_text": str(item.get("evidence_text") or item.get("evidence") or ""),
                "reason": str(item.get("reason") or ""),
                "query_variants": variants,
                "position": index,
                "source": "ai",
            }
        )
    normalized.sort(key=lambda item: (-item["confidence"], item["position"]))
    return normalized[:12]


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


def build_content_tracking_ai_prompt(
    *,
    title: str | None,
    text: str,
    platform: str | None,
    keywords: list[str],
    candidates: list[dict[str, Any]],
    comments: list[dict[str, Any]],
) -> str:
    schema = {
        "topic_summary": "string",
        "keyword_judgement": [
            {
                "keyword": "string",
                "value": "high|medium|low|noise",
                "reason": "string",
                "tracking_action": "include|exclude|watch",
            }
        ],
        "similar_content_patterns": ["string"],
        "comment_feedback": ["string"],
        "tracking_suggestions": {
            "included_keywords": ["string"],
            "excluded_keywords": ["string"],
            "platform_notes": ["string"],
        },
        "opportunities": ["string"],
        "risk_notes": ["string"],
    }
    evidence = {
        "source": {
            "title": title,
            "text": text[:4000],
            "platform": platform,
            "keywords": keywords,
        },
        "local_candidates": [
            _compact_candidate_for_ai(item) for item in candidates[:20]
        ],
        "local_comments": [
            {
                "platform": item.get("platform"),
                "post_id": item.get("post_id") or item.get("platform_post_id"),
                "content": str(item.get("content") or "")[:500],
                "like_count": item.get("like_count") or 0,
                "keyword_hits": item.get("keyword_hits") or item.get("matched_keywords") or [],
            }
            for item in comments[:30]
        ],
    }
    return (
        "你是内容增长研究员。只能基于输入的本地数据库证据做分析，不要编造外部事实。\n"
        "任务：判断这段内容的主题、哪些关键词值得持续追踪、本地同类内容呈现出什么模式、评论区有什么反馈，并给出追踪建议。\n"
        "硬性要求：\n"
        "1. 只返回 JSON，不要 Markdown。\n"
        "2. 每个判断必须能对应输入中的关键词、候选内容或评论证据。\n"
        "3. 样本不足时要在 risk_notes 说明，不要强行下结论。\n"
        "4. included_keywords 只放建议纳入追踪的词，excluded_keywords 只放噪音词或容易误伤的词。\n"
        f"输出 JSON schema 示例：{json.dumps(schema, ensure_ascii=False)}\n"
        f"本地证据：{json.dumps(evidence, ensure_ascii=False, default=str)}"
    )


def normalize_content_tracking_ai_output(output: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(output, dict):
        return _empty_ai_output("AI output is not a JSON object")
    suggestions = output.get("tracking_suggestions")
    if not isinstance(suggestions, dict):
        suggestions = {}
    return {
        "topic_summary": str(output.get("topic_summary") or output.get("summary") or ""),
        "keyword_judgement": [
            _normalize_keyword_judgement(item)
            for item in _list_of_dicts(output.get("keyword_judgement"))
        ],
        "similar_content_patterns": _string_list(output.get("similar_content_patterns")),
        "comment_feedback": _string_list(output.get("comment_feedback")),
        "tracking_suggestions": {
            "included_keywords": _string_list(suggestions.get("included_keywords")),
            "excluded_keywords": _string_list(suggestions.get("excluded_keywords")),
            "platform_notes": _string_list(suggestions.get("platform_notes")),
        },
        "opportunities": _string_list(output.get("opportunities")),
        "risk_notes": _string_list(output.get("risk_notes")),
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


def _float_between(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


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


def _compact_candidate_for_ai(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": item.get("platform"),
        "post_id": item.get("platform_post_id") or item.get("post_id"),
        "title": item.get("title"),
        "similarity_score": item.get("similarity_score"),
        "matched_keywords": item.get("matched_keywords") or item.get("keyword_hits") or [],
        "engagement": item.get("engagement") or {},
        "evidence": item.get("evidence") or {},
    }


def _normalize_keyword_judgement(item: dict[str, Any]) -> dict[str, str]:
    value = str(item.get("value") or "medium").lower()
    if value not in {"high", "medium", "low", "noise"}:
        value = "medium"
    action = str(item.get("tracking_action") or "watch").lower()
    if action not in {"include", "exclude", "watch"}:
        action = "watch"
    return {
        "keyword": str(item.get("keyword") or ""),
        "value": value,
        "reason": str(item.get("reason") or ""),
        "tracking_action": action,
    }


def _empty_ai_output(reason: str) -> dict[str, Any]:
    return {
        "topic_summary": "",
        "keyword_judgement": [],
        "similar_content_patterns": [],
        "comment_feedback": [],
        "tracking_suggestions": {
            "included_keywords": [],
            "excluded_keywords": [],
            "platform_notes": [],
        },
        "opportunities": [],
        "risk_notes": [reason],
    }


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]

import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from research.content_fingerprint import build_content_fingerprint

KEYWORD_HIGH_VALUE_MIN_SCORE = 55.0
KEYWORD_HIGH_VALUE_MAX_NOISE_RATE = 0.45
KEYWORD_NOISE_MIN_RATE = 0.5
KEYWORD_EXCLUDE_MIN_RATE = 0.6


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


def build_tracker_keyword_suggestion_ai_prompt(
    *,
    name: str,
    description: str,
    platforms: list[str],
    included_keywords: list[str],
    excluded_keywords: list[str],
) -> str:
    schema = {
        "included_keywords": ["string"],
        "excluded_keywords": ["string"],
        "expanded_keywords": ["string"],
        "platform_keywords": {"xhs": ["string"], "dy": ["string"]},
        "reason": "string",
    }
    payload = {
        "task": "Suggest practical search and tracking keywords for a content tracker.",
        "rules": [
            "Return JSON only.",
            "included_keywords should be precise phrases worth tracking.",
            "excluded_keywords should remove ads, giveaways, unrelated meanings, and misleading matches.",
            "expanded_keywords should include synonyms and platform-native search wording.",
            "Do not invent facts; infer only from the tracker name, description, platforms, and existing keywords.",
            "Keep each list concise; at most 12 included, 12 expanded, and 10 excluded keywords.",
        ],
        "tracker": {
            "name": name,
            "description": description,
            "platforms": platforms,
            "included_keywords": included_keywords,
            "excluded_keywords": excluded_keywords,
        },
        "output_schema": schema,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def normalize_tracker_keyword_suggestion_ai_output(output: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(output, dict):
        return {
            "included_keywords": [],
            "excluded_keywords": [],
            "expanded_keywords": [],
            "platform_keywords": {},
            "reason": "",
        }
    platform_keywords = output.get("platform_keywords")
    if not isinstance(platform_keywords, dict):
        platform_keywords = {}
    normalized_platform_keywords: dict[str, list[str]] = {}
    for platform, values in platform_keywords.items():
        normalized_platform_keywords[str(platform)] = _dedupe_strings(_string_list(values))[:12]
    return {
        "included_keywords": _dedupe_strings(
            _string_list(output.get("included_keywords") or output.get("include_keywords"))
        )[:12],
        "excluded_keywords": _dedupe_strings(
            _string_list(output.get("excluded_keywords") or output.get("exclude_keywords"))
        )[:10],
        "expanded_keywords": _dedupe_strings(
            _string_list(output.get("expanded_keywords") or output.get("expansion_keywords"))
        )[:12],
        "platform_keywords": normalized_platform_keywords,
        "reason": str(output.get("reason") or output.get("summary") or "")[:500],
    }


def build_tracker_ai_enhancement_prompt(
    *,
    analysis_bundle: dict[str, Any],
    candidates: list[dict[str, Any]],
    candidate_limit: int = 80,
) -> str:
    tracker = analysis_bundle.get("tracker") or {}
    schema = {
        "sample_selection": {
            "representative_samples": [
                {
                    "sample_key": "platform:post_id",
                    "relevance_score": 0,
                    "reason": "why selected",
                }
            ],
            "hot_samples": [],
            "early_signal_samples": [],
            "noise_samples": [],
        },
        "keyword_strategy": {
            "recommended_include_keywords": ["string"],
            "recommended_exclude_keywords": ["string"],
            "keyword_notes": ["string"],
        },
        "decision_explanation": {
            "headline": "string",
            "summary": "string",
            "evidence": ["string"],
            "recommended_actions": [
                {"action": "string", "reason": "string"}
            ],
        },
        "pattern_insights": {
            "summary": "string",
            "patterns": [
                {"name": "string", "description": "string", "sample_keys": ["platform:post_id"]}
            ],
        },
        "noise_diagnosis": {
            "summary": "string",
            "noise_terms": ["string"],
            "suggested_exclude_keywords": ["string"],
            "off_topic_reasons": ["string"],
        },
        "tracker_suggestions": {
            "included_keywords": ["string"],
            "excluded_keywords": ["string"],
            "split_tracker_suggestions": ["string"],
            "platform_notes": ["string"],
        },
    }
    payload = {
        "task": "Enhance a content tracking analysis using only the provided local evidence.",
        "rules": [
            "Return JSON only.",
            "Do not change, fabricate, or reinterpret raw numbers such as engagement, sample counts, publish time, author, or platform.",
            "Use only sample_key values present in candidates.",
            "Put low-engagement high-fit items into early_signal_samples rather than representative_samples when enough engaged samples exist.",
            "Keyword suggestions must be practical platform search terms, not broad category labels.",
            "Noise diagnosis must identify why matched content is off-topic and propose exclude keywords only when justified by evidence.",
            "Conclusion must mention uncertainty when sample quality or noise makes the judgement weak.",
        ],
        "tracker": tracker,
        "metrics": {
            "overview": analysis_bundle.get("overview") or {},
            "trends": _compact_metrics_dict(analysis_bundle.get("trends") or {}),
            "keywords": {
                "keyword_rows": (analysis_bundle.get("keywords") or {}).get("keyword_rows", [])[:12],
                "recommended_include_keywords": (analysis_bundle.get("keywords") or {}).get(
                    "recommended_include_keywords", []
                ),
                "recommended_exclude_keywords": (analysis_bundle.get("keywords") or {}).get(
                    "recommended_exclude_keywords", []
                ),
            },
            "patterns": {
                "content_type_distribution": (analysis_bundle.get("patterns") or {}).get(
                    "content_type_distribution", {}
                ),
                "pain_point_distribution": (analysis_bundle.get("patterns") or {}).get(
                    "pain_point_distribution", {}
                ),
                "audience_distribution": (analysis_bundle.get("patterns") or {}).get(
                    "audience_distribution", {}
                ),
                "pattern_clusters": (analysis_bundle.get("patterns") or {}).get(
                    "pattern_clusters", []
                )[:8],
            },
            "risks": analysis_bundle.get("risks") or {},
            "decisions": analysis_bundle.get("decisions") or {},
        },
        "output_schema": schema,
        "candidates": [
            _compact_tracker_sample_for_ai(candidate)
            for candidate in candidates[: max(1, int(candidate_limit or 80))]
        ],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def build_tracker_sample_selection_ai_prompt(
    *,
    tracker: dict[str, Any],
    candidates: list[dict[str, Any]],
    candidate_limit: int = 80,
) -> str:
    schema = {
        "representative_samples": [
            {
                "sample_key": "platform:post_id",
                "relevance_score": 0,
                "reason": "why this is a representative on-topic sample",
            }
        ],
        "hot_samples": [
            {
                "sample_key": "platform:post_id",
                "relevance_score": 0,
                "reason": "why this is a relevant high-engagement sample",
            }
        ],
        "early_signal_samples": [
            {
                "sample_key": "platform:post_id",
                "relevance_score": 0,
                "reason": "why this is a high-fit early signal",
            }
        ],
        "noise_samples": [
            {
                "sample_key": "platform:post_id",
                "relevance_score": 0,
                "reason": "why this looks off-topic or noisy",
            }
        ],
    }
    payload = {
        "task": "Select the best evidence samples for a content tracker analysis.",
        "rules": [
            "Return JSON only.",
            "Use only sample_key values present in candidates.",
            "representative_samples should be on-topic, market-validated, diverse across platforms/authors/patterns, and useful for human audit.",
            "For representative_samples, prefer candidates with engagement_total greater than 0. Only use zero-engagement samples when there are not enough relevant engaged samples.",
            "hot_samples should be both relevant and high-engagement; do not select noisy high-engagement samples.",
            "early_signal_samples should be highly relevant but not necessarily high-engagement yet; low-engagement high-fit samples belong here instead of representative_samples.",
            "noise_samples should contain keyword hits that are likely off-topic, ads, giveaways, or misleading matches.",
            "Return at most 10 items for each non-noise section and at most 8 noise samples.",
        ],
        "tracker": {
            "name": tracker.get("name"),
            "description": tracker.get("description"),
            "platforms": tracker.get("platforms") or [],
            "included_keywords": tracker.get("included_keywords") or [],
            "excluded_keywords": tracker.get("excluded_keywords") or [],
        },
        "output_schema": schema,
        "candidates": [
            _compact_tracker_sample_for_ai(candidate)
            for candidate in candidates[: max(1, int(candidate_limit or 80))]
        ],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def normalize_tracker_sample_selection_ai_output(
    output: dict[str, Any],
    *,
    allowed_sample_keys: set[str],
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(output, dict):
        return {
            "representative_samples": [],
            "hot_samples": [],
            "early_signal_samples": [],
            "noise_samples": [],
        }
    source = output.get("samples") if isinstance(output.get("samples"), dict) else output
    limits = {
        "representative_samples": 10,
        "hot_samples": 10,
        "early_signal_samples": 10,
        "noise_samples": 8,
    }
    aliases = {
        "representative_samples": ("representative_samples", "representative", "representatives"),
        "hot_samples": ("hot_samples", "hot", "viral_samples"),
        "early_signal_samples": ("early_signal_samples", "early_signals", "early"),
        "noise_samples": ("noise_samples", "noise", "off_topic_samples"),
    }
    normalized: dict[str, list[dict[str, Any]]] = {}
    for section, names in aliases.items():
        raw_items: Any = []
        for name in names:
            if isinstance(source.get(name), list):
                raw_items = source.get(name)
                break
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in _list_of_dicts(raw_items):
            sample_key = str(
                item.get("sample_key") or item.get("id") or item.get("key") or ""
            ).strip()
            if not sample_key or sample_key not in allowed_sample_keys or sample_key in seen:
                continue
            selected.append(
                {
                    "sample_key": sample_key,
                    "relevance_score": _score_between_zero_and_hundred(
                        item.get("relevance_score")
                        or item.get("score")
                        or item.get("confidence")
                    ),
                    "reason": str(item.get("reason") or item.get("rationale") or "")[:240],
                }
            )
            seen.add(sample_key)
            if len(selected) >= limits[section]:
                break
        normalized[section] = selected
    return normalized


def normalize_tracker_ai_enhancement_output(
    output: dict[str, Any],
    *,
    allowed_sample_keys: set[str],
) -> dict[str, Any]:
    if not isinstance(output, dict):
        output = {}
    sample_source = output.get("sample_selection")
    if not isinstance(sample_source, dict):
        sample_source = output
    keyword_strategy = output.get("keyword_strategy")
    if not isinstance(keyword_strategy, dict):
        keyword_strategy = {}
    decision_explanation = output.get("decision_explanation")
    if not isinstance(decision_explanation, dict):
        decision_explanation = {}
    pattern_insights = output.get("pattern_insights")
    if not isinstance(pattern_insights, dict):
        pattern_insights = {}
    noise_diagnosis = output.get("noise_diagnosis")
    if not isinstance(noise_diagnosis, dict):
        noise_diagnosis = {}
    tracker_suggestions = output.get("tracker_suggestions")
    if not isinstance(tracker_suggestions, dict):
        tracker_suggestions = {}
    return {
        "sample_selection": normalize_tracker_sample_selection_ai_output(
            sample_source,
            allowed_sample_keys=allowed_sample_keys,
        ),
        "keyword_strategy": {
            "recommended_include_keywords": _dedupe_strings(
                _string_list(keyword_strategy.get("recommended_include_keywords"))
            )[:12],
            "recommended_exclude_keywords": _dedupe_strings(
                _string_list(keyword_strategy.get("recommended_exclude_keywords"))
            )[:12],
            "keyword_notes": _dedupe_strings(_string_list(keyword_strategy.get("keyword_notes")))[:8],
        },
        "decision_explanation": {
            "headline": str(decision_explanation.get("headline") or "")[:160],
            "summary": str(decision_explanation.get("summary") or "")[:800],
            "evidence": _dedupe_strings(_string_list(decision_explanation.get("evidence")))[:8],
            "recommended_actions": [
                _normalize_ai_action(item)
                for item in _list_of_dicts(decision_explanation.get("recommended_actions"))
            ][:6],
        },
        "pattern_insights": {
            "summary": str(pattern_insights.get("summary") or "")[:800],
            "patterns": [
                _normalize_ai_pattern(item, allowed_sample_keys=allowed_sample_keys)
                for item in _list_of_dicts(pattern_insights.get("patterns"))
            ][:8],
        },
        "noise_diagnosis": {
            "summary": str(noise_diagnosis.get("summary") or "")[:800],
            "noise_terms": _dedupe_strings(_string_list(noise_diagnosis.get("noise_terms")))[:12],
            "suggested_exclude_keywords": _dedupe_strings(
                _string_list(noise_diagnosis.get("suggested_exclude_keywords"))
            )[:12],
            "off_topic_reasons": _dedupe_strings(
                _string_list(noise_diagnosis.get("off_topic_reasons"))
            )[:8],
        },
        "tracker_suggestions": {
            "included_keywords": _dedupe_strings(
                _string_list(tracker_suggestions.get("included_keywords"))
            )[:12],
            "excluded_keywords": _dedupe_strings(
                _string_list(tracker_suggestions.get("excluded_keywords"))
            )[:12],
            "split_tracker_suggestions": _dedupe_strings(
                _string_list(tracker_suggestions.get("split_tracker_suggestions"))
            )[:8],
            "platform_notes": _dedupe_strings(_string_list(tracker_suggestions.get("platform_notes")))[:8],
        },
    }


def apply_tracker_ai_enhancement(
    analysis_bundle: dict[str, Any],
    enhancement: dict[str, Any],
    *,
    source: str,
    provider: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selection = enhancement.get("sample_selection") or {}
    if any(selection.values()):
        apply_tracker_ai_sample_selection(
            analysis_bundle,
            selection,
            source=source,
            provider=provider,
        )
    _apply_ai_keyword_strategy(analysis_bundle, enhancement.get("keyword_strategy") or {})
    _apply_ai_decision_explanation(analysis_bundle, enhancement.get("decision_explanation") or {})
    _apply_ai_pattern_insights(analysis_bundle, enhancement.get("pattern_insights") or {})
    _apply_ai_noise_diagnosis(analysis_bundle, enhancement.get("noise_diagnosis") or {})
    _apply_ai_tracker_suggestions(analysis_bundle, enhancement.get("tracker_suggestions") or {})
    meta = analysis_bundle.setdefault("meta", {})
    meta["ai_enhancement"] = {
        "source": source,
        "provider": {
            "name": provider.get("name"),
            "model": provider.get("model"),
        }
        if provider
        else None,
        "features": [
            "tracker_keyword_suggestions",
            "keyword_analysis",
            "decision_explanation",
            "pattern_insights",
            "noise_diagnosis",
            "sample_reasons",
        ],
    }
    return analysis_bundle


def apply_tracker_ai_sample_selection(
    analysis_bundle: dict[str, Any],
    selection: dict[str, list[dict[str, Any]]],
    *,
    source: str,
    provider: dict[str, Any] | None = None,
) -> dict[str, Any]:
    samples = analysis_bundle.get("samples") or {}
    all_samples = samples.get("all_samples") or []
    sample_lookup = {
        str(sample.get("sample_key") or _sample_key(sample)): sample
        for sample in all_samples
        if str(sample.get("sample_key") or _sample_key(sample))
    }
    limits = {
        "representative_samples": 10,
        "hot_samples": 10,
        "early_signal_samples": 10,
    }
    for section, limit in limits.items():
        fallback = samples.get(section) or []
        selected = _selected_samples_from_ai(
            selection.get(section) or [],
            sample_lookup=sample_lookup,
            fallback=fallback,
            limit=limit,
            source=source,
            minimum_engagement=1 if section == "representative_samples" else None,
        )
        samples[section] = selected
    noise_samples = _selected_samples_from_ai(
        selection.get("noise_samples") or [],
        sample_lookup=sample_lookup,
        fallback=[],
        limit=8,
        source=source,
    )
    if noise_samples:
        samples["noise_samples"] = noise_samples
    analysis_bundle["samples"] = samples
    mark_tracker_sample_selection(
        analysis_bundle,
        source=source,
        reason="ai_selection_applied",
        provider=provider,
        counts={key: len(value) for key, value in selection.items()},
    )
    return analysis_bundle


def mark_tracker_sample_selection(
    analysis_bundle: dict[str, Any],
    *,
    source: str,
    reason: str,
    provider: dict[str, Any] | None = None,
    error: str | None = None,
    counts: dict[str, int] | None = None,
) -> None:
    meta = analysis_bundle.setdefault("meta", {})
    payload: dict[str, Any] = {
        "source": source,
        "reason": reason,
    }
    if provider:
        payload["provider"] = {
            "name": provider.get("name"),
            "model": provider.get("model"),
        }
    if error:
        payload["error"] = error[:500]
    if counts:
        payload["counts"] = counts
    meta["sample_selection"] = payload


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


def build_tracker_analysis_snapshot(
    *,
    tracker: dict[str, Any],
    posts: list[dict[str, Any]],
    analysis_version: str = "v1",
    window_days: int = 7,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_days = max(1, int(window_days or 7))
    window_start = now - timedelta(days=window_days)
    previous_start = window_start - timedelta(days=window_days)
    tracker_platforms = set(tracker.get("platforms") or [])
    included_keywords = _strip_terms(tracker.get("included_keywords") or [])
    excluded_keywords = _strip_terms(tracker.get("excluded_keywords") or [])

    filtered_posts = [
        post
        for post in posts
        if _post_matches_tracker_platforms(post, tracker_platforms)
    ]
    candidates = [
        _build_tracker_candidate(post, included_keywords, excluded_keywords)
        for post in filtered_posts
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    candidates.sort(key=_tracker_candidate_rank_key, reverse=True)
    candidates = _dedupe_tracker_candidates(candidates)

    current_candidates = [
        item for item in candidates if _in_window(item.get("publish_time"), window_start, now)
    ]
    previous_candidates = [
        item
        for item in candidates
        if _in_window(item.get("publish_time"), previous_start, window_start)
    ]
    if not current_candidates and candidates:
        current_candidates = candidates[: min(len(candidates), 200)]

    metrics = _build_tracker_metrics(
        tracker=tracker,
        candidates=candidates,
        current_candidates=current_candidates,
        previous_candidates=previous_candidates,
        window_start=window_start,
        now=now,
        window_days=window_days,
    )
    legacy_analysis = build_tracker_analysis(tracker=tracker, candidates=candidates[:50])
    metrics["legacy_analysis"] = legacy_analysis
    metrics["legacy_snapshot"] = _build_legacy_snapshot_payload(
        tracker=tracker,
        analysis=legacy_analysis,
        candidates=candidates,
    )
    metrics["run"] = {
        "tracker_id": tracker["id"],
        "status": "completed",
        "analysis_version": analysis_version,
        "window_days": window_days,
        "started_at": now,
        "completed_at": now,
        "sample_count": len(current_candidates),
        "candidate_count": len(candidates),
        "sample_quality_score": metrics["overview"]["sample_quality_score"],
        "trend_strength_score": metrics["trends"]["trend_strength_score"],
        "noise_rate": metrics["risks"]["tracker_noise_rate"],
        "decision_confidence": metrics["decisions"]["decision_confidence_score"],
        "input_summary": {
            "platforms": sorted(tracker_platforms),
            "included_keywords": included_keywords,
            "excluded_keywords": excluded_keywords,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "post_pool_size": len(filtered_posts),
        },
        "summary": {
            "status": metrics["overview"]["status"],
            "headline": metrics["decisions"]["headline"],
            "sample_quality_grade": metrics["overview"]["sample_quality_grade"],
            "trend_strength_score": metrics["trends"]["trend_strength_score"],
            "decision_confidence_score": metrics["decisions"]["decision_confidence_score"],
        },
    }
    return metrics


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


def _hit_count(hits: list[dict[str, Any]]) -> int:
    return sum(int(hit.get("count") or 0) for hit in hits)


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


def _build_tracker_metrics(
    *,
    tracker: dict[str, Any],
    candidates: list[dict[str, Any]],
    current_candidates: list[dict[str, Any]],
    previous_candidates: list[dict[str, Any]],
    window_start: datetime,
    now: datetime,
    window_days: int,
) -> dict[str, Any]:
    sample_quality = _sample_quality_metrics(
        tracker=tracker,
        candidates=current_candidates,
        all_candidates=candidates,
        window_days=window_days,
    )
    trend_metrics = _trend_metrics(
        current_candidates=current_candidates,
        previous_candidates=previous_candidates,
        window_start=window_start,
        now=now,
    )
    keyword_metrics = _keyword_metrics(
        candidates=current_candidates,
        included_keywords=_strip_terms(tracker.get("included_keywords") or []),
        excluded_keywords=_strip_terms(tracker.get("excluded_keywords") or []),
    )
    pattern_metrics = _pattern_metrics(current_candidates)
    creator_metrics = _creator_metrics(current_candidates, previous_candidates)
    risk_metrics = _risk_metrics(
        current_candidates=current_candidates,
        all_candidates=candidates,
        sample_quality=sample_quality,
        tracker_platforms=tracker.get("platforms") or [],
    )
    decision_metrics = _decision_metrics(
        sample_quality=sample_quality,
        trend_metrics=trend_metrics,
        creator_metrics=creator_metrics,
        risk_metrics=risk_metrics,
        pattern_metrics=pattern_metrics,
    )
    overview = _overview_metrics(
        tracker=tracker,
        current_candidates=current_candidates,
        trend_metrics=trend_metrics,
        creator_metrics=creator_metrics,
        sample_quality=sample_quality,
        risk_metrics=risk_metrics,
        decision_metrics=decision_metrics,
        now=now,
    )
    sample_metrics = _sample_metrics(current_candidates)

    return {
        "tracker": {
            "id": tracker["id"],
            "name": tracker.get("name"),
            "platforms": tracker.get("platforms") or [],
            "included_keywords": tracker.get("included_keywords") or [],
            "excluded_keywords": tracker.get("excluded_keywords") or [],
            "window_days": window_days,
            "tracking_mode": tracker.get("tracking_mode"),
            "updated_at": tracker.get("updated_at"),
        },
        "overview": overview,
        "trends": trend_metrics,
        "keywords": keyword_metrics,
        "patterns": pattern_metrics,
        "creators": creator_metrics,
        "samples": sample_metrics,
        "risks": risk_metrics,
        "decisions": decision_metrics,
        "meta": {
            "analysis_version": "v1",
            "generated_at": now.isoformat(),
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "post_pool_size": len(candidates),
            "current_window_candidates": len(current_candidates),
            "previous_window_candidates": len(previous_candidates),
            "sample_selection": {
                "source": "local_ranker",
                "mode": "diversified_rule_selection",
            },
        },
        "candidate_rows": current_candidates,
        "candidate_rows_all": candidates,
    }


def _build_tracker_candidate(
    post: dict[str, Any],
    included_keywords: list[str],
    excluded_keywords: list[str],
) -> dict[str, Any] | None:
    engagement = post.get("engagement_json") or {}
    title_text = _join_text(post.get("title"))
    body_text = _join_text(post.get("content"))
    context_text = _join_text(
        engagement.get("source_keyword"),
        engagement.get("tag_list"),
        engagement.get("desc"),
    )
    text = _join_text(
        title_text,
        body_text,
        context_text,
    )
    if not text.strip():
        return None
    hits = _keyword_hits(text, included_keywords)
    if not hits:
        return None
    title_hits = _keyword_hits(title_text, included_keywords)
    body_hits = _keyword_hits(body_text, included_keywords)
    context_hits = _keyword_hits(context_text, included_keywords)
    excluded_hits = _keyword_hits(text, excluded_keywords)
    excluded_title_hits = _keyword_hits(title_text, excluded_keywords)
    fingerprint = build_content_fingerprint(post)
    engagement_total = _post_engagement(post)
    unique_hit_terms = {hit["term"] for hit in hits}
    keyword_component = min(
        100.0,
        _hit_count(title_hits) * 38.0
        + _hit_count(body_hits) * 20.0
        + _hit_count(context_hits) * 14.0,
    )
    coverage_component = 0.0
    if included_keywords:
        coverage_component = len(unique_hit_terms) / len(included_keywords) * 100.0
    title_component = min(100.0, _hit_count(title_hits) * 45.0)
    pattern_component = _fingerprint_pattern_score(fingerprint)
    engagement_component = min(
        100.0,
        math.log1p(max(0, engagement_total)) / math.log1p(5000) * 100.0,
    )
    noise_penalty = min(
        55.0,
        _hit_count(excluded_hits) * 14.0 + _hit_count(excluded_title_hits) * 18.0,
    )
    specificity_bonus = min(
        8.0,
        sum(1.5 for hit in hits if len(str(hit.get("term") or "")) >= 4),
    )
    similarity_score_raw = (
        0.34 * keyword_component
        + 0.22 * coverage_component
        + 0.16 * title_component
        + 0.16 * pattern_component
        + 0.12 * engagement_component
        + specificity_bonus
        - noise_penalty
    )
    similarity_score = round(max(0.0, min(100.0, similarity_score_raw)), 2)
    candidate_level = _candidate_level(similarity_score)
    is_hot = engagement_total >= 100
    if noise_penalty >= 45 and candidate_level == "L3" and not is_hot:
        return None
    if candidate_level == "L3" and not is_hot and similarity_score < 35:
        return None
    return {
        "platform": post["platform"],
        "platform_post_id": post["platform_post_id"],
        "author_id": post.get("author_hash"),
        "author_name": _author_name_from_engagement(engagement),
        "title": post.get("title") or post.get("content") or post["platform_post_id"],
        "url": post.get("url"),
        "publish_time": post.get("publish_time"),
        "candidate_level": candidate_level,
        "similarity_score": similarity_score,
        "engagement_total": engagement_total,
        "is_hot": is_hot,
        "matched_keywords": hits,
        "excluded_hits": excluded_hits,
        "fingerprint": fingerprint,
        "engagement": engagement,
        "evidence": {
            "source": "local_analysis",
            "snippets": [hit["context"] for hit in hits[:5]],
            "excluded_snippets": [hit["context"] for hit in excluded_hits[:3]],
            "pattern_summary": fingerprint.get("summary"),
            "score_components": {
                "keyword": round(keyword_component, 2),
                "coverage": round(coverage_component, 2),
                "title": round(title_component, 2),
                "pattern": round(pattern_component, 2),
                "engagement": round(engagement_component, 2),
                "noise_penalty": round(noise_penalty, 2),
            },
        },
    }


def _dedupe_tracker_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (
            str(candidate.get("platform") or ""),
            str(candidate.get("platform_post_id") or ""),
        )
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        rows.append(candidate)
    return rows


def _author_name_from_engagement(engagement: dict[str, Any]) -> str | None:
    for key in ("nickname", "author_name", "user_name", "display_name"):
        value = str(engagement.get(key) or "").strip()
        if value:
            return value
    user = engagement.get("user")
    if isinstance(user, dict):
        value = str(user.get("nickname") or user.get("name") or "").strip()
        if value:
            return value
    return None


def _sample_quality_metrics(
    *,
    tracker: dict[str, Any],
    candidates: list[dict[str, Any]],
    all_candidates: list[dict[str, Any]],
    window_days: int,
) -> dict[str, Any]:
    content_count_7d = len(candidates)
    creator_count_7d = len({item.get("author_id") for item in candidates if item.get("author_id")})
    platform_count = len({item["platform"] for item in candidates})
    expected_platforms = len(set(tracker.get("platforms") or [])) or 1
    time_buckets = set()
    for item in candidates:
        publish_time = item.get("publish_time")
        if isinstance(publish_time, datetime):
            time_buckets.add(publish_time.date().isoformat())
    time_continuity = len(time_buckets) / max(1, min(window_days, 7))
    snapshot_coverage = len(
        [item for item in candidates if item.get("engagement_total", 0) > 0]
    ) / max(1, content_count_7d)
    history_baseline_ready = 1.0 if len(all_candidates) >= max(20, content_count_7d) else 0.0
    collection_success_rate = 1.0 if all_candidates else 0.0
    score = (
        0.22 * _normalize(content_count_7d, 20)
        + 0.18 * _normalize(creator_count_7d, 12)
        + 0.12 * _normalize(platform_count, expected_platforms)
        + 0.16 * _clamp01(time_continuity)
        + 0.14 * _clamp01(collection_success_rate)
        + 0.10 * _clamp01(snapshot_coverage)
        + 0.08 * _clamp01(history_baseline_ready)
    ) * 100.0
    rounded_score = round(score, 2)
    return {
        "content_count_7d": content_count_7d,
        "creator_count_7d": creator_count_7d,
        "platform_count": platform_count,
        "time_continuity": round(time_continuity, 4),
        "collection_success_rate": round(collection_success_rate, 4),
        "snapshot_coverage": round(snapshot_coverage, 4),
        "history_baseline_ready": round(history_baseline_ready, 4),
        "sample_quality_score": rounded_score,
        "sample_quality_grade": _sample_quality_grade(rounded_score),
    }


def _trend_metrics(
    *,
    current_candidates: list[dict[str, Any]],
    previous_candidates: list[dict[str, Any]],
    window_start: datetime,
    now: datetime,
) -> dict[str, Any]:
    current_content_count = len(current_candidates)
    previous_content_count = len(previous_candidates)
    current_engagement_total = sum(item["engagement_total"] for item in current_candidates)
    previous_engagement_total = sum(item["engagement_total"] for item in previous_candidates)
    current_creators = {item.get("author_id") for item in current_candidates if item.get("author_id")}
    previous_creators = {item.get("author_id") for item in previous_candidates if item.get("author_id")}
    new_creator_count = len(current_creators - previous_creators)
    previous_new_creator_proxy = max(1, len(previous_creators))
    current_viral_ratio = len([item for item in current_candidates if item.get("is_hot")]) / max(1, current_content_count)
    previous_viral_ratio = len([item for item in previous_candidates if item.get("is_hot")]) / max(1, previous_content_count)

    content_growth_rate = _growth_rate(current_content_count, previous_content_count)
    engagement_growth_rate = _growth_rate(current_engagement_total, previous_engagement_total)
    new_creator_growth_rate = _growth_rate(new_creator_count, previous_new_creator_proxy)
    viral_ratio_change = current_viral_ratio - previous_viral_ratio
    trend_strength_score = round(
        (
            0.35 * _growth_to_score(content_growth_rate)
            + 0.35 * _growth_to_score(engagement_growth_rate)
            + 0.20 * _growth_to_score(new_creator_growth_rate)
            + 0.10 * _ratio_to_score(viral_ratio_change)
        )
        * 100.0,
        2,
    )

    content_series = _build_daily_series(current_candidates, window_start, now, "count")
    engagement_series = _build_daily_series(current_candidates, window_start, now, "engagement")
    creator_series = _build_daily_series(current_candidates, window_start, now, "creators")
    platform_counts = Counter(item["platform"] for item in current_candidates)
    top_platform_count = platform_counts.most_common(1)[0][1] if platform_counts else 0
    platform_concentration = round(top_platform_count / max(1, current_content_count), 4)
    return {
        "current_window_content_count": current_content_count,
        "previous_window_content_count": previous_content_count,
        "current_window_engagement_total": current_engagement_total,
        "previous_window_engagement_total": previous_engagement_total,
        "new_creator_count": new_creator_count,
        "content_growth_rate": round(content_growth_rate, 4),
        "engagement_growth_rate": round(engagement_growth_rate, 4),
        "new_creator_growth_rate": round(new_creator_growth_rate, 4),
        "current_viral_ratio": round(current_viral_ratio, 4),
        "viral_ratio_change": round(viral_ratio_change, 4),
        "trend_strength_score": trend_strength_score,
        "platform_concentration": platform_concentration,
        "content_series": content_series,
        "engagement_series": engagement_series,
        "creator_series": creator_series,
        "platform_distribution": dict(platform_counts),
    }


def _keyword_metrics(
    *,
    candidates: list[dict[str, Any]],
    included_keywords: list[str],
    excluded_keywords: list[str],
) -> dict[str, Any]:
    stats: dict[str, dict[str, Any]] = {}
    first_seen_terms: set[str] = set()
    for keyword in included_keywords + excluded_keywords:
        first_seen_terms.add(keyword)
    for candidate in candidates:
        matched_terms = {hit["term"] for hit in candidate.get("matched_keywords") or []}
        for term in matched_terms:
            bucket = stats.setdefault(
                term,
                {
                    "keyword": term,
                    "type": "included" if term in included_keywords else "expanded",
                    "hit_content_count": 0,
                    "creator_ids": set(),
                    "similarity_sum": 0.0,
                    "engagement_sum": 0,
                    "viral_hits": 0,
                    "noise_hits": 0,
                },
            )
            bucket["hit_content_count"] += 1
            if candidate.get("author_id"):
                bucket["creator_ids"].add(candidate["author_id"])
            bucket["similarity_sum"] += float(candidate.get("similarity_score") or 0.0)
            bucket["engagement_sum"] += int(candidate.get("engagement_total") or 0)
            if candidate.get("is_hot"):
                bucket["viral_hits"] += 1
            if candidate.get("candidate_level") == "L3":
                bucket["noise_hits"] += 1
    rows = []
    max_hits = max((value["hit_content_count"] for value in stats.values()), default=1)
    max_engagement = max((value["engagement_sum"] for value in stats.values()), default=1)
    for bucket in stats.values():
        hit_content_count = bucket["hit_content_count"]
        avg_similarity = bucket["similarity_sum"] / max(1, hit_content_count)
        avg_engagement = bucket["engagement_sum"] / max(1, hit_content_count)
        viral_rate = bucket["viral_hits"] / max(1, hit_content_count)
        noise_rate = bucket["noise_hits"] / max(1, hit_content_count)
        keyword_value_score = (
            0.20 * _normalize(hit_content_count, max_hits)
            + 0.25 * _normalize(avg_similarity, 100)
            + 0.20 * _normalize(avg_engagement, max_engagement)
            + 0.20 * _clamp01(viral_rate)
            + 0.15 * _normalize(hit_content_count, max_hits)
            - 0.25 * _clamp01(noise_rate)
        ) * 100.0
        rows.append(
            {
                "keyword": bucket["keyword"],
                "type": bucket["type"],
                "hit_content_count": hit_content_count,
                "hit_creator_count": len(bucket["creator_ids"]),
                "avg_similarity": round(avg_similarity, 2),
                "avg_engagement": round(avg_engagement, 2),
                "viral_rate": round(viral_rate, 4),
                "noise_rate": round(noise_rate, 4),
                "growth_rate": 0.0,
                "keyword_value_score": round(keyword_value_score, 2),
                "recommended_action": _keyword_action(bucket["type"], noise_rate, keyword_value_score),
            }
        )
    rows.sort(key=lambda item: (item["keyword_value_score"], item["avg_engagement"]), reverse=True)
    protected_tracker_terms = {_keyword_identity(item) for item in included_keywords}
    high_value_rows = [
        item
        for item in rows
        if item["keyword_value_score"] >= KEYWORD_HIGH_VALUE_MIN_SCORE
        and item["noise_rate"] < KEYWORD_HIGH_VALUE_MAX_NOISE_RATE
    ][:10]
    high_value_terms = {_keyword_identity(item["keyword"]) for item in high_value_rows}
    noise_rows = [
        item
        for item in sorted(
            rows,
            key=lambda item: (item["noise_rate"], item["hit_content_count"]),
            reverse=True,
        )
        if item["noise_rate"] >= KEYWORD_NOISE_MIN_RATE
        and _keyword_identity(item["keyword"]) not in high_value_terms
        and _keyword_identity(item["keyword"]) not in protected_tracker_terms
    ][:10]
    noise_terms = {_keyword_identity(item["keyword"]) for item in noise_rows}
    recommended_include_keywords = [
        item["keyword"]
        for item in rows
        if item["type"] == "expanded"
        and item["keyword_value_score"] >= KEYWORD_HIGH_VALUE_MIN_SCORE
        and item["noise_rate"] < KEYWORD_HIGH_VALUE_MAX_NOISE_RATE
        and _keyword_identity(item["keyword"]) not in noise_terms
        and _keyword_identity(item["keyword"]) not in high_value_terms
        and _keyword_identity(item["keyword"]) not in protected_tracker_terms
    ][:10]
    protected_terms = protected_tracker_terms | high_value_terms | {
        _keyword_identity(item) for item in recommended_include_keywords
    }
    recommended_exclude_keywords = [
        item["keyword"]
        for item in rows
        if item["type"] == "expanded"
        and item["noise_rate"] >= KEYWORD_EXCLUDE_MIN_RATE
        and _keyword_identity(item["keyword"]) not in protected_terms
    ][:10]
    return {
        "keyword_rows": rows,
        "high_value_keywords": high_value_rows,
        "noise_keywords": noise_rows,
        "recommended_include_keywords": recommended_include_keywords,
        "recommended_exclude_keywords": recommended_exclude_keywords,
    }


def _pattern_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    content_type_counts = Counter()
    audience_counts = Counter()
    pain_counts = Counter()
    intent_counts = Counter()
    cluster_map: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        fingerprint = candidate.get("fingerprint") or {}
        content_type = str(fingerprint.get("content_type") or "unknown")
        audience = str(fingerprint.get("audience") or "unknown")
        pain_point = str(fingerprint.get("pain_point") or "unknown")
        intent = str(fingerprint.get("conversion_intent") or "unknown")
        topic = str(fingerprint.get("topic") or "unknown")
        content_type_counts[content_type] += 1
        audience_counts[audience] += 1
        pain_counts[pain_point] += 1
        intent_counts[intent] += 1
        cluster_key = f"{content_type}|{audience}|{intent}"
        bucket = cluster_map.setdefault(
            cluster_key,
            {
                "cluster_key": cluster_key,
                "content_type": content_type,
                "audience": audience,
                "conversion_intent": intent,
                "topic": topic,
                "sample_count": 0,
                "engagement_total": 0,
                "creator_ids": set(),
                "representative_sample": None,
            },
        )
        bucket["sample_count"] += 1
        bucket["engagement_total"] += candidate.get("engagement_total", 0)
        if candidate.get("author_id"):
            bucket["creator_ids"].add(candidate["author_id"])
        representative = bucket["representative_sample"]
        if representative is None or candidate["similarity_score"] > representative["similarity_score"]:
            bucket["representative_sample"] = {
                "platform": candidate["platform"],
                "platform_post_id": candidate["platform_post_id"],
                "title": candidate.get("title"),
                "similarity_score": candidate.get("similarity_score"),
            }
    clusters = []
    total_candidates = max(1, len(candidates))
    for bucket in cluster_map.values():
        pattern_spread = len(bucket["creator_ids"]) / total_candidates
        cluster_value_score = (
            0.30 * _normalize(bucket["sample_count"], total_candidates)
            + 0.25 * _normalize(bucket["engagement_total"] / max(1, bucket["sample_count"]), 500)
            + 0.20 * _normalize(len(bucket["creator_ids"]), total_candidates)
            + 0.15 * _clamp01(pattern_spread)
            + 0.10 * _normalize(bucket["sample_count"], total_candidates)
        ) * 100.0
        clusters.append(
            {
                "cluster_key": bucket["cluster_key"],
                "content_type": bucket["content_type"],
                "audience": bucket["audience"],
                "conversion_intent": bucket["conversion_intent"],
                "topic": bucket["topic"],
                "sample_count": bucket["sample_count"],
                "creator_count": len(bucket["creator_ids"]),
                "engagement_total": bucket["engagement_total"],
                "representative_sample": bucket["representative_sample"],
                "pattern_spread": round(pattern_spread, 4),
                "cluster_value_score": round(cluster_value_score, 2),
            }
        )
    clusters.sort(key=lambda item: (item["cluster_value_score"], item["sample_count"]), reverse=True)
    top3 = sum(item["sample_count"] for item in clusters[:3])
    return {
        "content_type_distribution": dict(content_type_counts),
        "audience_distribution": dict(audience_counts),
        "pain_point_distribution": dict(pain_counts),
        "conversion_intent_distribution": dict(intent_counts),
        "pattern_clusters": clusters[:12],
        "pattern_stability": round(top3 / total_candidates, 4),
        "pattern_variant_rate": round(len(clusters) / total_candidates, 4),
    }


def _creator_metrics(
    current_candidates: list[dict[str, Any]],
    previous_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    current_creator_map: dict[str, dict[str, Any]] = {}
    previous_creator_ids = {item.get("author_id") for item in previous_candidates if item.get("author_id")}
    for candidate in current_candidates:
        author_id = candidate.get("author_id")
        if not author_id:
            continue
        bucket = current_creator_map.setdefault(
            author_id,
            {
                "author_id": author_id,
                "platform": candidate["platform"],
                "post_count": 0,
                "engagement_total": 0,
                "avg_similarity_acc": 0.0,
                "titles": [],
            },
        )
        bucket["post_count"] += 1
        bucket["engagement_total"] += candidate.get("engagement_total", 0)
        bucket["avg_similarity_acc"] += candidate.get("similarity_score", 0.0)
        if candidate.get("title"):
            bucket["titles"].append(candidate["title"])
    rows = []
    for bucket in current_creator_map.values():
        rows.append(
            {
                "author_id": bucket["author_id"],
                "platform": bucket["platform"],
                "post_count": bucket["post_count"],
                "engagement_total": bucket["engagement_total"],
                "avg_similarity": round(bucket["avg_similarity_acc"] / max(1, bucket["post_count"]), 2),
                "is_new_creator": bucket["author_id"] not in previous_creator_ids,
                "sample_titles": bucket["titles"][:3],
            }
        )
    rows.sort(key=lambda item: (item["engagement_total"], item["avg_similarity"]), reverse=True)
    creator_count = len(rows)
    new_creator_count = len([item for item in rows if item["is_new_creator"]])
    repeat_creator_count = len([item for item in rows if item["post_count"] >= 2])
    top_creator_posts = sum(item["post_count"] for item in rows[:10])
    top_creator_dependency = top_creator_posts / max(1, len(current_candidates))
    new_creator_ratio = new_creator_count / max(1, creator_count)
    repeat_creator_ratio = repeat_creator_count / max(1, creator_count)
    creator_spread_score = (
        0.40 * _clamp01(new_creator_ratio)
        + 0.35 * _clamp01(repeat_creator_ratio)
        + 0.25 * (1.0 - _clamp01(top_creator_dependency))
    ) * 100.0
    return {
        "creator_count": creator_count,
        "new_creator_count": new_creator_count,
        "repeat_creator_count": repeat_creator_count,
        "new_creator_ratio": round(new_creator_ratio, 4),
        "repeat_creator_ratio": round(repeat_creator_ratio, 4),
        "top_creator_dependency": round(top_creator_dependency, 4),
        "creator_spread_score": round(creator_spread_score, 2),
        "top_creators": rows[:10],
        "emerging_creators": [item for item in rows if item["is_new_creator"]][:10],
    }


def _risk_metrics(
    *,
    current_candidates: list[dict[str, Any]],
    all_candidates: list[dict[str, Any]],
    sample_quality: dict[str, Any],
    tracker_platforms: list[str],
) -> dict[str, Any]:
    tracker_noise_rate = len(
        [item for item in current_candidates if item.get("candidate_level") == "L3"]
    ) / max(1, len(current_candidates))
    platform_counts = Counter(item["platform"] for item in current_candidates)
    top_platform_count = platform_counts.most_common(1)[0][1] if platform_counts else 0
    platform_concentration = top_platform_count / max(1, len(current_candidates))
    risk_notes = []
    if sample_quality["sample_quality_grade"] in {"low", "insufficient"}:
        risk_notes.append("sample_quality_low")
    if tracker_noise_rate >= 0.4:
        risk_notes.append("noise_high")
    if platform_concentration >= 0.75 and len(set(tracker_platforms or [])) > 1:
        risk_notes.append("platform_concentrated")
    if not all_candidates:
        risk_notes.append("no_candidates")
    return {
        "tracker_noise_rate": round(tracker_noise_rate, 4),
        "platform_concentration": round(platform_concentration, 4),
        "risk_notes": risk_notes,
        "sample_quality_grade": sample_quality["sample_quality_grade"],
        "status_constraints": {
            "can_decide_trend": sample_quality["sample_quality_grade"] not in {"low", "insufficient"},
            "noise_acceptable": tracker_noise_rate < 0.4,
        },
    }


def _decision_metrics(
    *,
    sample_quality: dict[str, Any],
    trend_metrics: dict[str, Any],
    creator_metrics: dict[str, Any],
    risk_metrics: dict[str, Any],
    pattern_metrics: dict[str, Any],
) -> dict[str, Any]:
    quality_score = sample_quality["sample_quality_score"]
    trend_score = trend_metrics["trend_strength_score"]
    creator_score = creator_metrics["creator_spread_score"]
    noise_rate = risk_metrics["tracker_noise_rate"]
    signal_consistency = _signal_consistency(trend_score, creator_score, noise_rate)
    decision_confidence = (
        0.45 * _normalize(quality_score, 100)
        + 0.20 * (1.0 - _clamp01(noise_rate))
        + 0.20 * _clamp01(sample_quality["history_baseline_ready"])
        + 0.15 * _clamp01(signal_consistency)
    ) * 100.0
    if quality_score < 40:
        conclusion_type = "collect_more"
        headline = "样本不足，优先补采"
    elif noise_rate >= 0.4:
        conclusion_type = "reduce_noise"
        headline = "噪音偏高，先调词再判断"
    elif trend_score >= 65 and creator_score >= 45:
        conclusion_type = "continue_tracking"
        headline = "趋势升温，建议继续追踪"
    elif trend_score <= 35:
        conclusion_type = "downgrade_watch"
        headline = "信号偏弱，建议降级观察"
    else:
        conclusion_type = "watch"
        headline = "趋势未完全确认，继续观察"
    actions = _recommended_actions(
        conclusion_type=conclusion_type,
        noise_rate=noise_rate,
        quality_score=quality_score,
        pattern_metrics=pattern_metrics,
        creator_metrics=creator_metrics,
    )
    return {
        "conclusion_type": conclusion_type,
        "headline": headline,
        "decision_confidence_score": round(decision_confidence, 2),
        "decision_confidence_label": _confidence_label(decision_confidence),
        "recommended_actions": actions,
        "signal_consistency": round(signal_consistency, 4),
    }


def _overview_metrics(
    *,
    tracker: dict[str, Any],
    current_candidates: list[dict[str, Any]],
    trend_metrics: dict[str, Any],
    creator_metrics: dict[str, Any],
    sample_quality: dict[str, Any],
    risk_metrics: dict[str, Any],
    decision_metrics: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    status = _tracker_status(
        quality_score=sample_quality["sample_quality_score"],
        trend_score=trend_metrics["trend_strength_score"],
        creator_spread_score=creator_metrics["creator_spread_score"],
        noise_rate=risk_metrics["tracker_noise_rate"],
    )
    current_creators = {item.get("author_id") for item in current_candidates if item.get("author_id")}
    platform_distribution = Counter(item["platform"] for item in current_candidates)
    growth_summary = {
        "content_growth_rate": trend_metrics["content_growth_rate"],
        "engagement_growth_rate": trend_metrics["engagement_growth_rate"],
        "new_creator_growth_rate": trend_metrics["new_creator_growth_rate"],
        "viral_ratio_change": trend_metrics["viral_ratio_change"],
    }
    return {
        "status": status,
        "judgement_confidence": decision_metrics["decision_confidence_label"],
        "headline": decision_metrics["headline"],
        "sample_quality_score": sample_quality["sample_quality_score"],
        "sample_quality_grade": sample_quality["sample_quality_grade"],
        "updated_at": now.isoformat(),
        "sample_size": {
            "content_count_24h": len([item for item in current_candidates if _is_recent(item.get("publish_time"), now, hours=24)]),
            "content_count_7d": len(current_candidates),
            "creator_count_7d": len(current_creators),
            "platform_count": len(platform_distribution),
        },
        "growth": growth_summary,
        "data_quality": {
            "time_continuity": sample_quality["time_continuity"],
            "snapshot_coverage": sample_quality["snapshot_coverage"],
            "history_baseline_ready": sample_quality["history_baseline_ready"],
        },
    }


def _sample_metrics(current_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [_sample_row(candidate) for candidate in current_candidates[:100]]
    return {
        "representative_samples": _representative_samples(rows, limit=10),
        "hot_samples": _hot_samples(rows, limit=10),
        "early_signal_samples": _early_signal_samples(rows, limit=10),
        "all_samples": rows,
    }


def _sample_row(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_key": _sample_key(candidate),
        "platform": candidate["platform"],
        "platform_post_id": candidate["platform_post_id"],
        "author_id": candidate.get("author_id"),
        "author_name": candidate.get("author_name"),
        "title": candidate.get("title"),
        "url": candidate.get("url"),
        "publish_time": candidate.get("publish_time"),
        "candidate_level": candidate.get("candidate_level"),
        "similarity_score": candidate.get("similarity_score"),
        "engagement_total": candidate.get("engagement_total"),
        "market_validation_status": _market_validation_status(candidate.get("engagement_total")),
        "matched_keywords": candidate.get("matched_keywords") or [],
        "fingerprint": candidate.get("fingerprint") or {},
        "evidence": candidate.get("evidence") or {},
    }


def _sample_key(item: dict[str, Any]) -> str:
    platform = str(item.get("platform") or "").strip()
    post_id = str(item.get("platform_post_id") or item.get("post_id") or "").strip()
    return f"{platform}:{post_id}" if platform and post_id else ""


def _tracker_candidate_rank_key(item: dict[str, Any]) -> tuple[float, int, int, float]:
    return (
        float(item.get("similarity_score") or 0.0),
        1 if item.get("candidate_level") == "L1" else 0,
        int(item.get("engagement_total") or 0),
        _timestamp_value(item.get("publish_time")),
    )


def _diverse_samples(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    author_counts: Counter[str] = Counter()
    pattern_counts: Counter[str] = Counter()
    platform_counts: Counter[str] = Counter()
    platform_total = len({row.get("platform") for row in rows if row.get("platform")}) or 1
    platform_cap = max(2, math.ceil(limit / platform_total) + 1)

    for row in rows:
        if len(selected) >= limit:
            break
        key = str(row.get("sample_key") or "")
        if not key or key in selected_keys:
            continue
        author_key = str(row.get("author_id") or row.get("author_name") or "")
        pattern_key = _sample_pattern_key(row)
        platform = str(row.get("platform") or "")
        if platform_counts[platform] >= platform_cap:
            continue
        if author_key and author_counts[author_key] >= 2:
            continue
        if pattern_key and pattern_counts[pattern_key] >= 3:
            continue
        selected.append(row)
        selected_keys.add(key)
        if author_key:
            author_counts[author_key] += 1
        if pattern_key:
            pattern_counts[pattern_key] += 1
        platform_counts[platform] += 1

    if len(selected) < limit:
        for row in rows:
            if len(selected) >= limit:
                break
            key = str(row.get("sample_key") or "")
            if key and key not in selected_keys:
                selected.append(row)
                selected_keys.add(key)
    return selected[:limit]


def _representative_samples(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    ranked_rows = _rank_representative_rows(rows)
    engaged_rows = [row for row in ranked_rows if _sample_engagement(row) > 0]
    pending_rows = [row for row in ranked_rows if _sample_engagement(row) <= 0]
    selected = _diverse_samples(engaged_rows, limit=limit)
    if len(selected) < limit:
        selected_keys = {str(row.get("sample_key") or "") for row in selected}
        pending_fillers = [
            _mark_pending_validation(row)
            for row in pending_rows
            if str(row.get("sample_key") or "") not in selected_keys
        ]
        selected.extend(_diverse_samples(pending_fillers, limit=limit - len(selected)))
    return selected[:limit]


def _rank_representative_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_engagement = max((_sample_engagement(row) for row in rows), default=0)
    timestamps = [
        _timestamp_value(row.get("publish_time"))
        for row in rows
        if _timestamp_value(row.get("publish_time")) > 0
    ]
    oldest = min(timestamps, default=0.0)
    newest = max(timestamps, default=0.0)
    return sorted(
        rows,
        key=lambda row: (
            _representative_rank_score(
                row,
                max_engagement=max_engagement,
                oldest_timestamp=oldest,
                newest_timestamp=newest,
            ),
            _sample_engagement(row),
            float(row.get("similarity_score") or 0.0),
        ),
        reverse=True,
    )


def _representative_rank_score(
    row: dict[str, Any],
    *,
    max_engagement: int,
    oldest_timestamp: float,
    newest_timestamp: float,
) -> float:
    similarity_score = _normalize(float(row.get("similarity_score") or 0.0), 100.0)
    engagement_score = _engagement_rank_score(_sample_engagement(row), max_engagement)
    recency_score = _recency_rank_score(
        row.get("publish_time"),
        oldest_timestamp=oldest_timestamp,
        newest_timestamp=newest_timestamp,
    )
    return round(
        (
            0.55 * similarity_score
            + 0.30 * engagement_score
            + 0.10 * recency_score
            + 0.05 * (1.0 if _sample_engagement(row) > 0 else 0.0)
        )
        * 100.0,
        4,
    )


def _engagement_rank_score(engagement_total: int, max_engagement: int) -> float:
    if max_engagement <= 0:
        return 0.0
    return _clamp01(math.log1p(max(0, engagement_total)) / math.log1p(max_engagement))


def _recency_rank_score(
    value: Any,
    *,
    oldest_timestamp: float,
    newest_timestamp: float,
) -> float:
    timestamp = _timestamp_value(value)
    if timestamp <= 0 or newest_timestamp <= oldest_timestamp:
        return 0.0
    return _clamp01((timestamp - oldest_timestamp) / (newest_timestamp - oldest_timestamp))


def _sample_engagement(row: dict[str, Any]) -> int:
    return int(row.get("engagement_total") or 0)


def _market_validation_status(value: Any) -> str:
    return "validated" if int(value or 0) > 0 else "pending_validation"


def _mark_pending_validation(row: dict[str, Any]) -> dict[str, Any]:
    marked = dict(row)
    marked["market_validation_status"] = "pending_validation"
    evidence = dict(marked.get("evidence") or {})
    evidence["sample_note"] = "low_engagement_filler"
    marked["evidence"] = evidence
    return marked


def _hot_samples(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    hot_rows = [row for row in rows if int(row.get("engagement_total") or 0) >= 100]
    hot_rows.sort(
        key=lambda item: (
            int(item.get("engagement_total") or 0),
            float(item.get("similarity_score") or 0.0),
            _timestamp_value(item.get("publish_time")),
        ),
        reverse=True,
    )
    return _diverse_samples(hot_rows, limit=limit)


def _early_signal_samples(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    early_rows = [
        row
        for row in rows
        if row.get("candidate_level") == "L1" and int(row.get("engagement_total") or 0) < 100
    ]
    if not early_rows:
        early_rows = [row for row in rows if row.get("candidate_level") == "L1"]
    early_rows.sort(
        key=lambda item: (
            float(item.get("similarity_score") or 0.0),
            _timestamp_value(item.get("publish_time")),
            -int(item.get("engagement_total") or 0),
        ),
        reverse=True,
    )
    return _diverse_samples(early_rows, limit=limit)


def _sample_pattern_key(row: dict[str, Any]) -> str:
    fingerprint = row.get("fingerprint") or {}
    return "|".join(
        str(fingerprint.get(key) or "")
        for key in ("content_type", "audience", "conversion_intent")
    )


def _build_legacy_snapshot_payload(
    *,
    tracker: dict[str, Any],
    analysis: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    keyword_distribution = {
        item["name"]: item["value"]
        for item in analysis.get("summary", {}).get("top_keywords", [])
    }
    content_type_distribution = Counter(
        (item.get("fingerprint") or {}).get("content_type") or "unknown"
        for item in candidates
    )
    publish_time_distribution = Counter()
    hot_count = 0
    for item in candidates:
        publish_time = item.get("publish_time")
        hour = getattr(publish_time, "hour", None)
        if hour is not None:
            publish_time_distribution[str(hour)] += 1
        if item.get("engagement_total", 0) >= 100:
            hot_count += 1
    return {
        "tracker_id": tracker["id"],
        "snapshot_date": date.today(),
        "platform": None,
        "keyword_distribution": keyword_distribution,
        "tag_distribution": {},
        "content_type_distribution": dict(content_type_distribution),
        "publish_time_distribution": dict(publish_time_distribution),
        "hot_post_rate": round(hot_count / max(1, len(candidates)), 4),
        "total_content_count": len(candidates),
        "evidence": {
            "hot_content": analysis.get("hot_content", []),
            "summary": analysis.get("summary", {}),
        },
    }


def _post_matches_tracker_platforms(post: dict[str, Any], tracker_platforms: set[str]) -> bool:
    if not tracker_platforms:
        return True
    return post.get("platform") in tracker_platforms


def _fingerprint_pattern_score(fingerprint: dict[str, Any]) -> float:
    score = 35.0
    if fingerprint.get("audience") and fingerprint.get("audience") != "泛家长":
        score += 20.0
    if fingerprint.get("pain_point") and fingerprint.get("pain_point") != "未明确痛点":
        score += 20.0
    if fingerprint.get("content_type"):
        score += 15.0
    if fingerprint.get("conversion_intent") and fingerprint.get("conversion_intent") != "弱转化":
        score += 10.0
    return min(100.0, score)


def _candidate_level(similarity_score: float) -> str:
    if similarity_score >= 75:
        return "L1"
    if similarity_score >= 55:
        return "L2"
    return "L3"


def _normalize(value: float, ceiling: float) -> float:
    if ceiling <= 0:
        return 0.0
    return _clamp01(float(value) / float(ceiling))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _growth_rate(current: float, previous: float) -> float:
    return (current - previous) / max(1.0, previous)


def _growth_to_score(value: float) -> float:
    return _clamp01((value + 1.0) / 2.0)


def _ratio_to_score(value: float) -> float:
    return _clamp01((value + 0.5) / 1.0)


def _sample_quality_grade(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 40:
        return "low"
    return "insufficient"


def _keyword_action(keyword_type: str, noise_rate: float, value_score: float) -> str:
    if noise_rate >= 0.5:
        return "exclude"
    if keyword_type == "expanded" and value_score >= 55:
        return "include"
    if value_score >= 45:
        return "keep"
    return "watch"


def _signal_consistency(trend_score: float, creator_score: float, noise_rate: float) -> float:
    signals = [
        trend_score >= 55,
        creator_score >= 40,
        noise_rate < 0.4,
    ]
    return sum(1 for item in signals if item) / len(signals)


def _confidence_label(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    if score >= 35:
        return "low"
    return "insufficient"


def _tracker_status(
    *,
    quality_score: float,
    trend_score: float,
    creator_spread_score: float,
    noise_rate: float,
) -> str:
    if quality_score < 40:
        return "sample_insufficient"
    if noise_rate >= 0.4:
        return "noise_high"
    if trend_score >= 65 and creator_spread_score >= 60:
        return "heating_up"
    if trend_score <= 35:
        return "declining"
    return "stable"


def _recommended_actions(
    *,
    conclusion_type: str,
    noise_rate: float,
    quality_score: float,
    pattern_metrics: dict[str, Any],
    creator_metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if quality_score < 40:
        actions.append({"action": "backfill_7d", "reason": "sample_quality_low"})
    if noise_rate >= 0.4:
        actions.append({"action": "adjust_keywords", "reason": "noise_high"})
    if conclusion_type == "continue_tracking":
        actions.append({"action": "continue_tracking", "reason": "trend_confirmed"})
    if pattern_metrics.get("pattern_variant_rate", 0) >= 0.35:
        actions.append({"action": "split_tracker", "reason": "multiple_pattern_clusters"})
    if creator_metrics.get("new_creator_ratio", 0) >= 0.3:
        actions.append({"action": "promote_creator_discovery", "reason": "creator_spread"})
    if not actions:
        actions.append({"action": "observe", "reason": "wait_for_more_signal"})
    return actions


def _build_daily_series(
    candidates: list[dict[str, Any]],
    window_start: datetime,
    now: datetime,
    series_type: str,
) -> list[dict[str, Any]]:
    buckets: dict[str, Any] = defaultdict(set if series_type == "creators" else int)
    cursor = window_start.date()
    while cursor <= now.date():
        key = cursor.isoformat()
        if series_type == "creators":
            buckets[key] = set()
        else:
            buckets[key] = 0
        cursor += timedelta(days=1)
    for item in candidates:
        publish_time = item.get("publish_time")
        if not isinstance(publish_time, datetime):
            continue
        key = publish_time.date().isoformat()
        if key not in buckets:
            continue
        if series_type == "count":
            buckets[key] += 1
        elif series_type == "engagement":
            buckets[key] += item.get("engagement_total", 0)
        elif series_type == "creators" and item.get("author_id"):
            buckets[key].add(item["author_id"])
    series = []
    for key in sorted(buckets):
        value = buckets[key]
        if isinstance(value, set):
            value = len(value)
        series.append({"date": key, "value": value})
    return series


def _in_window(value: Any, start: datetime, end: datetime) -> bool:
    if not isinstance(value, datetime):
        return False
    resolved = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return start <= resolved < end


def _timestamp_value(value: Any) -> float:
    if not isinstance(value, datetime):
        return 0.0
    resolved = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return resolved.timestamp()


def _is_recent(value: Any, now: datetime, *, hours: int) -> bool:
    if not isinstance(value, datetime):
        return False
    resolved = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return resolved >= now - timedelta(hours=hours)


def _strip_terms(values: list[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def _compact_tracker_sample_for_ai(item: dict[str, Any]) -> dict[str, Any]:
    fingerprint = item.get("fingerprint") or {}
    evidence = item.get("evidence") or {}
    return {
        "sample_key": _sample_key(item),
        "platform": item.get("platform"),
        "post_id": item.get("platform_post_id") or item.get("post_id"),
        "author": item.get("author_name") or item.get("author_id"),
        "title": str(item.get("title") or "")[:180],
        "publish_time": item.get("publish_time"),
        "candidate_level": item.get("candidate_level"),
        "similarity_score": item.get("similarity_score"),
        "engagement_total": item.get("engagement_total"),
        "matched_keywords": [
            {
                "term": hit.get("term"),
                "count": hit.get("count"),
            }
            for hit in _list_of_dicts(item.get("matched_keywords") or [])
        ][:8],
        "excluded_hits": [
            {
                "term": hit.get("term"),
                "count": hit.get("count"),
            }
            for hit in _list_of_dicts(item.get("excluded_hits") or [])
        ][:5],
        "fingerprint": {
            "content_type": fingerprint.get("content_type"),
            "audience": fingerprint.get("audience"),
            "pain_point": fingerprint.get("pain_point"),
            "conversion_intent": fingerprint.get("conversion_intent"),
            "summary": fingerprint.get("summary"),
        },
        "snippets": (evidence.get("snippets") or [])[:3],
        "excluded_snippets": (evidence.get("excluded_snippets") or [])[:2],
    }


def _selected_samples_from_ai(
    selected_items: list[dict[str, Any]],
    *,
    sample_lookup: dict[str, dict[str, Any]],
    fallback: list[dict[str, Any]],
    limit: int,
    source: str,
    minimum_engagement: int | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    enough_engaged_samples = (
        minimum_engagement is not None
        and len(
            [
                sample
                for sample in sample_lookup.values()
                if _sample_engagement(sample) >= minimum_engagement
            ]
        )
        >= limit
    )
    ordered_selected_items = selected_items
    if minimum_engagement is not None:
        ordered_selected_items = sorted(
            selected_items,
            key=lambda item: _sample_engagement(
                sample_lookup.get(str(item.get("sample_key") or ""), {})
            )
            >= int(minimum_engagement or 0),
            reverse=True,
        )
    for item in ordered_selected_items:
        sample_key = str(item.get("sample_key") or "")
        sample = sample_lookup.get(sample_key)
        if not sample or sample_key in selected_keys:
            continue
        if enough_engaged_samples and _sample_engagement(sample) < int(minimum_engagement or 0):
            continue
        selected.append(_annotate_ai_selected_sample(sample, item, source=source))
        selected_keys.add(sample_key)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for sample in fallback:
            sample_key = str(sample.get("sample_key") or _sample_key(sample))
            if sample_key and sample_key not in selected_keys:
                if enough_engaged_samples and _sample_engagement(sample) < int(minimum_engagement or 0):
                    continue
                selected.append(sample)
                selected_keys.add(sample_key)
            if len(selected) >= limit:
                break
    return selected[:limit]


def _annotate_ai_selected_sample(
    sample: dict[str, Any],
    selection: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    row = dict(sample)
    row["selection_source"] = source
    row["ai_relevance_score"] = selection.get("relevance_score")
    evidence = dict(row.get("evidence") or {})
    reason = str(selection.get("reason") or "").strip()
    if reason:
        evidence["ai_selection_reason"] = reason
    row["evidence"] = evidence
    return row


def _score_between_zero_and_hundred(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    return round(max(0.0, min(100.0, parsed)), 2)


def _apply_ai_keyword_strategy(
    analysis_bundle: dict[str, Any],
    keyword_strategy: dict[str, Any],
) -> None:
    keywords = analysis_bundle.setdefault("keywords", {})
    include_keywords = _dedupe_strings(
        _string_list(keywords.get("recommended_include_keywords"))
        + _string_list(keyword_strategy.get("recommended_include_keywords"))
    )
    exclude_keywords = _dedupe_strings(
        _string_list(keywords.get("recommended_exclude_keywords"))
        + _string_list(keyword_strategy.get("recommended_exclude_keywords"))
    )
    if include_keywords:
        keywords["recommended_include_keywords"] = include_keywords[:12]
    if exclude_keywords:
        keywords["recommended_exclude_keywords"] = exclude_keywords[:12]
    if keyword_strategy:
        keywords["ai_keyword_strategy"] = keyword_strategy
    _sanitize_keyword_recommendations(analysis_bundle)


def _apply_ai_decision_explanation(
    analysis_bundle: dict[str, Any],
    decision_explanation: dict[str, Any],
) -> None:
    if not decision_explanation:
        return
    decisions = analysis_bundle.setdefault("decisions", {})
    headline = str(decision_explanation.get("headline") or "").strip()
    if headline:
        decisions["headline"] = headline
    actions = _list_of_dicts(decisions.get("recommended_actions"))
    for action in _list_of_dicts(decision_explanation.get("recommended_actions")):
        normalized = _normalize_ai_action(action)
        if normalized["action"] and normalized not in actions:
            actions.append(normalized)
    if actions:
        decisions["recommended_actions"] = actions[:6]
    decisions["ai_explanation"] = decision_explanation
    overview = analysis_bundle.setdefault("overview", {})
    if headline:
        overview["headline"] = headline


def _apply_ai_pattern_insights(
    analysis_bundle: dict[str, Any],
    pattern_insights: dict[str, Any],
) -> None:
    if pattern_insights:
        analysis_bundle.setdefault("patterns", {})["ai_pattern_insights"] = pattern_insights


def _apply_ai_noise_diagnosis(
    analysis_bundle: dict[str, Any],
    noise_diagnosis: dict[str, Any],
) -> None:
    if not noise_diagnosis:
        return
    risks = analysis_bundle.setdefault("risks", {})
    risks["ai_noise_diagnosis"] = noise_diagnosis
    suggested_exclude = _string_list(noise_diagnosis.get("suggested_exclude_keywords"))
    if suggested_exclude:
        keywords = analysis_bundle.setdefault("keywords", {})
        keywords["recommended_exclude_keywords"] = _dedupe_strings(
            _string_list(keywords.get("recommended_exclude_keywords")) + suggested_exclude
        )[:12]
    _sanitize_keyword_recommendations(analysis_bundle)


def _apply_ai_tracker_suggestions(
    analysis_bundle: dict[str, Any],
    tracker_suggestions: dict[str, Any],
) -> None:
    if tracker_suggestions:
        analysis_bundle.setdefault("keywords", {})["ai_tracker_suggestions"] = tracker_suggestions


def _normalize_ai_action(item: dict[str, Any]) -> dict[str, str]:
    return {
        "action": str(item.get("action") or "").strip()[:80],
        "reason": str(item.get("reason") or "").strip()[:240],
    }


def _normalize_ai_pattern(
    item: dict[str, Any],
    *,
    allowed_sample_keys: set[str],
) -> dict[str, Any]:
    return {
        "name": str(item.get("name") or item.get("label") or "").strip()[:80],
        "description": str(item.get("description") or item.get("reason") or "").strip()[:360],
        "sample_keys": [
            sample_key
            for sample_key in _dedupe_strings(_string_list(item.get("sample_keys")))
            if sample_key in allowed_sample_keys
        ][:8],
    }


def _compact_metrics_dict(value: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            compact[key] = item
        elif isinstance(item, dict) and len(item) <= 12:
            compact[key] = item
        elif isinstance(item, list):
            compact[key] = item[:8]
    return compact


def _keyword_identity(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _keyword_row_identity(row: dict[str, Any]) -> str:
    return _keyword_identity(row.get("keyword"))


def _sanitize_keyword_recommendations(analysis_bundle: dict[str, Any]) -> None:
    keywords = analysis_bundle.setdefault("keywords", {})
    tracker = analysis_bundle.get("tracker") or {}
    tracker_included_terms = {
        _keyword_identity(item) for item in _string_list(tracker.get("included_keywords"))
    }

    high_value_rows = _list_of_dicts(keywords.get("high_value_keywords"))
    high_value_terms = {_keyword_row_identity(item) for item in high_value_rows}
    noise_rows = [
        item
        for item in _list_of_dicts(keywords.get("noise_keywords"))
        if _keyword_row_identity(item)
        and _keyword_row_identity(item) not in tracker_included_terms
        and _keyword_row_identity(item) not in high_value_terms
        and _float_between(item.get("noise_rate"), default=0.0) >= KEYWORD_NOISE_MIN_RATE
    ]
    noise_terms = {_keyword_row_identity(item) for item in noise_rows}

    recommended_include_keywords = [
        item
        for item in _dedupe_strings(_string_list(keywords.get("recommended_include_keywords")))
        if _keyword_identity(item)
        and _keyword_identity(item) not in noise_terms
        and _keyword_identity(item) not in tracker_included_terms
        and _keyword_identity(item) not in high_value_terms
    ][:12]
    recommended_include_terms = {_keyword_identity(item) for item in recommended_include_keywords}

    protected_terms = tracker_included_terms | high_value_terms | recommended_include_terms
    recommended_exclude_keywords = [
        item
        for item in _dedupe_strings(_string_list(keywords.get("recommended_exclude_keywords")))
        if _keyword_identity(item)
        and _keyword_identity(item) not in protected_terms
    ][:12]
    recommended_exclude_terms = {_keyword_identity(item) for item in recommended_exclude_keywords}

    keywords["noise_keywords"] = [
        item for item in noise_rows if _keyword_row_identity(item) not in recommended_include_terms
    ][:10]
    keywords["recommended_include_keywords"] = [
        item
        for item in recommended_include_keywords
        if _keyword_identity(item) not in recommended_exclude_terms
    ][:12]
    keywords["recommended_exclude_keywords"] = recommended_exclude_keywords


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        rows.append(item)
    return rows


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

from __future__ import annotations

from typing import Any

from research.ai_provider import OpenAICompatibleProvider

PROJECT_KEYWORD_TYPE_ALIASES = {
    "core": "core",
    "primary": "core",
    "expanded": "expanded",
    "secondary": "expanded",
    "synonym": "expanded",
    "platform_adapted": "expanded",
    "ai_suggested": "expanded",
    "excluded": "excluded",
    "negative": "excluded",
}


def build_keyword_expansion_prompt(input_text: str, target_platforms: list[str]) -> str:
    platforms = ", ".join(target_platforms) if target_platforms else "all supported social platforms"
    return (
        "You are helping build a social media growth intelligence keyword library.\n"
        f"Seed vertical or scene: {input_text}\n"
        f"Target platforms: {platforms}\n"
        "Return strict JSON with key suggestions. Each suggestion must include "
        "keyword, keyword_type, platform, reason, weight, and usage_flags. "
        "keyword_type must be one of primary, secondary, synonym, negative, "
        "platform_adapted.\n"
    )


async def expand_keywords_with_provider(
    provider_config: dict[str, Any], request: dict[str, Any]
) -> list[dict[str, Any]]:
    provider = OpenAICompatibleProvider(
        base_url=provider_config["base_url"],
        api_key=provider_config["api_key"],
        model=provider_config["model"],
        timeout=provider_config.get("timeout") or 60,
    )
    prompt = build_keyword_expansion_prompt(
        request["input_text"],
        request.get("target_platforms") or [],
    )
    result = await provider.complete_json(prompt=prompt)
    suggestions = result.get("suggestions") if isinstance(result, dict) else None
    if not isinstance(suggestions, list):
        raise ValueError("AI keyword expansion must return a suggestions list")
    return [normalize_ai_keyword_suggestion(item) for item in suggestions]


def normalize_ai_keyword_suggestion(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": str(item.get("keyword") or "").strip(),
        "keyword_type": str(item.get("keyword_type") or "secondary").strip(),
        "platform": item.get("platform") or None,
        "reason": item.get("reason") or "",
        "weight": float(item.get("weight") or 1.0),
        "usage_flags": item.get("usage_flags")
        or ["creator_discovery", "content_tracking", "keyword_heat"],
        "raw": item,
    }


def build_growth_project_keyword_suggestion_prompt(
    *,
    project_name: str,
    primary_goal: str,
    target_platforms: list[str],
    input_text: str,
    existing_keywords: list[str],
    count: int,
) -> str:
    platforms = ", ".join(target_platforms) if target_platforms else "all supported social platforms"
    existing = " / ".join(existing_keywords[:60]) if existing_keywords else "none"
    return (
        "You are helping a growth research analyst prepare social listening keywords.\n"
        'Return only strict JSON in the shape {"suggestions":[...]}. Do not return markdown.\n'
        f"Project name: {project_name}\n"
        f"Primary goal: {primary_goal}\n"
        f"Target platforms: {platforms}\n"
        f"User seed words or instruction: {input_text}\n"
        f"Existing project keywords to avoid repeating: {existing}\n"
        f"Target suggestion count: {count}\n"
        "Each suggestion must include keyword, keyword_type, reason, confidence.\n"
        "keyword_type must be one of core, expanded, excluded.\n"
        "Classification rules:\n"
        "- core: high-intent demand, category, brand, scenario, or comparison entry words suitable for direct collection.\n"
        "- expanded: related long-tail phrases, expressions, pain points, questions, and content-angle words.\n"
        "- excluded: noisy, misleading, spammy, recruitment, franchise, giveaway, or clearly irrelevant words.\n"
        "Quality rules:\n"
        "- Prefer Chinese keywords unless the input is mostly another language.\n"
        "- Keep keywords concise, usually 2-16 Chinese characters or a short phrase.\n"
        "- Avoid exact or near duplicates.\n"
        "- Confidence must be a number between 0 and 1.\n"
        "- Reasons should be short and concrete.\n"
    )


async def suggest_growth_project_keywords_with_provider(
    provider_config: dict[str, Any],
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    provider = OpenAICompatibleProvider(
        base_url=provider_config["base_url"],
        api_key=provider_config["api_key"],
        model=provider_config["model"],
        timeout=provider_config.get("timeout") or 60,
    )
    prompt = build_growth_project_keyword_suggestion_prompt(
        project_name=str(request.get("project_name") or "").strip() or "Growth Project",
        primary_goal=str(request.get("primary_goal") or "").strip() or "mixed_research",
        target_platforms=request.get("target_platforms") or [],
        input_text=str(request.get("input_text") or "").strip(),
        existing_keywords=request.get("existing_keywords") or [],
        count=int(request.get("count") or 24),
    )
    params = {
        "temperature": 0.2,
        "max_tokens": 1800,
        **(provider_config.get("default_params") or {}),
    }
    result = await provider.complete_json(prompt=prompt, params=params)
    suggestions = result.get("suggestions") if isinstance(result, dict) else None
    if not isinstance(suggestions, list):
        raise ValueError("AI keyword suggestion must return a suggestions list")
    existing = {_normalize_keyword_key(keyword) for keyword in request.get("existing_keywords") or []}
    seen = set(existing)
    normalized: list[dict[str, Any]] = []
    for item in suggestions:
        suggestion = normalize_growth_project_ai_keyword_suggestion(item)
        key = _normalize_keyword_key(suggestion["keyword"])
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(suggestion)
    return normalized[: max(1, int(request.get("count") or len(normalized) or 1))]


def normalize_growth_project_ai_keyword_suggestion(item: dict[str, Any]) -> dict[str, Any]:
    keyword = str(item.get("keyword") or "").strip()
    raw_type = str(item.get("keyword_type") or "expanded").strip().lower()
    keyword_type = PROJECT_KEYWORD_TYPE_ALIASES.get(raw_type, "expanded")
    confidence = item.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_value = None
    if confidence_value is not None:
        confidence_value = max(0.0, min(1.0, confidence_value))
    return {
        "keyword": keyword,
        "keyword_type": keyword_type,
        "reason": str(item.get("reason") or "").strip() or None,
        "confidence": confidence_value,
        "source": "ai",
        "raw": item,
    }


def _normalize_keyword_key(value: str) -> str:
    return str(value or "").strip().casefold()

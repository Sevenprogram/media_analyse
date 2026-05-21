from __future__ import annotations

from typing import Any

from research.ai_provider import OpenAICompatibleProvider


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

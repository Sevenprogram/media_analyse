from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


A_TIER_THRESHOLD = 75.0
B_TIER_THRESHOLD = 60.0


def tier_creator_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    score = float(candidate.get("match_score") or candidate.get("score") or 0)
    evidence = candidate.get("evidence") or candidate.get("evidence_json") or {}
    negative_flags = _negative_flags(candidate, evidence)
    evidence_types = _evidence_types(candidate, evidence)
    if negative_flags:
        tier = "C"
    elif score >= A_TIER_THRESHOLD and len(evidence_types) >= 2:
        tier = "A"
    elif score >= B_TIER_THRESHOLD:
        tier = "B"
    else:
        tier = "C"
    auto_pool_eligible = tier == "A" and not negative_flags
    return {
        "tier": tier,
        "tier_score": round(score, 4),
        "tier_reason": _tier_reason(tier, score, evidence_types, negative_flags),
        "evidence_types": sorted(evidence_types),
        "negative_flags": negative_flags,
        "auto_pool_eligible": auto_pool_eligible,
        "last_evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def tier_creator_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for candidate in candidates:
        tiering = tier_creator_candidate(candidate)
        evidence = candidate.get("evidence") or candidate.get("evidence_json") or {}
        results.append(
            {
                **candidate,
                "tier": tiering["tier"],
                "tier_score": tiering["tier_score"],
                "tier_reason": tiering["tier_reason"],
                "auto_pool_eligible": tiering["auto_pool_eligible"],
                "evidence": {
                    **evidence,
                    "tiering": tiering,
                },
            }
        )
    results.sort(key=lambda item: (item["tier"], -float(item.get("tier_score") or 0)))
    return results


def candidate_payload_with_tier(candidate: dict[str, Any]) -> dict[str, Any]:
    tiering = tier_creator_candidate(candidate)
    evidence = candidate.get("evidence") or candidate.get("evidence_json") or {}
    return {
        **candidate,
        "evidence_json": {
            **evidence,
            "tiering": tiering,
        },
        "notes": _append_note(candidate.get("notes"), f"tier={tiering['tier']}; {tiering['tier_reason']}"),
    }


def _negative_flags(candidate: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    flags = list(candidate.get("negative_flags") or evidence.get("negative_flags") or [])
    for hit in evidence.get("negative_hits") or []:
        keyword = hit.get("keyword") if isinstance(hit, dict) else hit
        if keyword:
            flags.append(f"negative_keyword:{keyword}")
    return sorted(set(str(flag) for flag in flags if flag))


def _evidence_types(candidate: dict[str, Any], evidence: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    if candidate.get("matched_tags") or candidate.get("matched_tags_json"):
        types.add("tag")
    if evidence.get("primary_hits") or evidence.get("secondary_hits"):
        types.add("keyword")
    if evidence.get("representative_posts") or candidate.get("representative_posts"):
        types.add("content")
    if candidate.get("recent_post_count_30d") or evidence.get("recent_post_count_30d"):
        types.add("activity")
    if candidate.get("follower_count") or evidence.get("profile_metrics"):
        types.add("profile")
    if candidate.get("match_score") or candidate.get("score"):
        types.add("score")
    return types


def _tier_reason(tier: str, score: float, evidence_types: set[str], negative_flags: list[str]) -> str:
    if negative_flags:
        return f"命中负面信号，降为 C 档：{', '.join(negative_flags[:3])}"
    if tier == "A":
        return f"分数 {score:.1f} 且证据类型 {len(evidence_types)} 类，建议自动监控"
    if tier == "B":
        return f"分数 {score:.1f}，证据仍需观察"
    return f"分数 {score:.1f} 或证据不足，仅保留证据"


def _append_note(current: str | None, note: str) -> str:
    if not current:
        return note
    if note in current:
        return current
    return f"{current}; {note}"

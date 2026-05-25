from __future__ import annotations

from typing import Any

from research.candidate_tiering import tier_creator_candidates


COMMERCIAL_TERMS = (
    "official",
    "brand",
    "course",
    "class",
    "school",
    "academy",
    "enroll",
    "admission",
    "consult",
    "trial",
    "private message",
    "dm",
    "wechat",
    "buy",
    "sale",
    "种草",
    "课程",
    "体验课",
    "训练营",
    "咨询",
    "招生",
    "报名",
    "机构",
    "学校",
    "老师",
    "官方",
    "品牌",
    "旗舰",
    "私信",
    "加微",
    "领取",
    "资料",
)


def recommend_suspected_competitors(
    *,
    candidates: list[dict[str, Any]],
    existing_competitors: list[dict[str, Any]] | None = None,
    limit: int = 20,
    min_score: float = 65.0,
) -> list[dict[str, Any]]:
    existing_keys = {
        (item.get("platform"), item.get("creator_id"))
        for item in existing_competitors or []
    }
    recommendations = []
    for candidate in tier_creator_candidates(candidates):
        key = (candidate.get("platform"), candidate.get("creator_id"))
        if key in existing_keys:
            continue
        score, reasons = _competitor_score(candidate)
        if score < min_score:
            continue
        recommendations.append(
            {
                "platform": candidate.get("platform"),
                "creator_id": candidate.get("creator_id"),
                "display_name": candidate.get("display_name") or candidate.get("nickname"),
                "profile_url": candidate.get("profile_url"),
                "vertical_id": candidate.get("vertical_id"),
                "recommendation_score": round(score, 2),
                "reasons": reasons,
                "source_candidate": candidate,
                "create_payload": {
                    "platform": candidate.get("platform"),
                    "creator_id": candidate.get("creator_id"),
                    "display_name": candidate.get("display_name") or candidate.get("nickname"),
                    "profile_url": candidate.get("profile_url"),
                    "vertical_id": candidate.get("vertical_id"),
                    "enabled": True,
                    "notes": "suspected_competitor_recommendation",
                },
            }
        )
    recommendations.sort(key=lambda item: item["recommendation_score"], reverse=True)
    return recommendations[:limit]


def _competitor_score(candidate: dict[str, Any]) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0
    tier = candidate.get("tier") or ((candidate.get("evidence") or {}).get("tiering") or {}).get("tier")
    if tier == "A":
        score += 30
        reasons.append("A-tier creator candidate")
    elif tier == "B":
        score += 15
        reasons.append("B-tier creator candidate")

    match_score = float(candidate.get("match_score") or candidate.get("tier_score") or 0)
    if match_score:
        score += min(30, match_score * 0.3)
        reasons.append(f"match score {match_score:.1f}")

    text = _candidate_text(candidate)
    commercial_hits = [term for term in COMMERCIAL_TERMS if term.lower() in text]
    if commercial_hits:
        score += min(25, 8 + len(commercial_hits) * 4)
        reasons.append(f"commercial signals: {', '.join(commercial_hits[:4])}")

    evidence = candidate.get("evidence") or {}
    representative_posts = evidence.get("representative_posts") or candidate.get("representative_posts") or []
    if len(representative_posts) >= 2:
        score += 8
        reasons.append("multiple representative posts")

    recent_count = int(candidate.get("recent_post_count_30d") or evidence.get("recent_post_count_30d") or 0)
    if recent_count >= 10:
        score += 7
        reasons.append(f"active posting: {recent_count}/30d")

    follower_count = int(candidate.get("follower_count") or 0)
    if follower_count >= 10000:
        score += 5
        reasons.append("meaningful follower base")

    return score, reasons


def _candidate_text(candidate: dict[str, Any]) -> str:
    evidence = candidate.get("evidence") or {}
    parts = [
        candidate.get("display_name"),
        candidate.get("nickname"),
        candidate.get("bio"),
        candidate.get("notes"),
        str(candidate.get("matched_tags") or ""),
        str(evidence.get("primary_hits") or ""),
        str(evidence.get("secondary_hits") or ""),
    ]
    for post in evidence.get("representative_posts") or []:
        if isinstance(post, dict):
            parts.extend([post.get("title"), post.get("content"), post.get("summary")])
    return " ".join(str(part or "") for part in parts).lower()

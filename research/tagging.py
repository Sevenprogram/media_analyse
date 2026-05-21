import json
from dataclasses import dataclass
from typing import Any

from research.ai_analysis import extract_chat_content, parse_json_response
from research.ai_provider import OpenAICompatibleProvider
from research.enums import TAG_SOURCE_AI, TAG_SOURCE_RULE
from research.enums import ENTITY_COMMENT, ENTITY_CREATOR, ENTITY_POST


TAG_TEXT_FIELDS = ("title", "content", "desc", "bio", "comment", "text")


@dataclass(frozen=True)
class TagCandidate:
    entity_type: str
    entity_id: str
    platform: str
    vertical_id: int
    tag_id: int
    confidence: float
    source: str
    evidence_json: dict[str, Any]
    analysis_version: str = "v1"

    def to_payload(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "platform": self.platform,
            "vertical_id": self.vertical_id,
            "tag_id": self.tag_id,
            "confidence": self.confidence,
            "source": self.source,
            "evidence_json": self.evidence_json,
            "analysis_version": self.analysis_version,
        }


class RuleTagger:
    def match_entity(
        self,
        *,
        entity: dict[str, Any],
        tag_definitions: list[dict[str, Any]],
        entity_type: str,
        entity_id: str,
        platform: str,
        analysis_version: str = "v1",
    ) -> list[TagCandidate]:
        candidates: dict[int, TagCandidate] = {}
        for tag in tag_definitions:
            candidate = self._match_tag(
                entity=entity,
                tag=tag,
                entity_type=entity_type,
                entity_id=entity_id,
                platform=platform,
                analysis_version=analysis_version,
            )
            if candidate is None:
                continue
            existing = candidates.get(candidate.tag_id)
            if existing is None or candidate.confidence > existing.confidence:
                candidates[candidate.tag_id] = candidate
        return list(candidates.values())

    def _match_tag(
        self,
        *,
        entity: dict[str, Any],
        tag: dict[str, Any],
        entity_type: str,
        entity_id: str,
        platform: str,
        analysis_version: str,
    ) -> TagCandidate | None:
        text_by_field = _entity_text_fields(entity)
        negative_terms = [*tag.get("negative_keywords", [])]
        for value in text_by_field.values():
            if _contains_any(value, negative_terms):
                return None

        terms = [*tag.get("keywords", []), *tag.get("synonyms", [])]
        evidence = []
        for field, value in text_by_field.items():
            for term in terms:
                if term and term.lower() in value.lower():
                    evidence.append(
                        {
                            "field": field,
                            "matched_term": term,
                            "matched_text": value,
                            "context": _context(value, term),
                        }
                    )
        if not evidence:
            return None

        weight = max(1, int(tag.get("weight") or 1))
        confidence = min(1.0, 0.6 + (0.2 if len(evidence) > 1 else 0.0) + min(0.2, weight / 50))
        return TagCandidate(
            entity_type=entity_type,
            entity_id=str(entity_id),
            platform=platform,
            vertical_id=int(tag["vertical_id"]),
            tag_id=int(tag["id"]),
            confidence=round(confidence, 4),
            source=TAG_SOURCE_RULE,
            evidence_json={"matches": evidence[:5], "tag_name": tag.get("tag_name")},
            analysis_version=analysis_version,
        )


class AITaggingService:
    def __init__(self, provider: OpenAICompatibleProvider):
        self.provider = provider

    async def tag_entity(
        self,
        *,
        entity: dict[str, Any],
        tag_definitions: list[dict[str, Any]],
        entity_type: str,
        entity_id: str,
        platform: str,
        analysis_version: str = "v1",
        params: dict[str, Any] | None = None,
    ) -> list[TagCandidate]:
        if not tag_definitions:
            return []
        allowed = {int(tag["id"]): tag for tag in tag_definitions}
        prompt = _build_ai_prompt(entity=entity, tag_definitions=tag_definitions)
        response = await self.provider.chat_json(
            messages=[{"role": "user", "content": prompt}],
            params=params or {"temperature": 0.1, "max_tokens": 800},
        )
        parsed = parse_json_response(extract_chat_content(response))
        items = parsed if isinstance(parsed, list) else parsed.get("tags", parsed.get("value", []))
        candidates = []
        for item in items if isinstance(items, list) else []:
            try:
                tag_id = int(item.get("tag_id"))
            except (TypeError, ValueError):
                continue
            tag = allowed.get(tag_id)
            if tag is None:
                continue
            confidence = float(item.get("confidence") or 0)
            if confidence <= 0:
                continue
            candidates.append(
                TagCandidate(
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    platform=platform,
                    vertical_id=int(tag["vertical_id"]),
                    tag_id=tag_id,
                    confidence=max(0.0, min(1.0, confidence)),
                    source=TAG_SOURCE_AI,
                    evidence_json={
                        "evidence": item.get("evidence") or "",
                        "tag_name": tag.get("tag_name"),
                    },
                    analysis_version=analysis_version,
                )
            )
        return candidates


class TaggingService:
    def __init__(self, repository, ai_provider: OpenAICompatibleProvider | None = None):
        self.repository = repository
        self.rule_tagger = RuleTagger()
        self.ai_provider = ai_provider

    async def tag_entity(
        self,
        *,
        entity: dict[str, Any],
        tag_definitions: list[dict[str, Any]],
        entity_type: str,
        entity_id: str,
        platform: str,
        analysis_version: str = "v1",
        use_ai: bool = False,
    ) -> list[dict[str, Any]]:
        candidates = self.rule_tagger.match_entity(
            entity=entity,
            tag_definitions=tag_definitions,
            entity_type=entity_type,
            entity_id=str(entity_id),
            platform=platform,
            analysis_version=analysis_version,
        )
        if use_ai and self.ai_provider is not None:
            ai_candidates = await AITaggingService(self.ai_provider).tag_entity(
                entity=entity,
                tag_definitions=tag_definitions,
                entity_type=entity_type,
                entity_id=str(entity_id),
                platform=platform,
                analysis_version=analysis_version,
            )
            candidates = _merge_candidates(candidates, ai_candidates)
        return await self.repository.bulk_upsert_entity_tags(
            [candidate.to_payload() for candidate in candidates]
        )


async def tag_research_job(
    repository,
    *,
    job_id: int | None,
    vertical_id: int | None = None,
    analysis_version: str = "v1",
    use_ai: bool = False,
) -> dict[str, Any]:
    tag_definitions = await repository.list_tag_definitions(
        vertical_id=vertical_id,
        enabled_only=True,
    )
    service = TaggingService(repository)
    posts = await repository.list_all_posts(job_id=job_id)
    comments = await repository.list_all_comments(job_id=job_id)
    authors = await repository.list_all_authors(job_id=job_id)
    tagged_posts = 0
    tagged_comments = 0
    tagged_creators = 0

    for post in posts:
        capability = await repository.get_platform_capability(post["platform"])
        if capability and (not capability["enabled"] or not capability["analysis_enabled"]):
            continue
        result = await service.tag_entity(
            entity=post,
            tag_definitions=tag_definitions,
            entity_type=ENTITY_POST,
            entity_id=post["platform_post_id"],
            platform=post["platform"],
            analysis_version=analysis_version,
            use_ai=use_ai,
        )
        tagged_posts += 1 if result else 0
        if post.get("author_hash"):
            creator_entity = {
                "title": post.get("title"),
                "content": post.get("content"),
                "engagement_json": post.get("engagement_json") or {},
            }
            result = await service.tag_entity(
                entity=creator_entity,
                tag_definitions=tag_definitions,
                entity_type=ENTITY_CREATOR,
                entity_id=post["author_hash"],
                platform=post["platform"],
                analysis_version=analysis_version,
                use_ai=False,
            )
            tagged_creators += 1 if result else 0

    for comment in comments:
        capability = await repository.get_platform_capability(comment["platform"])
        if capability and (not capability["enabled"] or not capability["analysis_enabled"]):
            continue
        result = await service.tag_entity(
            entity={"content": comment.get("content"), "comment": comment.get("content")},
            tag_definitions=tag_definitions,
            entity_type=ENTITY_COMMENT,
            entity_id=comment["platform_comment_id"],
            platform=comment["platform"],
            analysis_version=analysis_version,
            use_ai=use_ai,
        )
        tagged_comments += 1 if result else 0

    for author in authors:
        capability = await repository.get_platform_capability(author["platform"])
        if capability and (not capability["enabled"] or not capability["analysis_enabled"]):
            continue
        result = await service.tag_entity(
            entity={
                "bio": (author.get("metrics_json") or {}).get("bio"),
                "text": json.dumps(author.get("metrics_json") or {}, ensure_ascii=False),
            },
            tag_definitions=tag_definitions,
            entity_type=ENTITY_CREATOR,
            entity_id=author["author_hash"],
            platform=author["platform"],
            analysis_version=analysis_version,
            use_ai=use_ai,
        )
        tagged_creators += 1 if result else 0

    return {
        "job_id": job_id,
        "vertical_id": vertical_id,
        "analysis_version": analysis_version,
        "post_count": len(posts),
        "comment_count": len(comments),
        "author_count": len(authors),
        "tagged_posts": tagged_posts,
        "tagged_comments": tagged_comments,
        "tagged_creators": tagged_creators,
    }


def _entity_text_fields(entity: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in TAG_TEXT_FIELDS:
        value = entity.get(field)
        if value:
            result[field] = str(value)
    engagement = entity.get("engagement_json") or {}
    if isinstance(engagement, dict):
        tag_list = engagement.get("tag_list")
        if tag_list:
            result["tag_list"] = json.dumps(tag_list, ensure_ascii=False)
    return result


def _contains_any(value: str, terms: list[str]) -> bool:
    lowered = value.lower()
    return any(term and term.lower() in lowered for term in terms)


def _context(value: str, term: str, width: int = 40) -> str:
    index = value.lower().find(term.lower())
    if index < 0:
        return value[: width * 2]
    start = max(0, index - width)
    end = min(len(value), index + len(term) + width)
    return value[start:end]


def _merge_candidates(
    rule_candidates: list[TagCandidate],
    ai_candidates: list[TagCandidate],
) -> list[TagCandidate]:
    by_key = {(candidate.tag_id, candidate.source): candidate for candidate in rule_candidates}
    rule_best = {candidate.tag_id: candidate.confidence for candidate in rule_candidates}
    for candidate in ai_candidates:
        if candidate.confidence < rule_best.get(candidate.tag_id, 0):
            continue
        by_key[(candidate.tag_id, candidate.source)] = candidate
    return list(by_key.values())


def _build_ai_prompt(*, entity: dict[str, Any], tag_definitions: list[dict[str, Any]]) -> str:
    allowed = [
        {
            "tag_id": tag["id"],
            "tag_name": tag["tag_name"],
            "keywords": tag.get("keywords") or [],
            "hint": tag.get("ai_prompt_hint") or "",
        }
        for tag in tag_definitions
    ]
    return (
        "You classify a social media entity using only the allowed tags. "
        "Return JSON as {\"tags\":[{\"tag_id\": number, \"confidence\": 0-1, \"evidence\": string}]}.\n"
        f"Allowed tags: {json.dumps(allowed, ensure_ascii=False)}\n"
        f"Entity: {json.dumps(entity, ensure_ascii=False, default=str)}"
    )

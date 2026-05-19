from collections.abc import Callable
from typing import Any, Protocol

from research.normalizer import (
    normalize_weibo_author,
    normalize_weibo_comment,
    normalize_weibo_note,
    normalize_zhihu_author,
    normalize_zhihu_comment,
    normalize_zhihu_content,
)


class ResearchWriteRepository(Protocol):
    async def create_event(
        self,
        *,
        job_id: int,
        platform: str | None,
        event_type: str,
        message: str,
        stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    async def create_raw_record(
        self,
        *,
        job_id: int,
        platform: str,
        source_type: str,
        source_id: str | None,
        source_url: str | None,
        payload: dict[str, Any],
        parser_version: str = "research-v1",
    ) -> dict[str, Any]:
        ...

    async def upsert_author(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def upsert_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def upsert_comment(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class ResearchJobRunner:
    def __init__(self, repository: ResearchWriteRepository, *, author_hash_salt: str):
        if not author_hash_salt:
            raise ValueError("author_hash_salt is required")
        self.repository = repository
        self.author_hash_salt = author_hash_salt

    async def ingest_weibo_batch(
        self,
        *,
        job_id: int,
        notes: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        authors: list[dict[str, Any]],
    ) -> dict[str, int]:
        return await self._ingest_batch(
            job_id=job_id,
            platform="wb",
            posts=notes,
            comments=comments,
            authors=authors,
            post_normalizer=normalize_weibo_note,
            comment_normalizer=normalize_weibo_comment,
            author_normalizer=normalize_weibo_author,
            post_id_key="note_id",
            post_url_key="note_url",
            comment_id_key="comment_id",
            author_id_key="user_id",
        )

    async def ingest_zhihu_batch(
        self,
        *,
        job_id: int,
        contents: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        authors: list[dict[str, Any]],
    ) -> dict[str, int]:
        return await self._ingest_batch(
            job_id=job_id,
            platform="zhihu",
            posts=contents,
            comments=comments,
            authors=authors,
            post_normalizer=normalize_zhihu_content,
            comment_normalizer=normalize_zhihu_comment,
            author_normalizer=normalize_zhihu_author,
            post_id_key="content_id",
            post_url_key="content_url",
            comment_id_key="comment_id",
            author_id_key="user_id",
        )

    async def _ingest_batch(
        self,
        *,
        job_id: int,
        platform: str,
        posts: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        authors: list[dict[str, Any]],
        post_normalizer: Callable[..., dict[str, Any]],
        comment_normalizer: Callable[..., dict[str, Any]],
        author_normalizer: Callable[..., dict[str, Any]],
        post_id_key: str,
        post_url_key: str,
        comment_id_key: str,
        author_id_key: str,
    ) -> dict[str, int]:
        stats = {"posts": 0, "comments": 0, "authors": 0, "raw_records": 0}

        for author in authors:
            if author.get(author_id_key) in (None, ""):
                continue
            normalized_author = author_normalizer(
                author, job_id=job_id, salt=self.author_hash_salt
            )
            await self.repository.upsert_author(normalized_author)
            stats["authors"] += 1

        for post in posts:
            raw = await self.repository.create_raw_record(
                job_id=job_id,
                platform=platform,
                source_type="post",
                source_id=_string_or_none(post.get(post_id_key)),
                source_url=post.get(post_url_key),
                payload=post,
            )
            normalized_post = post_normalizer(post, job_id=job_id, salt=self.author_hash_salt)
            normalized_post["raw_record_id"] = raw["id"]
            await self.repository.upsert_post(normalized_post)
            stats["posts"] += 1
            stats["raw_records"] += 1

        for comment in comments:
            raw = await self.repository.create_raw_record(
                job_id=job_id,
                platform=platform,
                source_type="comment",
                source_id=_string_or_none(comment.get(comment_id_key)),
                source_url=None,
                payload=comment,
            )
            normalized_comment = comment_normalizer(
                comment, job_id=job_id, salt=self.author_hash_salt
            )
            normalized_comment["raw_record_id"] = raw["id"]
            await self.repository.upsert_comment(normalized_comment)
            stats["comments"] += 1
            stats["raw_records"] += 1

        await self.repository.create_event(
            job_id=job_id,
            platform=platform,
            event_type="ingest_batch",
            message=f"Ingested {platform} batch into research tables",
            stats=stats,
        )
        return stats


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)

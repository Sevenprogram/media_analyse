from typing import Any, Iterable

from sqlalchemy import or_, select

from database.db_session import get_session
from database.models import (
    BilibiliUpInfo,
    BilibiliVideo,
    BilibiliVideoComment,
    DouyinAweme,
    DouyinAwemeComment,
    DyCreator,
    KuaishouVideo,
    KuaishouVideoComment,
    TiebaComment,
    TiebaCreator,
    TiebaNote,
    WeiboCreator,
    WeiboNote,
    WeiboNoteComment,
    XhsCreator,
    XhsNote,
    XhsNoteComment,
    ZhihuComment,
    ZhihuContent,
    ZhihuCreator,
)
from research.repository import ResearchRepository
from research.runner import ResearchJobRunner
from research.time_window import time_window_from_job, timestamp_bounds


class ExistingPlatformBackfill:
    def __init__(self, repository: ResearchRepository, *, author_hash_salt: str):
        self.repository = repository
        self.runner = ResearchJobRunner(repository, author_hash_salt=author_hash_salt)

    async def backfill_platform(
        self,
        platform: str,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        handlers = {
            "wb": self.backfill_weibo,
            "zhihu": self.backfill_zhihu,
            "xhs": self.backfill_xhs,
            "dy": self.backfill_douyin,
            "ks": self.backfill_kuaishou,
            "bili": self.backfill_bilibili,
            "tieba": self.backfill_tieba,
        }
        handler = handlers.get(platform)
        if handler is None:
            raise ValueError(f"Unsupported research backfill platform: {platform}")
        return await handler(
            job_id=job_id,
            keywords=keywords,
            target_ids=target_ids,
            creator_ids=creator_ids,
            limit=limit,
        )

    async def backfill_weibo(
        self,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = time_window_from_job(job)

        async with get_session() as session:
            note_stmt = select(WeiboNote)
            if target_ids:
                note_stmt = note_stmt.where(WeiboNote.note_id.in_(_numeric_values(target_ids)))
            elif creator_ids:
                note_stmt = note_stmt.where(WeiboNote.user_id.in_(_text_values(creator_ids)))
            elif keywords:
                note_stmt = note_stmt.where(WeiboNote.source_keyword.in_(keywords))
            if limit:
                note_stmt = note_stmt.limit(limit)
            notes = list((await session.execute(note_stmt)).scalars().all())
            note_ids = [note.note_id for note in notes]
            user_ids = [note.user_id for note in notes if note.user_id]

            comments = []
            if note_ids:
                comment_stmt = select(WeiboNoteComment).where(WeiboNoteComment.note_id.in_(note_ids))
                comments = list((await session.execute(comment_stmt)).scalars().all())

            creators = []
            if user_ids:
                creator_stmt = select(WeiboCreator).where(WeiboCreator.user_id.in_(user_ids))
                creators = list((await session.execute(creator_stmt)).scalars().all())

        return await self.runner.ingest_weibo_batch(
            job_id=job_id,
            notes=[model_to_dict(item) for item in notes],
            comments=[model_to_dict(item) for item in comments],
            authors=[model_to_dict(item) for item in creators],
            time_window=time_window,
        )

    async def backfill_zhihu(
        self,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = time_window_from_job(job)

        async with get_session() as session:
            content_stmt = select(ZhihuContent)
            if target_ids:
                content_stmt = content_stmt.where(ZhihuContent.content_id.in_(_text_values(target_ids)))
            elif creator_ids:
                content_stmt = content_stmt.where(ZhihuContent.user_id.in_(_text_values(creator_ids)))
            elif keywords:
                content_stmt = content_stmt.where(ZhihuContent.source_keyword.in_(keywords))
            if limit:
                content_stmt = content_stmt.limit(limit)
            contents = list((await session.execute(content_stmt)).scalars().all())
            content_ids = [content.content_id for content in contents]
            user_ids = [content.user_id for content in contents if content.user_id]

            comments = []
            if content_ids:
                comment_stmt = select(ZhihuComment).where(ZhihuComment.content_id.in_(content_ids))
                comments = list((await session.execute(comment_stmt)).scalars().all())

            creators = []
            if user_ids:
                creator_stmt = select(ZhihuCreator).where(ZhihuCreator.user_id.in_(user_ids))
                creators = list((await session.execute(creator_stmt)).scalars().all())

        return await self.runner.ingest_zhihu_batch(
            job_id=job_id,
            contents=[model_to_dict(item) for item in contents],
            comments=[model_to_dict(item) for item in comments],
            authors=[model_to_dict(item) for item in creators],
            time_window=time_window,
        )

    async def backfill_xhs(
        self,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = time_window_from_job(job)

        async with get_session() as session:
            note_stmt = select(XhsNote)
            if target_ids:
                note_stmt = note_stmt.where(XhsNote.note_id.in_(_text_values(target_ids)))
            elif creator_ids:
                note_stmt = note_stmt.where(XhsNote.user_id.in_(_text_values(creator_ids)))
            elif keywords:
                note_stmt = note_stmt.where(XhsNote.source_keyword.in_(keywords))
            bounds = timestamp_bounds(time_window)
            if bounds:
                start_ts, end_ts = bounds
                note_stmt = note_stmt.where(XhsNote.time >= start_ts, XhsNote.time <= end_ts)
            if ((job or {}).get("comment_policy") or {}).get("prefer_latest_posts"):
                note_stmt = note_stmt.order_by(XhsNote.time.desc())
            if limit:
                note_stmt = note_stmt.limit(limit)
            notes = list((await session.execute(note_stmt)).scalars().all())
            note_ids = [note.note_id for note in notes]
            user_ids = [note.user_id for note in notes if note.user_id]

            comments = []
            if note_ids:
                comment_stmt = select(XhsNoteComment).where(XhsNoteComment.note_id.in_(note_ids))
                comments = list((await session.execute(comment_stmt)).scalars().all())
                user_ids.extend(comment.user_id for comment in comments if comment.user_id)

            creators = []
            if user_ids:
                creator_stmt = select(XhsCreator).where(XhsCreator.user_id.in_(set(user_ids)))
                creators = list((await session.execute(creator_stmt)).scalars().all())

        return await self.runner.ingest_xhs_batch(
            job_id=job_id,
            notes=[model_to_dict(item) for item in notes],
            comments=[model_to_dict(item) for item in comments],
            authors=[model_to_dict(item) for item in creators],
            time_window=time_window,
        )

    async def backfill_douyin(
        self,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = time_window_from_job(job)

        async with get_session() as session:
            aweme_stmt = select(DouyinAweme)
            if target_ids:
                aweme_stmt = aweme_stmt.where(DouyinAweme.aweme_id.in_(_numeric_values(target_ids)))
            elif creator_ids:
                creator_values = _text_values(creator_ids)
                aweme_stmt = aweme_stmt.where(
                    or_(
                        DouyinAweme.user_id.in_(creator_values),
                        DouyinAweme.sec_uid.in_(creator_values),
                    )
                )
            elif keywords:
                aweme_stmt = aweme_stmt.where(DouyinAweme.source_keyword.in_(keywords))
            if limit:
                aweme_stmt = aweme_stmt.limit(limit)
            awemes = list((await session.execute(aweme_stmt)).scalars().all())
            aweme_ids = [aweme.aweme_id for aweme in awemes]
            user_ids = [aweme.user_id for aweme in awemes if aweme.user_id]

            comments = []
            if aweme_ids:
                comment_stmt = select(DouyinAwemeComment).where(
                    DouyinAwemeComment.aweme_id.in_(aweme_ids)
                )
                comments = list((await session.execute(comment_stmt)).scalars().all())
                user_ids.extend(comment.user_id for comment in comments if comment.user_id)

            creators = []
            if user_ids:
                creator_stmt = select(DyCreator).where(DyCreator.user_id.in_(set(user_ids)))
                creators = list((await session.execute(creator_stmt)).scalars().all())

        return await self.runner.ingest_douyin_batch(
            job_id=job_id,
            awemes=[model_to_dict(item) for item in awemes],
            comments=[model_to_dict(item) for item in comments],
            authors=[model_to_dict(item) for item in creators],
            time_window=time_window,
        )

    async def backfill_kuaishou(
        self,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = time_window_from_job(job)

        async with get_session() as session:
            video_stmt = select(KuaishouVideo)
            if target_ids:
                video_stmt = video_stmt.where(KuaishouVideo.video_id.in_(_text_values(target_ids)))
            elif creator_ids:
                video_stmt = video_stmt.where(KuaishouVideo.user_id.in_(_text_values(creator_ids)))
            elif keywords:
                video_stmt = video_stmt.where(KuaishouVideo.source_keyword.in_(keywords))
            if limit:
                video_stmt = video_stmt.limit(limit)
            videos = list((await session.execute(video_stmt)).scalars().all())
            video_ids = [video.video_id for video in videos]

            comments = []
            if video_ids:
                comment_stmt = select(KuaishouVideoComment).where(
                    KuaishouVideoComment.video_id.in_(video_ids)
                )
                comments = list((await session.execute(comment_stmt)).scalars().all())

        authors = _dedupe_by_key(
            [model_to_dict(item) for item in [*videos, *comments]], key="user_id"
        )
        return await self.runner.ingest_kuaishou_batch(
            job_id=job_id,
            videos=[model_to_dict(item) for item in videos],
            comments=[model_to_dict(item) for item in comments],
            authors=authors,
            time_window=time_window,
        )

    async def backfill_bilibili(
        self,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = time_window_from_job(job)

        async with get_session() as session:
            video_stmt = select(BilibiliVideo)
            if target_ids:
                video_stmt = video_stmt.where(BilibiliVideo.video_id.in_(_numeric_values(target_ids)))
            elif creator_ids:
                video_stmt = video_stmt.where(BilibiliVideo.user_id.in_(_numeric_values(creator_ids)))
            elif keywords:
                video_stmt = video_stmt.where(BilibiliVideo.source_keyword.in_(keywords))
            if limit:
                video_stmt = video_stmt.limit(limit)
            videos = list((await session.execute(video_stmt)).scalars().all())
            video_ids = [video.video_id for video in videos]
            user_ids = [video.user_id for video in videos if video.user_id]

            comments = []
            if video_ids:
                comment_stmt = select(BilibiliVideoComment).where(
                    BilibiliVideoComment.video_id.in_(video_ids)
                )
                comments = list((await session.execute(comment_stmt)).scalars().all())
                user_ids.extend(comment.user_id for comment in comments if comment.user_id)

            creators = []
            if user_ids:
                creator_stmt = select(BilibiliUpInfo).where(BilibiliUpInfo.user_id.in_(set(user_ids)))
                creators = list((await session.execute(creator_stmt)).scalars().all())

        return await self.runner.ingest_bilibili_batch(
            job_id=job_id,
            videos=[model_to_dict(item) for item in videos],
            comments=[model_to_dict(item) for item in comments],
            authors=[model_to_dict(item) for item in creators],
            time_window=time_window,
        )

    async def backfill_tieba(
        self,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        target_ids: list[str] | None = None,
        creator_ids: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = time_window_from_job(job)

        async with get_session() as session:
            note_stmt = select(TiebaNote)
            if target_ids:
                note_stmt = note_stmt.where(TiebaNote.note_id.in_(_text_values(target_ids)))
            elif creator_ids:
                creator_values = _text_values(creator_ids)
                note_stmt = note_stmt.where(
                    or_(
                        TiebaNote.user_link.in_(creator_values),
                        TiebaNote.user_nickname.in_(creator_values),
                    )
                )
            elif keywords:
                note_stmt = note_stmt.where(TiebaNote.source_keyword.in_(keywords))
            if limit:
                note_stmt = note_stmt.limit(limit)
            notes = list((await session.execute(note_stmt)).scalars().all())
            note_ids = [note.note_id for note in notes]
            author_keys = {
                key
                for item in notes
                for key in (item.user_link, item.user_nickname)
                if key not in (None, "")
            }

            comments = []
            if note_ids:
                comment_stmt = select(TiebaComment).where(TiebaComment.note_id.in_(note_ids))
                comments = list((await session.execute(comment_stmt)).scalars().all())
                author_keys.update(
                    key
                    for item in comments
                    for key in (item.user_link, item.user_nickname)
                    if key not in (None, "")
                )

            creators = []
            if author_keys:
                creator_stmt = select(TiebaCreator).where(
                    or_(
                        TiebaCreator.user_id.in_(author_keys),
                        TiebaCreator.user_name.in_(author_keys),
                        TiebaCreator.nickname.in_(author_keys),
                    )
                )
                creators = list((await session.execute(creator_stmt)).scalars().all())

        return await self.runner.ingest_tieba_batch(
            job_id=job_id,
            notes=[model_to_dict(item) for item in notes],
            comments=[model_to_dict(item) for item in comments],
            authors=[model_to_dict(item) for item in creators],
            time_window=time_window,
        )


def model_to_dict(model: Any) -> dict[str, Any]:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


def _dedupe_by_key(rows: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        value = row.get(key)
        if value in (None, "") or value in seen:
            continue
        seen.add(value)
        result.append(row)
    return result


def _text_values(values: Iterable[Any] | None) -> list[str]:
    if not values:
        return []
    return [text for value in values if (text := str(value).strip())]


def _numeric_values(values: Iterable[Any] | None) -> list[int]:
    if not values:
        return []
    result: list[int] = []
    for value in values:
        text = str(value).strip()
        if text.isdigit():
            result.append(int(text))
    return result

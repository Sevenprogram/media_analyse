from typing import Any

from sqlalchemy import select

from database.db_session import get_session
from database.models import (
    WeiboCreator,
    WeiboNote,
    WeiboNoteComment,
    ZhihuComment,
    ZhihuContent,
    ZhihuCreator,
)
from research.repository import ResearchRepository
from research.runner import ResearchJobRunner
from research.time_window import TimeWindow


class ExistingPlatformBackfill:
    def __init__(self, repository: ResearchRepository, *, author_hash_salt: str):
        self.repository = repository
        self.runner = ResearchJobRunner(repository, author_hash_salt=author_hash_salt)

    async def backfill_weibo(
        self,
        *,
        job_id: int,
        keywords: list[str] | None = None,
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = TimeWindow.from_dates(job["start_date"], job["end_date"]) if job else None

        async with get_session() as session:
            note_stmt = select(WeiboNote)
            if keywords:
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
        limit: int | None = 1000,
    ) -> dict[str, int]:
        job = await self.repository.get_job(job_id)
        time_window = TimeWindow.from_dates(job["start_date"], job["end_date"]) if job else None

        async with get_session() as session:
            content_stmt = select(ZhihuContent)
            if keywords:
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


def model_to_dict(model: Any) -> dict[str, Any]:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}

from dataclasses import dataclass
from datetime import datetime, timezone
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

try:
    from media_platform.tikhub.search_controls import (
        EffectiveSearchControls,
        classify_time_range,
        effective_search_controls,
        metadata_for_item,
        search_controls_from_raw,
    )
except (ImportError, ModuleNotFoundError):
    @dataclass(frozen=True)
    class _FallbackSearchControls:
        sort_mode: str = "relevance"
        time_preset: str = "all"
        time_start: datetime | None = None
        time_end: datetime | None = None
        fill_strategy: str = "prefer_fill"
        max_extra_pages: int = 5

        @property
        def has_exact_range(self) -> bool:
            return self.time_start is not None and self.time_end is not None

    @dataclass(frozen=True)
    class EffectiveSearchControls:
        platform: str
        requested_sort_mode: str
        effective_sort_mode: str
        time_preset: str
        time_start: datetime | None
        time_end: datetime | None
        fill_strategy: str = "prefer_fill"
        max_extra_pages: int = 5
        downgraded: bool = False

        @property
        def has_exact_range(self) -> bool:
            return self.time_start is not None and self.time_end is not None

    @dataclass(frozen=True)
    class _FallbackTimeRangeClassification:
        within_requested_time_range: bool
        outside_requested_time_range: bool
        fill_reason: str

    def search_controls_from_raw(
        *,
        sort_mode: str = "relevance",
        time_preset: str = "all",
        time_start: str | datetime | None = None,
        time_end: str | datetime | None = None,
        fill_strategy: str = "prefer_fill",
        max_extra_pages: int = 5,
    ) -> _FallbackSearchControls:
        start = _parse_datetime(time_start)
        end = _parse_datetime(time_end)
        if (start is None) != (end is None):
            raise ValueError("time_start and time_end must be provided together")
        if start is not None and end is not None and start > end:
            raise ValueError("time_start must be before or equal to time_end")
        return _FallbackSearchControls(
            sort_mode=sort_mode or "relevance",
            time_preset=time_preset or "all",
            time_start=start,
            time_end=end,
            fill_strategy=fill_strategy or "prefer_fill",
            max_extra_pages=max(1, _safe_int(max_extra_pages, default=5)),
        )

    def effective_search_controls(
        platform: str,
        controls: _FallbackSearchControls,
    ) -> EffectiveSearchControls:
        requested_sort = controls.sort_mode
        if controls.has_exact_range:
            effective_sort = "latest"
        elif platform == "dy" and requested_sort not in {"relevance", "latest", "most_liked"}:
            effective_sort = "relevance"
        else:
            effective_sort = requested_sort
        return EffectiveSearchControls(
            platform=platform,
            requested_sort_mode=requested_sort,
            effective_sort_mode=effective_sort,
            time_preset=controls.time_preset,
            time_start=controls.time_start,
            time_end=controls.time_end,
            fill_strategy=controls.fill_strategy,
            max_extra_pages=controls.max_extra_pages,
            downgraded=effective_sort != requested_sort,
        )

    def classify_time_range(
        timestamp_value: Any,
        controls: EffectiveSearchControls,
    ) -> _FallbackTimeRangeClassification:
        if not controls.has_exact_range:
            return _FallbackTimeRangeClassification(True, False, "exact_match")
        timestamp = _unix_seconds(timestamp_value)
        if timestamp is None:
            return _FallbackTimeRangeClassification(False, True, "fill_to_target")
        published = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        within = controls.time_start <= published <= controls.time_end  # type: ignore[operator]
        return _FallbackTimeRangeClassification(
            within,
            not within,
            "exact_match" if within else "fill_to_target",
        )

    def metadata_for_item(
        controls: EffectiveSearchControls,
        classification: _FallbackTimeRangeClassification,
    ) -> dict[str, Any]:
        return {
            "requested_sort_mode": controls.requested_sort_mode,
            "effective_sort_mode": controls.effective_sort_mode,
            "requested_time_preset": controls.time_preset,
            "requested_time_start": controls.time_start.isoformat() if controls.time_start else None,
            "requested_time_end": controls.time_end.isoformat() if controls.time_end else None,
            "within_requested_time_range": classification.within_requested_time_range,
            "outside_requested_time_range": classification.outside_requested_time_range,
            "fill_reason": classification.fill_reason,
        }


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
        controls = controls_from_job(job, "xhs") if job_has_search_controls(job) else None
        allow_fill_fallback = should_preserve_fill_candidates(job, controls)
        candidate_limit = candidate_query_limit(limit, controls)

        async with get_session() as session:
            note_stmt = select(XhsNote)
            if target_ids:
                note_stmt = note_stmt.where(XhsNote.note_id.in_(_text_values(target_ids)))
            elif creator_ids:
                note_stmt = note_stmt.where(XhsNote.user_id.in_(_text_values(creator_ids)))
            elif keywords:
                note_stmt = note_stmt.where(XhsNote.source_keyword.in_(keywords))
            bounds = timestamp_bounds(time_window)
            if bounds and not allow_fill_fallback:
                start_ts, end_ts = bounds
                note_stmt = note_stmt.where(XhsNote.time >= start_ts, XhsNote.time <= end_ts)
            if should_order_by_latest(job, controls):
                note_stmt = note_stmt.order_by(XhsNote.time.desc())
            if candidate_limit:
                note_stmt = note_stmt.limit(candidate_limit)
            notes = list((await session.execute(note_stmt)).scalars().all())
            note_payloads = [model_to_dict(item) for item in notes]
            if controls is not None:
                note_payloads = annotate_prefer_fill_records(
                    note_payloads,
                    platform="xhs",
                    controls=controls,
                    timestamp_key="time",
                    limit=limit,
                )
            note_ids = [item["note_id"] for item in note_payloads]
            user_ids = [item.get("user_id") for item in note_payloads if item.get("user_id")]

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
            notes=note_payloads,
            comments=[model_to_dict(item) for item in comments],
            authors=[model_to_dict(item) for item in creators],
            time_window=None if allow_fill_fallback else time_window,
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
        controls = controls_from_job(job, "dy") if job_has_search_controls(job) else None
        allow_fill_fallback = should_preserve_fill_candidates(job, controls)
        candidate_limit = candidate_query_limit(limit, controls)

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
            if should_order_by_latest(job, controls):
                aweme_stmt = aweme_stmt.order_by(DouyinAweme.create_time.desc())
            if candidate_limit:
                aweme_stmt = aweme_stmt.limit(candidate_limit)
            awemes = list((await session.execute(aweme_stmt)).scalars().all())
            aweme_payloads = [model_to_dict(item) for item in awemes]
            if controls is not None:
                aweme_payloads = annotate_prefer_fill_records(
                    aweme_payloads,
                    platform="dy",
                    controls=controls,
                    timestamp_key="create_time",
                    limit=limit,
                )
            aweme_ids = [item["aweme_id"] for item in aweme_payloads]
            user_ids = [item.get("user_id") for item in aweme_payloads if item.get("user_id")]

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
            awemes=aweme_payloads,
            comments=[model_to_dict(item) for item in comments],
            authors=[model_to_dict(item) for item in creators],
            time_window=None if allow_fill_fallback else time_window,
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


SEARCH_CONTROL_POLICY_KEYS = (
    "sort_mode",
    "time_preset",
    "time_start",
    "time_end",
    "max_results_per_keyword_per_platform",
    "fill_strategy",
    "max_extra_pages",
)


def job_has_search_controls(job: dict[str, Any] | None) -> bool:
    policy = ((job or {}).get("comment_policy") or {})
    return any(policy.get(key) not in (None, "") for key in SEARCH_CONTROL_POLICY_KEYS)


def controls_from_job(job: dict[str, Any] | None, platform: str) -> EffectiveSearchControls:
    policy = ((job or {}).get("comment_policy") or {})
    controls = search_controls_from_raw(
        sort_mode=str(policy.get("sort_mode") or "relevance"),
        time_preset=str(policy.get("time_preset") or "all"),
        time_start=policy.get("time_start"),
        time_end=policy.get("time_end"),
        fill_strategy=str(policy.get("fill_strategy") or "prefer_fill"),
        max_extra_pages=_safe_int(policy.get("max_extra_pages"), default=5),
    )
    return effective_search_controls(platform, controls)


def annotate_prefer_fill_records(
    records: list[dict[str, Any]],
    *,
    platform: str,
    controls: EffectiveSearchControls,
    timestamp_key: str,
    limit: int | None,
) -> list[dict[str, Any]]:
    exact: list[dict[str, Any]] = []
    fill: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        classification = classify_time_range(item.get(timestamp_key), controls)
        item["crawl_meta"] = metadata_for_item(controls, classification)
        if classification.within_requested_time_range:
            exact.append(item)
        else:
            fill.append(item)

    target = _result_limit(limit, default=len(records))
    selected = exact[:target]
    if len(selected) < target:
        selected.extend(fill[: target - len(selected)])
    return selected


def should_preserve_fill_candidates(
    job: dict[str, Any] | None,
    controls: EffectiveSearchControls | None,
) -> bool:
    if controls is None or not job_has_search_controls(job) or not controls.has_exact_range:
        return False
    policy = ((job or {}).get("comment_policy") or {})
    return str(policy.get("fill_strategy") or "prefer_fill") == "prefer_fill"


def should_order_by_latest(
    job: dict[str, Any] | None,
    controls: EffectiveSearchControls | None,
) -> bool:
    policy = ((job or {}).get("comment_policy") or {})
    if policy.get("prefer_latest_posts"):
        return True
    return controls is not None and controls.effective_sort_mode == "latest"


def candidate_query_limit(limit: int | None, controls: EffectiveSearchControls | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    if controls is None or not controls.has_exact_range:
        return limit
    return limit * max(1, _safe_int(getattr(controls, "max_extra_pages", 5), default=5))


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


def _result_limit(value: int | None, *, default: int) -> int:
    if value is None or value <= 0:
        return max(0, default)
    return max(1, int(value))


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _unix_seconds(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        timestamp = value.timestamp()
    else:
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
    if timestamp <= 0:
        return None
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000
    return int(timestamp)

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, quote, urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import config
from api.deps.auth import require_current_user
from api.schemas import SaveDataOptionEnum
from api.routers.research import require_research_database
from media_platform.tikhub.client import TikHubClient
from media_platform.tikhub.mappers import get_mapper
from research.competitors import CompetitorService, build_competitor_composition_snapshot
from research.competitor_public_flow import (
    DEFAULT_LATEST_LIMIT,
    DEFAULT_MONITOR_INTERVAL_MINUTES,
    build_competitor_public_flow_snapshot,
    create_or_update_competitor_monitor_job,
    create_competitor_fetch_now_job,
    create_competitor_monitor_jobs,
    get_competitor_monitor_job,
)
from research.competitor_recommendations import recommend_suspected_competitors
from research.enums import CRAWL_UNIT_RETRYING, CRAWL_UNIT_SUCCEEDED
from research.repository import ResearchRepository
from research.scheduler import ResearchScheduler
from research.worker import run_worker_once
from research.schemas import CompetitorAccountCreate, CompetitorAccountUpdate, CompetitorCollectionRequest
from research.tikhub_creator_metrics import enrich_creator_metrics_from_tikhub

router = APIRouter(
    prefix="/competitors",
    tags=["competitors"],
    dependencies=[Depends(require_current_user)],
)
_fetch_now_tasks: dict[str, dict] = {}
FETCH_NOW_IMMEDIATE_RETRY_DELAY_SECONDS = 2


class CompetitorCompositionRequest(BaseModel):
    snapshot_date: str
    platform: str
    posts: list[dict] = Field(default_factory=list)
    entity_tags: list[dict] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class CompetitorCompositionRebuildRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    snapshot_date: str | None = None


class CompetitorPublicFlowRebuildRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    snapshot_date: str | None = None
    latest_limit: int = Field(default=DEFAULT_LATEST_LIMIT, ge=1, le=200)


class CompetitorMonitorSyncRequest(BaseModel):
    interval_minutes: int = Field(default=DEFAULT_MONITOR_INTERVAL_MINUTES, ge=30)
    latest_limit: int = Field(default=DEFAULT_LATEST_LIMIT, ge=1, le=200)


class CompetitorMonitorSettingsUpdateRequest(BaseModel):
    schedule_enabled: bool = True
    interval_minutes: int | None = Field(default=DEFAULT_MONITOR_INTERVAL_MINUTES, ge=30)


class CompetitorFetchNowRequest(BaseModel):
    latest_limit: int = Field(default=DEFAULT_LATEST_LIMIT, ge=1, le=200)
    days_back: int | None = Field(default=7, ge=1, le=365)
    max_attempts: int = Field(default=4, ge=1, le=10)
    execute_now: bool = True
    headless: bool = True


class CompetitorFromUrlRequest(BaseModel):
    platform: str
    profile_url: str
    monitor_type: str = Field(default="competitor", pattern="^(competitor|partner_creator)$")
    project_id: int | None = Field(default=None, ge=1)
    display_name: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    notes: str | None = None


class CompetitorFromCandidateRequest(BaseModel):
    platform: str
    creator_id: str = Field(min_length=1)
    monitor_type: str = Field(default="competitor", pattern="^(competitor|partner_creator)$")
    project_id: int | None = Field(default=None, ge=1)
    display_name: str | None = None
    profile_url: str | None = None
    vertical_id: int | None = Field(default=None, ge=1)
    notes: str | None = None


class CompetitorSampledPostsResponse(BaseModel):
    account_id: int
    date: str
    stale: bool
    timezone: str
    total: int
    rows: list[dict[str, Any]]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ranking_post_is_usable(post: dict) -> bool:
    return bool(post.get("author_verified"))


def _refresh_status_label(status: str | None) -> str:
    if status == "succeeded":
        return "成功"
    if status == "failed":
        return "失败"
    if status == "running":
        return "进行中"
    if status == "queued":
        return "排队中"
    return status or "未知"


def _diagnostic_reason_label(reason: str) -> str:
    if reason == "missing_xsec_token":
        return "缺少 xsec_token，链接不可用"
    if reason == "author_mismatch":
        return "作者归属无法核验，已过滤"
    if reason == "invalid_platform_url":
        return "帖子链接无效，已过滤"
    return "诊断通过"


def _diagnostic_level(reason: str) -> str:
    if reason == "missing_xsec_token":
        return "warn"
    if reason in {"author_mismatch", "invalid_platform_url"}:
        return "warn"
    return "info"


def _sampled_post_reason(post: dict[str, Any], *, platform: str, creator_id: str) -> str:
    if post.get("author_verified") and post.get("has_valid_url"):
        return "ok"
    if not post.get("author_verified"):
        return "author_mismatch"
    engagement = post.get("engagement_json") or {}
    if platform == "xhs" and str(engagement.get("platform_author_id") or "") == creator_id:
        if not str(engagement.get("xsec_token") or "").strip():
            return "missing_xsec_token"
    return "invalid_platform_url"


def _sampled_post_metric(post: dict[str, Any], *keys: str) -> int:
    engagement = post.get("engagement_json") or {}
    for key in keys:
        value = engagement.get(key)
        try:
            if value not in (None, ""):
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _post_source_url(*, platform: str, post_id: str, raw_url: Any) -> str:
    url = str(raw_url or "").strip()
    if url:
        return url

    clean_post_id = str(post_id or "").strip()
    if not clean_post_id:
        return ""
    encoded_id = quote(clean_post_id, safe="")
    platform_key = str(platform or "").strip().lower()
    if platform_key in {"xhs", "xiaohongshu"}:
        return f"https://www.xiaohongshu.com/explore/{encoded_id}"
    if platform_key in {"dy", "douyin"}:
        return f"https://www.douyin.com/video/{encoded_id}"
    if platform_key in {"bili", "bilibili"}:
        return f"https://www.bilibili.com/video/{encoded_id}"
    if platform_key == "zhihu":
        return f"https://www.zhihu.com/search?type=content&q={encoded_id}"
    return ""


def _ranking_row_signature(row: dict[str, Any]) -> str:
    title = " ".join(str(row.get("title") or "").split())
    publish_time = str(row.get("publish_time") or "").strip()
    if title and publish_time:
        return f"sig:{title}|{publish_time[:16]}"
    post_id = str(row.get("post_id") or "").strip()
    return f"id:{post_id}" if post_id else ""


def _ranking_row_score(row: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        1 if row.get("platform_url") else 0,
        1 if row.get("source_url") else 0,
        int(row.get("interaction_delta") or 0),
        int(row.get("interaction_total") or 0),
    )


def _dedupe_contribution_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[str, dict[str, Any]] = {}
    order_by_key: dict[str, int] = {}
    passthrough: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        key = _ranking_row_signature(row)
        if not key:
            passthrough.append({**row, "_order": index})
            continue
        existing = best_by_key.get(key)
        if existing is None:
            best_by_key[key] = {**row, "_order": index}
            order_by_key[key] = index
            continue
        if _ranking_row_score(row) > _ranking_row_score(existing):
            best_by_key[key] = {**row, "_order": order_by_key[key]}

    deduped = list(best_by_key.values()) + passthrough
    deduped.sort(key=lambda item: int(item.get("_order") or 0))
    for item in deduped:
        item.pop("_order", None)
    return deduped


def _sampled_post_sort_key(post: dict[str, Any]) -> tuple[datetime, int]:
    publish_time = post.get("publish_time")
    if isinstance(publish_time, str):
        try:
            publish_time = datetime.fromisoformat(publish_time.replace("Z", "+00:00"))
        except ValueError:
            publish_time = None
    if isinstance(publish_time, datetime):
        resolved = publish_time if publish_time.tzinfo else publish_time.replace(tzinfo=timezone.utc)
    else:
        resolved = datetime.min.replace(tzinfo=timezone.utc)
    return resolved, int(post.get("delta_total") or 0)


def _refresh_status_label(status: str | None) -> str:
    if status == "succeeded":
        return "成功"
    if status == "failed":
        return "失败"
    if status == "running":
        return "进行中"
    if status == "queued":
        return "排队中"
    return status or "未知"


def _diagnostic_reason_label(reason: str) -> str:
    if reason == "missing_xsec_token":
        return "缺少 xsec_token，链接不可用"
    if reason == "author_mismatch":
        return "作者归属无法核验，已过滤"
    if reason == "invalid_platform_url":
        return "帖子链接无效，已过滤"
    return "诊断通过"


async def _latest_competitor_refresh(repository: ResearchRepository, competitor_id: int) -> dict[str, str | None]:
    runs = await repository.list_collection_runs(
        target_type="competitor",
        target_id=competitor_id,
        run_type="competitor_monitor",
        limit=20,
    )
    for run in runs:
        if run.get("mode") != "collect_and_refresh":
            continue
        refresh_at = run.get("completed_at") or run.get("started_at")
        if refresh_at is None:
            continue
        return {
            "last_refresh_at": refresh_at,
            "last_refresh_status": run.get("status"),
        }
    return {"last_refresh_at": None, "last_refresh_status": None}


def _summary_int(summary: dict[str, Any], key: str) -> int:
    try:
        return int(summary.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _xhs_token_backfill_summary(run: dict[str, Any] | None) -> dict[str, Any]:
    summary = (run or {}).get("summary") or {}
    backfill = summary.get("xhs_token_backfill") or {}
    return backfill if isinstance(backfill, dict) else {}


def _xhs_token_backfill_last_error(backfill: dict[str, Any]) -> str:
    last_error = str(backfill.get("last_error") or "").strip()
    if last_error:
        return last_error
    errors = backfill.get("errors") or []
    if isinstance(errors, list) and errors:
        first = errors[0] if isinstance(errors[0], dict) else {}
        return str(first.get("message") or first.get("type") or "").strip()
    return ""


def _build_refresh_diagnostics_payload(
    *,
    competitor_id: int,
    target_date: date,
    stale: bool,
    runs: list[dict[str, Any]],
    latest_refresh: dict[str, str | None],
    diagnostics: dict[str, Any],
    displayed_rows: int,
) -> dict[str, Any]:
    stats = diagnostics["stats"]
    entries: list[dict[str, Any]] = []
    latest_run = next((run for run in runs if run.get("mode") == "collect_and_refresh"), None)
    if latest_run is not None:
        request_payload = latest_run.get("request_payload") or {}
        days_back = request_payload.get("days_back")
        latest_limit = request_payload.get("latest_limit")
        window_text = f"近 {days_back} 天" if days_back else "最近内容"
        limit_text = f"，上限 {latest_limit} 条" if latest_limit else ""
        entries.append(
            {
                "id": f"run-{latest_run['id']}",
                "timestamp": latest_run.get("completed_at")
                or latest_run.get("started_at")
                or latest_run.get("created_at"),
                "level": "success" if latest_run.get("status") == "succeeded" else "warn",
                "message": (
                    f"最近一次刷新{_refresh_status_label(latest_run.get('status'))}，"
                    f"采集窗口：{window_text}{limit_text}。"
                ),
            }
        )
        backfill = _xhs_token_backfill_summary(latest_run)
        backfill_failed = _summary_int(backfill, "failed")
        backfill_attempted = _summary_int(backfill, "attempted")
        if backfill_failed:
            last_error = _xhs_token_backfill_last_error(backfill)
            detail = f"；最近错误：{last_error}" if last_error else ""
            entries.append(
                {
                    "id": "diag-token-backfill",
                    "timestamp": latest_run.get("completed_at")
                    or latest_run.get("started_at")
                    or latest_run.get("created_at"),
                    "level": "warn",
                    "message": (
                        f"xsec_token 回填失败 {backfill_failed}/{backfill_attempted} 条；"
                        "已保留帖子并降级展示，链接会在后续补全后恢复。"
                        f"{detail}"
                    ),
                }
            )

    entries.append(
        {
            "id": "diag-matched",
            "timestamp": latest_refresh.get("last_refresh_at"),
            "level": "info",
            "message": (
                f"当前匹配到 {stats['raw_matched_posts']} 条候选帖子，"
                f"作者归属核验通过 {stats['author_verified_posts']} 条。"
            ),
        }
    )
    if stats["author_mismatch_posts"]:
        entries.append(
            {
                "id": "diag-mismatch",
                "timestamp": latest_refresh.get("last_refresh_at"),
                "level": "warn",
                "message": (
                    f"{stats['author_mismatch_posts']} 条帖子作者归属无法核验，"
                    "已从贡献榜过滤。"
                ),
            }
        )
    if stats["missing_token_posts"]:
        entries.append(
            {
                "id": "diag-token",
                "timestamp": latest_refresh.get("last_refresh_at"),
                "level": "warn",
                "message": (
                    f"{stats['missing_token_posts']} 条帖子缺少 xsec_token，"
                    "链接暂不可跳转，已在贡献榜降级展示并等待回填。"
                ),
            }
        )
    elif stats["invalid_url_posts"]:
        entries.append(
            {
                "id": "diag-invalid-url",
                "timestamp": latest_refresh.get("last_refresh_at"),
                "level": "warn",
                "message": (
                    f"{stats['invalid_url_posts']} 条帖子链接无效，"
                    "已从贡献榜过滤。"
                ),
            }
        )
    entries.append(
        {
            "id": "diag-eligible",
            "timestamp": latest_refresh.get("last_refresh_at"),
            "level": "success" if displayed_rows else "error",
            "message": (
                f"可点击链接 {stats['eligible_posts']} 条，"
                f"当前贡献榜展示 {displayed_rows} 条。"
            ),
        }
    )
    for index, example in enumerate(diagnostics["examples"], start=1):
        entries.append(
            {
                "id": f"example-{index}",
                "timestamp": example.get("publish_time"),
                "level": _diagnostic_level(example.get("reason") or ""),
                "message": (
                    f"{example.get('title') or example.get('post_id')}: "
                    f"{_diagnostic_reason_label(example.get('reason') or '')}"
                ),
            }
        )
    for run in runs[1:5]:
        if run.get("mode") != "collect_and_refresh":
            continue
        entries.append(
            {
                "id": f"history-{run['id']}",
                "timestamp": run.get("completed_at")
                or run.get("started_at")
                or run.get("created_at"),
                "level": "success" if run.get("status") == "succeeded" else "warn",
                "message": f"历史刷新 #{run['id']}：{_refresh_status_label(run.get('status'))}。",
            }
        )

    return {
        "account_id": competitor_id,
        "date": target_date.isoformat(),
        "stale": stale,
        "timezone": "Asia/Shanghai",
        "last_refresh_at": latest_refresh.get("last_refresh_at"),
        "last_refresh_status": latest_refresh.get("last_refresh_status"),
        "stats": stats,
        "entries": entries,
    }


_XHS_IMAGE_DETAIL_PATH = "/api/v1/xiaohongshu/app_v2/get_image_note_detail"
_XHS_VIDEO_DETAIL_PATH = "/api/v1/xiaohongshu/app_v2/get_video_note_detail"
_XHS_SHARE_TOKEN_PATH = "/api/v1/xiaohongshu/web/get_note_id_and_xsec_token"


def _xhs_detail_path(note_type: str) -> str:
    return _XHS_VIDEO_DETAIL_PATH if str(note_type or "").strip() == "video" else _XHS_IMAGE_DETAIL_PATH


def _deep_first_text(payload: Any, keys: set[str]) -> str:
    for text in _deep_text_values(payload, keys):
        return text
    return ""


def _deep_text_values(payload: Any, keys: set[str]) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys:
                if isinstance(value, (dict, list)):
                    values.extend(_deep_text_values(value, keys))
                else:
                    text = str(value or "").strip()
                    if text:
                        values.append(text)
            else:
                values.extend(_deep_text_values(value, keys))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_deep_text_values(item, keys))
    return values


def _canonical_xhs_note_url(note_id: str, xsec_token: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search"


def _extract_xhs_token_from_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    values = parse_qs(parsed.query, keep_blank_values=True).get("xsec_token") or []
    return str(values[0] or "").strip() if values else ""


def _extract_xhs_share_text(payload: Any, mapped_url: str) -> str:
    candidates = _deep_text_values(
        payload,
        {
            "share_text",
            "shareText",
            "share_url",
            "shareUrl",
            "shareURL",
            "share_link",
            "shareLink",
            "short_link",
            "shortLink",
            "xhs_link",
            "xhsLink",
            "note_url",
            "noteUrl",
            "web_url",
            "webUrl",
            "target_url",
            "targetUrl",
            "href",
            "url",
            "link",
            "content",
        },
    )
    if mapped_url:
        candidates.append(mapped_url)
    scored = [(_xhs_share_text_score(candidate), candidate) for candidate in candidates]
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return ""
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _xhs_share_text_score(text: str) -> int:
    candidate = str(text or "").strip()
    if not candidate:
        return 0
    if "xhslink.com" in candidate:
        return 3
    if "xiaohongshu.com" not in candidate:
        return 0
    token = _extract_xhs_token_from_url(candidate)
    return 2 if token else 1


async def _resolve_xhs_token_via_share_text(client: TikHubClient, share_text: str) -> str:
    text = str(share_text or "").strip()
    if not text:
        return ""
    payload = await client.request("GET", _XHS_SHARE_TOKEN_PATH, params={"share_text": text})
    return _deep_first_text(payload, {"xsec_token", "xsecToken"})


def _record_xhs_backfill_error(
    errors: list[dict[str, str]],
    failed_by_type: dict[str, int],
    *,
    note_id: str,
    error_type: str,
    message: str,
) -> None:
    failed_by_type[error_type] = failed_by_type.get(error_type, 0) + 1
    if len(errors) >= 5:
        return
    compact_message = " ".join(str(message or "").split())
    errors.append(
        {
            "note_id": note_id,
            "type": error_type,
            "message": compact_message[:300],
        }
    )


async def _backfill_xhs_tokens_for_competitor(
    repository: ResearchRepository,
    *,
    competitor: dict[str, Any],
    days_back: int | None,
    max_candidates: int = 500,
    client: TikHubClient | None = None,
) -> dict[str, Any]:
    if competitor.get("platform") != "xhs":
        return {"platform": "xhs", "attempted": 0, "updated": 0, "failed": 0, "skipped": 0}
    if client is None and not (
        getattr(config, "ENABLE_TIKHUB", False) or getattr(config, "TIKHUB_API_KEY", "")
    ):
        return {"platform": "xhs", "attempted": 0, "updated": 0, "failed": 0, "skipped": 0}

    candidates = await repository.list_xhs_notes_missing_token_by_creator(
        creator_id=str(competitor["creator_id"]),
        days_back=days_back,
        limit=max_candidates,
    )
    if not candidates:
        return {"platform": "xhs", "attempted": 0, "updated": 0, "failed": 0, "skipped": 0}

    mapper = get_mapper("xhs")
    attempted = 0
    updated = 0
    failed = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    failed_by_type: dict[str, int] = {}
    owned_client = client is None
    client = client or TikHubClient()
    try:
        for candidate in candidates:
            note_id = str(candidate.get("note_id") or "").strip()
            if not note_id:
                skipped += 1
                continue
            attempted += 1
            try:
                payload = await client.request(
                    "GET",
                    _xhs_detail_path(str(candidate.get("type") or "")),
                    params={"note_id": note_id},
                )
                mapped = mapper.map_content(payload, source_keyword="")
                token = str(mapped.get("xsec_token") or "").strip()
                mapped_url = str(mapped.get("note_url") or "").strip()
                if not token:
                    token = _extract_xhs_token_from_url(mapped_url)
                if not token:
                    token = _deep_first_text(
                        payload,
                        {"xsec_token", "xsecToken", "xsec_token_value", "xsecTokenValue"},
                    )
                if not token:
                    share_text = _extract_xhs_share_text(payload, mapped_url)
                    if share_text:
                        token = await _resolve_xhs_token_via_share_text(client, share_text)
                if not token:
                    failed += 1
                    _record_xhs_backfill_error(
                        errors,
                        failed_by_type,
                        note_id=note_id,
                        error_type="MissingXsecToken",
                        message="TikHub detail response did not include xsec_token.",
                    )
                    continue
                await repository.update_xhs_note_link_data(
                    note_id=note_id,
                    xsec_token=token,
                    note_url=_canonical_xhs_note_url(note_id, token),
                )
                updated += 1
            except Exception as exc:
                failed += 1
                _record_xhs_backfill_error(
                    errors,
                    failed_by_type,
                    note_id=note_id,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
    finally:
        if owned_client:
            await client.close()

    result: dict[str, Any] = {
        "platform": "xhs",
        "attempted": attempted,
        "updated": updated,
        "failed": failed,
        "skipped": skipped,
    }
    if errors:
        result["errors"] = errors
        result["last_error"] = errors[0]["message"]
        result["failed_by_type"] = failed_by_type
    return result


async def _run_competitor_collection_task(
    collection_run_id: int,
    competitor_id: int,
    request: CompetitorCollectionRequest,
    *,
    refresh_after: bool,
) -> None:
    repository = ResearchRepository()
    try:
        competitor = await repository.get_competitor_account(competitor_id)
        if competitor is None:
            await repository.update_collection_run(
                collection_run_id,
                {
                    "status": "failed",
                    "phase": "failed",
                    "completed_at": _now_utc(),
                    "error": {"message": "Competitor not found"},
                },
            )
            return
        await repository.update_collection_run(
            collection_run_id,
            {
                "status": "running",
                "phase": "collecting",
                "started_at": _now_utc(),
            },
        )
        fetch_result = await _run_fetch_now_inline(
            competitor_id,
            CompetitorFetchNowRequest(
                latest_limit=request.latest_limit,
                days_back=request.days_back,
                execute_now=request.execute_now,
                headless=request.headless,
            ),
            refresh_snapshot=refresh_after,
        )
        job = fetch_result.get("job") or {}
        snapshot = fetch_result.get("snapshot") or {}
        backfill = fetch_result.get("xhs_token_backfill") or {}
        await repository.update_collection_run(
            collection_run_id,
            {
                "status": "succeeded",
                "phase": "completed",
                "completed_at": _now_utc(),
                "job_id": job.get("id"),
                "summary": {
                    "competitor_name": (fetch_result.get("competitor") or {}).get("display_name"),
                    "job_id": job.get("id"),
                    "job_status": job.get("status"),
                    "latest_limit": request.latest_limit,
                    "days_back": request.days_back,
                    "refreshed_snapshot": bool(snapshot),
                    "snapshot_id": snapshot.get("id"),
                    "xhs_token_backfill": backfill,
                },
                "error": {},
            },
        )
    except Exception as exc:
        await repository.update_collection_run(
            collection_run_id,
            {
                "status": "failed",
                "phase": "failed",
                "completed_at": _now_utc(),
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            },
        )


@router.post("")
async def create_competitor_account(request: CompetitorAccountCreate):
    require_research_database()
    repository = ResearchRepository()
    try:
        created = await CompetitorService(repository).create_competitor(
            await _payload_with_display_name(repository, request.model_dump(mode="python"))
        )
        if not request.display_name:
            created = await _ensure_competitor_display_name(repository, created)
        return created
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/from-url")
async def create_competitor_from_url(request: CompetitorFromUrlRequest):
    require_research_database()
    repository = ResearchRepository()
    creator_id = _creator_id_from_profile_url(request.platform, request.profile_url)
    if not creator_id:
        raise HTTPException(status_code=400, detail="Unable to parse creator id from profile_url")
    try:
        payload = await _payload_with_display_name(
            repository,
            {
                "platform": request.platform,
                "creator_id": creator_id,
                "monitor_type": request.monitor_type,
                "project_id": request.project_id,
                "display_name": request.display_name,
                "profile_url": request.profile_url,
                "vertical_id": request.vertical_id,
                "enabled": True,
                "notes": request.notes,
            },
        )
        created = await CompetitorService(repository).create_competitor(payload)
        if not request.display_name:
            created = await _ensure_competitor_display_name(repository, created)
        return created
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/from-candidate")
async def create_competitor_from_candidate(request: CompetitorFromCandidateRequest):
    require_research_database()
    repository = ResearchRepository()
    try:
        payload = await _payload_with_display_name(
            repository,
            {
                "platform": request.platform,
                "creator_id": request.creator_id,
                "monitor_type": request.monitor_type,
                "project_id": request.project_id,
                "display_name": request.display_name,
                "profile_url": request.profile_url,
                "vertical_id": request.vertical_id,
                "enabled": True,
                "notes": request.notes or "suspected_competitor_confirmed",
            },
        )
        created = await CompetitorService(repository).create_competitor(payload)
        if not request.display_name:
            created = await _ensure_competitor_display_name(repository, created)
        return created
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def list_competitor_accounts(
    enabled_only: bool = False,
    monitor_type: str | None = "competitor",
    project_id: int | None = None,
):
    require_research_database()
    if monitor_type not in {"competitor", "partner_creator", None}:
        raise HTTPException(status_code=400, detail="monitor_type must be competitor or partner_creator")
    repository = ResearchRepository()
    competitors = await repository.list_competitor_accounts(
        enabled_only=enabled_only,
        monitor_type=monitor_type,
        project_id=project_id,
    )
    return {
        "competitors": await _enrich_competitors_with_display_names(repository, competitors)
    }


@router.get("/{competitor_id}/monitor-settings")
async def get_competitor_monitor_settings(competitor_id: int):
    require_research_database()
    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    job = await get_competitor_monitor_job(repository, competitor_id)
    latest_refresh = await _latest_competitor_refresh(repository, competitor_id)
    interval_minutes = (job or {}).get("schedule_interval_minutes")
    schedule_enabled = bool((job or {}).get("schedule_enabled")) if job else True
    return {
        "competitor_id": competitor_id,
        "job_id": (job or {}).get("id"),
        "schedule_enabled": schedule_enabled,
        "interval_minutes": interval_minutes or DEFAULT_MONITOR_INTERVAL_MINUTES,
        "cadence_label": _cadence_label(schedule_enabled, interval_minutes),
        "next_run_at": (job or {}).get("next_run_at"),
        "last_scheduled_at": (job or {}).get("last_scheduled_at"),
        "last_refresh_at": latest_refresh["last_refresh_at"],
        "last_refresh_status": latest_refresh["last_refresh_status"],
    }


@router.patch("/{competitor_id}/monitor-settings")
async def update_competitor_monitor_settings(
    competitor_id: int,
    request: CompetitorMonitorSettingsUpdateRequest,
):
    require_research_database()
    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    if request.schedule_enabled and not request.interval_minutes:
        raise HTTPException(status_code=400, detail="interval_minutes is required when schedule is enabled")
    job = await create_or_update_competitor_monitor_job(
        repository,
        competitor,
        schedule_enabled=request.schedule_enabled,
        interval_minutes=request.interval_minutes,
    )
    latest_refresh = await _latest_competitor_refresh(repository, competitor_id)
    return {
        "competitor_id": competitor_id,
        "job_id": job.get("id"),
        "schedule_enabled": bool(job.get("schedule_enabled")),
        "interval_minutes": job.get("schedule_interval_minutes"),
        "cadence_label": _cadence_label(job.get("schedule_enabled"), job.get("schedule_interval_minutes")),
        "next_run_at": job.get("next_run_at"),
        "last_scheduled_at": job.get("last_scheduled_at"),
        "last_refresh_at": latest_refresh["last_refresh_at"],
        "last_refresh_status": latest_refresh["last_refresh_status"],
    }


@router.get("/recommendations")
async def list_suspected_competitor_recommendations(
    platform: str | None = None,
    vertical_id: int | None = None,
    limit: int = 20,
    min_score: float = 65.0,
):
    require_research_database()
    repository = ResearchRepository()
    candidates = await repository.list_creator_candidates(
        platform=platform,
        vertical_id=vertical_id,
    )
    enriched = []
    for candidate in candidates:
        item = dict(candidate)
        if hasattr(repository, "get_creator_profile"):
            profile = await repository.get_creator_profile(candidate["platform"], candidate["creator_id"])
            if profile:
                item.update({key: value for key, value in profile.items() if value not in (None, "")})
        enriched.append(item)
    return {
        "recommendations": recommend_suspected_competitors(
            candidates=enriched,
            existing_competitors=await repository.list_competitor_accounts(enabled_only=False),
            limit=limit,
            min_score=min_score,
        )
    }


@router.get("/public-flow/latest")
async def list_latest_competitor_public_flow_snapshots(limit: int = 50):
    require_research_database()
    return {
        "snapshots": await ResearchRepository().list_competitor_composition_snapshots(
            limit=limit,
        )
    }


@router.patch("/{competitor_id}")
async def update_competitor_account(competitor_id: int, request: CompetitorAccountUpdate):
    require_research_database()
    result = await ResearchRepository().update_competitor_account(
        competitor_id,
        request.model_dump(mode="python", exclude_unset=True),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return result


@router.post("/{competitor_id}/refresh-profile")
async def refresh_competitor_profile(competitor_id: int):
    require_research_database()
    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    display_name, diagnostics = await _lookup_competitor_display_name_with_diagnostics(repository, competitor)
    if not display_name:
        return {
            "updated": False,
            "competitor": competitor,
            "diagnostics": diagnostics,
            "message": "未获取到昵称。请确认后端进程能读取 TIKHUB_API_KEY，或手动填写昵称。",
        }
    updated = await repository.update_competitor_account(
        competitor_id,
        {"display_name": display_name},
    )
    return {
        "updated": True,
        "competitor": updated or {**competitor, "display_name": display_name},
        "diagnostics": diagnostics,
        "message": f"已更新昵称：{display_name}",
    }


@router.delete("/{competitor_id}")
async def delete_competitor_account(competitor_id: int):
    require_research_database()
    result = await ResearchRepository().update_competitor_account(
        competitor_id,
        {"enabled": False},
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return {"deleted": True, "competitor": result}


@router.get("/{competitor_id}/daily-snapshots")
async def list_competitor_daily_snapshots(competitor_id: int):
    require_research_database()
    return {
        "snapshots": await ResearchRepository().list_competitor_snapshots(competitor_id)
    }


@router.get("/{competitor_id}/composition-snapshots")
async def list_competitor_composition_snapshots(competitor_id: int):
    require_research_database()
    return {
        "snapshots": await ResearchRepository().list_competitor_composition_snapshots(
            competitor_id=competitor_id,
            limit=50,
        )
    }


@router.post("/monitor-jobs/sync")
async def sync_competitor_monitor_jobs(request: CompetitorMonitorSyncRequest):
    require_research_database()
    return await create_competitor_monitor_jobs(
        ResearchRepository(),
        interval_minutes=request.interval_minutes,
        latest_limit=request.latest_limit,
    )


@router.get("/fetch-tasks")
async def list_fetch_now_tasks(limit: int = 20):
    tasks = sorted(
        _fetch_now_tasks.values(),
        key=lambda task: task.get("started_at") or "",
        reverse=True,
    )
    return {"tasks": tasks[: max(1, min(limit, 100))]}


@router.get("/fetch-tasks/{task_id}")
async def get_fetch_now_task(task_id: str):
    task = _fetch_now_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Fetch task not found")
    return task


@router.post("/{competitor_id}/fetch-now")
async def fetch_competitor_now(competitor_id: int, request: CompetitorFetchNowRequest):
    require_research_database()
    if request.execute_now:
        task = _create_fetch_now_task(competitor_id)
        asyncio.create_task(_run_fetch_now_task(task["task_id"], competitor_id, request))
        return task
    return await _run_fetch_now_inline(competitor_id, request)


@router.post("/{competitor_id}/collect")
async def collect_competitor_content(
    competitor_id: int,
    request: CompetitorCollectionRequest,
):
    require_research_database()
    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    collection_run = await repository.create_collection_run(
        {
            "run_type": "competitor_monitor",
            "target_type": "competitor",
            "target_id": competitor_id,
            "mode": "collect_only",
            "trigger_source": request.trigger_source,
            "status": "queued",
            "phase": "queued",
            "request_payload": request.model_dump(mode="python"),
            "summary": {"competitor_name": competitor.get("display_name")},
        }
    )
    asyncio.create_task(
        _run_competitor_collection_task(
            collection_run["id"],
            competitor_id,
            request,
            refresh_after=False,
        )
    )
    return {"competitor": competitor, "run": collection_run}


@router.post("/{competitor_id}/collect-and-refresh")
async def collect_and_refresh_competitor_content(
    competitor_id: int,
    request: CompetitorCollectionRequest,
):
    require_research_database()
    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    collection_run = await repository.create_collection_run(
        {
            "run_type": "competitor_monitor",
            "target_type": "competitor",
            "target_id": competitor_id,
            "mode": "collect_and_refresh",
            "trigger_source": request.trigger_source,
            "status": "queued",
            "phase": "queued",
            "request_payload": request.model_dump(mode="python"),
            "summary": {"competitor_name": competitor.get("display_name")},
        }
    )
    asyncio.create_task(
        _run_competitor_collection_task(
            collection_run["id"],
            competitor_id,
            request,
            refresh_after=True,
        )
    )
    return {"competitor": competitor, "run": collection_run}


@router.get("/collection-runs/{run_id}")
async def get_competitor_collection_run(run_id: int):
    require_research_database()
    repository = ResearchRepository()
    run = await repository.get_collection_run(run_id)
    if run is None or run.get("target_type") != "competitor":
        raise HTTPException(status_code=404, detail="Collection run not found")
    competitor = await repository.get_competitor_account(int(run["target_id"]))
    return {"run": run, "competitor": competitor}


@router.get("/{competitor_id}/refresh-diagnostics")
async def get_competitor_refresh_diagnostics(
    competitor_id: int,
    date: str | None = None,
):
    require_research_database()
    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    target_date = _parse_workbench_date(date)
    diagnostics = await repository.get_competitor_post_diagnostics(
        platform=competitor["platform"],
        creator_id=competitor["creator_id"],
    )
    runs = await repository.list_collection_runs(
        target_type="competitor",
        target_id=competitor_id,
        run_type="competitor_monitor",
        limit=8,
    )
    latest_refresh = await _latest_competitor_refresh(repository, competitor_id)
    current, _, stale, _ = await _load_workbench_snapshots(repository, competitor_id, target_date)
    current_pf = _public_flow(current)
    displayed_rows = len(current_pf.get("top_delta_posts") or [])
    return _build_refresh_diagnostics_payload(
        competitor_id=competitor_id,
        target_date=target_date,
        stale=stale,
        runs=runs,
        latest_refresh=latest_refresh,
        diagnostics=diagnostics,
        displayed_rows=displayed_rows,
    )

    entries: list[dict[str, Any]] = []
    latest_run = next((run for run in runs if run.get("mode") == "collect_and_refresh"), None)
    if latest_run is not None:
        request_payload = latest_run.get("request_payload") or {}
        days_back = request_payload.get("days_back")
        latest_limit = request_payload.get("latest_limit")
        window_text = f"近 {days_back} 天" if days_back else "最新内容"
        limit_text = f"，上限 {latest_limit} 条" if latest_limit else ""
        entries.append(
            {
                "id": f"run-{latest_run['id']}",
                "timestamp": latest_run.get("completed_at") or latest_run.get("started_at") or latest_run.get("created_at"),
                "level": "success" if latest_run.get("status") == "succeeded" else "warn",
                "message": f"最近一次刷新{_refresh_status_label(latest_run.get('status'))}，采集窗口：{window_text}{limit_text}。",
            }
        )

    entries.append(
        {
            "id": "diag-matched",
            "timestamp": latest_refresh.get("last_refresh_at"),
            "level": "info",
            "message": f"当前匹配到 {stats['raw_matched_posts']} 条候选帖子，作者归属核验通过 {stats['author_verified_posts']} 条。",
        }
    )
    if stats["author_mismatch_posts"]:
        entries.append(
            {
                "id": "diag-mismatch",
                "timestamp": latest_refresh.get("last_refresh_at"),
                "level": "warn",
                "message": f"{stats['author_mismatch_posts']} 条帖子作者归属无法核验，已从贡献榜过滤。",
            }
        )
    if stats["missing_token_posts"]:
        entries.append(
            {
                "id": "diag-token",
                "timestamp": latest_refresh.get("last_refresh_at"),
                "level": "warn",
                "message": f"{stats['missing_token_posts']} 条帖子缺少 xsec_token，链接暂不可跳转，已在贡献榜降级展示并等待回填。",
            }
        )
    elif stats["invalid_url_posts"]:
        entries.append(
            {
                "id": "diag-invalid-url",
                "timestamp": latest_refresh.get("last_refresh_at"),
                "level": "warn",
                "message": f"{stats['invalid_url_posts']} 条帖子链接无效，已从贡献榜过滤。",
            }
        )
    entries.append(
        {
            "id": "diag-eligible",
            "timestamp": latest_refresh.get("last_refresh_at"),
            "level": "success" if displayed_rows else "error",
            "message": f"可点击链接 {stats['eligible_posts']} 条，当前贡献榜展示 {displayed_rows} 条。",
        }
    )
    for index, example in enumerate(diagnostics["examples"], start=1):
        entries.append(
            {
                "id": f"example-{index}",
                "timestamp": example.get("publish_time"),
                "level": _diagnostic_level(example.get("reason") or ""),
                "message": f"{example.get('title') or example.get('post_id')}: {_diagnostic_reason_label(example.get('reason') or '')}",
            }
        )
    for run in runs[1:5]:
        if run.get("mode") != "collect_and_refresh":
            continue
        entries.append(
            {
                "id": f"history-{run['id']}",
                "timestamp": run.get("completed_at") or run.get("started_at") or run.get("created_at"),
                "level": "success" if run.get("status") == "succeeded" else "warn",
                "message": f"历史刷新 #{run['id']}：{_refresh_status_label(run.get('status'))}。",
            }
        )

    return {
        "account_id": competitor_id,
        "date": target_date.isoformat(),
        "stale": stale,
        "timezone": "Asia/Shanghai",
        "last_refresh_at": latest_refresh.get("last_refresh_at"),
        "last_refresh_status": latest_refresh.get("last_refresh_status"),
        "stats": stats,
        "entries": entries,
    }


def _create_fetch_now_task(competitor_id: int) -> dict:
    task_id = uuid4().hex
    task = {
        "task_id": task_id,
        "competitor_id": competitor_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "已创建即时采集任务，等待后端执行。",
        "logs": [],
        "result": None,
        "error": None,
        "started_at": _now_iso(),
        "finished_at": None,
    }
    _fetch_now_tasks[task_id] = task
    _trim_fetch_now_tasks()
    return task


async def _run_fetch_now_task(task_id: str, competitor_id: int, request: CompetitorFetchNowRequest) -> None:
    try:
        result = await _run_fetch_now_inline(
            competitor_id,
            request,
            progress=lambda stage, progress, message: _update_fetch_task(task_id, stage, progress, message),
        )
        _finish_fetch_task(task_id, result)
    except Exception as exc:
        _fail_fetch_task(task_id, exc)


async def _run_fetch_now_inline(
    competitor_id: int,
    request: CompetitorFetchNowRequest,
    progress=None,
    *,
    refresh_snapshot: bool = True,
) -> dict:
    repository = ResearchRepository()
    _emit_progress(progress, "loading_competitor", 5, "正在读取友商账号。")
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    _emit_progress(progress, "profile", 10, "正在补全账号昵称。")
    competitor = await _ensure_competitor_display_name(repository, competitor)
    _emit_progress(progress, "creating_job", 18, "正在创建即时采集任务。")
    job = await create_competitor_fetch_now_job(
        repository,
        competitor,
        latest_limit=request.latest_limit,
        days_back=request.days_back,
    )
    _emit_progress(progress, "scheduling", 28, "正在调度采集单元。")
    schedule = await ResearchScheduler(repository).schedule_job(
        job["id"],
        max_attempts=request.max_attempts,
        force=True,
    )
    xhs_token_backfill: dict[str, Any] = {
        "platform": "xhs",
        "attempted": 0,
        "updated": 0,
        "failed": 0,
        "skipped": 0,
    }
    worker_result = None
    if request.execute_now:
        _emit_progress(progress, "crawling", 40, "正在启动爬虫并采集主页最新内容。")
        worker_result = await _run_fetch_now_worker_until_done(
            competitor_id=competitor_id,
            request=request,
            job_id=job["id"],
            progress=progress,
        )
        _raise_if_worker_did_not_collect(worker_result)
        if competitor.get("platform") == "xhs":
            xhs_token_backfill = await _backfill_xhs_tokens_for_competitor(
                repository,
                competitor=competitor,
                days_back=request.days_back,
            )
        _emit_progress(progress, "worker_finished", 78, f"爬虫执行结束：{worker_result.get('status') if isinstance(worker_result, dict) else 'unknown'}。")
    else:
        _emit_progress(progress, "queued", 70, "已排队，等待常驻 worker 执行。")
    _emit_progress(progress, "rebuilding_snapshot", 88, "正在重建公开流量快照。")
    snapshot = None
    if refresh_snapshot:
        snapshot = await _rebuild_public_flow_snapshot_for_competitor(
            repository,
            competitor_id=competitor_id,
            keywords=[],
            snapshot_date=None,
            latest_limit=request.latest_limit,
            days_back=request.days_back,
        )
    return {
        "competitor": competitor,
        "job": job,
        "schedule": schedule,
        "worker": worker_result,
        "snapshot": snapshot,
        "xhs_token_backfill": xhs_token_backfill,
        "worker_hint": None
        if request.execute_now
        else "Run scripts/run_ops_monitor.py or keep the ops monitor daemon running to execute the queued crawl unit.",
    }


async def _run_fetch_now_worker_until_done(
    *,
    competitor_id: int,
    request: CompetitorFetchNowRequest,
    job_id: int,
    progress=None,
) -> dict | None:
    last_result = None
    max_attempts = max(1, int(request.max_attempts))
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            detail = _worker_failure_detail(last_result)
            _emit_progress(
                progress,
                "retrying",
                min(74, 40 + attempt * 8),
                f"第 {attempt}/{max_attempts} 次重试采集。上一轮原因：{detail}",
            )
            await asyncio.sleep(FETCH_NOW_IMMEDIATE_RETRY_DELAY_SECONDS)
        last_result = await run_worker_once(
            worker_id=f"fetch-now-competitor-{competitor_id}",
            save_option=SaveDataOptionEnum(config.SAVE_DATA_OPTION),
            headless=request.headless,
            job_id=job_id,
            ignore_schedule=attempt > 1,
        )
        if not isinstance(last_result, dict):
            return last_result
        status = last_result.get("status")
        if status == CRAWL_UNIT_SUCCEEDED:
            return last_result
        if status != CRAWL_UNIT_RETRYING:
            return last_result
    return last_result


def _worker_failure_detail(worker_result: dict | None) -> str:
    if not isinstance(worker_result, dict):
        return "未返回 worker 结果"
    return str(
        worker_result.get("error")
        or worker_result.get("last_error")
        or worker_result.get("status")
        or "未知错误"
    )


def _raise_if_worker_did_not_collect(worker_result: dict | None) -> None:
    if not isinstance(worker_result, dict):
        raise RuntimeError("即时采集没有返回 worker 结果，请检查后端 worker 日志。")
    status = worker_result.get("status")
    if status == CRAWL_UNIT_SUCCEEDED:
        return
    if status == "idle":
        raise RuntimeError("即时采集没有领取到采集单元，可能是调度未写入或数据库连接不一致。")
    detail = worker_result.get("error") or worker_result.get("last_error") or "请检查后端 worker 日志。"
    raise RuntimeError(f"即时采集未成功，worker 状态：{status or 'unknown'}，原因：{detail}")


def _emit_progress(progress, stage: str, value: int, message: str) -> None:
    if progress:
        progress(stage, value, message)


def _update_fetch_task(task_id: str, stage: str, progress: int, message: str) -> None:
    task = _fetch_now_tasks.get(task_id)
    if not task:
        return
    task["status"] = "running"
    task["stage"] = stage
    task["progress"] = progress
    task["message"] = message
    task["logs"].append({"time": _now_iso(), "stage": stage, "message": message})
    task["logs"] = task["logs"][-20:]


def _finish_fetch_task(task_id: str, result: dict) -> None:
    task = _fetch_now_tasks.get(task_id)
    if not task:
        return
    snapshot = result.get("snapshot") or {}
    evidence = snapshot.get("evidence") if isinstance(snapshot, dict) else {}
    public_flow = evidence.get("public_flow") if isinstance(evidence, dict) else {}
    post_count = public_flow.get("deduped_post_count", 0) if isinstance(public_flow, dict) else 0
    total_flow = snapshot.get("total_flow_count", 0) if isinstance(snapshot, dict) else 0
    message = (
        f"采集完成，已采到 {post_count} 条公开内容，当前快照公开互动 {total_flow}。"
        if post_count
        else "采集流程执行完成，但本次没有采到公开内容；请检查账号主页 URL、登录状态、平台限制或爬虫日志。"
    )
    task.update(
        {
            "status": "completed",
            "stage": "completed",
            "progress": 100,
            "message": message,
            "result": result,
            "finished_at": _now_iso(),
        }
    )
    task["logs"].append({"time": _now_iso(), "stage": "completed", "message": task["message"]})


def _fail_fetch_task(task_id: str, exc: Exception) -> None:
    task = _fetch_now_tasks.get(task_id)
    if not task:
        return
    message = str(exc)
    task.update(
        {
            "status": "failed",
            "stage": "failed",
            "progress": 100,
            "message": message,
            "error": {"type": type(exc).__name__, "message": message},
            "finished_at": _now_iso(),
        }
    )
    task["logs"].append({"time": _now_iso(), "stage": "failed", "message": message})


def _trim_fetch_now_tasks(max_tasks: int = 100) -> None:
    if len(_fetch_now_tasks) <= max_tasks:
        return
    for key in list(_fetch_now_tasks)[: len(_fetch_now_tasks) - max_tasks]:
        _fetch_now_tasks.pop(key, None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cadence_label(schedule_enabled: bool | None, interval_minutes: int | None) -> str:
    if not schedule_enabled:
        return "手动"
    if not interval_minutes:
        return "手动"
    mapping = {
        8 * 60: "每 8 小时",
        12 * 60: "每 12 小时",
        24 * 60: "每天一次",
        7 * 24 * 60: "每周一次",
    }
    return mapping.get(int(interval_minutes), f"每 {int(interval_minutes)} 分钟")


@router.post("/{competitor_id}/composition")
async def create_competitor_composition_snapshot(
    competitor_id: int,
    request: CompetitorCompositionRequest,
):
    require_research_database()
    from datetime import date

    snapshot = build_competitor_composition_snapshot(
        competitor_account_id=competitor_id,
        snapshot_date=date.fromisoformat(request.snapshot_date),
        platform=request.platform,
        posts=request.posts,
        entity_tags=request.entity_tags,
        keywords=request.keywords,
    )
    return await ResearchRepository().upsert_competitor_composition_snapshot(snapshot)


@router.post("/{competitor_id}/composition/rebuild")
async def rebuild_competitor_composition_snapshot(
    competitor_id: int,
    request: CompetitorCompositionRebuildRequest,
):
    require_research_database()
    from datetime import date

    repository = ResearchRepository()
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    competitor = await _ensure_competitor_display_name(repository, competitor)
    posts = await repository.list_posts_by_creator(
        platform=competitor["platform"],
        creator_id=competitor["creator_id"],
        limit=500,
    )
    tags = await repository.list_entity_tags(
        entity_type="creator",
        entity_id=competitor["creator_id"],
        platform=competitor["platform"],
        vertical_id=competitor.get("vertical_id"),
    )
    keywords = request.keywords
    if not keywords:
        scene_keywords = await repository.list_scene_pack_keywords(enabled_only=True)
        keywords = [
            item["keyword"]
            for item in scene_keywords
            if item.get("keyword_type") != "negative"
            and (item.get("platform") is None or item.get("platform") == competitor["platform"])
        ][:50]
    snapshot = build_competitor_composition_snapshot(
        competitor_account_id=competitor_id,
        snapshot_date=date.fromisoformat(request.snapshot_date) if request.snapshot_date else date.today(),
        platform=competitor["platform"],
        posts=posts,
        entity_tags=tags,
        keywords=keywords,
    )
    return await repository.upsert_competitor_composition_snapshot(snapshot)


@router.post("/{competitor_id}/public-flow/rebuild")
async def rebuild_competitor_public_flow_snapshot(
    competitor_id: int,
    request: CompetitorPublicFlowRebuildRequest,
):
    require_research_database()
    repository = ResearchRepository()
    return await _rebuild_public_flow_snapshot_for_competitor(
        repository,
        competitor_id=competitor_id,
        keywords=request.keywords,
        snapshot_date=request.snapshot_date,
        latest_limit=request.latest_limit,
    )


@router.post("/composition/rebuild-all")
async def rebuild_all_competitor_composition_snapshots(request: CompetitorCompositionRebuildRequest):
    require_research_database()
    repository = ResearchRepository()
    competitors = await repository.list_competitor_accounts(enabled_only=True)
    rebuilt = []
    for competitor in competitors:
        rebuilt.append(
            await rebuild_competitor_composition_snapshot(
                competitor["id"],
                request,
            )
        )
    return {"rebuilt_count": len(rebuilt), "snapshots": rebuilt}


@router.post("/public-flow/rebuild-all")
async def rebuild_all_competitor_public_flow_snapshots(request: CompetitorPublicFlowRebuildRequest):
    require_research_database()
    repository = ResearchRepository()
    competitors = await repository.list_competitor_accounts(enabled_only=True)
    rebuilt = []
    for competitor in competitors:
        rebuilt.append(
            await _rebuild_public_flow_snapshot_for_competitor(
                repository,
                competitor_id=competitor["id"],
                keywords=request.keywords,
                snapshot_date=request.snapshot_date,
                latest_limit=request.latest_limit,
            )
        )
    return {"rebuilt_count": len(rebuilt), "snapshots": rebuilt}


async def _rebuild_public_flow_snapshot_for_competitor(
    repository: ResearchRepository,
    *,
    competitor_id: int,
    keywords: list[str],
    snapshot_date: str | None,
    latest_limit: int,
    days_back: int | None = None,
) -> dict:
    competitor = await repository.get_competitor_account(competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    posts = await repository.list_posts_by_creator(
        platform=competitor["platform"],
        creator_id=competitor["creator_id"],
        limit=latest_limit * 2,
    )
    posts = _filter_posts_by_days(posts, days_back)
    tags = await repository.list_entity_tags(
        entity_type="creator",
        entity_id=competitor["creator_id"],
        platform=competitor["platform"],
        vertical_id=competitor.get("vertical_id"),
    )
    effective_keywords = keywords
    if not effective_keywords:
        scene_keywords = await repository.list_scene_pack_keywords(enabled_only=True)
        effective_keywords = [
            item["keyword"]
            for item in scene_keywords
            if item.get("keyword_type") != "negative"
            and (item.get("platform") is None or item.get("platform") == competitor["platform"])
        ][:50]
    previous_snapshots = await repository.list_competitor_composition_snapshots(
        competitor_id=competitor_id,
        limit=8,
    )
    snapshot = build_competitor_public_flow_snapshot(
        competitor=competitor,
        posts=posts,
        keywords=effective_keywords,
        entity_tags=tags,
        previous_snapshots=previous_snapshots,
        snapshot_date=date.fromisoformat(snapshot_date) if snapshot_date else date.today(),
        latest_limit=latest_limit,
    )
    snapshot["evidence"] = {
        **(snapshot.get("evidence") or {}),
        "time_window": {
            "days_back": days_back,
            "label": f"近 {days_back} 天" if days_back else "最新内容",
        },
    }
    return await repository.upsert_competitor_composition_snapshot(snapshot)


def _filter_posts_by_days(posts: list[dict], days_back: int | None) -> list[dict]:
    if not days_back:
        return posts
    start_at = datetime.combine(date.today() - timedelta(days=days_back - 1), time.min)
    result = []
    for post in posts:
        publish_time = _post_publish_datetime(post.get("publish_time"))
        if publish_time is None or publish_time >= start_at:
            result.append(post)
    return result


def _post_publish_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


async def _payload_with_display_name(repository: ResearchRepository, payload: dict) -> dict:
    if payload.get("display_name"):
        return payload
    display_name = await _lookup_competitor_display_name(repository, payload)
    if display_name:
        return {**payload, "display_name": display_name}
    return payload


async def _enrich_competitors_with_display_names(repository: ResearchRepository, competitors: list[dict]) -> list[dict]:
    enriched = []
    for competitor in competitors:
        enriched.append(await _ensure_competitor_display_name(repository, competitor))
    return enriched


async def _ensure_competitor_display_name(repository: ResearchRepository, competitor: dict) -> dict:
    if competitor.get("display_name"):
        return competitor
    display_name = await _lookup_competitor_display_name(repository, competitor)
    if not display_name:
        return competitor
    updated = await repository.update_competitor_account(
        competitor["id"],
        {"display_name": display_name},
    )
    return updated or {**competitor, "display_name": display_name}


async def _lookup_competitor_display_name(repository: ResearchRepository, payload: dict) -> str | None:
    display_name, _diagnostics = await _lookup_competitor_display_name_with_diagnostics(repository, payload)
    return display_name


async def _lookup_competitor_display_name_with_diagnostics(
    repository: ResearchRepository,
    payload: dict,
) -> tuple[str | None, dict]:
    platform = payload.get("platform")
    creator_id = payload.get("creator_id")
    can_try_tikhub = _tikhub_lookup_candidate(platform=platform, creator_id=creator_id, profile_url=payload.get("profile_url"))
    diagnostics = {
        "platform": platform,
        "creator_id": creator_id,
        "has_profile_url": bool(payload.get("profile_url")),
        "has_tikhub_api_key": bool(getattr(config, "TIKHUB_API_KEY", "")),
        "enable_tikhub": bool(getattr(config, "ENABLE_TIKHUB", False)),
        "local_profile": "not_checked",
        "tikhub": "not_checked",
        "candidate_pool": "not_checked",
        "account_profile": "not_checked",
    }
    if not platform or not creator_id:
        diagnostics["reason"] = "missing_platform_or_creator_id"
        return None, diagnostics

    if hasattr(repository, "get_creator_profile"):
        profile = await repository.get_creator_profile(platform, creator_id)
        name = _public_display_name(profile, creator_id)
        if name:
            diagnostics["local_profile"] = "hit"
            return name, diagnostics
        diagnostics["local_profile"] = "miss"

    if _tikhub_profile_lookup_enabled() and can_try_tikhub:
        name, tikhub_status = await _lookup_display_name_from_tikhub(repository, payload)
        diagnostics["tikhub"] = tikhub_status
        if name:
            return name, diagnostics
    else:
        missing = []
        if not _tikhub_profile_lookup_enabled():
            missing.append("api_key")
        if not can_try_tikhub:
            missing.append("lookup_key")
        diagnostics["tikhub"] = f"skipped_missing_{'_and_'.join(missing)}"

    if hasattr(repository, "list_creator_candidates"):
        candidates = await repository.list_creator_candidates(platform=platform)
        for candidate in candidates:
            if candidate.get("creator_id") == creator_id:
                name = _public_display_name(candidate, creator_id)
                if name:
                    diagnostics["candidate_pool"] = "hit"
                    return name, diagnostics
        diagnostics["candidate_pool"] = "miss"

    if hasattr(repository, "list_account_profiles"):
        profiles = await repository.list_account_profiles(platform=platform)
        for profile in profiles:
            if profile.get("account_id") == creator_id:
                name = _public_display_name(profile, creator_id)
                if name:
                    diagnostics["account_profile"] = "hit"
                    return name, diagnostics
        diagnostics["account_profile"] = "miss"
    return None, diagnostics


def _tikhub_profile_lookup_enabled() -> bool:
    return bool(getattr(config, "ENABLE_TIKHUB", False) or getattr(config, "TIKHUB_API_KEY", ""))


def _tikhub_lookup_candidate(*, platform: str | None, creator_id: str | None, profile_url: str | None) -> bool:
    if str(profile_url or "").strip():
        return True
    if platform == "xhs" and str(creator_id or "").strip():
        return True
    if platform == "dy" and str(creator_id or "").strip().isdigit():
        return True
    return False


async def _lookup_display_name_from_tikhub(repository: ResearchRepository, payload: dict) -> tuple[str | None, str]:
    try:
        result = await enrich_creator_metrics_from_tikhub(repository, [payload])
    except Exception as exc:
        return None, f"error:{type(exc).__name__}:{str(exc)[:120]}"
    for item in result.get("enriched") or []:
        name = _public_display_name(item, payload.get("creator_id"))
        if name:
            return name, "hit"
    failed = result.get("failed") or []
    if failed:
        error = failed[0].get("error") if isinstance(failed[0], dict) else failed[0]
        return None, f"failed:{str(error)[:160]}"
    return None, "miss"


def _public_display_name(item: dict | None, creator_id: str | None) -> str | None:
    if not item:
        return None
    for key in ("display_name", "nickname", "nick_name", "name"):
        value = str(item.get(key) or "").strip()
        if value and value != str(creator_id or ""):
            return value
    return None


def _creator_id_from_profile_url(platform: str, profile_url: str) -> str | None:
    from urllib.parse import urlparse

    path = urlparse(profile_url).path.strip("/")
    parts = [part for part in path.split("/") if part]
    if platform == "xhs" and "profile" in parts:
        index = parts.index("profile")
        if index + 1 < len(parts):
            return parts[index + 1]
    if platform == "dy" and parts:
        if parts[0] == "user" and len(parts) > 1:
            return parts[1]
        return parts[-1]
    return parts[-1] if parts else None


# ===========================================================================
# Workbench 聚合接口（友商监控工作台用）
# ===========================================================================

def _parse_workbench_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {value}") from exc


def _isoformat(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


async def _load_workbench_snapshots(
    repository: ResearchRepository,
    competitor_id: int,
    target_date: date,
) -> tuple[dict | None, dict | None, bool, list[dict]]:
    """返回 (current, previous, stale, history_recent7).

    current 是 snapshot_date <= target_date 的最新一条快照；previous 是再往前一条；
    stale=True 当 current 的快照日期 < target_date；history_recent7 是按时间倒序的最近 7 条。
    """
    snapshots = await repository.list_competitor_composition_snapshots(
        competitor_id=competitor_id,
        limit=30,
    )
    eligible = [s for s in snapshots if s.get("snapshot_date") and s["snapshot_date"] <= target_date]
    current = eligible[0] if eligible else None
    previous = eligible[1] if len(eligible) > 1 else None
    stale = bool(current and current["snapshot_date"] != target_date)
    return current, previous, stale, snapshots[:7]


def _public_flow(snapshot: dict | None) -> dict:
    if not snapshot:
        return {}
    return ((snapshot.get("evidence") or {}).get("public_flow")) or {}


def _delta_pct(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0 if current <= 0 else 100.0
    return round((current - previous) / previous * 100.0, 1)


@router.get("/{competitor_id}/today-summary")
async def get_competitor_today_summary(competitor_id: int, date: str | None = None):
    """每日流量账本（今日 vs 昨日）。"""
    require_research_database()
    repository = ResearchRepository()
    account = await repository.get_competitor_account(competitor_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    target_date = _parse_workbench_date(date)
    current, previous, stale, _ = await _load_workbench_snapshots(repository, competitor_id, target_date)

    current_pf = _public_flow(current)
    previous_pf = _public_flow(previous)
    current_delta = current_pf.get("delta") or {}
    previous_delta = previous_pf.get("delta") or {}

    anomalies = ((current.get("evidence") or {}).get("anomalies")) if current else []
    anomalies = anomalies or []
    new_hot_count = sum(1 for a in anomalies if a.get("type") == "new_hot_post")

    # 新 vs 老内容贡献：join delta_by_post → ResearchPost.publish_time
    delta_by_post = current_pf.get("delta_by_post") or {}
    new_delta_total = 0
    old_delta_total = 0
    unmatched_count = 0
    if delta_by_post:
        posts = await repository.list_posts_by_creator(
            platform=account["platform"],
            creator_id=account["creator_id"],
            limit=200,
        )
        publish_by_id = {
            str(p.get("platform_post_id") or ""): p.get("publish_time")
            for p in posts
        }
        boundary = datetime.combine(target_date, time.min, tzinfo=timezone.utc) - timedelta(hours=24)
        for post_id, delta in delta_by_post.items():
            inc = int((delta or {}).get("total_interaction") or 0)
            if inc <= 0:
                continue
            pub = publish_by_id.get(str(post_id))
            if isinstance(pub, str):
                try:
                    pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                except ValueError:
                    pub = None
            if pub is None:
                unmatched_count += 1
                old_delta_total += inc
            elif pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
                if pub >= boundary:
                    new_delta_total += inc
                else:
                    old_delta_total += inc
            else:
                if pub >= boundary:
                    new_delta_total += inc
                else:
                    old_delta_total += inc

    total_contrib = new_delta_total + old_delta_total
    new_pct = round(new_delta_total / total_contrib * 100, 1) if total_contrib else 0.0
    old_pct = round(100.0 - new_pct, 1) if total_contrib else 0.0

    new_post_count = int(current_pf.get("new_post_count") or current_pf.get("deduped_post_count") or 0) if current else 0
    # 估算「新增内容」：用本次 delta_by_post 中 inc>0 的帖子数（更贴近"今日新增内容"语义）
    today_new_posts = sum(1 for d in delta_by_post.values() if int((d or {}).get("total_interaction") or 0) > 0)
    prev_new_posts = sum(1 for d in (previous_pf.get("delta_by_post") or {}).values() if int((d or {}).get("total_interaction") or 0) > 0)
    interaction_total = int(current_delta.get("total_interaction") or 0)
    prev_interaction_total = int(previous_delta.get("total_interaction") or 0)

    def metric_pair(key: str):
        cur = int(current_delta.get(key) or 0)
        prev = int(previous_delta.get(key) or 0)
        return {"value": cur, "delta_pct": _delta_pct(cur, prev)}

    return {
        "account_id": competitor_id,
        "date": target_date.isoformat(),
        "stale": stale,
        "snapshot_date": current.get("snapshot_date").isoformat() if current and current.get("snapshot_date") else None,
        "unmatched_post_count": unmatched_count,
        "metrics": {
            "new_post_count": today_new_posts,
            "interaction_delta": interaction_total,
            "new_hot_post_count": new_hot_count,
            "anomaly_count": len(anomalies),
            "new_content_contribution": new_delta_total,
            "old_content_contribution": old_delta_total,
            "new_content_contribution_pct": new_pct,
            "old_content_contribution_pct": old_pct,
            "breakdown": {
                "like": metric_pair("like"),
                "comment": metric_pair("comment"),
                "collect": metric_pair("collect"),
                "share": metric_pair("share"),
            },
            "yesterday_diff_pct": {
                "new_posts": _delta_pct(today_new_posts, prev_new_posts),
                "interaction": _delta_pct(interaction_total, prev_interaction_total),
            },
            "deduped_post_count": int(current_pf.get("deduped_post_count") or 0) if current else 0,
        },
    }


@router.get("/{competitor_id}/sampled-posts", response_model=CompetitorSampledPostsResponse)
async def get_competitor_sampled_posts(
    competitor_id: int,
    date: str | None = None,
    limit: int = 100,
):
    require_research_database()
    repository = ResearchRepository()
    account = await repository.get_competitor_account(competitor_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    target_date = _parse_workbench_date(date)
    current, _, stale, _ = await _load_workbench_snapshots(repository, competitor_id, target_date)
    current_pf = _public_flow(current)
    sampled_metrics = current_pf.get("posts_by_id") or {}
    delta_by_post = current_pf.get("delta_by_post") or {}
    sampled_ids = [str(post_id or "").strip() for post_id in sampled_metrics.keys() if str(post_id or "").strip()]
    if not sampled_ids:
        return {
            "account_id": competitor_id,
            "date": target_date.isoformat(),
            "stale": stale,
            "timezone": "Asia/Shanghai",
            "total": 0,
            "rows": [],
        }

    limit = max(1, min(limit, 200))
    posts = await repository.list_posts_by_platform_post_ids(
        platform=account["platform"],
        creator_id=account["creator_id"],
        post_ids=sampled_ids,
    )
    posts_by_id = {
        str(post.get("platform_post_id") or ""): post
        for post in posts
        if str(post.get("platform_post_id") or "").strip()
    }
    rows: list[dict[str, Any]] = []
    for post_id in sampled_ids:
        post = posts_by_id.get(post_id)
        if not post:
            continue
        reason = _sampled_post_reason(
            post,
            platform=account["platform"],
            creator_id=account["creator_id"],
        )
        rows.append(
            {
                "post_id": post_id,
                "title": post.get("title") or "",
                "publish_time": _isoformat(post.get("publish_time")),
                "platform_url": post.get("url") or "",
                "source_url": _post_source_url(
                    platform=str(account["platform"]),
                    post_id=post_id,
                    raw_url=post.get("url"),
                ),
                "content_type": "video" if (post.get("engagement_json") or {}).get("video_duration") else "note",
                "author_verified": bool(post.get("author_verified")),
                "has_valid_url": bool(post.get("has_valid_url")),
                "link_status": _diagnostic_reason_label(reason),
                "interaction_total": int((sampled_metrics.get(post_id) or {}).get("total_interaction") or 0),
                "interaction_delta": int((delta_by_post.get(post_id) or {}).get("total_interaction") or 0),
                "like_count": _sampled_post_metric(post, "liked_count", "like_count"),
                "comment_count": _sampled_post_metric(post, "comment_count", "comments_count"),
                "collect_count": _sampled_post_metric(post, "collected_count", "collect_count"),
                "share_count": _sampled_post_metric(post, "share_count", "shared_count"),
            }
        )
    rows.sort(key=_sampled_post_sort_key, reverse=True)
    return {
        "account_id": competitor_id,
        "date": target_date.isoformat(),
        "stale": stale,
        "timezone": "Asia/Shanghai",
        "total": len(sampled_ids),
        "rows": rows[:limit],
    }


@router.get("/{competitor_id}/contribution-ranking")
async def get_competitor_contribution_ranking(
    competitor_id: int,
    date: str | None = None,
    scope: str = "all",
    limit: int = 20,
):
    """内容贡献排行：基于 public_flow.top_delta_posts，并 join publish_time 给出 is_new。"""
    require_research_database()
    if scope not in ("all", "new", "old"):
        raise HTTPException(status_code=400, detail="scope must be all|new|old")
    limit = max(1, min(limit, 100))

    repository = ResearchRepository()
    account = await repository.get_competitor_account(competitor_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    target_date = _parse_workbench_date(date)
    current, _, stale, _ = await _load_workbench_snapshots(repository, competitor_id, target_date)
    current_pf = _public_flow(current)
    top = list(current_pf.get("top_delta_posts") or [])
    delta_total_global = int((current_pf.get("delta") or {}).get("total_interaction") or 0)

    # 拿 publish_time
    posts = await repository.list_posts_by_creator(
        platform=account["platform"],
        creator_id=account["creator_id"],
        limit=200,
    )
    publish_by_id = {str(p.get("platform_post_id") or ""): p for p in posts}
    boundary = datetime.combine(target_date, time.min, tzinfo=timezone.utc) - timedelta(hours=24)

    rows: list[dict] = []
    for index, item in enumerate(top, start=1):
        pid = str(item.get("platform_post_id") or "")
        post_row = publish_by_id.get(pid) or {}
        if not _ranking_post_is_usable(post_row):
            continue
        reason = _sampled_post_reason(
            post_row,
            platform=str(account["platform"]),
            creator_id=str(account["creator_id"]),
        )
        has_valid_url = bool(post_row.get("has_valid_url"))
        source_url = _post_source_url(
            platform=str(account["platform"]),
            post_id=pid,
            raw_url=post_row.get("url") or item.get("url"),
        )
        pub = post_row.get("publish_time")
        if isinstance(pub, str):
            try:
                pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except ValueError:
                pub = None
        if isinstance(pub, datetime) and pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        is_new = bool(pub and pub >= boundary)
        delta_total = int(item.get("delta_total") or 0)
        interaction_total = int(((current_pf.get("posts_by_id") or {}).get(pid, {}) or {}).get("total_interaction") or 0)
        prev_total = max(
            0,
            interaction_total - delta_total,
        )
        rows.append(
            {
                "rank": index,
                "post_id": pid,
                "title": item.get("title") or post_row.get("title") or "",
                "thumbnail_url": None,
                "duration_sec": None,
                "publish_time": _isoformat(pub),
                "is_new": is_new,
                "interaction_total": interaction_total,
                "interaction_delta": delta_total,
                "delta_pct": _delta_pct(delta_total, prev_total),
                "contribution_share": round(delta_total / delta_total_global * 100, 1) if delta_total_global else 0.0,
                "tags": [],
                "platform_url": str(post_row.get("url") or "") if has_valid_url else "",
                "source_url": source_url,
                "author_verified": bool(post_row.get("author_verified")),
                "has_valid_url": has_valid_url,
                "link_available": has_valid_url,
                "link_status": _diagnostic_reason_label(reason),
                "content_type": "video" if (post_row.get("engagement_json") or {}).get("video_duration") else "note",
            }
        )

    rows = _dedupe_contribution_rows(rows)

    if scope == "new":
        rows = [r for r in rows if r["is_new"]]
    elif scope == "old":
        rows = [r for r in rows if not r["is_new"]]
    rows = rows[:limit]
    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    return {
        "account_id": competitor_id,
        "date": target_date.isoformat(),
        "stale": stale,
        "scope": scope,
        "rows": rows,
        "total": len(rows),
    }


@router.get("/{competitor_id}/composition")
async def get_competitor_composition_breakdown(competitor_id: int, date: str | None = None):
    """关键词分布 + 内容类型 + 7 天 × 4 时段发布热力图。"""
    require_research_database()
    repository = ResearchRepository()
    if await repository.get_competitor_account(competitor_id) is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    target_date = _parse_workbench_date(date)
    current, _, stale, history = await _load_workbench_snapshots(repository, competitor_id, target_date)

    keyword_dist = (current or {}).get("keyword_distribution") or {}
    content_type_dist = (current or {}).get("content_type_distribution") or {}
    keywords = [
        {"word": str(k), "weight": int(v or 0)}
        for k, v in sorted(keyword_dist.items(), key=lambda kv: int(kv[1] or 0), reverse=True)[:50]
    ]
    content_types = [
        {"name": str(k), "value": int(v or 0)}
        for k, v in content_type_dist.items()
    ]

    buckets = ["morning", "afternoon", "night", "late_night"]
    days_iso: list[str] = []
    values: list[list[int]] = []
    snapshot_by_date = {
        s["snapshot_date"]: s for s in history if s.get("snapshot_date")
    }
    for offset in range(6, -1, -1):
        day = target_date - timedelta(days=offset)
        days_iso.append(day.isoformat())
        snap = snapshot_by_date.get(day)
        dist = (snap or {}).get("publish_time_distribution") or {}
        values.append([int(dist.get(b) or 0) for b in buckets])

    return {
        "account_id": competitor_id,
        "date": target_date.isoformat(),
        "stale": stale,
        "keywords": keywords,
        "content_types": content_types,
        "publish_heatmap": {
            "buckets": buckets,
            "days": days_iso,
            "values": values,
        },
    }


@router.get("/{competitor_id}/anomalies")
async def get_competitor_anomalies(competitor_id: int, date: str | None = None, limit: int = 20):
    """异常监控 feed：展开 evidence_json.anomalies。"""
    require_research_database()
    repository = ResearchRepository()
    if await repository.get_competitor_account(competitor_id) is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    target_date = _parse_workbench_date(date)
    current, _, stale, _ = await _load_workbench_snapshots(repository, competitor_id, target_date)
    raw = ((current or {}).get("evidence") or {}).get("anomalies") or []
    timestamp = _isoformat((current or {}).get("created_at")) if current else None
    items: list[dict] = []
    for idx, a in enumerate(raw[: max(1, min(limit, 100))]):
        post = a.get("post") or None
        items.append(
            {
                "id": f"{competitor_id}-{(current or {}).get('id')}-{idx}",
                "type": a.get("type", "unknown"),
                "severity": a.get("severity", "medium"),
                "title": a.get("title") or "",
                "reason": a.get("reason") or "",
                "timestamp": timestamp,
                "post_ref": (
                    {"id": str(post.get("platform_post_id") or ""), "title": post.get("title") or ""}
                    if post else None
                ),
            }
        )

    return {
        "account_id": competitor_id,
        "date": target_date.isoformat(),
        "stale": stale,
        "items": items,
    }

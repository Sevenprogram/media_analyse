import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from api.services.crawler_manager import crawler_manager
from research.enums import JOB_CANCELLED
from research.repository import ResearchRepository


RUNNING_STATUSES = {"running", "stopping"}
QUEUED_STATUSES = {"queued", "pending"}
FAILED_STATUSES = {"failed", "error"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "error", "paused_by_platform_config"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _status(value: str | None) -> str:
    raw = str(value or "unknown").lower()
    if raw in {"pending"}:
        return "queued"
    if raw in {"error"}:
        return "failed"
    return raw


def _source_for_job(job: dict[str, Any] | None, queued: dict[str, Any] | None = None) -> str:
    if queued and queued.get("project_id"):
        return "growth_project"
    topic = str((job or {}).get("topic") or "")
    if topic == "content_realtime_discovery":
        return "content_search"
    if topic == "creator_realtime_discovery":
        return "creator_search"
    return "research"


def _progress_for_status(status: str, label: str | None = None) -> dict[str, Any]:
    percent_by_status = {
        "queued": 5,
        "running": 50,
        "stopping": 80,
        "completed": 100,
        "failed": 100,
        "cancelled": 100,
    }
    return {
        "percent": percent_by_status.get(status, 0),
        "stage": status,
        "label": label or status,
    }


def _summary(tasks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(tasks),
        "running": sum(1 for task in tasks if task["status"] in RUNNING_STATUSES),
        "queued": sum(1 for task in tasks if task["status"] in QUEUED_STATUSES),
        "cancellable": sum(1 for task in tasks if task.get("cancellable")),
        "deletable": sum(1 for task in tasks if task.get("deletable")),
        "failed": sum(1 for task in tasks if task["status"] in FAILED_STATUSES),
        "completed": sum(1 for task in tasks if task["status"] == "completed"),
        "cancelled": sum(1 for task in tasks if task["status"] == "cancelled"),
    }


class BackgroundTaskCenter:
    def __init__(self, repository: ResearchRepository | None = None):
        self.repository = repository or ResearchRepository()

    async def list_tasks(self) -> dict[str, Any]:
        tasks: list[dict[str, Any]] = []
        crawler = self._crawler_task()
        if crawler:
            tasks.append(crawler)
        research_tasks = await self._research_tasks()
        tasks.extend(research_tasks)
        tasks.extend(await self._persisted_active_research_tasks(_related_job_ids(research_tasks)))
        tasks.extend(self._creator_search_tasks())
        tasks.extend(self._ai_analysis_tasks())
        tasks.sort(key=lambda item: item.get("updated_at") or item.get("started_at") or "", reverse=True)
        return {"tasks": tasks, "summary": _summary(tasks)}

    async def cancel(self, task_id: str) -> dict[str, Any]:
        if task_id == "crawler:current":
            return await self._cancel_crawler()
        if task_id.startswith("research-execution:"):
            return await self._cancel_research_execution(_parse_int_id(task_id, "research-execution:"))
        if task_id.startswith("research-queue:"):
            return await self._cancel_research_queue(_parse_int_id(task_id, "research-queue:"))
        if task_id.startswith("creator-search:"):
            return await self._cancel_creator_search(task_id.removeprefix("creator-search:"))
        if task_id.startswith("ai-analysis:"):
            return await self._cancel_ai_analysis(_parse_int_id(task_id, "ai-analysis:"))
        raise HTTPException(status_code=404, detail="Background task not found")

    async def delete(self, task_id: str) -> dict[str, Any]:
        if task_id == "crawler:current":
            raise HTTPException(status_code=409, detail="Crawler is running; cancel it before deleting the task")
        if task_id.startswith("research-execution:"):
            raise HTTPException(status_code=409, detail="Research execution is running; cancel it before deleting the task")
        if task_id.startswith("research-queue:"):
            return await self._delete_research_queue(_parse_int_id(task_id, "research-queue:"))
        if task_id.startswith("research-db:"):
            return await self._delete_persisted_research_task(_parse_int_id(task_id, "research-db:"))
        if task_id.startswith("creator-search:"):
            return await self._delete_creator_search(task_id.removeprefix("creator-search:"))
        if task_id.startswith("ai-analysis:"):
            return await self._delete_ai_analysis(_parse_int_id(task_id, "ai-analysis:"))
        raise HTTPException(status_code=404, detail="Background task not found")

    def _crawler_task(self) -> dict[str, Any] | None:
        if _research_execution_is_running():
            return None
        status = crawler_manager.get_status()
        normalized_status = _status(status.get("status"))
        if normalized_status == "idle":
            return None
        latest_log = crawler_manager.logs[-1].message if crawler_manager.logs else None
        return {
            "id": "crawler:current",
            "type": "crawler",
            "title": "Crawler process",
            "status": normalized_status,
            "progress": _progress_for_status(normalized_status, latest_log or "Crawler process"),
            "source": "crawler",
            "started_at": status.get("started_at"),
            "updated_at": _now_iso(),
            "cancellable": normalized_status in RUNNING_STATUSES,
            "cancel_reason": None if normalized_status in RUNNING_STATUSES else "Crawler is not running",
            "deletable": False,
            "delete_reason": "Cancel the crawler before deleting the task",
            "related_job_id": None,
            "detail": {
                "platform": status.get("platform"),
                "crawler_type": status.get("crawler_type"),
                "latest_log": latest_log,
            },
        }

    async def _research_tasks(self) -> list[dict[str, Any]]:
        import api.routers.research as research_router

        tasks: list[dict[str, Any]] = []
        live_executions = getattr(research_router, "_live_research_executions")()
        for running_job_id, record in live_executions.items():
            job = await self._get_job(running_job_id)
            source = _source_for_job(job)
            tasks.append(
                {
                    "id": f"research-execution:{running_job_id}",
                    "type": "research_execution",
                    "title": _research_title(job, running_job_id, source),
                    "status": "running",
                    "progress": _progress_for_status("running", "Research execution running"),
                    "source": source,
                    "started_at": None,
                    "updated_at": _now_iso(),
                    "cancellable": True,
                    "cancel_reason": None,
                    "deletable": False,
                    "delete_reason": "Cancel the running research execution before deleting it",
                    "related_job_id": running_job_id,
                    "detail": {
                        "job": _safe_job_detail(job),
                        "started_at": record.get("started_at"),
                        "queue": getattr(research_router, "_collection_queue_snapshot")(),
                    },
                }
            )

        for queued in list(getattr(research_router, "_research_execution_queue", [])):
            job_id = int(queued["job_id"])
            job = await self._get_job(job_id)
            source = _source_for_job(job, queued)
            tasks.append(
                {
                    "id": f"research-queue:{job_id}",
                    "type": "research_queue",
                    "title": _research_title(job, job_id, source),
                    "status": "queued",
                    "progress": _progress_for_status("queued", f"Queue position {_queue_position(queued)}"),
                    "source": source,
                    "started_at": queued.get("enqueued_at"),
                    "updated_at": queued.get("enqueued_at") or _now_iso(),
                    "cancellable": True,
                    "cancel_reason": None,
                    "deletable": True,
                    "delete_reason": None,
                    "related_job_id": job_id,
                    "detail": {
                        "project_id": queued.get("project_id"),
                        "queue_position": queued.get("queue_position"),
                        "job": _safe_job_detail(job),
                    },
                }
            )
        return tasks

    async def _persisted_active_research_tasks(self, seen_job_ids: set[int]) -> list[dict[str, Any]]:
        try:
            jobs = await self.repository.list_jobs()
        except Exception:
            return []

        tasks: list[dict[str, Any]] = []
        for job in jobs:
            job_id = _int_or_none(job.get("id"))
            status = _status(job.get("status"))
            if job_id is None or job_id in seen_job_ids or status not in {"queued", "running"}:
                continue
            source = _source_for_job(job)
            tasks.append(
                {
                    "id": f"research-db:{job_id}",
                    "type": "research_execution",
                    "title": _research_title(job, job_id, source),
                    "status": status,
                    "progress": _progress_for_status(status, "Database state is active, but no live process handle was found"),
                    "source": source,
                    "started_at": _iso(job.get("last_scheduled_at") or job.get("created_at")),
                    "updated_at": _iso(job.get("updated_at") or job.get("last_scheduled_at") or job.get("created_at")),
                    "cancellable": False,
                    "cancel_reason": "No live task handle in the current Web backend process",
                    "deletable": True,
                    "delete_reason": None,
                    "related_job_id": job_id,
                    "detail": {
                        "job": _safe_job_detail(job),
                        "visibility": "persisted_active_job_without_process_handle",
                    },
                }
            )
        return tasks

    def _creator_search_tasks(self) -> list[dict[str, Any]]:
        from api.routers.creator_search import CREATOR_SEARCH_TASKS

        tasks = []
        for task_id, task in CREATOR_SEARCH_TASKS.items():
            status = _status(task.get("status"))
            progress = task.get("progress") or _progress_for_status(status)
            tasks.append(
                {
                    "id": f"creator-search:{task_id}",
                    "type": "creator_search",
                    "title": f"Creator search {task_id[:8]}",
                    "status": status,
                    "progress": {
                        "percent": int(progress.get("percent") or 0),
                        "stage": progress.get("stage") or status,
                        "label": progress.get("label") or status,
                    },
                    "source": "creator_search",
                    "started_at": task.get("created_at"),
                    "updated_at": task.get("updated_at"),
                    "cancellable": status in {"queued", "running"},
                    "cancel_reason": None if status in {"queued", "running"} else "Task is already terminal",
                    "deletable": status in TERMINAL_STATUSES,
                    "delete_reason": None if status in TERMINAL_STATUSES else "Cancel the creator search before deleting it",
                    "related_job_id": None,
                    "detail": {
                        "request": _safe_mapping(task.get("request") or {}),
                        "error": task.get("error"),
                    },
                }
            )
        return tasks

    def _ai_analysis_tasks(self) -> list[dict[str, Any]]:
        import api.routers.research as research_router

        tasks = []
        for analysis_job_id, record in getattr(research_router, "AI_ANALYSIS_TASKS", {}).items():
            task = record.get("task")
            done = bool(task and task.done())
            status = _status(record.get("status") or ("completed" if done else "running"))
            tasks.append(
                {
                    "id": f"ai-analysis:{analysis_job_id}",
                    "type": "ai_analysis",
                    "title": f"AI analysis #{analysis_job_id}",
                    "status": status,
                    "progress": _progress_for_status(status, record.get("message") or "AI analysis"),
                    "source": "ai_analysis",
                    "started_at": record.get("created_at"),
                    "updated_at": record.get("updated_at") or record.get("created_at"),
                    "cancellable": status in {"queued", "running"} and bool(task and not task.done()),
                    "cancel_reason": None if bool(task and not task.done()) else "No live AI task handle",
                    "deletable": status in TERMINAL_STATUSES or not bool(task and not task.done()),
                    "delete_reason": None
                    if status in TERMINAL_STATUSES or not bool(task and not task.done())
                    else "Cancel the AI analysis before deleting it",
                    "related_job_id": record.get("research_job_id"),
                    "detail": {"analysis_job_id": analysis_job_id},
                }
            )
        return tasks

    async def _cancel_crawler(self) -> dict[str, Any]:
        if not crawler_manager.process or crawler_manager.process.poll() is not None:
            raise HTTPException(status_code=409, detail="Crawler is not running")
        stopped = await crawler_manager.stop()
        return {"status": "stopping" if stopped else "not_cancellable", "task": self._crawler_task()}

    async def _cancel_research_execution(self, job_id: int) -> dict[str, Any]:
        import api.routers.research as research_router

        live = getattr(research_router, "_live_research_executions")()
        record = live.get(job_id)
        running_task = record.get("task") if record else None
        if record is None and getattr(research_router, "_research_execution_job_id", None) == job_id:
            legacy_task = getattr(research_router, "_research_execution_task", None)
            if legacy_task and not legacy_task.done():
                record = {"task": legacy_task, "crawler_manager": crawler_manager}
                running_task = legacy_task
        if not record or not running_task or running_task.done():
            raise HTTPException(status_code=409, detail="Research execution is not running in this process")
        manager = record.get("crawler_manager") or crawler_manager
        await manager.stop()
        running_task.cancel()
        await self._mark_research_cancelled(job_id, "Research execution cancelled from background task center")
        return {"status": "stopping", "task": None}

    async def _cancel_research_queue(self, job_id: int) -> dict[str, Any]:
        import api.routers.research as research_router

        queue = getattr(research_router, "_research_execution_queue", [])
        before = len(queue)
        queue[:] = [item for item in queue if int(item["job_id"]) != job_id]
        if len(queue) == before:
            raise HTTPException(status_code=404, detail="Queued research task not found")
        await self._mark_research_cancelled(job_id, "Queued research execution cancelled from background task center")
        return {"status": "cancelled", "task": None}

    async def _cancel_creator_search(self, task_id: str) -> dict[str, Any]:
        from api.routers.creator_search import CREATOR_SEARCH_TASKS

        task = CREATOR_SEARCH_TASKS.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Creator search task not found")
        if task.get("status") in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="Creator search task is already terminal")
        task["status"] = "cancelled"
        task["progress"] = {
            "stage": "cancelled",
            "label": "Cancelled",
            "percent": int((task.get("progress") or {}).get("percent") or 0),
        }
        task["updated_at"] = _now_iso()
        return {"status": "cancelled", "task": self._creator_search_tasks_by_id(task_id)}

    async def _cancel_ai_analysis(self, analysis_job_id: int) -> dict[str, Any]:
        import api.routers.research as research_router

        registry = getattr(research_router, "AI_ANALYSIS_TASKS", {})
        record = registry.get(analysis_job_id)
        task = record.get("task") if record else None
        if not record or not task or task.done():
            raise HTTPException(status_code=409, detail="AI analysis task has no live process handle")
        record["status"] = "cancelled"
        record["updated_at"] = _now_iso()
        task.cancel()
        await self.repository.update_ai_analysis_job_status(analysis_job_id, "cancelled")
        related_job_id = record.get("research_job_id")
        if related_job_id:
            await self.repository.create_event(
                job_id=int(related_job_id),
                platform=None,
                event_type="ai_analysis_cancelled",
                message=f"AI analysis job {analysis_job_id} cancelled from background task center",
                stats={"analysis_job_id": analysis_job_id},
            )
        return {"status": "cancelled", "task": None}

    async def _delete_research_queue(self, job_id: int) -> dict[str, Any]:
        import api.routers.research as research_router

        queue = getattr(research_router, "_research_execution_queue", [])
        before = len(queue)
        queue[:] = [item for item in queue if int(item["job_id"]) != job_id]
        if len(queue) == before:
            raise HTTPException(status_code=404, detail="Queued research task not found")
        await self._mark_research_deleted(job_id, "Queued research execution deleted from background task center")
        return {"status": "deleted", "task": None}

    async def _delete_persisted_research_task(self, job_id: int) -> dict[str, Any]:
        job = await self._get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Persisted research task not found")
        status = _status(job.get("status"))
        if status not in {"queued", "running"} | TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail=f"Research task cannot be deleted from status {status}")
        await self._mark_research_deleted(job_id, "Persisted research task deleted from background task center")
        return {"status": "deleted", "task": None}

    async def _delete_creator_search(self, task_id: str) -> dict[str, Any]:
        from api.routers.creator_search import CREATOR_SEARCH_TASKS

        task = CREATOR_SEARCH_TASKS.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Creator search task not found")
        status = _status(task.get("status"))
        if status not in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="Creator search is active; cancel it before deleting the task")
        CREATOR_SEARCH_TASKS.pop(task_id, None)
        return {"status": "deleted", "task": None}

    async def _delete_ai_analysis(self, analysis_job_id: int) -> dict[str, Any]:
        import api.routers.research as research_router

        registry = getattr(research_router, "AI_ANALYSIS_TASKS", {})
        record = registry.get(analysis_job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="AI analysis task not found")
        task = record.get("task")
        status = _status(record.get("status") or ("completed" if bool(task and task.done()) else "running"))
        if status not in TERMINAL_STATUSES and bool(task and not task.done()):
            raise HTTPException(status_code=409, detail="AI analysis is active; cancel it before deleting the task")
        registry.pop(analysis_job_id, None)
        return {"status": "deleted", "task": None}

    async def _mark_research_cancelled(self, job_id: int, message: str) -> None:
        job = await self.repository.update_job(job_id, {"status": JOB_CANCELLED})
        await self.repository.create_event(
            job_id=job_id,
            platform=None,
            event_type="background_task_cancelled",
            message=message,
            stats={"job_id": job_id},
        )
        if job:
            await self._mark_growth_project_stopped(job)

    async def _mark_research_deleted(self, job_id: int, message: str) -> None:
        job = await self.repository.update_job(job_id, {"status": JOB_CANCELLED})
        await self.repository.create_event(
            job_id=job_id,
            platform=None,
            event_type="background_task_deleted",
            message=message,
            stats={"job_id": job_id},
        )
        if job:
            await self._mark_growth_project_stopped(job)

    async def _mark_growth_project_stopped(self, job: dict[str, Any]) -> None:
        project_id = str(job.get("topic") or "")
        if not project_id:
            return
        get_record = getattr(self.repository, "list_growth_project_records", None)
        if get_record is None:
            return
        try:
            for record in await self.repository.list_growth_project_records(include_archived=True):
                if _project_slug(record.get("name")) == project_id:
                    await self.repository.update_growth_project(
                        record["id"],
                        {"collection_status": "stopped", "recommended_action": "start_collection"},
                    )
                    break
        except Exception:
            return

    async def _get_job(self, job_id: int | None) -> dict[str, Any] | None:
        if not job_id:
            return None
        try:
            return await self.repository.get_job(int(job_id))
        except Exception:
            return None

    def _creator_search_tasks_by_id(self, task_id: str) -> dict[str, Any] | None:
        for task in self._creator_search_tasks():
            if task["id"] == f"creator-search:{task_id}":
                return task
        return None


def _parse_int_id(task_id: str, prefix: str) -> int:
    try:
        return int(task_id.removeprefix(prefix))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Background task not found") from exc


def _queue_position(queued: dict[str, Any]) -> int:
    try:
        return int(queued.get("queue_position") or 0)
    except (TypeError, ValueError):
        return 0


def _research_title(job: dict[str, Any] | None, job_id: int, source: str) -> str:
    name = (job or {}).get("name")
    if name:
        return str(name)
    labels = {
        "growth_project": "Growth project collection",
        "content_search": "Content realtime search",
        "creator_search": "Creator realtime discovery",
    }
    return f"{labels.get(source, 'Research execution')} #{job_id}"


def _safe_job_detail(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "topic": job.get("topic"),
        "platforms": job.get("platforms") or [],
        "collection_mode": job.get("collection_mode"),
        "status": job.get("status"),
    }


def _safe_mapping(value: dict[str, Any]) -> dict[str, Any]:
    hidden = {"cookies", "api_key", "apiKey", "password", "secret"}
    return {key: ("***" if key in hidden else item) for key, item in value.items()}


def _related_job_ids(tasks: list[dict[str, Any]]) -> set[int]:
    ids = set()
    for task in tasks:
        job_id = _int_or_none(task.get("related_job_id"))
        if job_id is not None:
            ids.add(job_id)
    return ids


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _project_slug(value: Any) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(value or "").strip().lower())
    return slug.strip("_")


def _research_execution_is_running() -> bool:
    try:
        import api.routers.research as research_router

        return bool(getattr(research_router, "_running_research_job_ids")())
    except Exception:
        return False

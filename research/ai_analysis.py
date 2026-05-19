import asyncio
import json
import re
from typing import Any, Protocol

from research.ai_provider import OpenAICompatibleProvider


class AIAnalysisRepository(Protocol):
    async def get_ai_analysis_job(self, analysis_job_id: int) -> dict[str, Any] | None:
        ...

    async def get_ai_provider(self, provider_id: int, *, include_secret: bool = False) -> dict[str, Any] | None:
        ...

    async def get_prompt_template(self, prompt_id: int) -> dict[str, Any] | None:
        ...

    async def list_posts(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        ...

    async def list_comments(self, job_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        ...

    async def update_ai_analysis_job_status(
        self, analysis_job_id: int, status: str
    ) -> dict[str, Any] | None:
        ...

    async def create_ai_analysis_result(
        self, *, analysis_job_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        ...

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


class AIAnalysisRunner:
    def __init__(self, repository: AIAnalysisRepository):
        self.repository = repository

    async def run(self, analysis_job_id: int) -> dict[str, Any]:
        job = await self.repository.get_ai_analysis_job(analysis_job_id)
        if job is None:
            raise ValueError("AI analysis job not found")
        provider_config = await self.repository.get_ai_provider(
            job["provider_config_id"], include_secret=True
        )
        if provider_config is None:
            raise ValueError("AI provider config not found")
        prompt = await self.repository.get_prompt_template(job["prompt_template_id"])
        if prompt is None:
            raise ValueError("AI prompt template not found")

        await self.repository.update_ai_analysis_job_status(analysis_job_id, "running")
        targets = await self._load_targets(job)
        provider = OpenAICompatibleProvider(
            base_url=provider_config["base_url"],
            api_key=provider_config["api_key"],
            model=provider_config["model"],
            timeout=provider_config["timeout"],
        )
        params = provider_config.get("default_params") or {}
        max_concurrency = int(provider_config.get("max_concurrency") or 1)
        semaphore = asyncio.Semaphore(max(1, max_concurrency))

        async def run_one(target: dict[str, Any]) -> dict[str, Any] | None:
            async with semaphore:
                return await self._analyze_target(
                    analysis_job_id=analysis_job_id,
                    provider=provider,
                    prompt=prompt,
                    target=target,
                    params=params,
                )

        results = await asyncio.gather(*(run_one(target) for target in targets), return_exceptions=True)
        success_count = sum(1 for item in results if isinstance(item, dict))
        error_count = sum(1 for item in results if isinstance(item, Exception))
        final_status = "completed" if error_count == 0 else "failed"
        await self.repository.update_ai_analysis_job_status(analysis_job_id, final_status)
        await self.repository.create_event(
            job_id=job["research_job_id"],
            platform=None,
            event_type="ai_analysis_completed",
            message=f"AI analysis job {analysis_job_id} finished",
            stats={"success": success_count, "errors": error_count, "targets": len(targets)},
        )
        return {"status": final_status, "success": success_count, "errors": error_count}

    async def _load_targets(self, job: dict[str, Any]) -> list[dict[str, Any]]:
        scope = job.get("scope") or {}
        limit = scope.get("limit")
        target_type = scope.get("target_type", "post")
        if target_type == "comment":
            records = await self.repository.list_comments(job["research_job_id"], limit=limit)
        else:
            records = await self.repository.list_posts(job["research_job_id"], limit=limit)
            target_type = "post"
        platform = scope.get("platform")
        if platform:
            records = [record for record in records if record.get("platform") == platform]
        return [dict(record, target_type=target_type) for record in records]

    async def _analyze_target(
        self,
        *,
        analysis_job_id: int,
        provider: OpenAICompatibleProvider,
        prompt: dict[str, Any],
        target: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        prompt_text = render_prompt(prompt["prompt_text"], target)
        response = await provider.chat_json(
            messages=[{"role": "user", "content": prompt_text}],
            params=params,
        )
        content = extract_chat_content(response)
        result_json = parse_json_response(content)
        target_id = str(target.get("platform_post_id") or target.get("platform_comment_id") or target["id"])
        return await self.repository.create_ai_analysis_result(
            analysis_job_id=analysis_job_id,
            payload={
                "target_type": target["target_type"],
                "target_id": target_id,
                "result": result_json,
                "model": provider.model,
                "prompt_version": prompt["version"],
            },
        )


def render_prompt(template: str, target: dict[str, Any]) -> str:
    values = {
        "platform": target.get("platform", ""),
        "target_id": target.get("platform_post_id") or target.get("platform_comment_id") or target.get("id", ""),
        "title": target.get("title") or "",
        "content": target.get("content") or "",
        "publish_time": target.get("publish_time") or "",
        "engagement_json": json.dumps(target.get("engagement_json") or {}, ensure_ascii=False, default=str),
    }
    return template.format_map(_SafeDict(values))


def extract_chat_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def parse_json_response(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"text": content}
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"

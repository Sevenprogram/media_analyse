import json
from typing import Any

import httpx


def build_chat_completions_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/v1"):
        return f"{clean}/chat/completions"
    return f"{clean}/v1/chat/completions"


class OpenAICompatibleProvider:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def chat_json(
        self, *, messages: list[dict[str, str]], params: dict[str, Any]
    ) -> dict[str, Any]:
        payload = {"model": self.model, "messages": messages, **params}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                build_chat_completions_url(self.base_url), headers=headers, json=payload
            )
            response.raise_for_status()
            return response.json()

    async def test_connection(self) -> dict[str, Any]:
        response = await self.chat_json(
            messages=[{"role": "user", "content": 'Return JSON: {"ok": true}'}],
            params={"temperature": 0, "max_tokens": 20},
        )
        return {"ok": True, "response": response}

    async def complete_json(
        self, *, prompt: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await self.chat_json(
            messages=[{"role": "user", "content": prompt}],
            params={
                "temperature": 0.2,
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
                **(params or {}),
            },
        )
        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "{}")
        )
        return json.loads(content)

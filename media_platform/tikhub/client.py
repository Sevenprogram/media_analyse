import asyncio
import os
from typing import Any, Optional

import httpx

import config

from .errors import (
    TikHubAuthError,
    TikHubConfigError,
    TikHubRateLimitError,
    TikHubUpstreamError,
    TikHubValidationError,
)


def resolve_tikhub_api_key() -> str:
    """Resolve TikHub API key with environment variable precedence."""

    return os.getenv("TIKHUB_API_KEY") or getattr(config, "TIKHUB_API_KEY", "")


class TikHubClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.api_key = api_key or resolve_tikhub_api_key()
        if not self.api_key:
            raise TikHubConfigError(
                "TikHub API key is missing. Set TIKHUB_API_KEY or config.TIKHUB_API_KEY."
            )

        self.base_url = (base_url or config.TIKHUB_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else config.TIKHUB_TIMEOUT_SECONDS
        self.max_retries = (
            max_retries if max_retries is not None else config.TIKHUB_MAX_RETRIES
        )
        self.retry_backoff = (
            retry_backoff
            if retry_backoff is not None
            else config.TIKHUB_RETRY_BACKOFF_SECONDS
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> Any:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    path,
                    params=self._clean_params(params),
                    json=json,
                )
                return self._handle_response(response)
            except TikHubRateLimitError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(self.retry_backoff * (attempt + 1))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise TikHubUpstreamError(
                        f"TikHub request failed after retries: {exc}"
                    ) from exc
                await asyncio.sleep(self.retry_backoff * (attempt + 1))

        raise TikHubUpstreamError(f"TikHub request failed: {last_error}")

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code in (401, 403):
            raise TikHubAuthError(
                "TikHub token is invalid, unauthorized, or lacks permission/balance."
            )
        if response.status_code == 429:
            raise TikHubRateLimitError("TikHub rate limit reached.")
        if response.status_code in (400, 422):
            raise TikHubValidationError(response.text)
        if response.status_code >= 500:
            raise TikHubUpstreamError(response.text)

        payload = response.json()
        if not isinstance(payload, dict):
            return payload

        code = payload.get("code", response.status_code)
        if code in (401, 403):
            raise TikHubAuthError(str(payload))
        if code == 429:
            raise TikHubRateLimitError(str(payload))
        if code == 422:
            raise TikHubValidationError(str(payload))
        if isinstance(code, int) and code >= 500:
            raise TikHubUpstreamError(str(payload))

        return payload["data"] if "data" in payload else payload

    def _clean_params(
        self, params: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        if params is None:
            return None
        return {key: value for key, value in params.items() if value not in (None, "")}

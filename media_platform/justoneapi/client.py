import asyncio
import os
from typing import Any, Optional

import httpx

import config


class JustOneAPIError(RuntimeError):
    """Base JustOneAPI error."""


class JustOneAPIConfigError(JustOneAPIError):
    """Client configuration is missing or invalid."""


class JustOneAPIAuthError(JustOneAPIError):
    """Token is invalid or unauthorized."""


class JustOneAPIValidationError(JustOneAPIError):
    """Request was rejected by JustOneAPI."""


class JustOneAPIUpstreamError(JustOneAPIError):
    """JustOneAPI upstream failed after retries."""


class JustOneAPIRateLimitError(JustOneAPIError):
    """JustOneAPI rate limit reached."""


def resolve_justone_api_key() -> str:
    return os.getenv("JUSTONE_API_KEY") or getattr(config, "JUSTONE_API_KEY", "")


class JustOneAPIClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.api_key = api_key or resolve_justone_api_key()
        if not self.api_key:
            raise JustOneAPIConfigError(
                "JustOneAPI key is missing. Set JUSTONE_API_KEY or config.JUSTONE_API_KEY."
            )

        self.base_url = (base_url or config.JUSTONE_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else config.JUSTONE_TIMEOUT_SECONDS
        self.max_retries = (
            max_retries if max_retries is not None else config.JUSTONE_MAX_RETRIES
        )
        self.retry_backoff = (
            retry_backoff
            if retry_backoff is not None
            else config.JUSTONE_RETRY_BACKOFF_SECONDS
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
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
                request_params = {"token": self.api_key, **(params or {})}
                response = await self._client.request(
                    method,
                    path,
                    params=self._clean(request_params),
                    json=self._clean(json),
                )
                return self._handle_response(response)
            except JustOneAPIRateLimitError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(self.retry_backoff * (attempt + 1))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise JustOneAPIUpstreamError(
                        "JustOneAPI request failed after retries: "
                        f"{type(exc).__name__} while requesting {method.upper()} {self.base_url}{path}: {str(exc).strip() or type(exc).__name__}"
                    ) from exc
                await asyncio.sleep(self.retry_backoff * (attempt + 1))

        raise JustOneAPIUpstreamError(f"JustOneAPI request failed: {last_error}")

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code in (401, 403):
            raise JustOneAPIAuthError("JustOneAPI token is invalid or unauthorized.")
        if response.status_code == 429:
            raise JustOneAPIRateLimitError("JustOneAPI rate limit reached.")
        if response.status_code in (400, 404, 422):
            raise JustOneAPIValidationError(response.text)
        if response.status_code >= 500:
            raise JustOneAPIUpstreamError(response.text)

        payload = response.json()
        if not isinstance(payload, dict):
            return payload

        code = payload.get("code")
        normalized_code = _normalize_code(code)
        if normalized_code == 0:
            return payload.get("data")
        if normalized_code == 100:
            raise JustOneAPIAuthError(str(payload))
        if normalized_code in (302, 429):
            raise JustOneAPIRateLimitError(str(payload))
        if isinstance(normalized_code, int) and normalized_code >= 500:
            raise JustOneAPIUpstreamError(str(payload))
        raise JustOneAPIValidationError(str(payload))

    @staticmethod
    def _clean(payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if payload is None:
            return None
        return {key: value for key, value in payload.items() if value not in (None, "")}


def _normalize_code(code: Any) -> int | None:
    if isinstance(code, int):
        return code
    if isinstance(code, str):
        stripped = code.strip()
        if stripped.isdigit():
            return int(stripped)
    return None

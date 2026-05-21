import httpx
import pytest

import config
from media_platform.tikhub.client import TikHubClient
from media_platform.tikhub.errors import (
    TikHubAuthError,
    TikHubConfigError,
    TikHubRateLimitError,
    TikHubUpstreamError,
    TikHubValidationError,
)


@pytest.mark.asyncio
async def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("TIKHUB_API_KEY", raising=False)
    monkeypatch.setattr(config, "TIKHUB_API_KEY", "", raising=False)

    with pytest.raises(TikHubConfigError):
        TikHubClient()


@pytest.mark.asyncio
async def test_client_sends_bearer_token(monkeypatch):
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"code": 200, "data": {"ok": True}})

    monkeypatch.setenv("TIKHUB_API_KEY", "secret")
    client = TikHubClient(transport=httpx.MockTransport(handler))

    data = await client.request("GET", "/api/v1/example", params={"a": 1})
    await client.close()

    assert seen["authorization"] == "Bearer secret"
    assert data == {"ok": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, TikHubValidationError),
        (401, TikHubAuthError),
        (403, TikHubAuthError),
        (429, TikHubRateLimitError),
        (422, TikHubValidationError),
        (500, TikHubUpstreamError),
    ],
)
async def test_client_maps_http_errors(monkeypatch, status_code, error_type):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"code": status_code, "message": "bad"})

    monkeypatch.setenv("TIKHUB_API_KEY", "secret")
    client = TikHubClient(
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )

    with pytest.raises(error_type):
        await client.request("GET", "/api/v1/example")
    await client.close()


@pytest.mark.asyncio
async def test_client_retries_retryable_validation_error(monkeypatch):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                400,
                json={
                    "detail": {
                        "code": 400,
                        "message": "Request failed. Please retry.",
                    }
                },
            )
        return httpx.Response(200, json={"code": 200, "data": {"ok": True}})

    monkeypatch.setenv("TIKHUB_API_KEY", "secret")
    client = TikHubClient(
        transport=httpx.MockTransport(handler),
        max_retries=1,
        retry_backoff=0,
    )

    data = await client.request("GET", "/api/v1/example")
    await client.close()

    assert calls == 2
    assert data == {"ok": True}

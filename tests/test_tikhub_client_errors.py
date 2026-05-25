from __future__ import annotations

import httpx
import pytest

from media_platform.tikhub.client import TikHubClient
from media_platform.tikhub.errors import TikHubUpstreamError


@pytest.mark.asyncio
async def test_transport_error_includes_endpoint_and_network_hint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("", request=request)

    client = TikHubClient(
        api_key="test-token",
        base_url="https://api.tikhub.io",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(TikHubUpstreamError) as exc_info:
        await client.request("GET", "/api/v1/xiaohongshu/app/search_notes")

    await client.close()
    message = str(exc_info.value)
    assert "ConnectError" in message
    assert "GET https://api.tikhub.io/api/v1/xiaohongshu/app/search_notes" in message
    assert "proxy" in message
    assert "DNS/TUN" in message

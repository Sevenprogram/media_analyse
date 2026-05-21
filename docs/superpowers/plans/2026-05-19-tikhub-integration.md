# TikHub Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TikHub as a config-enabled replacement data source for the existing seven MediaCrawler platforms.

**Architecture:** Keep the current platform names and storage contracts. Add one shared `media_platform/tikhub` crawler that uses a TikHub client, endpoint registry, platform mappers, and a raw JSONL fallback writer. `main.CrawlerFactory` chooses TikHub only when `config.ENABLE_TIKHUB` is true.

**Tech Stack:** Python 3.11, httpx, pytest, pytest-asyncio, existing MediaCrawler config/store/model modules.

---

## File Map

- Modify `config/base_config.py`: TikHub configuration values.
- Modify `main.py`: route all existing platforms to `TikHubCrawler` when enabled.
- Create `media_platform/tikhub/__init__.py`: export `TikHubCrawler`.
- Create `media_platform/tikhub/errors.py`: typed exceptions.
- Create `media_platform/tikhub/client.py`: auth, HTTP, response envelope handling, retry.
- Create `media_platform/tikhub/endpoints.py`: platform capability registry.
- Create `media_platform/tikhub/raw_writer.py`: raw JSONL fallback output.
- Create `media_platform/tikhub/mappers/base.py`: mapper protocol and helper functions.
- Create `media_platform/tikhub/mappers/xhs.py`, `douyin.py`, `kuaishou.py`, `bilibili.py`, `weibo.py`, `tieba.py`, `zhihu.py`: platform mapping.
- Create `media_platform/tikhub/mappers/__init__.py`: mapper registry.
- Create `media_platform/tikhub/core.py`: crawler flow for search/detail/creator/comments.
- Create `tests/test_tikhub_config.py`
- Create `tests/test_tikhub_client.py`
- Create `tests/test_tikhub_endpoints.py`
- Create `tests/test_tikhub_raw_writer.py`
- Create `tests/test_tikhub_mappers.py`
- Create `tests/test_tikhub_crawler_flow.py`
- Create `tests/test_tikhub_factory.py`

## Task 1: Configuration and Key Resolution

**Files:**
- Modify: `config/base_config.py`
- Create: `media_platform/tikhub/__init__.py`
- Create: `media_platform/tikhub/errors.py`
- Create: `tests/test_tikhub_config.py`

- [ ] **Step 1: Write failing tests for API key resolution**

Create `tests/test_tikhub_config.py`:

```python
import importlib

import config


def test_tikhub_api_key_prefers_environment(monkeypatch):
    from media_platform.tikhub.client import resolve_tikhub_api_key

    monkeypatch.setenv("TIKHUB_API_KEY", "env-key")
    monkeypatch.setattr(config, "TIKHUB_API_KEY", "config-key", raising=False)

    assert resolve_tikhub_api_key() == "env-key"


def test_tikhub_api_key_falls_back_to_config(monkeypatch):
    from media_platform.tikhub.client import resolve_tikhub_api_key

    monkeypatch.delenv("TIKHUB_API_KEY", raising=False)
    monkeypatch.setattr(config, "TIKHUB_API_KEY", "config-key", raising=False)

    assert resolve_tikhub_api_key() == "config-key"


def test_tikhub_config_defaults_exist():
    importlib.reload(config)

    assert isinstance(config.ENABLE_TIKHUB, bool)
    assert config.TIKHUB_BASE_URL == "https://api.tikhub.io"
    assert config.TIKHUB_TIMEOUT_SECONDS > 0
    assert config.TIKHUB_MAX_RETRIES >= 0
    assert config.TIKHUB_RETRY_BACKOFF_SECONDS >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tikhub_config.py -v`

Expected: FAIL because `media_platform.tikhub.client` and config fields do not exist.

- [ ] **Step 3: Add config defaults**

Append near the other runtime settings in `config/base_config.py`:

```python
# TikHub third-party API data source.
# When enabled, main.CrawlerFactory routes supported platforms to TikHubCrawler.
ENABLE_TIKHUB = False
TIKHUB_API_KEY = ""
TIKHUB_BASE_URL = "https://api.tikhub.io"
TIKHUB_TIMEOUT_SECONDS = 30
TIKHUB_MAX_RETRIES = 3
TIKHUB_RETRY_BACKOFF_SECONDS = 2
```

- [ ] **Step 4: Add package shell and errors**

Create `media_platform/tikhub/__init__.py`:

```python
from .core import TikHubCrawler

__all__ = ["TikHubCrawler"]
```

Create `media_platform/tikhub/errors.py`:

```python
class TikHubError(Exception):
    """Base error for TikHub crawler failures."""


class TikHubConfigError(TikHubError):
    """TikHub configuration is missing or invalid."""


class TikHubAuthError(TikHubError):
    """TikHub rejected the configured token."""


class TikHubRateLimitError(TikHubError):
    """TikHub rate limit was reached."""


class TikHubValidationError(TikHubError):
    """TikHub rejected request parameters."""


class TikHubUpstreamError(TikHubError):
    """TikHub or the network failed after retries."""


class TikHubCapabilityError(TikHubError):
    """Requested capability is not supported by the registry."""
```

- [ ] **Step 5: Add temporary key resolver**

Create `media_platform/tikhub/client.py`:

```python
import os

import config


def resolve_tikhub_api_key() -> str:
    return os.getenv("TIKHUB_API_KEY") or getattr(config, "TIKHUB_API_KEY", "")
```

- [ ] **Step 6: Add temporary core shell**

Create `media_platform/tikhub/core.py`:

```python
class TikHubCrawler:
    def __init__(self, platform: str):
        self.platform = platform

    async def start(self) -> None:
        raise NotImplementedError("TikHubCrawler flow is implemented in later tasks.")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_tikhub_config.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add config/base_config.py media_platform/tikhub tests/test_tikhub_config.py
git commit -m "feat: add tikhub configuration"
```

## Task 2: TikHub HTTP Client

**Files:**
- Modify: `media_platform/tikhub/client.py`
- Modify: `media_platform/tikhub/errors.py`
- Create: `tests/test_tikhub_client.py`

- [ ] **Step 1: Write failing client tests**

Create `tests/test_tikhub_client.py`:

```python
import httpx
import pytest

import config
from media_platform.tikhub.client import TikHubClient
from media_platform.tikhub.errors import (
    TikHubAuthError,
    TikHubConfigError,
    TikHubRateLimitError,
    TikHubValidationError,
    TikHubUpstreamError,
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

    assert seen["authorization"] == "Bearer secret"
    assert data == {"ok": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
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
    client = TikHubClient(transport=httpx.MockTransport(handler), max_retries=0)

    with pytest.raises(error_type):
        await client.request("GET", "/api/v1/example")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tikhub_client.py -v`

Expected: FAIL because `TikHubClient` is not implemented.

- [ ] **Step 3: Implement client**

Replace `media_platform/tikhub/client.py` with:

```python
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
                "TikHub API key is missing. Set environment variable TIKHUB_API_KEY "
                "or config.TIKHUB_API_KEY before enabling TikHub mode."
            )

        self.base_url = (base_url or config.TIKHUB_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else config.TIKHUB_TIMEOUT_SECONDS
        self.max_retries = max_retries if max_retries is not None else config.TIKHUB_MAX_RETRIES
        self.retry_backoff = retry_backoff if retry_backoff is not None else config.TIKHUB_RETRY_BACKOFF_SECONDS
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
                response = await self._client.request(method, path, params=params, json=json)
                return self._handle_response(response)
            except TikHubRateLimitError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(self.retry_backoff * (attempt + 1))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise TikHubUpstreamError(f"TikHub request failed after retries: {exc}") from exc
                await asyncio.sleep(self.retry_backoff * (attempt + 1))

        raise TikHubUpstreamError(f"TikHub request failed: {last_error}")

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code in (401, 403):
            raise TikHubAuthError("TikHub token is invalid, unauthorized, or lacks balance/permission.")
        if response.status_code == 429:
            raise TikHubRateLimitError("TikHub rate limit reached.")
        if response.status_code == 422:
            raise TikHubValidationError(response.text)
        if response.status_code >= 500:
            raise TikHubUpstreamError(response.text)

        payload = response.json()
        code = payload.get("code", response.status_code) if isinstance(payload, dict) else response.status_code
        if code in (401, 403):
            raise TikHubAuthError(str(payload))
        if code == 429:
            raise TikHubRateLimitError(str(payload))
        if code == 422:
            raise TikHubValidationError(str(payload))
        if isinstance(code, int) and code >= 500:
            raise TikHubUpstreamError(str(payload))

        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_tikhub_config.py tests/test_tikhub_client.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add media_platform/tikhub/client.py media_platform/tikhub/errors.py tests/test_tikhub_client.py
git commit -m "feat: add tikhub http client"
```

## Task 3: Endpoint Registry

**Files:**
- Create: `media_platform/tikhub/endpoints.py`
- Create: `tests/test_tikhub_endpoints.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_tikhub_endpoints.py`:

```python
import pytest

from media_platform.tikhub.endpoints import Capability, get_endpoint, supports_capability
from media_platform.tikhub.errors import TikHubCapabilityError


@pytest.mark.parametrize("platform", ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"])
def test_platforms_have_search_detail_creator_entries(platform):
    assert supports_capability(platform, Capability.SEARCH)
    assert supports_capability(platform, Capability.DETAIL)
    assert supports_capability(platform, Capability.CREATOR)


def test_get_endpoint_returns_parameter_mapping():
    endpoint = get_endpoint("xhs", Capability.SEARCH)

    assert endpoint.method == "GET"
    assert endpoint.path.startswith("/api/v1/")
    assert "keyword" in endpoint.params


def test_unsupported_platform_raises():
    with pytest.raises(TikHubCapabilityError):
        get_endpoint("unknown", Capability.SEARCH)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tikhub_endpoints.py -v`

Expected: FAIL because registry does not exist.

- [ ] **Step 3: Implement registry**

Create `media_platform/tikhub/endpoints.py`:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .errors import TikHubCapabilityError


class Capability(str, Enum):
    SEARCH = "search"
    DETAIL = "detail"
    CREATOR = "creator"
    COMMENTS = "comments"
    SUB_COMMENTS = "sub_comments"


@dataclass(frozen=True)
class EndpointSpec:
    method: str
    path: str
    params: dict[str, str] = field(default_factory=dict)
    page_param: str = "page"
    cursor_param: str = ""
    page_size_param: str = ""
    default_params: dict[str, Any] = field(default_factory=dict)
    supported: bool = True


REGISTRY: dict[str, dict[Capability, EndpointSpec]] = {
    "xhs": {
        Capability.SEARCH: EndpointSpec("GET", "/api/v1/xiaohongshu/web_v3/fetch_search_notes", {"keyword": "keyword", "page": "page"}),
        Capability.DETAIL: EndpointSpec("GET", "/api/v1/xiaohongshu/web/get_note_info", {"note_id": "note_id", "share_text": "share_text"}),
        Capability.CREATOR: EndpointSpec("GET", "/api/v1/xiaohongshu/web/get_user_notes", {"user_id": "user_id", "page": "page"}),
        Capability.COMMENTS: EndpointSpec("GET", "/api/v1/xiaohongshu/web/get_note_comments", {"note_id": "note_id", "cursor": "cursor"}),
        Capability.SUB_COMMENTS: EndpointSpec("GET", "/api/v1/xiaohongshu/web/get_note_sub_comments", {"note_id": "note_id", "comment_id": "comment_id", "cursor": "cursor"}, supported=False),
    },
    "dy": {
        Capability.SEARCH: EndpointSpec("GET", "/api/v1/douyin/web/fetch_general_search_result", {"keyword": "keyword", "offset": "offset"}),
        Capability.DETAIL: EndpointSpec("GET", "/api/v1/douyin/web/fetch_one_video", {"aweme_id": "aweme_id"}),
        Capability.CREATOR: EndpointSpec("GET", "/api/v1/douyin/web/fetch_user_post_videos", {"sec_user_id": "sec_user_id", "max_cursor": "max_cursor"}),
        Capability.COMMENTS: EndpointSpec("GET", "/api/v1/douyin/web/fetch_video_comments", {"aweme_id": "aweme_id", "cursor": "cursor"}),
        Capability.SUB_COMMENTS: EndpointSpec("GET", "/api/v1/douyin/web/fetch_video_comment_replies", {"aweme_id": "aweme_id", "comment_id": "comment_id", "cursor": "cursor"}),
    },
    "ks": {
        Capability.SEARCH: EndpointSpec("GET", "/api/v1/kuaishou/web/search_video", {"keyword": "keyword", "pcursor": "pcursor"}),
        Capability.DETAIL: EndpointSpec("GET", "/api/v1/kuaishou/web/fetch_one_video", {"photo_id": "photo_id"}),
        Capability.CREATOR: EndpointSpec("GET", "/api/v1/kuaishou/web/fetch_user_profile", {"user_id": "user_id"}),
        Capability.COMMENTS: EndpointSpec("GET", "/api/v1/kuaishou/web/fetch_video_comments", {"photo_id": "photo_id", "pcursor": "pcursor"}),
        Capability.SUB_COMMENTS: EndpointSpec("GET", "/api/v1/kuaishou/web/fetch_video_sub_comments", {"photo_id": "photo_id", "comment_id": "comment_id", "pcursor": "pcursor"}, supported=False),
    },
    "bili": {
        Capability.SEARCH: EndpointSpec("GET", "/api/v1/bilibili/web/search", {"keyword": "keyword", "page": "page"}),
        Capability.DETAIL: EndpointSpec("GET", "/api/v1/bilibili/web/fetch_video_detail", {"bvid": "bvid", "aid": "aid"}),
        Capability.CREATOR: EndpointSpec("GET", "/api/v1/bilibili/web/fetch_user_videos", {"mid": "mid", "page": "page"}),
        Capability.COMMENTS: EndpointSpec("GET", "/api/v1/bilibili/web/fetch_video_comments", {"oid": "oid", "next": "next"}),
        Capability.SUB_COMMENTS: EndpointSpec("GET", "/api/v1/bilibili/web/fetch_video_sub_comments", {"oid": "oid", "root": "root", "next": "next"}),
    },
    "wb": {
        Capability.SEARCH: EndpointSpec("GET", "/api/v1/weibo/web/search_notes", {"keyword": "keyword", "page": "page"}),
        Capability.DETAIL: EndpointSpec("GET", "/api/v1/weibo/web/fetch_note_detail", {"note_id": "note_id"}),
        Capability.CREATOR: EndpointSpec("GET", "/api/v1/weibo/web/fetch_user_notes", {"user_id": "user_id", "page": "page"}),
        Capability.COMMENTS: EndpointSpec("GET", "/api/v1/weibo/web/fetch_note_comments", {"note_id": "note_id", "max_id": "max_id"}),
        Capability.SUB_COMMENTS: EndpointSpec("GET", "/api/v1/weibo/web/fetch_comment_replies", {"comment_id": "comment_id", "max_id": "max_id"}, supported=False),
    },
    "tieba": {
        Capability.SEARCH: EndpointSpec("GET", "/api/v1/baidu_tieba/web/search_posts", {"keyword": "keyword", "page": "page"}),
        Capability.DETAIL: EndpointSpec("GET", "/api/v1/baidu_tieba/web/fetch_post_detail", {"thread_id": "thread_id"}),
        Capability.CREATOR: EndpointSpec("GET", "/api/v1/baidu_tieba/web/fetch_user_posts", {"user_id": "user_id", "page": "page"}),
        Capability.COMMENTS: EndpointSpec("GET", "/api/v1/baidu_tieba/web/fetch_post_comments", {"thread_id": "thread_id", "page": "page"}),
        Capability.SUB_COMMENTS: EndpointSpec("GET", "/api/v1/baidu_tieba/web/fetch_sub_comments", {"thread_id": "thread_id", "comment_id": "comment_id", "page": "page"}, supported=False),
    },
    "zhihu": {
        Capability.SEARCH: EndpointSpec("GET", "/api/v1/zhihu/web/search", {"keyword": "keyword", "page": "page"}),
        Capability.DETAIL: EndpointSpec("GET", "/api/v1/zhihu/web/fetch_content_detail", {"content_id": "content_id"}),
        Capability.CREATOR: EndpointSpec("GET", "/api/v1/zhihu/web/fetch_user_contents", {"user_id": "user_id", "page": "page"}),
        Capability.COMMENTS: EndpointSpec("GET", "/api/v1/zhihu/web/fetch_content_comments", {"content_id": "content_id", "offset": "offset"}),
        Capability.SUB_COMMENTS: EndpointSpec("GET", "/api/v1/zhihu/web/fetch_comment_replies", {"comment_id": "comment_id", "offset": "offset"}, supported=False),
    },
}


def supports_capability(platform: str, capability: Capability) -> bool:
    return platform in REGISTRY and capability in REGISTRY[platform] and REGISTRY[platform][capability].supported


def get_endpoint(platform: str, capability: Capability) -> EndpointSpec:
    try:
        endpoint = REGISTRY[platform][capability]
    except KeyError as exc:
        raise TikHubCapabilityError(f"TikHub capability {capability.value!r} is not configured for platform {platform!r}.") from exc
    if not endpoint.supported:
        raise TikHubCapabilityError(f"TikHub capability {capability.value!r} is not supported for platform {platform!r}.")
    return endpoint
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_tikhub_endpoints.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add media_platform/tikhub/endpoints.py tests/test_tikhub_endpoints.py
git commit -m "feat: add tikhub endpoint registry"
```

## Task 4: Raw Fallback Writer

**Files:**
- Create: `media_platform/tikhub/raw_writer.py`
- Create: `tests/test_tikhub_raw_writer.py`

- [ ] **Step 1: Write failing raw writer test**

Create `tests/test_tikhub_raw_writer.py`:

```python
import json

import pytest

from media_platform.tikhub.raw_writer import TikHubRawWriter


@pytest.mark.asyncio
async def test_raw_writer_writes_jsonl(tmp_path):
    writer = TikHubRawWriter(base_dir=tmp_path)

    await writer.write(
        platform="xhs",
        crawler_type="search",
        entity_type="content",
        payload={"id": "1", "text": "hello"},
        source_keyword="keyword",
        entity_id="1",
    )

    files = list(tmp_path.glob("tikhub_xhs_search_raw_*.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert record["platform"] == "xhs"
    assert record["crawler_type"] == "search"
    assert record["entity_type"] == "content"
    assert record["entity_id"] == "1"
    assert record["raw"]["text"] == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tikhub_raw_writer.py -v`

Expected: FAIL because `raw_writer.py` does not exist.

- [ ] **Step 3: Implement writer**

Create `media_platform/tikhub/raw_writer.py`:

```python
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiofiles

import config


class TikHubRawWriter:
    def __init__(self, base_dir: Optional[str | Path] = None) -> None:
        configured = config.SAVE_DATA_PATH or "data"
        self.base_dir = Path(base_dir or configured)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def write(
        self,
        *,
        platform: str,
        crawler_type: str,
        entity_type: str,
        payload: Any,
        source_keyword: str = "",
        entity_id: str = "",
    ) -> None:
        now = datetime.now()
        file_name = f"tikhub_{platform}_{crawler_type}_raw_{now:%Y-%m-%d}.jsonl"
        record = {
            "platform": platform,
            "crawler_type": crawler_type,
            "source_keyword": source_keyword,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "fetched_at": now.isoformat(),
            "raw": payload,
        }
        async with aiofiles.open(self.base_dir / file_name, "a", encoding="utf-8") as f:
            await f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_tikhub_raw_writer.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add media_platform/tikhub/raw_writer.py tests/test_tikhub_raw_writer.py
git commit -m "feat: add tikhub raw fallback writer"
```

## Task 5: Mapper Base and Platform Mappers

**Files:**
- Create: `media_platform/tikhub/mappers/base.py`
- Create: `media_platform/tikhub/mappers/__init__.py`
- Create: seven platform mapper files
- Create: `tests/test_tikhub_mappers.py`

- [ ] **Step 1: Write failing mapper tests**

Create `tests/test_tikhub_mappers.py`:

```python
import pytest

from media_platform.tikhub.mappers import get_mapper


@pytest.mark.parametrize(
    ("platform", "expected_id_key"),
    [
        ("xhs", "note_id"),
        ("dy", "aweme_id"),
        ("ks", "video_id"),
        ("bili", "video_id"),
        ("wb", "note_id"),
        ("tieba", "note_id"),
        ("zhihu", "content_id"),
    ],
)
def test_mappers_emit_platform_content_id(platform, expected_id_key):
    mapper = get_mapper(platform)
    item = {
        "id": "item-1",
        "aweme_id": "item-1",
        "note_id": "item-1",
        "video_id": "item-1",
        "thread_id": "item-1",
        "content_id": "item-1",
        "title": "Title",
        "desc": "Description",
        "content": "Description",
        "text": "Description",
        "user": {"id": "user-1", "nickname": "Nick"},
        "author": {"id": "user-1", "name": "Nick"},
        "stats": {"like_count": 1, "comment_count": 2, "share_count": 3},
    }

    mapped = mapper.map_content(item, source_keyword="kw")

    assert mapped[expected_id_key] == "item-1"
    assert mapped["source_keyword"] == "kw"
    assert "raw_data" in mapped


@pytest.mark.parametrize("platform", ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"])
def test_mappers_emit_comment(platform):
    mapper = get_mapper(platform)
    mapped = mapper.map_comment(
        {"id": "comment-1", "content": "hello", "user": {"id": "u1", "nickname": "n1"}},
        content_id="item-1",
    )

    assert mapped
    assert "raw_data" in mapped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tikhub_mappers.py -v`

Expected: FAIL because mapper package does not exist.

- [ ] **Step 3: Implement mapper base**

Create `media_platform/tikhub/mappers/base.py`:

```python
import json
from typing import Any


def pick(payload: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return default


def nested(payload: dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current not in (None, "") else default


def raw(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


class BaseTikHubMapper:
    platform: str

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        raise NotImplementedError

    def map_comment(self, item: dict[str, Any], content_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def map_creator(self, item: dict[str, Any]) -> dict[str, Any]:
        user = item.get("user") if isinstance(item.get("user"), dict) else item
        return {
            "user_id": str(pick(user, "id", "user_id", "uid", "mid")),
            "nickname": str(pick(user, "nickname", "name", "screen_name")),
            "avatar": str(pick(user, "avatar", "avatar_url", "face")),
            "desc": str(pick(user, "desc", "description", "signature", "bio")),
            "raw_data": raw(item),
        }
```

- [ ] **Step 4: Implement seven focused mappers**

Create mapper files with these classes:

`media_platform/tikhub/mappers/xhs.py`:

```python
from typing import Any

from .base import BaseTikHubMapper, nested, pick, raw


class XhsTikHubMapper(BaseTikHubMapper):
    platform = "xhs"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        user = item.get("user") if isinstance(item.get("user"), dict) else item.get("author", {})
        return {
            "note_id": str(pick(item, "note_id", "id")),
            "type": str(pick(item, "type", "note_type", default="normal")),
            "title": str(pick(item, "title")),
            "desc": str(pick(item, "desc", "content", "text")),
            "video_url": str(pick(item, "video_url", "video")),
            "time": pick(item, "time", "create_time", "timestamp", default=0),
            "last_update_time": pick(item, "last_update_time", "update_time", "timestamp", default=0),
            "user_id": str(pick(user, "user_id", "id")),
            "nickname": str(pick(user, "nickname", "name")),
            "avatar": str(pick(user, "avatar", "avatar_url")),
            "liked_count": nested(item, "stats", "like_count", default=pick(item, "liked_count", "like_count", default=0)),
            "collected_count": pick(item, "collected_count", "collect_count", default=0),
            "comment_count": nested(item, "stats", "comment_count", default=pick(item, "comment_count", default=0)),
            "share_count": nested(item, "stats", "share_count", default=pick(item, "share_count", default=0)),
            "ip_location": str(pick(item, "ip_location")),
            "image_list": pick(item, "image_list", "images", default=[]),
            "tag_list": pick(item, "tag_list", "tags", default=[]),
            "note_url": str(pick(item, "note_url", "url", "share_url")),
            "source_keyword": source_keyword,
            "xsec_token": str(pick(item, "xsec_token")),
            "raw_data": raw(item),
        }

    def map_comment(self, item: dict[str, Any], content_id: str) -> dict[str, Any]:
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        return {
            "comment_id": str(pick(item, "comment_id", "id")),
            "create_time": pick(item, "create_time", "time", default=0),
            "ip_location": str(pick(item, "ip_location")),
            "note_id": content_id,
            "content": str(pick(item, "content", "text")),
            "user_id": str(pick(user, "user_id", "id")),
            "nickname": str(pick(user, "nickname", "name")),
            "avatar": str(pick(user, "avatar", "avatar_url")),
            "sub_comment_count": pick(item, "sub_comment_count", "reply_count", default=0),
            "pictures": pick(item, "pictures", "images", default=""),
            "parent_comment_id": pick(item, "parent_comment_id", default=0),
            "like_count": pick(item, "like_count", "liked_count", default=0),
            "raw_data": raw(item),
        }
```

Create the other mapper files using the same helper functions and platform ID keys:

- `douyin.py`: class `DouyinTikHubMapper`, content key `aweme_id`, comment key `comment_id`.
- `kuaishou.py`: class `KuaishouTikHubMapper`, content key `video_id`, comment key `comment_id`.
- `bilibili.py`: class `BilibiliTikHubMapper`, content key `video_id`, comment key `comment_id`.
- `weibo.py`: class `WeiboTikHubMapper`, content key `note_id`, comment key `comment_id`.
- `tieba.py`: class `TiebaTikHubMapper`, content key `note_id`, comment key `comment_id`.
- `zhihu.py`: class `ZhihuTikHubMapper`, content key `content_id`, comment key `comment_id`.

For each of these six files, use this minimal mapping pattern and change `id_key`:

```python
from typing import Any

from .base import BaseTikHubMapper, nested, pick, raw


class PlatformTikHubMapper(BaseTikHubMapper):
    platform = "platform"
    id_key = "content_id"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        user = item.get("user") if isinstance(item.get("user"), dict) else item.get("author", {})
        return {
            self.id_key: str(pick(item, self.id_key, "id", "aweme_id", "video_id", "thread_id", "content_id")),
            "title": str(pick(item, "title", "desc", "content", "text")),
            "desc": str(pick(item, "desc", "content", "text", "summary")),
            "user_id": str(pick(user, "user_id", "id", "uid", "mid", "sec_user_id")),
            "nickname": str(pick(user, "nickname", "name", "screen_name")),
            "avatar": str(pick(user, "avatar", "avatar_url", "face")),
            "liked_count": nested(item, "stats", "like_count", default=pick(item, "liked_count", "like_count", default=0)),
            "comment_count": nested(item, "stats", "comment_count", default=pick(item, "comment_count", default=0)),
            "share_count": nested(item, "stats", "share_count", default=pick(item, "share_count", default=0)),
            "time": pick(item, "time", "create_time", "timestamp", default=0),
            "source_keyword": source_keyword,
            "raw_data": raw(item),
        }

    def map_comment(self, item: dict[str, Any], content_id: str) -> dict[str, Any]:
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        return {
            "comment_id": str(pick(item, "comment_id", "id")),
            "content": str(pick(item, "content", "text")),
            "user_id": str(pick(user, "user_id", "id", "uid", "mid")),
            "nickname": str(pick(user, "nickname", "name", "screen_name")),
            "create_time": pick(item, "create_time", "time", default=0),
            "like_count": pick(item, "like_count", "liked_count", default=0),
            "content_id": content_id,
            "raw_data": raw(item),
        }
```

Rename the class, `platform`, and `id_key` in each file.

- [ ] **Step 5: Implement mapper registry**

Create `media_platform/tikhub/mappers/__init__.py`:

```python
from .bilibili import BilibiliTikHubMapper
from .douyin import DouyinTikHubMapper
from .kuaishou import KuaishouTikHubMapper
from .tieba import TiebaTikHubMapper
from .weibo import WeiboTikHubMapper
from .xhs import XhsTikHubMapper
from .zhihu import ZhihuTikHubMapper


_MAPPERS = {
    "xhs": XhsTikHubMapper(),
    "dy": DouyinTikHubMapper(),
    "ks": KuaishouTikHubMapper(),
    "bili": BilibiliTikHubMapper(),
    "wb": WeiboTikHubMapper(),
    "tieba": TiebaTikHubMapper(),
    "zhihu": ZhihuTikHubMapper(),
}


def get_mapper(platform: str):
    return _MAPPERS[platform]
```

- [ ] **Step 6: Run mapper tests**

Run: `uv run pytest tests/test_tikhub_mappers.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add media_platform/tikhub/mappers tests/test_tikhub_mappers.py
git commit -m "feat: add tikhub platform mappers"
```

## Task 6: TikHubCrawler Flow

**Files:**
- Modify: `media_platform/tikhub/core.py`
- Create: `tests/test_tikhub_crawler_flow.py`

- [ ] **Step 1: Write failing flow tests**

Create `tests/test_tikhub_crawler_flow.py`:

```python
import pytest

import config
from media_platform.tikhub.core import TikHubCrawler


class FakeClient:
    def __init__(self):
        self.calls = []

    async def request(self, method, path, *, params=None, json=None):
        self.calls.append((method, path, params or {}))
        if "comments" in path:
            return {"comments": [{"id": "c1", "content": "hello"}]}
        return {"items": [{"id": "n1", "title": "title", "user": {"id": "u1", "nickname": "nick"}}], "has_more": False}

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_search_flow_calls_client_and_store(monkeypatch):
    saved = []
    comments = []

    async def save_note(item):
        saved.append(item)

    async def save_comments(note_id, items):
        comments.extend(items)

    monkeypatch.setattr(config, "CRAWLER_TYPE", "search", raising=False)
    monkeypatch.setattr(config, "KEYWORDS", "kw", raising=False)
    monkeypatch.setattr(config, "START_PAGE", 1, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 1, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0, raising=False)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", True, raising=False)
    monkeypatch.setattr("store.xhs.update_xhs_note", save_note)
    monkeypatch.setattr("store.xhs.batch_update_xhs_note_comments", save_comments)

    crawler = TikHubCrawler(platform="xhs", client=FakeClient())
    await crawler.start()

    assert saved[0]["note_id"] == "n1"
    assert comments[0]["comment_id"] == "c1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tikhub_crawler_flow.py -v`

Expected: FAIL because `TikHubCrawler` does not implement flow or dependency injection.

- [ ] **Step 3: Implement crawler flow**

Replace `media_platform/tikhub/core.py` with a real implementation:

```python
import asyncio
from typing import Any, Optional

import config
from store import bilibili as bilibili_store
from store import douyin as douyin_store
from store import kuaishou as kuaishou_store
from store import tieba as tieba_store
from store import weibo as weibo_store
from store import xhs as xhs_store
from store import zhihu as zhihu_store
from tools import utils
from var import crawler_type_var, source_keyword_var

from .client import TikHubClient
from .endpoints import Capability, get_endpoint, supports_capability
from .errors import TikHubCapabilityError
from .mappers import get_mapper
from .raw_writer import TikHubRawWriter


class TikHubCrawler:
    def __init__(self, platform: str, client: Optional[TikHubClient] = None, raw_writer: Optional[TikHubRawWriter] = None):
        self.platform = platform
        self.client = client or TikHubClient()
        self.mapper = get_mapper(platform)
        self.raw_writer = raw_writer or TikHubRawWriter()

    async def start(self) -> None:
        crawler_type_var.set(config.CRAWLER_TYPE)
        try:
            if config.CRAWLER_TYPE == "search":
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_notes()
            else:
                raise ValueError(f"Unsupported crawler type for TikHub: {config.CRAWLER_TYPE}")
        finally:
            await self.client.close()

    async def search(self) -> None:
        endpoint = get_endpoint(self.platform, Capability.SEARCH)
        max_count = max(config.CRAWLER_MAX_NOTES_COUNT, 1)
        for keyword in [item.strip() for item in config.KEYWORDS.split(",") if item.strip()]:
            source_keyword_var.set(keyword)
            saved = 0
            page = config.START_PAGE
            while saved < max_count:
                data = await self.client.request(endpoint.method, endpoint.path, params={"keyword": keyword, "page": page})
                items = self._extract_items(data)
                if not items:
                    break
                for item in items:
                    mapped = self.mapper.map_content(item, source_keyword=keyword)
                    await self._save_content(mapped)
                    saved += 1
                    if config.ENABLE_GET_COMMENTS:
                        await self._fetch_and_save_comments(mapped)
                    if saved >= max_count:
                        break
                page += 1
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

    async def get_specified_notes(self) -> None:
        endpoint = get_endpoint(self.platform, Capability.DETAIL)
        for content_id in self._specified_ids():
            params = self._detail_params(content_id)
            data = await self.client.request(endpoint.method, endpoint.path, params=params)
            item = data if isinstance(data, dict) else {"id": content_id, "raw": data}
            mapped = self.mapper.map_content(item, source_keyword="")
            await self._save_content(mapped)
            if config.ENABLE_GET_COMMENTS:
                await self._fetch_and_save_comments(mapped)

    async def get_creators_and_notes(self) -> None:
        endpoint = get_endpoint(self.platform, Capability.CREATOR)
        for creator_id in self._creator_ids():
            data = await self.client.request(endpoint.method, endpoint.path, params={"user_id": creator_id, "page": 1})
            creator_payload = data.get("user") if isinstance(data, dict) and isinstance(data.get("user"), dict) else data
            await self._save_creator(self.mapper.map_creator(creator_payload if isinstance(creator_payload, dict) else {"id": creator_id}))
            for item in self._extract_items(data):
                mapped = self.mapper.map_content(item, source_keyword="")
                await self._save_content(mapped)
                if config.ENABLE_GET_COMMENTS:
                    await self._fetch_and_save_comments(mapped)

    async def _fetch_and_save_comments(self, mapped_content: dict[str, Any]) -> None:
        if not supports_capability(self.platform, Capability.COMMENTS):
            utils.logger.warning(f"[TikHubCrawler] Comments unsupported for platform={self.platform}")
            return
        endpoint = get_endpoint(self.platform, Capability.COMMENTS)
        content_id = self._content_id(mapped_content)
        data = await self.client.request(endpoint.method, endpoint.path, params={"note_id": content_id, "aweme_id": content_id, "video_id": content_id, "thread_id": content_id, "content_id": content_id})
        comments = [self.mapper.map_comment(item, content_id=content_id) for item in self._extract_comments(data)]
        if comments:
            await self._save_comments(content_id, comments[: config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES])
        if config.ENABLE_GET_SUB_COMMENTS and not supports_capability(self.platform, Capability.SUB_COMMENTS):
            utils.logger.warning(f"[TikHubCrawler] Sub-comments unsupported for platform={self.platform}")

    def _extract_items(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("items", "list", "data", "notes", "videos", "aweme_list", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data] if data else []

    def _extract_comments(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("comments", "list", "data", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _specified_ids(self) -> list[str]:
        attr = {
            "xhs": "XHS_SPECIFIED_NOTE_URL_LIST",
            "dy": "DY_SPECIFIED_ID_LIST",
            "ks": "KS_SPECIFIED_ID_LIST",
            "bili": "BILI_SPECIFIED_ID_LIST",
            "wb": "WEIBO_SPECIFIED_ID_LIST",
            "tieba": "TIEBA_SPECIFIED_ID_LIST",
            "zhihu": "ZHIHU_SPECIFIED_ID_LIST",
        }[self.platform]
        return list(getattr(config, attr, []))

    def _creator_ids(self) -> list[str]:
        attr = {
            "xhs": "XHS_CREATOR_ID_LIST",
            "dy": "DY_CREATOR_ID_LIST",
            "ks": "KS_CREATOR_ID_LIST",
            "bili": "BILI_CREATOR_ID_LIST",
            "wb": "WEIBO_CREATOR_ID_LIST",
            "tieba": "TIEBA_CREATOR_URL_LIST",
            "zhihu": "ZHIHU_CREATOR_ID_LIST",
        }[self.platform]
        return list(getattr(config, attr, []))

    def _detail_params(self, content_id: str) -> dict[str, str]:
        return {
            "note_id": content_id,
            "share_text": content_id if content_id.startswith("http") else "",
            "aweme_id": content_id,
            "photo_id": content_id,
            "bvid": content_id,
            "aid": content_id,
            "thread_id": content_id,
            "content_id": content_id,
        }

    def _content_id(self, item: dict[str, Any]) -> str:
        for key in ("note_id", "aweme_id", "video_id", "content_id"):
            if item.get(key):
                return str(item[key])
        return ""

    async def _save_content(self, item: dict[str, Any]) -> None:
        if self.platform == "xhs":
            await xhs_store.update_xhs_note(item)
        elif self.platform == "dy":
            await douyin_store.update_douyin_aweme(item)
        elif self.platform == "ks":
            await kuaishou_store.update_kuaishou_video(item)
        elif self.platform == "bili":
            await bilibili_store.update_bilibili_video(item)
        elif self.platform == "wb":
            await weibo_store.update_weibo_note(item)
        elif self.platform == "tieba":
            await self.raw_writer.write(platform=self.platform, crawler_type=config.CRAWLER_TYPE, entity_type="content", payload=item, entity_id=self._content_id(item))
        elif self.platform == "zhihu":
            await self.raw_writer.write(platform=self.platform, crawler_type=config.CRAWLER_TYPE, entity_type="content", payload=item, entity_id=self._content_id(item))

    async def _save_comments(self, content_id: str, comments: list[dict[str, Any]]) -> None:
        if self.platform == "xhs":
            await xhs_store.batch_update_xhs_note_comments(content_id, comments)
        elif self.platform == "dy":
            await douyin_store.batch_update_dy_aweme_comments(content_id, comments)
        elif self.platform == "ks":
            await kuaishou_store.batch_update_ks_video_comments(content_id, comments)
        elif self.platform == "bili":
            await bilibili_store.batch_update_bilibili_video_comments(content_id, comments)
        elif self.platform == "wb":
            await weibo_store.batch_update_weibo_note_comments(content_id, comments)
        else:
            await self.raw_writer.write(platform=self.platform, crawler_type=config.CRAWLER_TYPE, entity_type="comment", payload=comments, entity_id=content_id)

    async def _save_creator(self, creator: dict[str, Any]) -> None:
        user_id = str(creator.get("user_id", ""))
        if self.platform == "xhs":
            await xhs_store.save_creator(user_id, creator)
        elif self.platform == "dy":
            await douyin_store.save_creator(user_id, creator)
        elif self.platform == "ks":
            await kuaishou_store.save_creator(user_id, creator)
        elif self.platform == "wb":
            await weibo_store.save_creator(user_id, creator)
        else:
            await self.raw_writer.write(platform=self.platform, crawler_type=config.CRAWLER_TYPE, entity_type="creator", payload=creator, entity_id=user_id)
```

- [ ] **Step 4: Run flow test**

Run: `uv run pytest tests/test_tikhub_crawler_flow.py -v`

Expected: PASS.

- [ ] **Step 5: Run all TikHub tests so far**

Run: `uv run pytest tests/test_tikhub_config.py tests/test_tikhub_client.py tests/test_tikhub_endpoints.py tests/test_tikhub_raw_writer.py tests/test_tikhub_mappers.py tests/test_tikhub_crawler_flow.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add media_platform/tikhub/core.py tests/test_tikhub_crawler_flow.py
git commit -m "feat: add tikhub crawler flow"
```

## Task 7: Factory Wiring

**Files:**
- Modify: `main.py`
- Create: `tests/test_tikhub_factory.py`

- [ ] **Step 1: Write failing factory tests**

Create `tests/test_tikhub_factory.py`:

```python
import config
from main import CrawlerFactory
from media_platform.tikhub import TikHubCrawler
from media_platform.xhs import XiaoHongShuCrawler


def test_factory_uses_existing_crawler_when_tikhub_disabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_TIKHUB", False, raising=False)

    assert isinstance(CrawlerFactory.create_crawler("xhs"), XiaoHongShuCrawler)


def test_factory_uses_tikhub_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)

    crawler = CrawlerFactory.create_crawler("xhs")

    assert isinstance(crawler, TikHubCrawler)
    assert crawler.platform == "xhs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tikhub_factory.py -v`

Expected: FAIL because factory ignores `ENABLE_TIKHUB`.

- [ ] **Step 3: Wire factory**

Modify `main.py` imports:

```python
from media_platform.tikhub import TikHubCrawler
```

Modify `CrawlerFactory.create_crawler` before selecting platform-specific class:

```python
        if getattr(config, "ENABLE_TIKHUB", False):
            if platform not in CrawlerFactory.CRAWLERS:
                supported = ", ".join(sorted(CrawlerFactory.CRAWLERS))
                raise ValueError(f"Invalid media platform for TikHub mode: {platform!r}. Supported: {supported}")
            return TikHubCrawler(platform=platform)
```

- [ ] **Step 4: Run factory tests**

Run: `uv run pytest tests/test_tikhub_factory.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_tikhub_factory.py
git commit -m "feat: route enabled tikhub crawler"
```

## Task 8: CLI and Config Smoke Tests

**Files:**
- Modify: `cmd_arg/arg.py` only if config parsing breaks.
- Add tests to existing `tests/test_cmd_arg_tieba.py` or create `tests/test_tikhub_cli.py`.

- [ ] **Step 1: Write CLI preservation test**

Create `tests/test_tikhub_cli.py`:

```python
import pytest

import cmd_arg
import config


@pytest.mark.asyncio
async def test_existing_cli_shape_still_parses_with_tikhub_config(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)

    args = await cmd_arg.parse_cmd([
        "--platform", "xhs",
        "--type", "search",
        "--keywords", "口红",
        "--save_data_option", "jsonl",
    ])

    assert args.platform == "xhs"
    assert args.type == "search"
    assert config.KEYWORDS == "口红"
```

- [ ] **Step 2: Run CLI test**

Run: `uv run pytest tests/test_tikhub_cli.py -v`

Expected: PASS. If it fails from unrelated Typer behavior, keep CLI unchanged and fix the test to match existing parse patterns.

- [ ] **Step 3: Commit**

```bash
git add tests/test_tikhub_cli.py cmd_arg/arg.py
git commit -m "test: preserve cli shape for tikhub mode"
```

## Task 9: Endpoint Verification Against Current TikHub Docs

**Files:**
- Modify: `media_platform/tikhub/endpoints.py`
- Modify: `tests/test_tikhub_endpoints.py`

- [ ] **Step 1: Verify documented endpoint paths**

Use the TikHub docs already referenced in the design:

- Root docs: `https://docs.tikhub.io/`
- Xiaohongshu search example: `https://api.tikhub.io/api/v1/xiaohongshu/web_v3/fetch_search_notes`
- Xiaohongshu detail example: `https://api.tikhub.io/api/v1/xiaohongshu/web/get_note_info`

For each platform registry entry, update `path` and parameter names to match the current docs. Keep unsupported endpoints marked `supported=False` when no stable endpoint is found.

- [ ] **Step 2: Add endpoint path sanity assertions**

Extend `tests/test_tikhub_endpoints.py`:

```python
def test_xhs_documented_paths_are_exact():
    assert get_endpoint("xhs", Capability.SEARCH).path == "/api/v1/xiaohongshu/web_v3/fetch_search_notes"
    assert get_endpoint("xhs", Capability.DETAIL).path == "/api/v1/xiaohongshu/web/get_note_info"
```

- [ ] **Step 3: Run endpoint tests**

Run: `uv run pytest tests/test_tikhub_endpoints.py -v`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add media_platform/tikhub/endpoints.py tests/test_tikhub_endpoints.py
git commit -m "chore: align tikhub endpoint registry with docs"
```

## Task 10: Full Verification and Manual Smoke Command

**Files:**
- Modify tests only if failures reveal real bugs.

- [ ] **Step 1: Run targeted TikHub test suite**

Run:

```bash
uv run pytest \
  tests/test_tikhub_config.py \
  tests/test_tikhub_client.py \
  tests/test_tikhub_endpoints.py \
  tests/test_tikhub_raw_writer.py \
  tests/test_tikhub_mappers.py \
  tests/test_tikhub_crawler_flow.py \
  tests/test_tikhub_factory.py \
  tests/test_tikhub_cli.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run existing nearby tests**

Run:

```bash
uv run pytest \
  tests/test_cmd_arg_tieba.py \
  tests/test_store_factory.py \
  tests/test_research_execution.py \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run a no-network factory smoke**

Run:

```bash
uv run python -c "import config; config.ENABLE_TIKHUB=True; from main import CrawlerFactory; c=CrawlerFactory.create_crawler('xhs'); print(type(c).__name__, c.platform)"
```

Expected output contains:

```text
TikHubCrawler xhs
```

- [ ] **Step 4: Manual live TikHub smoke with user-provided token**

Run only when `TIKHUB_API_KEY` is configured and the user accepts possible TikHub billing:

```bash
uv run python main.py --platform xhs --type search --keywords 口红 --save_data_option jsonl --get_comment false
```

Expected: crawler starts without Playwright/CDP login, calls TikHub, and writes mapped JSONL or raw fallback JSONL.

- [ ] **Step 5: Commit final fixes**

```bash
git add .
git commit -m "test: verify tikhub integration"
```

## Self-Review

- Spec coverage: configuration, activation, client, endpoint registry, raw fallback, platform mapping, crawler flow, factory wiring, and tests are covered.
- Scope: limited to existing seven MediaCrawler platforms; no new external platforms are added.
- API key behavior: environment variable takes precedence over config.
- Unsupported capabilities: endpoint registry can mark capability unsupported and crawler logs warnings instead of failing whole run.
- Media binaries: plan does not download media binaries.
- Automated tests: all network behavior is mocked except the optional manual live smoke.

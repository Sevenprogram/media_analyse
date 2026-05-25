from __future__ import annotations

from typing import Any

import pytest

import config
from media_platform.tikhub import core as tikhub_core
from media_platform.tikhub.core import TikHubCrawler
from media_platform.tikhub.errors import TikHubValidationError


class FakeTikHubClient:
    def __init__(self, responses: dict[tuple[str, str], dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = json if json is not None else params
        assert payload is not None
        self.requests.append(
            {"method": method, "path": path, "json": json, "params": params, "payload": payload}
        )
        page_key = str(payload.get("page", payload.get("cursor", 0)))
        response = self.responses.get((str(payload.get("keyword")), page_key), {"items": []})
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self) -> None:
        return None


class FakeRawWriter:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def write(
        self,
        *,
        platform: str,
        crawler_type: str,
        entity_type: str,
        payload: Any,
        source_keyword: str,
        entity_id: str,
    ) -> None:
        self.rows.append(
            {
                "platform": platform,
                "crawler_type": crawler_type,
                "entity_type": entity_type,
                "payload": payload,
                "source_keyword": source_keyword,
                "entity_id": entity_id,
            }
        )


def _configure_search(
    monkeypatch: pytest.MonkeyPatch,
    *,
    keywords: str = "cat food",
    limit: int = 2,
    sort_mode: str = "relevance",
    time_preset: str = "all",
    time_start: str = "",
    time_end: str = "",
    max_extra_pages: int = 5,
) -> None:
    monkeypatch.setattr(config, "KEYWORDS", keywords)
    monkeypatch.setattr(config, "START_PAGE", 1)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", limit)
    monkeypatch.setattr(config, "CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM", limit, raising=False)
    monkeypatch.setattr(config, "CRAWLER_SEARCH_SORT_MODE", sort_mode, raising=False)
    monkeypatch.setattr(config, "CRAWLER_SEARCH_TIME_PRESET", time_preset, raising=False)
    monkeypatch.setattr(config, "CRAWLER_SEARCH_TIME_START", time_start, raising=False)
    monkeypatch.setattr(config, "CRAWLER_SEARCH_TIME_END", time_end, raising=False)
    monkeypatch.setattr(config, "CRAWLER_FILL_STRATEGY", "prefer_fill", raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_EXTRA_PAGES", max_extra_pages, raising=False)
    monkeypatch.setattr(config, "CRAWLER_PREFER_LATEST_POSTS", False, raising=False)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", False)
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0)


@pytest.mark.asyncio
async def test_search_caps_results_per_keyword_not_globally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_search(monkeypatch, keywords="alpha,beta", limit=1)
    saved: list[dict[str, Any]] = []

    async def save(item: dict[str, Any]) -> None:
        saved.append(item)

    monkeypatch.setattr(tikhub_core.xhs_store, "update_xhs_note", save)
    client = FakeTikHubClient(
        {
            ("alpha", "1"): {
                "items": [
                    {"id": "alpha-1", "title": "alpha 1", "time": 1_778_112_000},
                    {"id": "alpha-2", "title": "alpha 2", "time": 1_778_112_000},
                ]
            },
            ("beta", "1"): {
                "items": [
                    {"id": "beta-1", "title": "beta 1", "time": 1_778_112_000},
                    {"id": "beta-2", "title": "beta 2", "time": 1_778_112_000},
                ]
            },
        }
    )

    await TikHubCrawler("xhs", client=client).search()

    assert [item["note_id"] for item in saved] == ["alpha-1", "beta-1"]
    assert [request["payload"]["keyword"] for request in client.requests] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_xhs_prefer_fill_saves_exact_matches_before_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_search(
        monkeypatch,
        limit=2,
        sort_mode="most_liked",
        time_start="2026-05-01T00:00:00+00:00",
        time_end="2026-05-07T23:59:59+00:00",
    )
    saved: list[dict[str, Any]] = []

    async def save(item: dict[str, Any]) -> None:
        saved.append(item)

    monkeypatch.setattr(tikhub_core.xhs_store, "update_xhs_note", save)
    client = FakeTikHubClient(
        {
            ("cat food", "1"): {
                "items": [
                    {"id": "outside-first", "title": "outside", "time": 1_779_000_000},
                    {"id": "inside", "title": "inside", "time": 1_778_112_000},
                ]
            }
        }
    )

    await TikHubCrawler("xhs", client=client).search()

    assert [item["note_id"] for item in saved] == ["inside", "outside-first"]
    assert saved[0]["crawl_meta"]["within_requested_time_range"] is True
    assert saved[1]["crawl_meta"]["outside_requested_time_range"] is True
    assert saved[1]["crawl_meta"]["fill_reason"] == "fill_to_target"
    assert client.requests[0]["params"]["sort_type"] == "time_descending"
    assert client.requests[0]["params"]["filter_note_time"] == "\u4e0d\u9650"


@pytest.mark.asyncio
async def test_max_extra_pages_limits_deep_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_search(
        monkeypatch,
        limit=2,
        time_start="2026-05-01T00:00:00+00:00",
        time_end="2026-05-07T23:59:59+00:00",
        max_extra_pages=1,
    )
    saved: list[dict[str, Any]] = []

    async def save(item: dict[str, Any]) -> None:
        saved.append(item)

    monkeypatch.setattr(tikhub_core.xhs_store, "update_xhs_note", save)
    client = FakeTikHubClient(
        {
            ("cat food", "1"): {
                "items": [{"id": "outside", "title": "outside", "time": 1_779_000_000}],
                "has_more": True,
            },
            ("cat food", "2"): {
                "items": [{"id": "inside", "title": "inside", "time": 1_778_112_000}]
            },
        }
    )

    await TikHubCrawler("xhs", client=client).search()

    assert [item["note_id"] for item in saved] == ["outside"]
    assert len(client.requests) == 1


@pytest.mark.asyncio
async def test_douyin_prefer_fill_uses_json_body_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_search(
        monkeypatch,
        limit=2,
        time_start="2026-05-01T00:00:00+00:00",
        time_end="2026-05-07T23:59:59+00:00",
    )
    saved: list[dict[str, Any]] = []

    async def save(item: dict[str, Any]) -> None:
        saved.append(item)

    monkeypatch.setattr(tikhub_core.douyin_store, "update_douyin_aweme", save)
    client = FakeTikHubClient(
        {
            ("cat food", "0"): {
                "items": [
                    {"aweme_id": "dy-outside", "desc": "outside", "create_time": 1_779_000_000},
                    {"aweme_id": "dy-inside", "desc": "inside", "create_time": 1_778_112_000},
                ]
            }
        }
    )

    await TikHubCrawler("dy", client=client).search()

    assert [item["aweme_id"] for item in saved] == ["dy-inside", "dy-outside"]
    assert saved[0]["crawl_meta"]["within_requested_time_range"] is True
    assert saved[1]["crawl_meta"]["outside_requested_time_range"] is True
    assert client.requests[0]["json"]["sort_type"] == "2"
    assert client.requests[0]["json"]["publish_time"] == "0"
    assert client.requests[0]["params"] is None


@pytest.mark.asyncio
async def test_douyin_pagination_validation_error_keeps_partial_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_search(monkeypatch, limit=2, max_extra_pages=3)
    saved: list[dict[str, Any]] = []

    async def save(item: dict[str, Any]) -> None:
        saved.append(item)

    monkeypatch.setattr(tikhub_core.douyin_store, "update_douyin_aweme", save)
    client = FakeTikHubClient(
        {
            ("cat food", "0"): {
                "items": [
                    {"aweme_id": "dy-first", "desc": "first", "create_time": 1_778_112_000}
                ],
                "cursor": 20,
                "has_more": True,
            },
            ("cat food", "20"): TikHubValidationError(
                '{"detail":{"code":400,"params":{"keyword":"cat food","cursor":20}}}'
            ),
        }
    )

    await TikHubCrawler("dy", client=client).search()

    assert [item["aweme_id"] for item in saved] == ["dy-first"]
    assert [request["json"]["cursor"] for request in client.requests] == [0, "20"]


@pytest.mark.asyncio
async def test_xhs_deprecated_comments_endpoint_disables_remaining_comment_fetches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_search(monkeypatch, limit=2)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", True)
    saved: list[dict[str, Any]] = []

    async def save(item: dict[str, Any]) -> None:
        saved.append(item)

    monkeypatch.setattr(tikhub_core.xhs_store, "update_xhs_note", save)
    raw_writer = FakeRawWriter()
    client = FakeTikHubClient(
        {
            ("cat food", "1"): {
                "items": [
                    {"id": "xhs-1", "title": "first", "time": 1_778_112_000},
                    {"id": "xhs-2", "title": "second", "time": 1_778_112_000},
                ]
            },
            ("None", "0"): TikHubValidationError(
                '{"detail":{"code":400,"message":"This endpoint has been deprecated. '
                'Please migrate to the Xiaohongshu-App-V2-API series of APIs.",'
                '"router":"/api/v1/xiaohongshu/web/get_note_comments"}}'
            ),
        }
    )

    await TikHubCrawler("xhs", client=client, raw_writer=raw_writer).search()

    assert [item["note_id"] for item in saved] == ["xhs-1", "xhs-2"]
    comment_requests = [
        request
        for request in client.requests
        if request["path"] == "/api/v1/xiaohongshu/web/get_note_comments"
    ]
    assert len(comment_requests) == 1
    assert raw_writer.rows[0]["entity_type"] == "comment_fetch_disabled"
    assert "deprecated" in raw_writer.rows[0]["payload"]["reason"]

import pytest

import config
from media_platform.tikhub.core import TikHubCrawler
from media_platform.tikhub.endpoints import Capability, get_endpoint
from media_platform.tikhub.errors import TikHubValidationError


class FakeClient:
    def __init__(self):
        self.calls = []

    async def request(self, method, path, *, params=None, json=None):
        self.calls.append((method, path, params or {}))
        if "comments" in path:
            return {"comments": [{"id": "c1", "content": "hello", "user": {"id": "u2"}}]}
        return {
            "data": {
                "items": [
                    {
                        "model_type": "note",
                        "note": {
                            "id": "n1",
                            "title": "title",
                            "user": {"userid": "u1", "nickname": "nick"},
                        },
                    }
                ],
                "has_more": False,
            }
        }

    async def close(self):
        pass


class FakeRawWriter:
    def __init__(self):
        self.records = []

    async def write(self, **kwargs):
        self.records.append(kwargs)


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
    monkeypatch.setattr(config, "CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES", 10, raising=False)
    monkeypatch.setattr("store.xhs.update_xhs_note", save_note)
    monkeypatch.setattr("store.xhs.batch_update_xhs_note_comments", save_comments)

    crawler = TikHubCrawler(platform="xhs", client=FakeClient(), raw_writer=FakeRawWriter())
    await crawler.start()

    assert saved[0]["note_id"] == "n1"
    assert comments[0]["id"] == "c1"


def test_xhs_latest_search_params_override_tikhub_defaults(monkeypatch):
    monkeypatch.setattr(config, "CRAWLER_PREFER_LATEST_POSTS", True, raising=False)
    monkeypatch.setattr(config, "CRAWLER_SORT_TYPE", "time_descending", raising=False)
    monkeypatch.setattr(config, "CRAWLER_FILTER_NOTE_TIME", "一周内", raising=False)
    monkeypatch.setattr(config, "CRAWLER_COLLECTION_WINDOW_DAYS", 3, raising=False)

    crawler = TikHubCrawler(platform="xhs", client=FakeClient(), raw_writer=FakeRawWriter())
    params = crawler._search_params(get_endpoint("xhs", Capability.SEARCH), "K12", 1, "")

    assert params["keyword"] == "K12"
    assert params["sort_type"] == "time_descending"
    assert params["filter_note_time"] == "一周内"


@pytest.mark.asyncio
async def test_search_max_notes_count_is_global_across_keywords(monkeypatch):
    saved = []

    async def save_note(item):
        saved.append(item)

    class MultiKeywordClient(FakeClient):
        async def request(self, method, path, *, params=None, json=None):
            self.calls.append((method, path, params or {}))
            keyword = (params or {}).get("keyword") or (json or {}).get("keyword") or "kw"
            return {
                "data": {
                    "items": [
                        {
                            "note": {
                                "id": f"{keyword}-{index}",
                                "title": f"{keyword} title {index}",
                                "user": {"userid": "u1", "nickname": "nick"},
                            },
                        }
                        for index in range(3)
                    ],
                    "has_more": False,
                }
            }

    monkeypatch.setattr(config, "CRAWLER_TYPE", "search", raising=False)
    monkeypatch.setattr(config, "KEYWORDS", "kw1,kw2", raising=False)
    monkeypatch.setattr(config, "START_PAGE", 1, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 2, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0, raising=False)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", False, raising=False)
    monkeypatch.setattr("store.xhs.update_xhs_note", save_note)

    crawler = TikHubCrawler(platform="xhs", client=MultiKeywordClient(), raw_writer=FakeRawWriter())
    await crawler.start()

    assert [item["note_id"] for item in saved] == ["kw1-0", "kw1-1"]


@pytest.mark.asyncio
async def test_search_skips_comments_for_synthetic_xhs_note_id(monkeypatch):
    saved = []
    comments = []

    async def save_note(item):
        saved.append(item)

    async def save_comments(note_id, items):
        comments.extend(items)

    class SyntheticIdClient(FakeClient):
        async def request(self, method, path, *, params=None, json=None):
            self.calls.append((method, path, params or {}))
            if "comments" in path:
                raise AssertionError("synthetic xhs note ids should not fetch comments")
            return {
                "data": {
                    "items": [
                        {
                            "note": {
                                "title": "fallback-only note",
                                "user": {"userid": "u1", "nickname": "nick"},
                            },
                        }
                    ],
                    "has_more": False,
                }
            }

    raw_writer = FakeRawWriter()
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search", raising=False)
    monkeypatch.setattr(config, "KEYWORDS", "kw", raising=False)
    monkeypatch.setattr(config, "START_PAGE", 1, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 1, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0, raising=False)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", True, raising=False)
    monkeypatch.setattr("store.xhs.update_xhs_note", save_note)
    monkeypatch.setattr("store.xhs.batch_update_xhs_note_comments", save_comments)

    crawler = TikHubCrawler(platform="xhs", client=SyntheticIdClient(), raw_writer=raw_writer)
    await crawler.start()

    assert saved[0]["note_id"].startswith("tikhub_xhs_")
    assert comments == []
    assert raw_writer.records[0]["entity_type"] == "comment_skipped_synthetic_id"


@pytest.mark.asyncio
async def test_comment_validation_error_does_not_fail_search(monkeypatch):
    saved = []

    async def save_note(item):
        saved.append(item)

    class RejectingCommentsClient(FakeClient):
        async def request(self, method, path, *, params=None, json=None):
            self.calls.append((method, path, params or {}))
            if "comments" in path:
                raise TikHubValidationError("bad comment request")
            return await super().request(method, path, params=params, json=json)

    raw_writer = FakeRawWriter()
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search", raising=False)
    monkeypatch.setattr(config, "KEYWORDS", "kw", raising=False)
    monkeypatch.setattr(config, "START_PAGE", 1, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 1, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0, raising=False)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", True, raising=False)
    monkeypatch.setattr("store.xhs.update_xhs_note", save_note)

    crawler = TikHubCrawler(platform="xhs", client=RejectingCommentsClient(), raw_writer=raw_writer)
    await crawler.start()

    assert saved[0]["note_id"] == "n1"
    assert raw_writer.records[0]["entity_type"] == "comment_fetch_rejected"

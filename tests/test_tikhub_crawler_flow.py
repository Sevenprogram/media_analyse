import pytest

import config
from media_platform.tikhub.core import TikHubCrawler


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

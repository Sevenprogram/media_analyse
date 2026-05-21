import json

import pytest

import config
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


@pytest.mark.asyncio
async def test_raw_writer_uses_d1_when_configured(monkeypatch, tmp_path):
    calls = []

    async def fake_store_raw_record(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "d1", raising=False)
    monkeypatch.setattr("media_platform.tikhub.raw_writer.store_raw_record", fake_store_raw_record)
    writer = TikHubRawWriter(base_dir=tmp_path)

    await writer.write(
        platform="xhs",
        crawler_type="search",
        entity_type="content",
        payload={"id": "1"},
        source_keyword="kw",
        entity_id="1",
    )

    assert calls[0]["platform"] == "xhs"
    assert calls[0]["entity_id"] == "1"
    assert not list(tmp_path.glob("*.jsonl"))

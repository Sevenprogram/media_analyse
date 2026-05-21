import json

import httpx
import pytest

import config
from store.d1_store import CloudflareD1Client, D1Schema, D1StoreImplement, store_raw_record


@pytest.fixture(autouse=True)
def reset_d1_schema():
    D1Schema._initialized = False


def _d1_client(monkeypatch, seen):
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        seen.append(payload)
        assert request.headers["Authorization"] == "Bearer token"
        assert request.url.path == "/client/v4/accounts/account/d1/database/database/query"
        return httpx.Response(200, json={"success": True, "result": [{"success": True}]})

    monkeypatch.setattr(config, "CLOUDFLARE_ACCOUNT_ID", "account", raising=False)
    monkeypatch.setattr(config, "CLOUDFLARE_D1_DATABASE_ID", "database", raising=False)
    monkeypatch.setenv("CLOUDFLARE_D1_API_TOKEN", "token")
    return CloudflareD1Client(
        base_url="https://api.cloudflare.com/client/v4",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_d1_store_creates_schema_and_writes_xhs_content(monkeypatch):
    seen = []
    client = _d1_client(monkeypatch, seen)
    store = D1StoreImplement("xhs", client=client)

    await store.store_content({
        "note_id": "note-1",
        "title": "Title",
        "desc": "Desc",
        "user_id": "user-1",
        "nickname": "Nick",
        "source_keyword": "kw",
    })
    await client.close()

    sql_text = "\n".join(item["sql"] for item in seen)
    assert "CREATE TABLE IF NOT EXISTS xhs_notes" in sql_text
    assert "CREATE TABLE IF NOT EXISTS xhs_comments" in sql_text
    assert "INSERT INTO xhs_notes" in sql_text
    insert_payload = seen[-1]
    assert insert_payload["params"][0] == "xhs:content:note-1"
    assert insert_payload["params"][1] == "note-1"


@pytest.mark.asyncio
async def test_d1_raw_record_writes_crawler_raw_table(monkeypatch):
    seen = []
    client = _d1_client(monkeypatch, seen)

    await store_raw_record(
        platform="xhs",
        crawler_type="search",
        entity_type="content",
        entity_id="note-1",
        source_keyword="kw",
        payload={"note_id": "note-1"},
        client=client,
    )
    await client.close()

    sql_text = "\n".join(item["sql"] for item in seen)
    assert "CREATE TABLE IF NOT EXISTS crawler_raw_records" in sql_text
    assert "INSERT INTO crawler_raw_records" in sql_text
    assert seen[-1]["params"][0] == "xhs:raw:content:note-1"

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

import config
from base.base_crawler import AbstractStore


CONTENT_TABLES = {
    "xhs": ("xhs_notes", "note_id"),
    "dy": ("douyin_awemes", "aweme_id"),
    "ks": ("kuaishou_videos", "video_id"),
    "bili": ("bilibili_videos", "video_id"),
    "wb": ("weibo_notes", "note_id"),
    "tieba": ("tieba_notes", "note_id"),
    "zhihu": ("zhihu_contents", "content_id"),
}

COMMENT_TABLES = {
    "xhs": ("xhs_comments", "comment_id", "note_id"),
    "dy": ("douyin_comments", "comment_id", "aweme_id"),
    "ks": ("kuaishou_comments", "comment_id", "video_id"),
    "bili": ("bilibili_comments", "comment_id", "video_id"),
    "wb": ("weibo_comments", "comment_id", "note_id"),
    "tieba": ("tieba_comments", "comment_id", "note_id"),
    "zhihu": ("zhihu_comments", "comment_id", "content_id"),
}


class D1ConfigError(RuntimeError):
    pass


def resolve_cloudflare_d1_api_token() -> str:
    return os.getenv("CLOUDFLARE_D1_API_TOKEN") or getattr(
        config, "CLOUDFLARE_D1_API_TOKEN", ""
    )


class CloudflareD1Client:
    def __init__(
        self,
        account_id: Optional[str] = None,
        database_id: Optional[str] = None,
        api_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.account_id = account_id or config.CLOUDFLARE_ACCOUNT_ID
        self.database_id = database_id or config.CLOUDFLARE_D1_DATABASE_ID
        self.api_token = api_token or resolve_cloudflare_d1_api_token()
        if not self.account_id or not self.database_id or not self.api_token:
            raise D1ConfigError(
                "Cloudflare D1 storage requires CLOUDFLARE_ACCOUNT_ID, "
                "CLOUDFLARE_D1_DATABASE_ID, and CLOUDFLARE_D1_API_TOKEN."
            )

        self.base_url = (base_url or config.CLOUDFLARE_D1_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout or config.CLOUDFLARE_D1_TIMEOUT_SECONDS,
            transport=transport,
            headers={"Authorization": f"Bearer {self.api_token}"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def query(self, sql: str, params: Optional[list[Any]] = None) -> Any:
        path = f"/accounts/{self.account_id}/d1/database/{self.database_id}/query"
        response = await self._client.post(path, json={"sql": sql, "params": params or []})
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(f"Cloudflare D1 query failed: {payload}")
        return payload


class D1Schema:
    _initialized = False

    CONTENT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
      id TEXT PRIMARY KEY,
      entity_id TEXT,
      title TEXT,
      content TEXT,
      user_id TEXT,
      nickname TEXT,
      source_keyword TEXT,
      publish_time TEXT,
      payload_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """

    COMMENT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
      id TEXT PRIMARY KEY,
      entity_id TEXT,
      parent_entity_id TEXT,
      content TEXT,
      user_id TEXT,
      nickname TEXT,
      source_keyword TEXT,
      publish_time TEXT,
      payload_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """

    @classmethod
    async def ensure(cls, client: CloudflareD1Client) -> None:
        if cls._initialized:
            return
        for table, _ in CONTENT_TABLES.values():
            await client.query(cls.CONTENT_SCHEMA.format(table=table))
        for table, _, _ in COMMENT_TABLES.values():
            await client.query(cls.COMMENT_SCHEMA.format(table=table))
        await client.query(
            """
            CREATE TABLE IF NOT EXISTS platform_creators (
              id TEXT PRIMARY KEY,
              platform TEXT NOT NULL,
              user_id TEXT,
              nickname TEXT,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        await client.query(
            """
            CREATE TABLE IF NOT EXISTS crawler_raw_records (
              id TEXT PRIMARY KEY,
              platform TEXT NOT NULL,
              crawler_type TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              entity_id TEXT,
              source_keyword TEXT,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        cls._initialized = True


class D1StoreImplement(AbstractStore):
    def __init__(self, platform: str, client: Optional[CloudflareD1Client] = None):
        self.platform = platform
        self._owns_client = client is None
        self.client = client or CloudflareD1Client()

    async def store_content(self, content_item: dict):
        try:
            table, id_key = CONTENT_TABLES[self.platform]
            entity_id = str(content_item.get(id_key) or content_item.get("id") or "")
            if not entity_id:
                return
            await D1Schema.ensure(self.client)
            await self._upsert_record(
                table=table,
                record_id=f"{self.platform}:content:{entity_id}",
                entity_id=entity_id,
                title=self._title(content_item),
                content=self._content(content_item),
                user_id=str(content_item.get("user_id") or ""),
                nickname=str(content_item.get("nickname") or ""),
                source_keyword=str(content_item.get("source_keyword") or ""),
                publish_time=str(content_item.get("create_time") or content_item.get("time") or ""),
                payload=content_item,
            )
        finally:
            await self._close_if_owned()

    async def store_comment(self, comment_item: dict):
        try:
            table, id_key, parent_key = COMMENT_TABLES[self.platform]
            comment_id = str(comment_item.get(id_key) or comment_item.get("id") or "")
            if not comment_id:
                return
            await D1Schema.ensure(self.client)
            await self._upsert_comment(
                table=table,
                record_id=f"{self.platform}:comment:{comment_id}",
                entity_id=comment_id,
                parent_entity_id=str(comment_item.get(parent_key) or ""),
                content=self._content(comment_item),
                user_id=str(comment_item.get("user_id") or ""),
                nickname=str(comment_item.get("nickname") or ""),
                source_keyword=str(comment_item.get("source_keyword") or ""),
                publish_time=str(comment_item.get("create_time") or comment_item.get("publish_time") or ""),
                payload=comment_item,
            )
        finally:
            await self._close_if_owned()

    async def store_creator(self, creator: dict):
        try:
            user_id = str(creator.get("user_id") or creator.get("id") or "")
            if not user_id:
                return
            await D1Schema.ensure(self.client)
            now = _now()
            await self.client.query(
                """
                INSERT INTO platform_creators
                  (id, platform, user_id, nickname, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  nickname=excluded.nickname,
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                [
                    f"{self.platform}:creator:{user_id}",
                    self.platform,
                    user_id,
                    str(creator.get("nickname") or creator.get("user_nickname") or ""),
                    _json(creator),
                    now,
                    now,
                ],
            )
        finally:
            await self._close_if_owned()

    async def close(self) -> None:
        await self.client.close()

    async def _close_if_owned(self) -> None:
        if self._owns_client:
            await self.client.close()

    async def _upsert_record(
        self,
        *,
        table: str,
        record_id: str,
        entity_id: str,
        title: str,
        content: str,
        user_id: str,
        nickname: str,
        source_keyword: str,
        publish_time: str,
        payload: dict,
    ) -> None:
        now = _now()
        await self.client.query(
            f"""
            INSERT INTO {table}
              (id, entity_id, title, content, user_id, nickname, source_keyword,
               publish_time, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,
              content=excluded.content,
              user_id=excluded.user_id,
              nickname=excluded.nickname,
              source_keyword=excluded.source_keyword,
              publish_time=excluded.publish_time,
              payload_json=excluded.payload_json,
              updated_at=excluded.updated_at
            """,
            [
                record_id,
                entity_id,
                title,
                content,
                user_id,
                nickname,
                source_keyword,
                publish_time,
                _json(payload),
                now,
                now,
            ],
        )

    async def _upsert_comment(
        self,
        *,
        table: str,
        record_id: str,
        entity_id: str,
        parent_entity_id: str,
        content: str,
        user_id: str,
        nickname: str,
        source_keyword: str,
        publish_time: str,
        payload: dict,
    ) -> None:
        now = _now()
        await self.client.query(
            f"""
            INSERT INTO {table}
              (id, entity_id, parent_entity_id, content, user_id, nickname,
               source_keyword, publish_time, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              parent_entity_id=excluded.parent_entity_id,
              content=excluded.content,
              user_id=excluded.user_id,
              nickname=excluded.nickname,
              source_keyword=excluded.source_keyword,
              publish_time=excluded.publish_time,
              payload_json=excluded.payload_json,
              updated_at=excluded.updated_at
            """,
            [
                record_id,
                entity_id,
                parent_entity_id,
                content,
                user_id,
                nickname,
                source_keyword,
                publish_time,
                _json(payload),
                now,
                now,
            ],
        )

    def _title(self, item: dict) -> str:
        return str(item.get("title") or item.get("desc") or item.get("content") or "")[:500]

    def _content(self, item: dict) -> str:
        return str(item.get("content") or item.get("desc") or item.get("title") or "")[:2000]


async def store_raw_record(
    *,
    platform: str,
    crawler_type: str,
    entity_type: str,
    payload: Any,
    source_keyword: str = "",
    entity_id: str = "",
    client: Optional[CloudflareD1Client] = None,
) -> None:
    d1_client = client or CloudflareD1Client()
    await D1Schema.ensure(d1_client)
    now = _now()
    await d1_client.query(
        """
        INSERT INTO crawler_raw_records
          (id, platform, crawler_type, entity_type, entity_id, source_keyword, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          payload_json=excluded.payload_json,
          source_keyword=excluded.source_keyword
        """,
        [
            f"{platform}:raw:{entity_type}:{entity_id or now}",
            platform,
            crawler_type,
            entity_type,
            entity_id,
            source_keyword,
            _json(payload),
            now,
        ],
    )
    if client is None:
        await d1_client.close()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

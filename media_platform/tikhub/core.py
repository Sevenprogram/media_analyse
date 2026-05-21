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
from .endpoints import Capability, EndpointSpec, get_endpoint, supports_capability
from .mappers import get_mapper
from .raw_writer import TikHubRawWriter


class TikHubCrawler:
    def __init__(
        self,
        platform: str,
        client: Optional[TikHubClient] = None,
        raw_writer: Optional[TikHubRawWriter] = None,
    ) -> None:
        self.platform = platform
        self.client = client
        self.mapper = get_mapper(platform)
        self.raw_writer = raw_writer

    async def start(self) -> None:
        crawler_type_var.set(config.CRAWLER_TYPE)
        if self.client is None:
            self.client = TikHubClient()

        try:
            if config.CRAWLER_TYPE == "search":
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_notes()
            else:
                raise ValueError(f"Unsupported TikHub crawler type: {config.CRAWLER_TYPE}")
        finally:
            await self.client.close()

    async def search(self) -> None:
        endpoint = get_endpoint(self.platform, Capability.SEARCH)
        max_count = max(int(config.CRAWLER_MAX_NOTES_COUNT), 1)
        for keyword in [item.strip() for item in config.KEYWORDS.split(",") if item.strip()]:
            source_keyword_var.set(keyword)
            saved_count = 0
            page = int(config.START_PAGE)
            cursor = ""
            while saved_count < max_count:
                params = self._search_params(endpoint, keyword, page, cursor)
                data = await self.client.request(
                    endpoint.method,
                    endpoint.path,
                    json=params if endpoint.json_body else None,
                    params=None if endpoint.json_body else params,
                )
                items = self._extract_items(data)
                if not items:
                    break

                for item in items:
                    mapped = self.mapper.map_content(item, source_keyword=keyword)
                    await self._save_content(mapped)
                    saved_count += 1
                    if config.ENABLE_GET_COMMENTS:
                        await self._fetch_and_save_comments(mapped)
                    if saved_count >= max_count:
                        break

                cursor = self._next_cursor(data)
                if not cursor and not self._has_more(data):
                    break
                page += 1
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

    async def get_specified_notes(self) -> None:
        endpoint = get_endpoint(self.platform, Capability.DETAIL)
        for content_id in self._specified_ids():
            data = await self.client.request(
                endpoint.method,
                endpoint.path,
                params=self._content_params(endpoint, content_id),
            )
            item = self._extract_detail(data, fallback_id=content_id)
            mapped = self.mapper.map_content(item, source_keyword="")
            await self._save_content(mapped)
            if config.ENABLE_GET_COMMENTS:
                await self._fetch_and_save_comments(mapped)
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

    async def get_creators_and_notes(self) -> None:
        endpoint = get_endpoint(self.platform, Capability.CREATOR)
        for creator_id in self._creator_ids():
            data = await self.client.request(
                endpoint.method,
                endpoint.path,
                params=self._creator_params(endpoint, creator_id, page=1),
            )
            creator_payload = self._extract_creator(data, creator_id)
            await self._save_creator(self.mapper.map_creator(creator_payload))

            for item in self._extract_items(data):
                mapped = self.mapper.map_content(item, source_keyword="")
                await self._save_content(mapped)
                if config.ENABLE_GET_COMMENTS:
                    await self._fetch_and_save_comments(mapped)
            await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

    async def _fetch_and_save_comments(self, mapped_content: Any) -> None:
        if not supports_capability(self.platform, Capability.COMMENTS):
            utils.logger.warning(f"[TikHubCrawler] Comments unsupported for {self.platform}")
            return

        endpoint = get_endpoint(self.platform, Capability.COMMENTS)
        content_id = self._content_id(mapped_content)
        if not content_id:
            await self._write_raw("content_missing_id", mapped_content)
            return

        data = await self.client.request(
            endpoint.method,
            endpoint.path,
            params=self._content_params(endpoint, content_id),
        )
        comments = [
            self.mapper.map_comment(item, content_id=content_id)
            for item in self._extract_comments(data)
        ][: int(config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES)]
        if comments:
            await self._save_comments(content_id, comments)

        if config.ENABLE_GET_SUB_COMMENTS and not supports_capability(
            self.platform, Capability.SUB_COMMENTS
        ):
            utils.logger.warning(f"[TikHubCrawler] Sub-comments unsupported for {self.platform}")

    def _search_params(
        self, endpoint: EndpointSpec, keyword: str, page: int, cursor: str
    ) -> dict[str, Any]:
        params = dict(endpoint.default_params)
        params[endpoint.keyword_param] = keyword
        if endpoint.cursor_param and cursor:
            params[endpoint.cursor_param] = cursor
        elif endpoint.cursor_param:
            params.setdefault(endpoint.cursor_param, 0)
        elif endpoint.page_param:
            params[endpoint.page_param] = page
        return params

    def _content_params(self, endpoint: EndpointSpec, content_id: str) -> dict[str, Any]:
        params = dict(endpoint.default_params)
        params[endpoint.content_param] = content_id
        return params

    def _creator_params(
        self, endpoint: EndpointSpec, creator_id: str, page: int
    ) -> dict[str, Any]:
        params = dict(endpoint.default_params)
        params[endpoint.creator_param] = creator_id
        params[endpoint.page_param] = page
        return params

    def _extract_items(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in (
            "items",
            "list",
            "data",
            "notes",
            "videos",
            "aweme_list",
            "results",
            "feeds",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested_items = self._extract_items(value)
                if nested_items:
                    return nested_items
        return [data] if data else []

    def _extract_comments(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("comments", "list", "data", "items", "replies"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested_comments = self._extract_comments(value)
                if nested_comments:
                    return nested_comments
        return []

    def _extract_detail(self, data: Any, fallback_id: str) -> dict[str, Any]:
        if isinstance(data, dict):
            for key in ("item", "note", "aweme_detail", "video", "post", "detail"):
                value = data.get(key)
                if isinstance(value, dict):
                    return value
            return data
        return {"id": fallback_id, "raw": data}

    def _extract_creator(self, data: Any, creator_id: str) -> dict[str, Any]:
        if isinstance(data, dict):
            for key in ("user", "author", "creator", "profile"):
                value = data.get(key)
                if isinstance(value, dict):
                    return value
            return data
        return {"id": creator_id}

    def _next_cursor(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        for key in ("cursor", "next_cursor", "max_id", "pcursor", "offset", "next"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _has_more(self, data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        return bool(data.get("has_more") or data.get("hasMore"))

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
        return [str(item) for item in getattr(config, attr, [])]

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
        return [str(item) for item in getattr(config, attr, [])]

    def _content_id(self, item: Any) -> str:
        if hasattr(item, "note_id"):
            return str(item.note_id)
        if hasattr(item, "content_id"):
            return str(item.content_id)
        if isinstance(item, dict):
            for key in ("note_id", "aweme_id", "content_id"):
                if item.get(key):
                    return str(item[key])
            if isinstance(item.get("photo"), dict) and item["photo"].get("id"):
                return str(item["photo"]["id"])
            if isinstance(item.get("View"), dict) and item["View"].get("aid"):
                return str(item["View"]["aid"])
            if isinstance(item.get("mblog"), dict) and item["mblog"].get("id"):
                return str(item["mblog"]["id"])
        return ""

    async def _save_content(self, item: Any) -> None:
        try:
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
                await tieba_store.update_tieba_note(item)
            elif self.platform == "zhihu":
                await zhihu_store.update_zhihu_content(item)
        except Exception as exc:
            utils.logger.warning(f"[TikHubCrawler] Store content failed, writing raw fallback: {exc}")
            await self._write_raw("content", item)

    async def _save_comments(self, content_id: str, comments: list[Any]) -> None:
        try:
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
            elif self.platform == "tieba":
                await tieba_store.batch_update_tieba_note_comments(content_id, comments)
            elif self.platform == "zhihu":
                await zhihu_store.batch_update_zhihu_note_comments(comments)
        except Exception as exc:
            utils.logger.warning(f"[TikHubCrawler] Store comments failed, writing raw fallback: {exc}")
            await self._write_raw("comment", comments, content_id)

    async def _save_creator(self, creator: Any) -> None:
        try:
            if self.platform == "xhs":
                await xhs_store.save_creator(self._creator_id(creator), creator)
            elif self.platform == "dy":
                await douyin_store.save_creator(self._creator_id(creator), creator)
            elif self.platform == "ks":
                await kuaishou_store.save_creator(self._creator_id(creator), creator)
            elif self.platform == "wb":
                await weibo_store.save_creator(self._creator_id(creator), creator)
            elif self.platform == "tieba":
                await tieba_store.save_creator(creator)
            elif self.platform == "zhihu":
                await zhihu_store.save_creator(creator)
        except Exception as exc:
            utils.logger.warning(f"[TikHubCrawler] Store creator failed, writing raw fallback: {exc}")
            await self._write_raw("creator", creator, self._creator_id(creator))

    def _creator_id(self, creator: Any) -> str:
        if hasattr(creator, "user_id"):
            return str(creator.user_id)
        if isinstance(creator, dict):
            if creator.get("user_id"):
                return str(creator["user_id"])
            if isinstance(creator.get("user"), dict):
                return str(creator["user"].get("uid") or creator["user"].get("id") or "")
        return ""

    async def _write_raw(
        self, entity_type: str, payload: Any, entity_id: str = ""
    ) -> None:
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        if self.raw_writer is None:
            self.raw_writer = TikHubRawWriter()
        await self.raw_writer.write(
            platform=self.platform,
            crawler_type=config.CRAWLER_TYPE,
            entity_type=entity_type,
            payload=payload,
            source_keyword=source_keyword_var.get(),
            entity_id=entity_id or self._content_id(payload),
        )

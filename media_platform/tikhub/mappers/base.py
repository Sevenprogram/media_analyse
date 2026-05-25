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


def first_url(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(pick(first, "url", "url_default", "src"))
    if isinstance(value, dict):
        urls = value.get("url_list")
        if isinstance(urls, list) and urls:
            return str(urls[0])
        return str(pick(value, "url", "url_default", "src", "uri"))
    return ""


def raw(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def author(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("author", "user", "owner", "member"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


class BaseTikHubMapper:
    platform: str

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> Any:
        raise NotImplementedError

    def map_comment(self, item: dict[str, Any], content_id: str) -> Any:
        raise NotImplementedError

    def map_creator(self, item: dict[str, Any]) -> Any:
        user = author(item) or item
        return {
            "user_id": str(pick(user, "id", "user_id", "uid", "mid", "sec_user_id")),
            "nickname": str(pick(user, "nickname", "name", "screen_name", "uname")),
            "avatar": first_url(pick(user, "avatar", "avatar_url", "face", "profile_image_url")),
            "desc": str(pick(user, "desc", "description", "signature", "bio")),
            "raw_data": raw(item),
        }

import hashlib
import re
from typing import Any

from .base import BaseTikHubMapper, author, first_url, nested, pick, raw


class XhsTikHubMapper(BaseTikHubMapper):
    platform = "xhs"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        original = item
        item = _unwrap_note(item)
        user = author(item)
        title = str(pick(item, "title", "displayTitle", "display_title"))
        xsec_token = _xsec_token(item)
        note_id = str(pick(item, "note_id", "noteId", "id", default=""))
        if not note_id:
            note_id = _fallback_note_id(item, title, xsec_token)
        image_list = pick(item, "image_list", "images", "images_list", "cover", default=[])
        if isinstance(image_list, dict):
            image_list = [image_list]
        if isinstance(image_list, list):
            image_list = [_normalize_image(image) for image in image_list]
        return {
            "note_id": note_id,
            "type": str(pick(item, "type", "note_type", default="normal")),
            "title": title,
            "desc": str(pick(item, "desc", "content", "text", "displayTitle", "display_title")),
            "video": pick(item, "video", default={}),
            "time": pick(item, "time", "create_time", "createTime", "timestamp", default=""),
            "last_update_time": pick(item, "last_update_time", "update_time", default=0),
            "user": {
                "user_id": str(pick(user, "user_id", "userId", "id", "userid", "red_id")),
                "nickname": str(pick(user, "nickname", "nickName", "name")),
                "avatar": first_url(pick(user, "avatar", "avatar_url", "image", "images")),
            },
            "interact_info": {
                "liked_count": _metric_count(
                    item,
                    ("stats", "like_count"),
                    ("interact_info", "liked_count"),
                    ("interactInfo", "likedCount"),
                    fallback_keys=("liked_count", "like_count", "likes", "nice_count"),
                ),
                "collected_count": _metric_count(
                    item,
                    ("interact_info", "collected_count"),
                    ("interactInfo", "collectedCount"),
                    fallback_keys=("collected_count", "collect_count"),
                ),
                "comment_count": _metric_count(
                    item,
                    ("stats", "comment_count"),
                    ("interact_info", "comment_count"),
                    ("interactInfo", "commentCount"),
                    fallback_keys=("comment_count", "comments_count"),
                ),
                "share_count": _metric_count(
                    item,
                    ("interact_info", "share_count"),
                    ("interactInfo", "shareCount"),
                    fallback_keys=("share_count", "shared_count"),
                ),
            },
            "ip_location": str(pick(item, "ip_location")),
            "image_list": image_list,
            "tag_list": pick(item, "tag_list", "tags", default=[]),
            "note_url": _note_url(item, note_id),
            "source_keyword": source_keyword,
            "xsec_token": xsec_token,
            "raw_data": raw(original),
        }

    def map_comment(self, item: dict[str, Any], content_id: str) -> dict[str, Any]:
        user = author(item)
        return {
            "id": str(pick(item, "comment_id", "id")),
            "create_time": pick(item, "create_time", "time", "timestamp", default=0),
            "ip_location": str(pick(item, "ip_location")),
            "content": str(pick(item, "content", "text")),
            "user_info": {
                "user_id": str(pick(user, "user_id", "id")),
                "nickname": str(pick(user, "nickname", "name")),
                "image": first_url(pick(user, "avatar", "avatar_url", "image")),
            },
            "sub_comment_count": pick(item, "sub_comment_count", "reply_count", default=0),
            "pictures": pick(item, "pictures", "images", default=[]),
            "target_comment": {"id": pick(item, "parent_comment_id", default=0)},
            "like_count": pick(item, "like_count", "liked_count", default=0),
            "raw_data": raw(item),
        }

    def map_creator(self, item: dict[str, Any]) -> dict[str, Any]:
        user = author(item) or item
        interactions = pick(user, "interactions", default=pick(item, "interactions", default=[]))
        liked = pick(user, "liked", "liked_count", "like_count", default=pick(item, "liked", "liked_count", "like_count", default=0))
        collected = pick(user, "collected", "collected_count", "collect_count", default=pick(item, "collected", "collected_count", "collect_count", default=0))
        interaction_default = pick(
            user,
            "interaction",
            "total_liked_count",
            default=pick(item, "interaction", "total_liked_count", default=liked),
        )
        return {
            "user_id": str(pick(user, "user_id", "userId", "id", "userid", "red_id")),
            "basicInfo": {
                "nickname": str(pick(user, "nickname", "name")),
                "gender": pick(user, "gender", default=None),
                "images": first_url(pick(user, "avatar", "avatar_url", "image")),
                "desc": str(pick(user, "desc", "description", "bio", default=nested(item, "share_info", "content"))),
                "ipLocation": str(pick(user, "ip_location")),
            },
            "interactions": [
                {"type": "follows", "count": _interaction_count(interactions, "follows", pick(user, "follows", "following_count", default=pick(item, "follows", default=0)))},
                {"type": "fans", "count": _interaction_count(interactions, "fans", pick(user, "fans", "followers_count", "follower_count", default=pick(item, "fans", default=0)))},
                {"type": "interaction", "count": _interaction_count(interactions, "interaction", interaction_default)},
                {"type": "liked", "count": liked},
                {"type": "collected", "count": pick(user, "collected_count", "collect_count", "favorite_count", "favorites_count", default=collected)},
                {"type": "notes", "count": pick(user, "notes_count", "note_count", "posts_count", default=0)},
            ],
            "tags": pick(user, "tags", default=[]),
            "raw_data": raw(item),
        }


def _unwrap_note(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    current = item
    for _ in range(8):
        next_item = _next_note_wrapper(current)
        if next_item is None:
            return current
        current = next_item
    return current


def _next_note_wrapper(item: dict[str, Any]) -> dict[str, Any] | None:
    for key in (
        "note",
        "note_card",
        "noteCard",
        "note_info",
        "noteInfo",
        "item",
        "card",
        "detail",
        "post",
        "data",
        "result",
    ):
        value = item.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            first = next((entry for entry in value if isinstance(entry, dict)), None)
            if first is not None:
                return first
    return None


def author_from_item(item: dict[str, Any]) -> dict[str, Any]:
    item = _unwrap_note(item)
    user = author(item)
    if not isinstance(user, dict):
        return {}
    return {
        "user_id": str(pick(user, "user_id", "userId", "id", "userid", "red_id")),
        "nickname": str(pick(user, "nickname", "nickName", "name")),
        "avatar": first_url(pick(user, "avatar", "avatar_url", "image", "images")),
    }


def _normalize_image(image: Any) -> dict[str, Any]:
    if not isinstance(image, dict):
        url = str(image or "")
        return {"url": url, "url_default": url}

    normalized = dict(image)
    url = first_url(normalized)
    if not normalized.get("url"):
        normalized["url"] = url
    if not normalized.get("url_default"):
        normalized["url_default"] = url
    return normalized


def _fallback_note_id(item: dict[str, Any], title: str, xsec_token: str) -> str:
    stable = "|".join(part for part in (xsec_token, title, raw(item)) if part)
    digest = hashlib.sha1(stable.encode("utf-8")).hexdigest()[:24]
    return f"tikhub_xhs_{digest}"


def _xsec_token(item: dict[str, Any]) -> str:
    return str(
        pick(
            item,
            "xsec_token",
            "xsecToken",
            "xsec_token_value",
            "xsecTokenValue",
            default=_deep_pick(
                item,
                {"xsec_token", "xsecToken", "xsec_token_value", "xsecTokenValue"},
            ),
        )
    )


def _note_url(item: dict[str, Any], note_id: str) -> str:
    return str(
        pick(
            item,
            "note_url",
            "noteUrl",
            "url",
            "share_url",
            "shareUrl",
            default=nested(
                item,
                "share_info",
                "share_url",
                default=nested(
                    item,
                    "shareInfo",
                    "shareUrl",
                    default=f"https://www.xiaohongshu.com/explore/{note_id}",
                ),
            ),
        )
    )


def _metric_count(
    item: dict[str, Any],
    *paths: tuple[str, ...],
    fallback_keys: tuple[str, ...],
) -> int:
    for path in paths:
        value = nested(item, *path)
        if value not in (None, ""):
            return _count(value)
    return _count(pick(item, *fallback_keys, default=0))


def _deep_pick(payload: Any, keys: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and value not in (None, "") and not isinstance(value, (dict, list)):
                return value
        for value in payload.values():
            nested_value = _deep_pick(value, keys)
            if nested_value not in (None, ""):
                return nested_value
    elif isinstance(payload, list):
        for item in payload:
            nested_value = _deep_pick(item, keys)
            if nested_value not in (None, ""):
                return nested_value
    return ""


def _count(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith("k") or text.endswith("K"):
        multiplier = 1000
        text = text[:-1]
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 0
    return int(float(match.group(0)) * multiplier)


def _interaction_count(interactions: Any, interaction_type: str, default: Any = 0) -> Any:
    if isinstance(interactions, list):
        for item in interactions:
            if isinstance(item, dict) and item.get("type") == interaction_type:
                return item.get("count", default)
    return default

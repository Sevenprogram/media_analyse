from typing import Any

from .base import BaseTikHubMapper, author, first_url, nested, pick, raw


class XhsTikHubMapper(BaseTikHubMapper):
    platform = "xhs"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        original = item
        item = _unwrap_note(item)
        user = author(item)
        note_id = str(pick(item, "note_id", "id"))
        image_list = pick(item, "image_list", "images", "images_list", default=[])
        if isinstance(image_list, list):
            image_list = [_normalize_image(image) for image in image_list]
        return {
            "note_id": note_id,
            "type": str(pick(item, "type", "note_type", default="normal")),
            "title": str(pick(item, "title")),
            "desc": str(pick(item, "desc", "content", "text")),
            "video": pick(item, "video", default={}),
            "time": pick(item, "time", "create_time", "timestamp", default=0),
            "last_update_time": pick(item, "last_update_time", "update_time", default=0),
            "user": {
                "user_id": str(pick(user, "user_id", "id", "userid", "red_id")),
                "nickname": str(pick(user, "nickname", "name")),
                "avatar": first_url(pick(user, "avatar", "avatar_url", "image", "images")),
            },
            "interact_info": {
                "liked_count": nested(item, "stats", "like_count", default=pick(item, "liked_count", "like_count", default=0)),
                "collected_count": pick(item, "collected_count", "collect_count", default=0),
                "comment_count": nested(item, "stats", "comment_count", default=pick(item, "comment_count", "comments_count", default=0)),
                "share_count": nested(item, "stats", "share_count", default=pick(item, "share_count", "shared_count", default=0)),
            },
            "ip_location": str(pick(item, "ip_location")),
            "image_list": image_list,
            "tag_list": pick(item, "tag_list", "tags", default=[]),
            "note_url": str(pick(item, "note_url", "url", "share_url", default=f"https://www.xiaohongshu.com/explore/{note_id}")),
            "source_keyword": source_keyword,
            "xsec_token": str(pick(item, "xsec_token")),
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
        return {
            "basicInfo": {
                "nickname": str(pick(user, "nickname", "name")),
                "gender": pick(user, "gender", default=None),
                "images": first_url(pick(user, "avatar", "avatar_url", "image")),
                "desc": str(pick(user, "desc", "description", "bio")),
                "ipLocation": str(pick(user, "ip_location")),
            },
            "interactions": [
                {"type": "follows", "count": pick(user, "follows", "following_count", default=0)},
                {"type": "fans", "count": pick(user, "fans", "followers_count", default=0)},
                {"type": "interaction", "count": pick(user, "interaction", "liked_count", default=0)},
            ],
            "tags": pick(user, "tags", default=[]),
            "raw_data": raw(item),
        }


def _unwrap_note(item: dict[str, Any]) -> dict[str, Any]:
    note = item.get("note")
    return note if isinstance(note, dict) else item


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

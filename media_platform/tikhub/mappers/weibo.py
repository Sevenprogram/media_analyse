from datetime import datetime
from email.utils import format_datetime
from typing import Any

from .base import BaseTikHubMapper, author, first_url, nested, pick, raw


def _created_at(item: dict[str, Any]) -> str:
    value = pick(item, "created_at", default="")
    if value:
        return str(value)
    timestamp = pick(item, "create_time", "time", "timestamp", default=0)
    try:
        return format_datetime(datetime.fromtimestamp(int(timestamp)))
    except (TypeError, ValueError, OSError):
        return format_datetime(datetime.fromtimestamp(0))


class WeiboTikHubMapper(BaseTikHubMapper):
    platform = "wb"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        user = author(item)
        note_id = str(pick(item, "note_id", "id", "mid"))
        return {
            "mblog": {
                "id": note_id,
                "text": str(pick(item, "text", "content", "desc")),
                "created_at": _created_at(item),
                "attitudes_count": nested(item, "stats", "like_count", default=pick(item, "like_count", default=0)),
                "comments_count": nested(item, "stats", "comment_count", default=pick(item, "comment_count", default=0)),
                "reposts_count": nested(item, "stats", "share_count", default=pick(item, "share_count", "reposts_count", default=0)),
                "region_name": str(pick(item, "region_name", "ip_location")),
                "user": {
                    "id": str(pick(user, "id", "user_id", "uid")),
                    "screen_name": str(pick(user, "screen_name", "nickname", "name")),
                    "gender": str(pick(user, "gender")),
                    "profile_url": str(pick(user, "profile_url")),
                    "profile_image_url": first_url(pick(user, "profile_image_url", "avatar", "avatar_url")),
                },
            },
            "source_keyword": source_keyword,
            "raw_data": raw(item),
        }

    def map_comment(self, item: dict[str, Any], content_id: str) -> dict[str, Any]:
        user = author(item)
        return {
            "id": str(pick(item, "comment_id", "id")),
            "created_at": _created_at(item),
            "text": str(pick(item, "text", "content")),
            "total_number": pick(item, "total_number", "sub_comment_count", default=0),
            "like_count": pick(item, "like_count", default=0),
            "source": str(pick(item, "source", "ip_location")),
            "rootid": str(pick(item, "rootid", "parent_comment_id")),
            "user": {
                "id": str(pick(user, "id", "user_id", "uid")),
                "screen_name": str(pick(user, "screen_name", "nickname", "name")),
                "gender": str(pick(user, "gender")),
                "profile_url": str(pick(user, "profile_url")),
                "profile_image_url": first_url(pick(user, "profile_image_url", "avatar", "avatar_url")),
            },
            "raw_data": raw(item),
        }

    def map_creator(self, item: dict[str, Any]) -> dict[str, Any]:
        user = author(item) or item
        return {
            "screen_name": str(pick(user, "screen_name", "nickname", "name")),
            "gender": str(pick(user, "gender")),
            "avatar_hd": first_url(pick(user, "avatar_hd", "avatar", "avatar_url")),
            "description": str(pick(user, "description", "desc", "bio")),
            "source": str(pick(user, "source", "ip_location")),
            "follow_count": pick(user, "follow_count", "follows", default=0),
            "followers_count": pick(user, "followers_count", "fans", default=0),
            "raw_data": raw(item),
        }

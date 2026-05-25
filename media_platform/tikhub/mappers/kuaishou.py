from typing import Any

from .base import BaseTikHubMapper, author, first_url, nested, pick, raw


class KuaishouTikHubMapper(BaseTikHubMapper):
    platform = "ks"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        user = author(item)
        video_id = str(pick(item, "photo_id", "video_id", "id"))
        return {
            "type": str(pick(item, "type", default="video")),
            "photo": {
                "id": video_id,
                "caption": str(pick(item, "caption", "title", "desc", "content", "text")),
                "timestamp": pick(item, "timestamp", "create_time", "time", default=0),
                "realLikeCount": nested(item, "stats", "like_count", default=pick(item, "like_count", default=0)),
                "viewCount": nested(item, "stats", "view_count", default=pick(item, "view_count", default=0)),
                "coverUrl": first_url(pick(item, "cover", "cover_url", "image")),
                "photoUrl": first_url(pick(item, "video_url", "photo_url", "url")),
            },
            "author": {
                "id": str(pick(user, "id", "user_id")),
                "name": str(pick(user, "name", "nickname")),
                "headerUrl": first_url(pick(user, "avatar", "avatar_url", "headurl")),
            },
            "source_keyword": source_keyword,
            "raw_data": raw(item),
        }

    def map_comment(self, item: dict[str, Any], content_id: str) -> dict[str, Any]:
        user = author(item)
        return {
            "comment_id": str(pick(item, "comment_id", "commentId", "id")),
            "timestamp": pick(item, "timestamp", "create_time", "time", default=0),
            "content": str(pick(item, "content", "text")),
            "author_id": str(pick(user, "id", "user_id", "author_id")),
            "author_name": str(pick(user, "name", "nickname", "author_name")),
            "headurl": first_url(pick(user, "avatar", "avatar_url", "headurl")),
            "commentCount": pick(item, "commentCount", "sub_comment_count", default=0),
            "raw_data": raw(item),
        }

    def map_creator(self, item: dict[str, Any]) -> dict[str, Any]:
        user = author(item) or item
        return {
            "profile": {
                "user_name": str(pick(user, "nickname", "name")),
                "gender": pick(user, "gender", default="U"),
                "headurl": first_url(pick(user, "avatar", "avatar_url", "headurl")),
                "user_text": str(pick(user, "desc", "bio", "signature")),
            },
            "ownerCount": {
                "follow": pick(user, "follows", "following_count", default=0),
                "fan": pick(user, "fans", "followers_count", default=0),
                "photo_public": pick(user, "interaction", "video_count", default=0),
            },
            "raw_data": raw(item),
        }

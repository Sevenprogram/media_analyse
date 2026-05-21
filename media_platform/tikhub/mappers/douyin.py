from typing import Any

from .base import BaseTikHubMapper, author, first_url, nested, pick, raw


class DouyinTikHubMapper(BaseTikHubMapper):
    platform = "dy"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        item = item.get("aweme_info") if isinstance(item.get("aweme_info"), dict) else item
        user = author(item)
        aweme_id = str(pick(item, "aweme_id", "id", "item_id", "video_id"))
        if not aweme_id:
            aweme_id = self.stable_numeric_id(item)
        return {
            "aweme_id": aweme_id,
            "aweme_type": pick(item, "aweme_type", default=0),
            "desc": str(pick(item, "desc", "title", "content", "text")),
            "create_time": pick(item, "create_time", "time", "timestamp", default=0),
            "author": {
                "uid": str(pick(user, "uid", "user_id", "id")),
                "sec_uid": str(pick(user, "sec_uid", "sec_user_id")),
                "short_id": str(pick(user, "short_id")),
                "unique_id": str(pick(user, "unique_id")),
                "signature": str(pick(user, "signature", "desc", "bio")),
                "nickname": str(pick(user, "nickname", "name")),
                "avatar_thumb": {"url_list": [first_url(pick(user, "avatar", "avatar_url"))]},
            },
            "statistics": {
                "digg_count": nested(item, "stats", "like_count", default=pick(item, "liked_count", "like_count", default=0)),
                "collect_count": pick(item, "collected_count", "collect_count", default=0),
                "comment_count": nested(item, "stats", "comment_count", default=pick(item, "comment_count", default=0)),
                "share_count": nested(item, "stats", "share_count", default=pick(item, "share_count", default=0)),
            },
            "video": pick(item, "video", default={}),
            "images": pick(item, "images", "image_list", default=[]),
            "music": pick(item, "music", default={}),
            "ip_label": str(pick(item, "ip_label", "ip_location")),
            "source_keyword": source_keyword,
            "raw_data": raw(item),
        }

    def stable_numeric_id(self, item: dict[str, Any]) -> str:
        import hashlib

        source = raw(item)
        digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:15]
        return str(int(digest, 16))

    def map_comment(self, item: dict[str, Any], content_id: str) -> dict[str, Any]:
        user = author(item)
        return {
            "cid": str(pick(item, "cid", "comment_id", "id")),
            "aweme_id": content_id,
            "create_time": pick(item, "create_time", "time", "timestamp", default=0),
            "ip_label": str(pick(item, "ip_label", "ip_location")),
            "text": str(pick(item, "text", "content")),
            "user": {
                "uid": str(pick(user, "uid", "user_id", "id")),
                "sec_uid": str(pick(user, "sec_uid", "sec_user_id")),
                "short_id": str(pick(user, "short_id")),
                "unique_id": str(pick(user, "unique_id")),
                "signature": str(pick(user, "signature", "desc")),
                "nickname": str(pick(user, "nickname", "name")),
                "avatar_thumb": {"url_list": [first_url(pick(user, "avatar", "avatar_url"))]},
            },
            "reply_comment_total": pick(item, "reply_comment_total", "sub_comment_count", default=0),
            "digg_count": pick(item, "digg_count", "like_count", default=0),
            "reply_id": str(pick(item, "reply_id", "parent_comment_id", default="0")),
            "image_list": pick(item, "image_list", "images", default=[]),
            "raw_data": raw(item),
        }

    def map_creator(self, item: dict[str, Any]) -> dict[str, Any]:
        user = author(item) or item.get("user_info") or item
        return {
            "user": {
                "nickname": str(pick(user, "nickname", "nick_name", "name")),
                "gender": pick(user, "gender", default=0),
                "avatar_300x300": {"uri": first_url(pick(user, "avatar", "avatar_url"))},
                "signature": str(pick(user, "signature", "desc", "bio")),
                "ip_location": str(pick(user, "ip_location")),
                "following_count": pick(user, "follows", "following_count", "favoriting_count", default=nested(user, "follow_info", "following_count", default=0)),
                "max_follower_count": pick(user, "fans", "fans_cnt", "followers_count", "follower_count", default=nested(user, "follow_info", "follower_count", default=0)),
                "total_favorited": pick(user, "interaction", "like_cnt", "liked_count", "total_favorited", "like_count", default=0),
                "collect_count": pick(user, "collected_count", "collect_count", "favorite_count", "favorites_count", default=0),
                "aweme_count": pick(user, "videos_count", "publish_cnt", "aweme_count", "posts_count", default=0),
            },
            "raw_data": raw(item),
        }

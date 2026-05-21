from typing import Any

from .base import BaseTikHubMapper, author, first_url, nested, pick, raw


class BilibiliTikHubMapper(BaseTikHubMapper):
    platform = "bili"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> dict[str, Any]:
        user = author(item)
        aid = str(pick(item, "aid", "video_id", "id"))
        return {
            "View": {
                "aid": aid,
                "title": str(pick(item, "title", "desc", "content")),
                "desc": str(pick(item, "desc", "content", "summary")),
                "pubdate": pick(item, "pubdate", "create_time", "time", default=0),
                "pic": first_url(pick(item, "pic", "cover", "cover_url")),
                "owner": {
                    "mid": str(pick(user, "mid", "user_id", "id")),
                    "name": str(pick(user, "name", "nickname")),
                    "face": first_url(pick(user, "face", "avatar", "avatar_url")),
                },
                "stat": {
                    "like": nested(item, "stats", "like_count", default=pick(item, "like_count", default=0)),
                    "dislike": pick(item, "dislike", default=0),
                    "view": nested(item, "stats", "view_count", default=pick(item, "view_count", default=0)),
                    "favorite": pick(item, "favorite", "favorite_count", default=0),
                    "share": nested(item, "stats", "share_count", default=pick(item, "share_count", default=0)),
                    "coin": pick(item, "coin", "coin_count", default=0),
                    "danmaku": pick(item, "danmaku", default=0),
                    "reply": nested(item, "stats", "comment_count", default=pick(item, "comment_count", default=0)),
                },
            },
            "source_keyword": source_keyword,
            "raw_data": raw(item),
        }

    def map_comment(self, item: dict[str, Any], content_id: str) -> dict[str, Any]:
        user = author(item)
        return {
            "rpid": str(pick(item, "rpid", "comment_id", "id")),
            "parent": pick(item, "parent", "parent_comment_id", default=0),
            "ctime": pick(item, "ctime", "create_time", "time", default=0),
            "content": {"message": str(pick(item, "message", "content", "text"))},
            "member": {
                "mid": str(pick(user, "mid", "user_id", "id")),
                "uname": str(pick(user, "uname", "nickname", "name")),
                "sex": str(pick(user, "sex", "gender")),
                "sign": str(pick(user, "sign", "signature")),
                "avatar": first_url(pick(user, "avatar", "avatar_url", "face")),
            },
            "like": pick(item, "like", "like_count", default=0),
            "rcount": pick(item, "rcount", "sub_comment_count", default=0),
            "raw_data": raw(item),
        }

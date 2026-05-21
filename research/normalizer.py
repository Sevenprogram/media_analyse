from datetime import datetime, timezone
from typing import Any

from research.anonymizer import hash_author_id, hash_optional_text


def parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return datetime.fromtimestamp(int(stripped), tz=timezone.utc)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(stripped, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def normalize_weibo_note(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    platform_post_id = str(item["note_id"])
    author_hash = _author_hash("wb", item.get("user_id"), salt=salt)
    return {
        "job_id": job_id,
        "platform": "wb",
        "platform_post_id": platform_post_id,
        "author_hash": author_hash,
        "title": None,
        "content": item.get("content"),
        "url": item.get("note_url"),
        "publish_time": parse_timestamp(item.get("create_time") or item.get("create_date_time")),
        "engagement_json": {
            "liked_count": item.get("liked_count"),
            "comments_count": item.get("comments_count"),
            "shared_count": item.get("shared_count"),
            "source_keyword": item.get("source_keyword"),
            "ip_location": item.get("ip_location"),
        },
    }


def normalize_weibo_comment(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "wb",
        "platform_comment_id": str(item["comment_id"]),
        "platform_post_id": str(item["note_id"]),
        "parent_comment_id": _none_if_root(item.get("parent_comment_id")),
        "author_hash": _author_hash("wb", item.get("user_id"), salt=salt),
        "content": item.get("content"),
        "publish_time": parse_timestamp(item.get("create_time") or item.get("create_date_time")),
        "like_count": _to_int(item.get("comment_like_count")),
    }


def normalize_weibo_author(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    author_hash = _author_hash("wb", item.get("user_id"), salt=salt)
    return {
        "job_id": job_id,
        "platform": "wb",
        "author_hash": author_hash,
        "raw_author_id_encrypted": None,
        "display_name_hash": hash_optional_text(item.get("nickname"), salt=salt),
        "profile_url_hash": hash_optional_text(item.get("profile_url"), salt=salt),
        "metrics_json": {
            "follows": item.get("follows"),
            "fans": item.get("fans"),
            "gender": item.get("gender"),
            "ip_location": item.get("ip_location"),
            "tag_list": item.get("tag_list"),
        },
    }


def normalize_zhihu_content(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    platform_post_id = str(item["content_id"])
    return {
        "job_id": job_id,
        "platform": "zhihu",
        "platform_post_id": platform_post_id,
        "author_hash": _author_hash("zhihu", item.get("user_id"), salt=salt),
        "title": item.get("title"),
        "content": item.get("content_text") or item.get("desc"),
        "url": item.get("content_url"),
        "publish_time": parse_timestamp(item.get("created_time")),
        "engagement_json": {
            "content_type": item.get("content_type"),
            "question_id": item.get("question_id"),
            "voteup_count": item.get("voteup_count"),
            "comment_count": item.get("comment_count"),
            "source_keyword": item.get("source_keyword"),
        },
    }


def normalize_zhihu_comment(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "zhihu",
        "platform_comment_id": str(item["comment_id"]),
        "platform_post_id": str(item["content_id"]),
        "parent_comment_id": _none_if_root(item.get("parent_comment_id")),
        "author_hash": _author_hash("zhihu", item.get("user_id"), salt=salt),
        "content": item.get("content"),
        "publish_time": parse_timestamp(item.get("publish_time")),
        "like_count": _to_int(item.get("like_count")),
    }


def normalize_zhihu_author(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "zhihu",
        "author_hash": _author_hash("zhihu", item.get("user_id"), salt=salt),
        "raw_author_id_encrypted": None,
        "display_name_hash": hash_optional_text(item.get("user_nickname"), salt=salt),
        "profile_url_hash": hash_optional_text(item.get("user_link"), salt=salt),
        "metrics_json": {
            "follows": item.get("follows"),
            "fans": item.get("fans"),
            "gender": item.get("gender"),
            "ip_location": item.get("ip_location"),
            "answer_count": item.get("anwser_count"),
            "question_count": item.get("question_count"),
            "voteup_count": item.get("get_voteup_count"),
        },
    }


def normalize_xhs_note(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "xhs",
        "platform_post_id": str(item["note_id"]),
        "author_hash": _author_hash("xhs", item.get("user_id"), salt=salt),
        "title": item.get("title"),
        "content": item.get("desc"),
        "url": item.get("note_url"),
        "publish_time": parse_timestamp(item.get("time")),
        "engagement_json": {
            "type": item.get("type"),
            "author_id": item.get("user_id"),
            "nickname": item.get("nickname"),
            "liked_count": item.get("liked_count"),
            "collected_count": item.get("collected_count"),
            "comment_count": item.get("comment_count"),
            "share_count": item.get("share_count"),
            "source_keyword": item.get("source_keyword"),
            "ip_location": item.get("ip_location"),
            "tag_list": item.get("tag_list"),
        },
    }


def normalize_xhs_comment(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "xhs",
        "platform_comment_id": str(item["comment_id"]),
        "platform_post_id": str(item["note_id"]),
        "parent_comment_id": _none_if_root(item.get("parent_comment_id")),
        "author_hash": _author_hash("xhs", item.get("user_id"), salt=salt),
        "content": item.get("content"),
        "publish_time": parse_timestamp(item.get("create_time")),
        "like_count": _to_int(item.get("like_count")),
    }


def normalize_xhs_author(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "xhs",
        "author_hash": _author_hash("xhs", item.get("user_id"), salt=salt),
        "raw_author_id_encrypted": None,
        "display_name_hash": hash_optional_text(item.get("nickname"), salt=salt),
        "profile_url_hash": None,
        "metrics_json": {
            "follows": item.get("follows"),
            "fans": item.get("fans"),
            "interaction": item.get("interaction"),
            "gender": item.get("gender"),
            "ip_location": item.get("ip_location"),
            "tag_list": item.get("tag_list"),
        },
    }


def normalize_douyin_aweme(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "dy",
        "platform_post_id": str(item["aweme_id"]),
        "author_hash": _author_hash("dy", item.get("user_id"), salt=salt),
        "title": item.get("title"),
        "content": item.get("desc"),
        "url": item.get("aweme_url"),
        "publish_time": parse_timestamp(item.get("create_time")),
        "engagement_json": {
            "aweme_type": item.get("aweme_type"),
            "author_id": item.get("user_id"),
            "sec_uid": item.get("sec_uid"),
            "nickname": item.get("nickname"),
            "signature": item.get("user_signature"),
            "liked_count": item.get("liked_count"),
            "comment_count": item.get("comment_count"),
            "share_count": item.get("share_count"),
            "collected_count": item.get("collected_count"),
            "source_keyword": item.get("source_keyword"),
            "ip_location": item.get("ip_location"),
        },
    }


def normalize_douyin_comment(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "dy",
        "platform_comment_id": str(item["comment_id"]),
        "platform_post_id": str(item["aweme_id"]),
        "parent_comment_id": _none_if_root(item.get("parent_comment_id")),
        "author_hash": _author_hash("dy", item.get("user_id"), salt=salt),
        "content": item.get("content"),
        "publish_time": parse_timestamp(item.get("create_time")),
        "like_count": _to_int(item.get("like_count")),
    }


def normalize_douyin_author(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "dy",
        "author_hash": _author_hash("dy", item.get("user_id"), salt=salt),
        "raw_author_id_encrypted": None,
        "display_name_hash": hash_optional_text(item.get("nickname"), salt=salt),
        "profile_url_hash": None,
        "metrics_json": {
            "follows": item.get("follows"),
            "fans": item.get("fans"),
            "interaction": item.get("interaction"),
            "videos_count": item.get("videos_count"),
            "gender": item.get("gender"),
            "ip_location": item.get("ip_location"),
            "signature": item.get("user_signature") or item.get("desc"),
        },
    }


def normalize_kuaishou_video(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "ks",
        "platform_post_id": str(item["video_id"]),
        "author_hash": _author_hash("ks", item.get("user_id"), salt=salt),
        "title": item.get("title"),
        "content": item.get("desc"),
        "url": item.get("video_url"),
        "publish_time": parse_timestamp(item.get("create_time")),
        "engagement_json": {
            "video_type": item.get("video_type"),
            "liked_count": item.get("liked_count"),
            "viewd_count": item.get("viewd_count"),
            "source_keyword": item.get("source_keyword"),
        },
    }


def normalize_kuaishou_comment(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "ks",
        "platform_comment_id": str(item["comment_id"]),
        "platform_post_id": str(item["video_id"]),
        "parent_comment_id": None,
        "author_hash": _author_hash("ks", item.get("user_id"), salt=salt),
        "content": item.get("content"),
        "publish_time": parse_timestamp(item.get("create_time")),
        "like_count": None,
    }


def normalize_kuaishou_author(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "ks",
        "author_hash": _author_hash("ks", item.get("user_id"), salt=salt),
        "raw_author_id_encrypted": None,
        "display_name_hash": hash_optional_text(item.get("nickname"), salt=salt),
        "profile_url_hash": None,
        "metrics_json": {"avatar_set": bool(item.get("avatar"))},
    }


def normalize_bilibili_video(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "bili",
        "platform_post_id": str(item["video_id"]),
        "author_hash": _author_hash("bili", item.get("user_id"), salt=salt),
        "title": item.get("title"),
        "content": item.get("desc"),
        "url": item.get("video_url"),
        "publish_time": parse_timestamp(item.get("create_time")),
        "engagement_json": {
            "video_type": item.get("video_type"),
            "liked_count": item.get("liked_count"),
            "disliked_count": item.get("disliked_count"),
            "play_count": item.get("video_play_count"),
            "favorite_count": item.get("video_favorite_count"),
            "share_count": item.get("video_share_count"),
            "coin_count": item.get("video_coin_count"),
            "danmaku_count": item.get("video_danmaku"),
            "comment_count": item.get("video_comment"),
            "source_keyword": item.get("source_keyword"),
        },
    }


def normalize_bilibili_comment(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "bili",
        "platform_comment_id": str(item["comment_id"]),
        "platform_post_id": str(item["video_id"]),
        "parent_comment_id": _none_if_root(item.get("parent_comment_id")),
        "author_hash": _author_hash("bili", item.get("user_id"), salt=salt),
        "content": item.get("content"),
        "publish_time": parse_timestamp(item.get("create_time")),
        "like_count": _to_int(item.get("like_count")),
    }


def normalize_bilibili_author(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "bili",
        "author_hash": _author_hash("bili", item.get("user_id"), salt=salt),
        "raw_author_id_encrypted": None,
        "display_name_hash": hash_optional_text(item.get("nickname"), salt=salt),
        "profile_url_hash": None,
        "metrics_json": {
            "total_fans": item.get("total_fans"),
            "total_liked": item.get("total_liked"),
            "user_rank": item.get("user_rank"),
            "is_official": item.get("is_official"),
            "sex": item.get("sex"),
            "sign_hash": hash_optional_text(item.get("sign"), salt=salt),
        },
    }


def normalize_tieba_note(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "tieba",
        "platform_post_id": str(item["note_id"]),
        "author_hash": _author_hash("tieba", _tieba_author_key(item), salt=salt),
        "title": item.get("title"),
        "content": item.get("desc"),
        "url": item.get("note_url"),
        "publish_time": parse_timestamp(item.get("publish_time")),
        "engagement_json": {
            "tieba_id": item.get("tieba_id"),
            "tieba_name": item.get("tieba_name"),
            "total_replay_num": item.get("total_replay_num"),
            "total_replay_page": item.get("total_replay_page"),
            "source_keyword": item.get("source_keyword"),
            "ip_location": item.get("ip_location"),
        },
    }


def normalize_tieba_comment(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "platform": "tieba",
        "platform_comment_id": str(item["comment_id"]),
        "platform_post_id": str(item["note_id"]),
        "parent_comment_id": _none_if_root(item.get("parent_comment_id")),
        "author_hash": _author_hash("tieba", _tieba_author_key(item), salt=salt),
        "content": item.get("content"),
        "publish_time": parse_timestamp(item.get("publish_time")),
        "like_count": None,
    }


def normalize_tieba_author(item: dict[str, Any], *, job_id: int, salt: str) -> dict[str, Any]:
    author_key = _first_non_empty(item.get("user_id"), item.get("user_name"), item.get("nickname"))
    return {
        "job_id": job_id,
        "platform": "tieba",
        "author_hash": _author_hash("tieba", author_key, salt=salt),
        "raw_author_id_encrypted": None,
        "display_name_hash": hash_optional_text(item.get("nickname") or item.get("user_name"), salt=salt),
        "profile_url_hash": None,
        "metrics_json": {
            "follows": item.get("follows"),
            "fans": item.get("fans"),
            "gender": item.get("gender"),
            "ip_location": item.get("ip_location"),
            "registration_duration": item.get("registration_duration"),
        },
    }


def _author_hash(platform: str, raw_author_id: Any, *, salt: str) -> str | None:
    if raw_author_id in (None, ""):
        return None
    return hash_author_id(platform=platform, raw_author_id=str(raw_author_id), salt=salt)


def _none_if_root(value: Any) -> str | None:
    if value in (None, "", 0, "0"):
        return None
    return str(value)


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _tieba_author_key(item: dict[str, Any]) -> Any:
    return _first_non_empty(item.get("user_id"), item.get("user_link"), item.get("user_nickname"))

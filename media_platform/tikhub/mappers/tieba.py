from typing import Any

from model.m_baidu_tieba import TiebaComment, TiebaCreator, TiebaNote

from .base import BaseTikHubMapper, author, first_url, pick


class TiebaTikHubMapper(BaseTikHubMapper):
    platform = "tieba"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> TiebaNote:
        note_id = str(pick(item, "note_id", "thread_id", "id"))
        user = author(item)
        tieba_name = str(pick(item, "tieba_name", "forum_name", default=""))
        return TiebaNote(
            note_id=note_id,
            title=str(pick(item, "title", "desc", "content", "text")),
            desc=str(pick(item, "desc", "content", "text")),
            note_url=str(pick(item, "note_url", "url", default=f"https://tieba.baidu.com/p/{note_id}")),
            publish_time=str(pick(item, "publish_time", "create_time", "time")),
            user_link=str(pick(user, "user_link", "url")),
            user_nickname=str(pick(user, "nickname", "name", "user_name")),
            user_avatar=first_url(pick(user, "avatar", "avatar_url")),
            tieba_name=tieba_name,
            tieba_link=str(pick(item, "tieba_link", default=f"https://tieba.baidu.com/f?kw={tieba_name}")),
            total_replay_num=int(pick(item, "total_replay_num", "comment_count", "reply_count", default=0) or 0),
            total_replay_page=int(pick(item, "total_replay_page", default=0) or 0),
            ip_location=str(pick(item, "ip_location")),
            source_keyword=source_keyword,
        )

    def map_comment(self, item: dict[str, Any], content_id: str) -> TiebaComment:
        user = author(item)
        tieba_name = str(pick(item, "tieba_name", "forum_name", default=""))
        return TiebaComment(
            comment_id=str(pick(item, "comment_id", "id")),
            parent_comment_id=str(pick(item, "parent_comment_id", default="")),
            content=str(pick(item, "content", "text")),
            user_link=str(pick(user, "user_link", "url")),
            user_nickname=str(pick(user, "nickname", "name", "user_name")),
            user_avatar=first_url(pick(user, "avatar", "avatar_url")),
            publish_time=str(pick(item, "publish_time", "create_time", "time")),
            ip_location=str(pick(item, "ip_location")),
            sub_comment_count=int(pick(item, "sub_comment_count", "reply_count", default=0) or 0),
            note_id=content_id,
            note_url=f"https://tieba.baidu.com/p/{content_id}",
            tieba_id=str(pick(item, "tieba_id", "forum_id")),
            tieba_name=tieba_name,
            tieba_link=str(pick(item, "tieba_link", default=f"https://tieba.baidu.com/f?kw={tieba_name}")),
        )

    def map_creator(self, item: dict[str, Any]) -> TiebaCreator:
        user = author(item) or item
        return TiebaCreator(
            user_id=str(pick(user, "user_id", "id")),
            user_name=str(pick(user, "user_name", "name", "nickname")),
            nickname=str(pick(user, "nickname", "name", "user_name")),
            gender=str(pick(user, "gender")),
            avatar=first_url(pick(user, "avatar", "avatar_url")),
            ip_location=str(pick(user, "ip_location")),
            follows=int(pick(user, "follows", "following_count", default=0) or 0),
            fans=int(pick(user, "fans", "followers_count", default=0) or 0),
            registration_duration=str(pick(user, "registration_duration")),
        )

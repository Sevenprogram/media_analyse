from typing import Any

from model.m_zhihu import ZhihuComment, ZhihuContent, ZhihuCreator

from .base import BaseTikHubMapper, author, first_url, nested, pick


class ZhihuTikHubMapper(BaseTikHubMapper):
    platform = "zhihu"

    def map_content(self, item: dict[str, Any], source_keyword: str = "") -> ZhihuContent:
        user = author(item)
        content_id = str(pick(item, "content_id", "answer_id", "article_id", "id"))
        return ZhihuContent(
            content_id=content_id,
            content_type=str(pick(item, "content_type", "type", default="answer")),
            content_text=str(pick(item, "content_text", "content", "text")),
            content_url=str(pick(item, "content_url", "url", default=f"https://www.zhihu.com/question/{content_id}")),
            question_id=str(pick(item, "question_id")),
            title=str(pick(item, "title")),
            desc=str(pick(item, "desc", "summary")),
            created_time=int(pick(item, "created_time", "create_time", "time", default=0) or 0),
            updated_time=int(pick(item, "updated_time", "update_time", default=0) or 0),
            voteup_count=int(nested(item, "stats", "voteup_count", default=pick(item, "voteup_count", "like_count", default=0)) or 0),
            comment_count=int(nested(item, "stats", "comment_count", default=pick(item, "comment_count", default=0)) or 0),
            source_keyword=source_keyword,
            user_id=str(pick(user, "user_id", "id")),
            user_link=str(pick(user, "user_link", "url")),
            user_nickname=str(pick(user, "nickname", "name")),
            user_avatar=first_url(pick(user, "avatar", "avatar_url")),
            user_url_token=str(pick(user, "url_token")),
        )

    def map_comment(self, item: dict[str, Any], content_id: str) -> ZhihuComment:
        user = author(item)
        return ZhihuComment(
            comment_id=str(pick(item, "comment_id", "id")),
            parent_comment_id=str(pick(item, "parent_comment_id", default="")),
            content=str(pick(item, "content", "text")),
            publish_time=int(pick(item, "publish_time", "create_time", "time", default=0) or 0),
            ip_location=str(pick(item, "ip_location")),
            sub_comment_count=int(pick(item, "sub_comment_count", "reply_count", default=0) or 0),
            like_count=int(pick(item, "like_count", "liked_count", default=0) or 0),
            dislike_count=int(pick(item, "dislike_count", default=0) or 0),
            content_id=content_id,
            content_type=str(pick(item, "content_type", default="answer")),
            user_id=str(pick(user, "user_id", "id")),
            user_link=str(pick(user, "user_link", "url")),
            user_nickname=str(pick(user, "nickname", "name")),
            user_avatar=first_url(pick(user, "avatar", "avatar_url")),
        )

    def map_creator(self, item: dict[str, Any]) -> ZhihuCreator:
        user = author(item) or item
        return ZhihuCreator(
            user_id=str(pick(user, "user_id", "id")),
            user_link=str(pick(user, "user_link", "url")),
            user_nickname=str(pick(user, "nickname", "name")),
            user_avatar=first_url(pick(user, "avatar", "avatar_url")),
            url_token=str(pick(user, "url_token")),
            gender=str(pick(user, "gender")),
            ip_location=str(pick(user, "ip_location")),
            follows=int(pick(user, "follows", "following_count", default=0) or 0),
            fans=int(pick(user, "fans", "followers_count", default=0) or 0),
            anwser_count=int(pick(user, "anwser_count", "answer_count", default=0) or 0),
            video_count=int(pick(user, "video_count", default=0) or 0),
            question_count=int(pick(user, "question_count", default=0) or 0),
            article_count=int(pick(user, "article_count", default=0) or 0),
            column_count=int(pick(user, "column_count", default=0) or 0),
            get_voteup_count=int(pick(user, "get_voteup_count", "voteup_count", default=0) or 0),
        )

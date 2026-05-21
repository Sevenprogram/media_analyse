from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .errors import TikHubCapabilityError


class Capability(str, Enum):
    SEARCH = "search"
    DETAIL = "detail"
    CREATOR = "creator"
    COMMENTS = "comments"
    SUB_COMMENTS = "sub_comments"


@dataclass(frozen=True)
class EndpointSpec:
    method: str
    path: str
    keyword_param: str = "keyword"
    content_param: str = "id"
    creator_param: str = "user_id"
    cursor_param: str = ""
    page_param: str = "page"
    default_params: dict[str, Any] = field(default_factory=dict)
    supported: bool = True
    json_body: bool = False


REGISTRY: dict[str, dict[Capability, EndpointSpec]] = {
    "xhs": {
        Capability.SEARCH: EndpointSpec(
            "GET",
            "/api/v1/xiaohongshu/app/search_notes",
            keyword_param="keyword",
            default_params={
                "sort_type": "general",
                "filter_note_type": "不限",
                "filter_note_time": "不限",
            },
        ),
        Capability.DETAIL: EndpointSpec(
            "GET",
            "/api/v1/xiaohongshu/web/get_note_info",
            content_param="note_id",
        ),
        Capability.CREATOR: EndpointSpec(
            "GET",
            "/api/v1/xiaohongshu/web/get_user_notes",
            creator_param="user_id",
        ),
        Capability.COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/xiaohongshu/web/get_note_comments",
            content_param="note_id",
            cursor_param="cursor",
        ),
        Capability.SUB_COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/xiaohongshu/web/get_note_sub_comments",
            content_param="note_id",
            cursor_param="cursor",
            supported=False,
        ),
    },
    "dy": {
        Capability.SEARCH: EndpointSpec(
            "POST",
            "/api/v1/douyin/search/fetch_general_search_v1",
            keyword_param="keyword",
            cursor_param="cursor",
            page_param="",
            default_params={
                "cursor": 0,
                "sort_type": "0",
                "publish_time": "0",
                "filter_duration": "0",
                "content_type": "0",
                "search_id": "",
                "backtrace": "",
            },
            json_body=True,
        ),
        Capability.DETAIL: EndpointSpec(
            "GET",
            "/api/v1/douyin/web/fetch_one_video_v2",
            content_param="aweme_id",
        ),
        Capability.CREATOR: EndpointSpec(
            "GET",
            "/api/v1/douyin/web/fetch_user_post_videos",
            creator_param="sec_user_id",
            page_param="max_cursor",
        ),
        Capability.COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/douyin/web/fetch_video_comments",
            content_param="aweme_id",
            cursor_param="cursor",
        ),
        Capability.SUB_COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/douyin/web/fetch_video_comment_replies",
            content_param="aweme_id",
            cursor_param="cursor",
        ),
    },
    "ks": {
        Capability.SEARCH: EndpointSpec(
            "GET",
            "/api/v1/kuaishou/web/search_video",
            keyword_param="keyword",
            page_param="pcursor",
        ),
        Capability.DETAIL: EndpointSpec(
            "GET",
            "/api/v1/kuaishou/web/fetch_one_video",
            content_param="photo_id",
        ),
        Capability.CREATOR: EndpointSpec(
            "GET",
            "/api/v1/kuaishou/web/fetch_user_profile",
            creator_param="user_id",
        ),
        Capability.COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/kuaishou/web/fetch_video_comments",
            content_param="photo_id",
            cursor_param="pcursor",
        ),
        Capability.SUB_COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/kuaishou/web/fetch_video_sub_comments",
            content_param="photo_id",
            cursor_param="pcursor",
            supported=False,
        ),
    },
    "bili": {
        Capability.SEARCH: EndpointSpec(
            "GET",
            "/api/v1/bilibili/web/search",
            keyword_param="keyword",
        ),
        Capability.DETAIL: EndpointSpec(
            "GET",
            "/api/v1/bilibili/web/fetch_video_detail",
            content_param="bvid",
        ),
        Capability.CREATOR: EndpointSpec(
            "GET",
            "/api/v1/bilibili/web/fetch_user_videos",
            creator_param="mid",
        ),
        Capability.COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/bilibili/web/fetch_video_comments",
            content_param="oid",
            cursor_param="next",
        ),
        Capability.SUB_COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/bilibili/web/fetch_video_sub_comments",
            content_param="oid",
            cursor_param="next",
        ),
    },
    "wb": {
        Capability.SEARCH: EndpointSpec(
            "GET",
            "/api/v1/weibo/app/fetch_ai_smart_search",
            keyword_param="query",
        ),
        Capability.DETAIL: EndpointSpec(
            "GET",
            "/api/v1/weibo/web_v2/fetch_post_detail",
            content_param="id",
        ),
        Capability.CREATOR: EndpointSpec(
            "GET",
            "/api/v1/weibo/web_v2/fetch_user_posts",
            creator_param="uid",
        ),
        Capability.COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/weibo/web_v2/fetch_post_comments",
            content_param="id",
            cursor_param="max_id",
            default_params={"count": 20},
        ),
        Capability.SUB_COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/weibo/web_v2/fetch_post_sub_comments",
            content_param="id",
            cursor_param="max_id",
            supported=False,
        ),
    },
    "tieba": {
        Capability.SEARCH: EndpointSpec(
            "GET",
            "/api/v1/baidu_tieba/web/search_posts",
            keyword_param="keyword",
        ),
        Capability.DETAIL: EndpointSpec(
            "GET",
            "/api/v1/baidu_tieba/web/fetch_post_detail",
            content_param="thread_id",
        ),
        Capability.CREATOR: EndpointSpec(
            "GET",
            "/api/v1/baidu_tieba/web/fetch_user_posts",
            creator_param="user_id",
        ),
        Capability.COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/baidu_tieba/web/fetch_post_comments",
            content_param="thread_id",
        ),
        Capability.SUB_COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/baidu_tieba/web/fetch_sub_comments",
            content_param="thread_id",
            supported=False,
        ),
    },
    "zhihu": {
        Capability.SEARCH: EndpointSpec(
            "GET",
            "/api/v1/zhihu/web/search",
            keyword_param="keyword",
        ),
        Capability.DETAIL: EndpointSpec(
            "GET",
            "/api/v1/zhihu/web/fetch_content_detail",
            content_param="content_id",
        ),
        Capability.CREATOR: EndpointSpec(
            "GET",
            "/api/v1/zhihu/web/fetch_user_contents",
            creator_param="user_id",
        ),
        Capability.COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/zhihu/web/fetch_content_comments",
            content_param="content_id",
            cursor_param="offset",
        ),
        Capability.SUB_COMMENTS: EndpointSpec(
            "GET",
            "/api/v1/zhihu/web/fetch_comment_replies",
            content_param="comment_id",
            cursor_param="offset",
            supported=False,
        ),
    },
}


def supports_capability(platform: str, capability: Capability) -> bool:
    return (
        platform in REGISTRY
        and capability in REGISTRY[platform]
        and REGISTRY[platform][capability].supported
    )


def get_endpoint(platform: str, capability: Capability) -> EndpointSpec:
    try:
        endpoint = REGISTRY[platform][capability]
    except KeyError as exc:
        raise TikHubCapabilityError(
            f"TikHub capability {capability.value!r} is not configured for platform {platform!r}."
        ) from exc
    if not endpoint.supported:
        raise TikHubCapabilityError(
            f"TikHub capability {capability.value!r} is not supported for platform {platform!r}."
        )
    return endpoint

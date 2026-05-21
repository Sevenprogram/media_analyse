from model.m_baidu_tieba import TiebaComment, TiebaNote
from model.m_zhihu import ZhihuComment, ZhihuContent
from media_platform.tikhub.core import TikHubCrawler
from media_platform.tikhub.endpoints import Capability, get_endpoint
from media_platform.tikhub.mappers import get_mapper


def test_xhs_mapper_emits_store_compatible_content():
    mapper = get_mapper("xhs")

    mapped = mapper.map_content(
        {
            "id": "note-1",
            "title": "Title",
            "desc": "Desc",
            "user": {"id": "user-1", "nickname": "Nick", "avatar": "avatar"},
            "stats": {"like_count": 1, "comment_count": 2, "share_count": 3},
        },
        source_keyword="kw",
    )

    assert mapped["note_id"] == "note-1"
    assert mapped["user"]["user_id"] == "user-1"
    assert mapped["interact_info"]["liked_count"] == 1
    assert mapped["source_keyword"] == "kw"
    assert "raw_data" in mapped


def test_xhs_mapper_unwraps_app_search_note_item():
    mapper = get_mapper("xhs")

    mapped = mapper.map_content(
        {
            "model_type": "note",
            "note": {
                "id": "note-2",
                "title": "Nested",
                "comments_count": 4,
                "shared_count": 5,
                "images_list": [
                    {"url_default": "https://example.test/1.jpg"},
                    {"url_default": None},
                ],
                "user": {"userid": "user-2", "nickname": "Nested User", "images": "avatar"},
            },
        },
        source_keyword="nested",
    )

    assert mapped["note_id"] == "note-2"
    assert mapped["user"]["user_id"] == "user-2"
    assert mapped["interact_info"]["comment_count"] == 4
    assert mapped["interact_info"]["share_count"] == 5
    assert mapped["image_list"][0]["url_default"] == "https://example.test/1.jpg"
    assert mapped["image_list"][1]["url_default"] == ""


def test_xhs_mapper_supports_web_v3_user_notes_item():
    mapper = get_mapper("xhs")

    mapped = mapper.map_content(
        {
            "noteId": "",
            "displayTitle": "这届家长太难带！娃练魔方，妈练打乱！✅",
            "type": "video",
            "xsecToken": "token-1",
            "user": {
                "userId": "5ddcadd900000000010032a1",
                "nickName": "学而思",
                "avatar": "avatar",
            },
            "interactInfo": {"likedCount": "6.2万", "commentCount": "12"},
            "cover": {"url": "https://example.test/cover.jpg"},
        }
    )

    assert mapped["note_id"].startswith("tikhub_xhs_")
    assert mapped["title"] == "这届家长太难带！娃练魔方，妈练打乱！✅"
    assert mapped["user"]["user_id"] == "5ddcadd900000000010032a1"
    assert mapped["user"]["nickname"] == "学而思"
    assert mapped["interact_info"]["liked_count"] == 62000
    assert mapped["interact_info"]["comment_count"] == 12
    assert mapped["image_list"][0]["url"] == "https://example.test/cover.jpg"


def test_xhs_mapper_supports_app_v2_user_notes_item():
    mapper = get_mapper("xhs")

    mapped = mapper.map_content(
        {
            "id": "683eca230000000022005c76",
            "display_title": "AppV2 title",
            "desc": "AppV2 desc",
            "type": "video",
            "likes": 62488,
            "comments_count": 103,
            "collected_count": 5146,
            "share_count": 162,
            "create_time": 1748945443,
            "user": {
                "userid": "5ddcadd900000000010032a1",
                "nickname": "学而思",
                "images": "avatar",
            },
        }
    )

    assert mapped["note_id"] == "683eca230000000022005c76"
    assert mapped["title"] == "AppV2 title"
    assert mapped["time"] == 1748945443
    assert mapped["user"]["user_id"] == "5ddcadd900000000010032a1"
    assert mapped["user"]["nickname"] == "学而思"
    assert mapped["interact_info"]["liked_count"] == 62488
    assert mapped["interact_info"]["comment_count"] == 103
    assert mapped["interact_info"]["collected_count"] == 5146


def test_tikhub_extract_items_ignores_error_payload():
    crawler = TikHubCrawler("xhs")

    assert crawler._extract_items({"detail": "Not Found"}) == []


def test_tikhub_creator_params_skip_empty_page_param():
    crawler = TikHubCrawler("xhs")
    endpoint = get_endpoint("xhs", Capability.CREATOR)

    assert crawler._creator_params(endpoint, "user-1", page=1) == {"user_id": "user-1"}
    assert crawler._creator_params(endpoint, "user-1", page=2, cursor="cursor-1") == {
        "user_id": "user-1",
        "cursor": "cursor-1",
    }


def test_tikhub_extract_creator_uses_first_note_user_for_app_v2_payload():
    crawler = TikHubCrawler("xhs")

    creator = crawler._extract_creator(
        {"data": {"data": {"notes": []}}},
        "5ddcadd900000000010032a1",
        [
            {
                "user": {
                    "userid": "5ddcadd900000000010032a1",
                    "nickname": "学而思",
                    "images": "avatar",
                }
            }
        ],
    )

    assert creator["user_id"] == "5ddcadd900000000010032a1"
    assert creator["nickname"] == "学而思"

    mapped = get_mapper("xhs").map_creator(creator)
    assert mapped["user_id"] == "5ddcadd900000000010032a1"


def test_douyin_mapper_emits_store_compatible_content():
    mapper = get_mapper("dy")

    mapped = mapper.map_content(
        {
            "id": "aweme-1",
            "title": "Title",
            "user": {"id": "user-1", "nickname": "Nick"},
            "stats": {"like_count": 1, "comment_count": 2},
        }
    )

    assert mapped["aweme_id"] == "aweme-1"
    assert mapped["author"]["uid"] == "user-1"
    assert mapped["statistics"]["digg_count"] == 1


def test_douyin_mapper_generates_numeric_id_when_tikhub_payload_has_no_aweme_id():
    mapper = get_mapper("dy")

    mapped = mapper.map_content(
        {
            "title": "Title without id",
            "user": {"id": "user-1", "nickname": "Nick"},
        }
    )

    assert mapped["aweme_id"].isdigit()


def test_tikhub_creator_mappers_preserve_profile_metrics():
    xhs = get_mapper("xhs").map_creator(
        {
            "user": {
                "id": "x1",
                "nickname": "XHS Creator",
                "followers_count": 1200,
                "liked_count": 34000,
                "collected_count": 560,
                "notes_count": 42,
            }
        }
    )
    xhs_metrics = {item["type"]: item["count"] for item in xhs["interactions"]}

    dy = get_mapper("dy").map_creator(
        {
            "user": {
                "uid": "d1",
                "sec_uid": "sec-1",
                "nickname": "DY Creator",
                "followers_count": 2200,
                "total_favorited": 88000,
                "collect_count": 900,
                "aweme_count": 55,
            }
        }
    )

    assert xhs_metrics["fans"] == 1200
    assert xhs_metrics["interaction"] == 34000
    assert xhs_metrics["collected"] == 560
    assert xhs_metrics["notes"] == 42
    assert dy["user"]["max_follower_count"] == 2200
    assert dy["user"]["total_favorited"] == 88000
    assert dy["user"]["collect_count"] == 900
    assert dy["user"]["aweme_count"] == 55


def test_bilibili_mapper_emits_store_compatible_content():
    mapper = get_mapper("bili")

    mapped = mapper.map_content({"id": "123", "title": "Title", "user": {"id": "u1"}})

    assert mapped["View"]["aid"] == "123"
    assert mapped["View"]["owner"]["mid"] == "u1"


def test_tieba_and_zhihu_mappers_emit_models():
    tieba = get_mapper("tieba")
    zhihu = get_mapper("zhihu")

    assert isinstance(tieba.map_content({"id": "1", "title": "T"}), TiebaNote)
    assert isinstance(tieba.map_comment({"id": "c1", "content": "C"}, "1"), TiebaComment)
    assert isinstance(zhihu.map_content({"id": "1", "title": "T"}), ZhihuContent)
    assert isinstance(zhihu.map_comment({"id": "c1", "content": "C"}, "1"), ZhihuComment)

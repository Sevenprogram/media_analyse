from model.m_baidu_tieba import TiebaComment, TiebaNote
from model.m_zhihu import ZhihuComment, ZhihuContent
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

import pytest

import cmd_arg
import config


@pytest.mark.asyncio
async def test_existing_cli_shape_still_parses_with_tikhub_config(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)

    args = await cmd_arg.parse_cmd([
        "--platform", "xhs",
        "--type", "search",
        "--keywords", "口红",
        "--save_data_option", "jsonl",
    ])

    assert args.platform == "xhs"
    assert args.type == "search"
    assert config.KEYWORDS == "口红"


@pytest.mark.asyncio
async def test_cli_accepts_d1_save_option(monkeypatch):
    args = await cmd_arg.parse_cmd([
        "--platform", "xhs",
        "--type", "search",
        "--keywords", "口红",
        "--save_data_option", "d1",
    ])

    assert args.save_data_option == "d1"
    assert config.SAVE_DATA_OPTION == "d1"


@pytest.mark.asyncio
async def test_cli_accepts_latest_search_options(monkeypatch):
    args = await cmd_arg.parse_cmd([
        "--platform", "xhs",
        "--type", "search",
        "--keywords", "口红",
        "--prefer_latest_posts", "true",
        "--sort_type", "time_descending",
        "--filter_note_time", "一周内",
        "--collection_window_days", "3",
    ])

    assert args.platform == "xhs"
    assert config.CRAWLER_PREFER_LATEST_POSTS is True
    assert config.CRAWLER_SORT_TYPE == "time_descending"
    assert config.CRAWLER_FILTER_NOTE_TIME == "一周内"
    assert config.CRAWLER_COLLECTION_WINDOW_DAYS == 3

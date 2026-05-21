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

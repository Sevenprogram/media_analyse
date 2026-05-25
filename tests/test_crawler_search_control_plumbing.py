from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import config
from api.schemas import CrawlerStartRequest, PlatformEnum
from api.services.crawler_manager import CrawlerManager
from cmd_arg.arg import parse_cmd


def test_crawler_request_validates_exact_time_range() -> None:
    with pytest.raises(ValidationError, match="provided together"):
        CrawlerStartRequest(
            platform=PlatformEnum.XHS,
            keywords="cat food",
            time_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )

    with pytest.raises(ValidationError, match="before or equal"):
        CrawlerStartRequest(
            platform=PlatformEnum.XHS,
            keywords="cat food",
            time_start=datetime(2026, 5, 8, tzinfo=timezone.utc),
            time_end=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )


def test_crawler_manager_command_includes_search_controls() -> None:
    request = CrawlerStartRequest(
        platform=PlatformEnum.XHS,
        keywords="cat food",
        sort_mode="latest",
        time_preset="7d",
        time_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        time_end=datetime(2026, 5, 7, 23, 59, 59, tzinfo=timezone.utc),
        max_results_per_keyword_per_platform=200,
        max_extra_pages=8,
    )

    cmd = CrawlerManager()._build_command(request)

    assert _arg_value(cmd, "--sort_mode") == "latest"
    assert _arg_value(cmd, "--time_preset") == "7d"
    assert _arg_value(cmd, "--time_start") == "2026-05-01T00:00:00+00:00"
    assert _arg_value(cmd, "--time_end") == "2026-05-07T23:59:59+00:00"
    assert _arg_value(cmd, "--max_results_per_keyword_per_platform") == "200"
    assert _arg_value(cmd, "--max_extra_pages") == "8"


@pytest.mark.asyncio
async def test_parse_cmd_assigns_search_control_config(monkeypatch) -> None:
    monkeypatch.setattr(config, "CRAWLER_SORT_MODE", "relevance", raising=False)
    monkeypatch.setattr(config, "CRAWLER_TIME_PRESET", "all", raising=False)
    monkeypatch.setattr(config, "CRAWLER_TIME_START", None, raising=False)
    monkeypatch.setattr(config, "CRAWLER_TIME_END", None, raising=False)
    monkeypatch.setattr(
        config,
        "CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM",
        None,
        raising=False,
    )
    monkeypatch.setattr(config, "CRAWLER_FILL_STRATEGY", "prefer_fill", raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_EXTRA_PAGES", 5, raising=False)

    result = await parse_cmd(
        [
            "--platform",
            "xhs",
            "--sort_mode",
            "latest",
            "--time_preset",
            "30d",
            "--time_start",
            "2026-05-01T00:00:00+00:00",
            "--time_end",
            "2026-05-07T23:59:59+00:00",
            "--max_results_per_keyword_per_platform",
            "200",
            "--max_extra_pages",
            "9",
        ]
    )

    assert config.CRAWLER_SORT_MODE == "latest"
    assert config.CRAWLER_TIME_PRESET == "30d"
    assert config.CRAWLER_TIME_START == "2026-05-01T00:00:00+00:00"
    assert config.CRAWLER_TIME_END == "2026-05-07T23:59:59+00:00"
    assert config.CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM == 200
    assert config.CRAWLER_FILL_STRATEGY == "prefer_fill"
    assert config.CRAWLER_MAX_EXTRA_PAGES == 9
    assert result.sort_mode == "latest"
    assert result.max_results_per_keyword_per_platform == 200


def _arg_value(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]

from api.schemas import CrawlerStartRequest, PlatformEnum
from api.services.crawler_manager import CrawlerManager


def test_build_command_includes_latest_search_options():
    request = CrawlerStartRequest(
        platform=PlatformEnum.XHS,
        keywords="K12",
        prefer_latest_posts=True,
        sort_type="time_descending",
        filter_note_time="一周内",
        collection_window_days=3,
    )

    command = CrawlerManager()._build_command(request)

    assert "--prefer_latest_posts" in command
    assert command[command.index("--sort_type") + 1] == "time_descending"
    assert command[command.index("--filter_note_time") + 1] == "一周内"
    assert command[command.index("--collection_window_days") + 1] == "3"

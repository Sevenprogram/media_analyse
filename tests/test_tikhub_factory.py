import config
from main import CrawlerFactory
from media_platform.tikhub import TikHubCrawler
from media_platform.xhs import XiaoHongShuCrawler


def test_factory_uses_existing_crawler_when_tikhub_disabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_TIKHUB", False, raising=False)

    assert isinstance(CrawlerFactory.create_crawler("xhs"), XiaoHongShuCrawler)


def test_factory_uses_tikhub_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_TIKHUB", True, raising=False)

    crawler = CrawlerFactory.create_crawler("xhs")

    assert isinstance(crawler, TikHubCrawler)
    assert crawler.platform == "xhs"

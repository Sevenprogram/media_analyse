import pytest

from media_platform.tikhub.endpoints import Capability, get_endpoint, supports_capability
from media_platform.tikhub.errors import TikHubCapabilityError


@pytest.mark.parametrize("platform", ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"])
def test_platforms_have_search_detail_creator_entries(platform):
    assert supports_capability(platform, Capability.SEARCH)
    assert supports_capability(platform, Capability.DETAIL)
    assert supports_capability(platform, Capability.CREATOR)


def test_get_endpoint_returns_parameter_mapping():
    endpoint = get_endpoint("xhs", Capability.SEARCH)

    assert endpoint.method == "GET"
    assert endpoint.path == "/api/v1/xiaohongshu/app/search_notes"
    assert endpoint.keyword_param == "keyword"
    assert endpoint.default_params["filter_note_type"] == "不限"


def test_douyin_search_uses_current_search_endpoint():
    endpoint = get_endpoint("dy", Capability.SEARCH)

    assert endpoint.method == "POST"
    assert endpoint.path == "/api/v1/douyin/search/fetch_general_search_v1"
    assert endpoint.cursor_param == "cursor"
    assert endpoint.default_params["cursor"] == 0
    assert endpoint.json_body is True


def test_unsupported_platform_raises():
    with pytest.raises(TikHubCapabilityError):
        get_endpoint("unknown", Capability.SEARCH)

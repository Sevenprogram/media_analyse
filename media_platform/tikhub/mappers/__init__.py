from .bilibili import BilibiliTikHubMapper
from .douyin import DouyinTikHubMapper
from .kuaishou import KuaishouTikHubMapper
from .tieba import TiebaTikHubMapper
from .weibo import WeiboTikHubMapper
from .xhs import XhsTikHubMapper
from .zhihu import ZhihuTikHubMapper


_MAPPERS = {
    "xhs": XhsTikHubMapper(),
    "dy": DouyinTikHubMapper(),
    "ks": KuaishouTikHubMapper(),
    "bili": BilibiliTikHubMapper(),
    "wb": WeiboTikHubMapper(),
    "tieba": TiebaTikHubMapper(),
    "zhihu": ZhihuTikHubMapper(),
}


def get_mapper(platform: str):
    return _MAPPERS[platform]

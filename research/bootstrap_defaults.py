from typing import Any

from research.enums import SUPPORTED_RESEARCH_PLATFORMS


DEFAULT_VERTICALS: list[dict[str, Any]] = [
    {
        "code": "education",
        "name": "教育",
        "groups": [
            {
                "name": "人群",
                "tags": [
                    {
                        "tag_name": "单亲妈妈",
                        "keywords": ["单亲妈妈", "单亲母亲", "单亲家庭"],
                        "synonyms": ["宝妈独自带娃", "离异带娃"],
                        "weight": 12,
                    },
                    {
                        "tag_name": "家长",
                        "keywords": ["家长", "父母", "妈妈", "爸爸"],
                        "synonyms": ["宝妈", "陪读家长"],
                        "weight": 8,
                    },
                ],
            },
            {
                "name": "教育阶段",
                "tags": [
                    {
                        "tag_name": "K12教育",
                        "keywords": ["K12", "小学", "初中", "高中", "中小学"],
                        "synonyms": ["校内学习", "义务教育", "升学"],
                        "weight": 15,
                    },
                    {
                        "tag_name": "素质教育",
                        "keywords": ["素质教育", "编程课", "音乐课", "美术课"],
                        "synonyms": ["兴趣班", "课外班"],
                        "weight": 8,
                    },
                ],
            },
        ],
    },
    {
        "code": "technology",
        "name": "科技",
        "groups": [
            {
                "name": "主题",
                "tags": [
                    {
                        "tag_name": "AI工具",
                        "keywords": ["AI工具", "人工智能", "大模型", "ChatGPT"],
                        "synonyms": ["智能体", "AIGC"],
                        "weight": 12,
                    },
                    {
                        "tag_name": "数码评测",
                        "keywords": ["数码评测", "手机评测", "电脑评测"],
                        "synonyms": ["开箱", "测评"],
                        "weight": 9,
                    },
                ],
            }
        ],
    },
    {
        "code": "beauty",
        "name": "美妆",
        "groups": [
            {
                "name": "主题",
                "tags": [
                    {
                        "tag_name": "护肤",
                        "keywords": ["护肤", "精华", "面霜", "敏感肌"],
                        "synonyms": ["修护", "抗老"],
                        "weight": 10,
                    },
                    {
                        "tag_name": "彩妆",
                        "keywords": ["彩妆", "口红", "粉底", "眼影"],
                        "synonyms": ["妆容", "化妆教程"],
                        "weight": 10,
                    },
                ],
            }
        ],
    },
    {
        "code": "maternal_child",
        "name": "母婴",
        "groups": [
            {
                "name": "主题",
                "tags": [
                    {
                        "tag_name": "育儿",
                        "keywords": ["育儿", "带娃", "宝宝", "早教"],
                        "synonyms": ["亲子", "养娃"],
                        "weight": 11,
                    },
                    {
                        "tag_name": "孕产",
                        "keywords": ["孕期", "产后", "备孕"],
                        "synonyms": ["孕妈", "产康"],
                        "weight": 9,
                    },
                ],
            }
        ],
    },
    {
        "code": "health",
        "name": "健康",
        "groups": [
            {
                "name": "主题",
                "tags": [
                    {
                        "tag_name": "运动健身",
                        "keywords": ["健身", "减脂", "增肌", "运动"],
                        "synonyms": ["塑形", "训练"],
                        "weight": 10,
                    },
                    {
                        "tag_name": "营养健康",
                        "keywords": ["营养", "健康饮食", "控糖"],
                        "synonyms": ["膳食", "轻食"],
                        "weight": 8,
                    },
                ],
            }
        ],
    },
    {
        "code": "finance",
        "name": "金融",
        "groups": [
            {
                "name": "主题",
                "tags": [
                    {
                        "tag_name": "理财",
                        "keywords": ["理财", "基金", "存款", "资产配置"],
                        "synonyms": ["攒钱", "家庭财务"],
                        "weight": 10,
                    },
                    {
                        "tag_name": "职场收入",
                        "keywords": ["副业", "收入", "工资", "职场"],
                        "synonyms": ["搞钱", "自由职业"],
                        "weight": 9,
                    },
                ],
            }
        ],
    },
]


async def bootstrap_default_research_config(repository) -> dict[str, Any]:
    capabilities = []
    for platform in sorted(SUPPORTED_RESEARCH_PLATFORMS):
        capabilities.append(
            await repository.upsert_platform_capability(
                {
                    "platform": platform,
                    "enabled": True,
                    "crawl_search_enabled": True,
                    "crawl_creator_enabled": True,
                    "crawl_detail_enabled": True,
                    "comments_enabled": True,
                    "analysis_enabled": True,
                    "daily_monitor_enabled": True,
                    "keyword_heat_enabled": True,
                    "rate_limit_per_minute": 12,
                    "max_daily_jobs": None,
                    "notes": "bootstrapped default",
                }
            )
        )

    verticals = []
    groups = []
    tags = []
    for vertical_payload in DEFAULT_VERTICALS:
        vertical = await repository.upsert_vertical_by_code(
            {
                "code": vertical_payload["code"],
                "name": vertical_payload["name"],
                "enabled": True,
            }
        )
        verticals.append(vertical)
        for group_payload in vertical_payload["groups"]:
            group = await repository.upsert_tag_group_by_name(
                {
                    "vertical_id": vertical["id"],
                    "name": group_payload["name"],
                    "description": None,
                    "sort_order": len(groups) * 10,
                    "enabled": True,
                }
            )
            groups.append(group)
            for tag_payload in group_payload["tags"]:
                tag = await repository.upsert_tag_definition_by_name(
                    {
                        "vertical_id": vertical["id"],
                        "group_id": group["id"],
                        "tag_name": tag_payload["tag_name"],
                        "keywords": tag_payload.get("keywords", []),
                        "synonyms": tag_payload.get("synonyms", []),
                        "negative_keywords": tag_payload.get("negative_keywords", []),
                        "ai_prompt_hint": tag_payload.get("ai_prompt_hint"),
                        "weight": tag_payload.get("weight", 1),
                        "enabled": tag_payload.get("enabled", True),
                    }
                )
                tags.append(tag)

    return {
        "capabilities": capabilities,
        "verticals": verticals,
        "tag_groups": groups,
        "tag_definitions": tags,
    }

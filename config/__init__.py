# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/config/__init__.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


import os
from pathlib import Path

from .base_config import *
from .db_config import *


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _load_dotenv() -> None:
    root = Path(__file__).resolve().parent.parent
    original_keys = set(os.environ)
    values = {
        **_read_env_file(root / ".env.example"),
        **_read_env_file(root / ".env"),
    }
    for key, value in values.items():
        if key not in original_keys:
            os.environ[key] = value


_load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SAVE_DATA_OPTION = os.getenv("SAVE_DATA_OPTION", SAVE_DATA_OPTION)
HEADLESS = _env_bool("HEADLESS", HEADLESS)
ENABLE_CDP_MODE = _env_bool("ENABLE_CDP_MODE", ENABLE_CDP_MODE)
CDP_CONNECT_EXISTING = _env_bool("CDP_CONNECT_EXISTING", CDP_CONNECT_EXISTING)
ENABLE_TIKHUB = _env_bool("ENABLE_TIKHUB", ENABLE_TIKHUB)
TIKHUB_API_KEY = os.getenv("TIKHUB_API_KEY", TIKHUB_API_KEY)
TIKHUB_BASE_URL = os.getenv("TIKHUB_BASE_URL", TIKHUB_BASE_URL)
TIKHUB_TIMEOUT_SECONDS = int(os.getenv("TIKHUB_TIMEOUT_SECONDS", TIKHUB_TIMEOUT_SECONDS))
TIKHUB_MAX_RETRIES = int(os.getenv("TIKHUB_MAX_RETRIES", TIKHUB_MAX_RETRIES))
TIKHUB_RETRY_BACKOFF_SECONDS = float(
    os.getenv("TIKHUB_RETRY_BACKOFF_SECONDS", TIKHUB_RETRY_BACKOFF_SECONDS)
)

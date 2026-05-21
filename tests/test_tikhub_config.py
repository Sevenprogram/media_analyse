import importlib

import config


def test_tikhub_api_key_prefers_environment(monkeypatch):
    from media_platform.tikhub.client import resolve_tikhub_api_key

    monkeypatch.setenv("TIKHUB_API_KEY", "env-key")
    monkeypatch.setattr(config, "TIKHUB_API_KEY", "config-key", raising=False)

    assert resolve_tikhub_api_key() == "env-key"


def test_tikhub_api_key_falls_back_to_config(monkeypatch):
    from media_platform.tikhub.client import resolve_tikhub_api_key

    monkeypatch.delenv("TIKHUB_API_KEY", raising=False)
    monkeypatch.setattr(config, "TIKHUB_API_KEY", "config-key", raising=False)

    assert resolve_tikhub_api_key() == "config-key"


def test_tikhub_config_defaults_exist():
    importlib.reload(config)

    assert isinstance(config.ENABLE_TIKHUB, bool)
    assert config.TIKHUB_BASE_URL == "https://api.tikhub.io"
    assert config.TIKHUB_TIMEOUT_SECONDS > 0
    assert config.TIKHUB_MAX_RETRIES >= 0
    assert config.TIKHUB_RETRY_BACKOFF_SECONDS >= 0

from __future__ import annotations

from youdotcom_temporal.config import YouConfig


def test_env_resolution(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key-123")
    monkeypatch.setenv("YDC_SERVER_URL", "https://custom.you.com")
    cfg = YouConfig.resolve()
    assert cfg.api_key == "test-key-123"
    assert cfg.server_url == "https://custom.you.com"


def test_missing_key_leaves_none(monkeypatch):
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    monkeypatch.delenv("YDC_SERVER_URL", raising=False)
    cfg = YouConfig.resolve()
    assert cfg.api_key is None
    assert cfg.server_url is None


def test_explicit_override_wins_over_env(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "env-key")
    cfg = YouConfig.resolve(YouConfig(api_key="explicit-key"))
    assert cfg.api_key == "explicit-key"


def test_global_override_wins_over_env(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "env-key")
    import youdotcom_temporal.activities as activities

    try:
        activities.set_config(YouConfig(api_key="global-key"))
        # Production read path is _cfg() -> YouConfig.resolve(_config).
        cfg = YouConfig.resolve(activities._config)
        assert cfg.api_key == "global-key"
    finally:
        activities.set_config(None)
        assert activities._config is None


def test_defaults():
    cfg = YouConfig()
    assert cfg.timeout_seconds == 300.0
    assert cfg.api_key is None
    assert cfg.server_url is None

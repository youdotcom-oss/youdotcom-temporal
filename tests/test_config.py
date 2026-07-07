from __future__ import annotations

import os

from youdotcom_temporal.config import YouConfig


def test_env_resolution():
    os.environ["YDC_API_KEY"] = "test-key-123"
    os.environ["YDC_SERVER_URL"] = "https://custom.you.com"
    try:
        cfg = YouConfig.resolve()
        assert cfg.api_key == "test-key-123"
        assert cfg.server_url == "https://custom.you.com"
    finally:
        del os.environ["YDC_API_KEY"]
        del os.environ["YDC_SERVER_URL"]


def test_missing_key_leaves_none():
    os.environ.pop("YDC_API_KEY", None)
    os.environ.pop("YDC_SERVER_URL", None)
    cfg = YouConfig.resolve()
    assert cfg.api_key is None
    assert cfg.server_url is None


def test_explicit_override_wins_over_env():
    os.environ["YDC_API_KEY"] = "env-key"
    try:
        cfg = YouConfig.resolve(YouConfig(api_key="explicit-key"))
        assert cfg.api_key == "explicit-key"
    finally:
        del os.environ["YDC_API_KEY"]


def test_defaults():
    cfg = YouConfig()
    assert cfg.timeout_seconds == 30.0
    assert cfg.api_key is None
    assert cfg.server_url is None


def test_frozen():
    cfg = YouConfig(api_key="key")
    try:
        cfg.api_key = "other"  # type: ignore[misc]
        raise AssertionError("Should have raised FrozenInstanceError")
    except AttributeError:
        pass

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from youdotcom_temporal import __version__
from youdotcom_temporal._client import you_client
from youdotcom_temporal.config import YouConfig


def _fake_you():
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value="CLIENT")
    client.__aexit__ = AsyncMock(return_value=None)
    return client


async def test_client_kwargs_without_server_url():
    cfg = YouConfig(api_key="k", timeout_seconds=30.0)
    with patch("youdotcom_temporal._client.You", return_value=_fake_you()) as you_cls:
        async with you_client(cfg) as client:
            assert client == "CLIENT"
    assert you_cls.call_args.kwargs == {
        "api_key_auth": "k",
        "retry_config": None,
        "timeout_ms": 30000,
        "app_name": "youdotcom-temporal",
        "app_version": __version__,
    }

async def test_client_default_timeout_is_300s():
    cfg = YouConfig(api_key="k")
    assert cfg.timeout_seconds == 300.0
    with patch("youdotcom_temporal._client.You", return_value=_fake_you()) as you_cls:
        async with you_client(cfg):
            pass
    assert you_cls.call_args.kwargs["timeout_ms"] == 300000


async def test_client_includes_server_url_when_set():
    cfg = YouConfig(api_key="k", server_url="https://custom", timeout_seconds=5.0)
    with patch("youdotcom_temporal._client.You", return_value=_fake_you()) as you_cls:
        async with you_client(cfg):
            pass
    assert you_cls.call_args.kwargs == {
        "api_key_auth": "k",
        "retry_config": None,
        "timeout_ms": 5000,
        "app_name": "youdotcom-temporal",
        "app_version": __version__,
        "server_url": "https://custom",
    }


def test_attribution_header_includes_package_version():
    assert __version__ != "0.0.0-dev"

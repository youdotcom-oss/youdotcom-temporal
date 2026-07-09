from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from youdotcom._hooks.registration import YDCUserAgentOverrideHook
from youdotcom._hooks.types import BeforeRequestContext
from youdotcom.sdkconfiguration import SDKConfiguration

from youdotcom_temporal._client import (
    _USER_AGENT,
    _patch_user_agent,
    _TemporalUserAgentHook,
    you_client,
)
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
    }


async def test_client_includes_server_url_when_set():
    cfg = YouConfig(api_key="k", server_url="https://custom", timeout_seconds=5.0)
    with patch("youdotcom_temporal._client.You", return_value=_fake_you()) as you_cls:
        async with you_client(cfg):
            pass
    assert you_cls.call_args.kwargs == {
        "api_key_auth": "k",
        "retry_config": None,
        "timeout_ms": 5000,
        "server_url": "https://custom",
    }


def test_user_agent_constant():
    assert _USER_AGENT == "youdotcom-temporal/0.1.0"


def test_temporal_user_agent_hook_sets_header():
    hook = _TemporalUserAgentHook()
    request = httpx.Request("GET", "https://api.you.com/test")
    cfg = SDKConfiguration(
        client=None,
        client_supplied=False,
        async_client=None,
        async_client_supplied=False,
        debug_logger=MagicMock(),
    )
    ctx = BeforeRequestContext.__new__(BeforeRequestContext)
    ctx.config = cfg
    result = hook.before_request(ctx, request)
    assert result.headers["User-Agent"] == _USER_AGENT


def test_patch_user_agent_replaces_default_hook():
    sdk_config = SDKConfiguration(
        client=None,
        client_supplied=False,
        async_client=None,
        async_client_supplied=False,
        debug_logger=MagicMock(),
    )
    # Simulate what the SDK constructor does
    from youdotcom._hooks.sdkhooks import SDKHooks

    hooks = SDKHooks()
    sdk_config.__dict__["_hooks"] = hooks

    client = MagicMock()
    client.sdk_configuration = sdk_config

    _patch_user_agent(client)

    assert len(hooks.before_request_hooks) == 1
    assert isinstance(hooks.before_request_hooks[0], _TemporalUserAgentHook)
    assert not isinstance(
        hooks.before_request_hooks[0], YDCUserAgentOverrideHook
    )

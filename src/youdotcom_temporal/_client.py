from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from youdotcom import You
from youdotcom._hooks.registration import YDCUserAgentOverrideHook
from youdotcom._hooks.types import BeforeRequestContext, BeforeRequestHook

from .config import YouConfig

_USER_AGENT = "youdotcom-temporal/0.1.0"


class _TemporalUserAgentHook(BeforeRequestHook):
    """Set the temporal integration's User-Agent on every request."""

    def before_request(
        self, hook_ctx: BeforeRequestContext, request: httpx.Request
    ) -> httpx.Request:
        request.headers["User-Agent"] = _USER_AGENT
        if not request.headers.get("User-Agent"):
            request.headers["x-sdk-user-agent"] = _USER_AGENT
        return request


def _patch_user_agent(client: You) -> None:
    """Replace the SDK's default User-Agent hook with the temporal one."""
    hooks = client.sdk_configuration.__dict__.get("_hooks")
    if hooks is None:
        return
    hooks.before_request_hooks = [
        _TemporalUserAgentHook() if isinstance(h, YDCUserAgentOverrideHook) else h
        for h in hooks.before_request_hooks
    ]


@asynccontextmanager
async def you_client(cfg: YouConfig) -> AsyncIterator[You]:
    kwargs: dict[str, object] = {
        "api_key_auth": cfg.api_key,
        "retry_config": None,
        "timeout_ms": int(cfg.timeout_seconds * 1000),
    }
    if cfg.server_url:
        kwargs["server_url"] = cfg.server_url
    client = You(**kwargs)  # type: ignore[arg-type]
    _patch_user_agent(client)
    async with client as entered:
        yield entered

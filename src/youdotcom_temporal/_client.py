from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from youdotcom import You

from . import __version__
from .config import YouConfig

# Caller-identity segments emitted in the SDK's ``X-Client-Info`` header on
# every outbound request (shipped in youdotcom 3.1.2). The SDK keeps its own
# ``user-agent`` as ``youdotcom-python-sdk/<v>``; the plugin identity rides
# the attribution header instead.
_APP_NAME = "youdotcom-temporal"
_APP_VERSION = __version__


@asynccontextmanager
async def you_client(cfg: YouConfig) -> AsyncIterator[You]:
    kwargs: dict[str, object] = {
        "api_key_auth": cfg.api_key,
        "retry_config": None,
        "timeout_ms": int(cfg.timeout_seconds * 1000),
        "app_name": _APP_NAME,
        "app_version": _APP_VERSION,
    }
    if cfg.server_url:
        kwargs["server_url"] = cfg.server_url
    client = You(**kwargs)  # type: ignore[arg-type]
    async with client as entered:
        yield entered

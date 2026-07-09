from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from youdotcom import You

from . import __version__
from .config import YouConfig

_USER_AGENT = f"youdotcom-temporal/{__version__}"


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
    client.sdk_configuration.user_agent = _USER_AGENT
    async with client as entered:
        yield entered

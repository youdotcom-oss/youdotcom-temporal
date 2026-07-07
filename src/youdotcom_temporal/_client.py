from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from youdotcom import You

from .config import YouConfig


@asynccontextmanager
async def you_client(cfg: YouConfig) -> AsyncIterator[You]:
    kwargs: dict[str, object] = {
        "api_key_auth": cfg.api_key,
        "retry_config": None,
        "timeout_ms": int(cfg.timeout_seconds * 1000),
    }
    if cfg.server_url:
        kwargs["server_url"] = cfg.server_url
    async with You(**kwargs) as client:  # type: ignore[arg-type]
        yield client

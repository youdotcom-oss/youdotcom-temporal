from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class YouConfig:
    api_key: str | None = None
    server_url: str | None = None
    timeout_seconds: float = 30.0

    @classmethod
    def resolve(cls, override: YouConfig | None = None) -> YouConfig:
        if override is not None:
            return override
        return cls(
            api_key=os.getenv("YDC_API_KEY") or None,
            server_url=os.getenv("YDC_SERVER_URL") or None,
        )

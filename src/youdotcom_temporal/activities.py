from __future__ import annotations

from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError
from youdotcom import models

from ._client import you_client
from ._errors import to_temporal_error
from .config import YouConfig
from .models import ContentsInput, ResearchInput, SearchInput

_config: YouConfig | None = None


def set_config(cfg: YouConfig | None) -> None:
    global _config
    _config = cfg


def _cfg() -> YouConfig:
    cfg = YouConfig.resolve(_config)
    if not cfg.api_key:
        raise ApplicationError(
            "You.com plugin requires YDC_API_KEY (or YouConfig.api_key).",
            type="YouAuthError",
            non_retryable=True,
        )
    return cfg


@activity.defn(name="youdotcom_search")
async def youdotcom_search(inp: SearchInput) -> dict[str, Any]:
    cfg = _cfg()
    if not inp.query or not inp.query.strip():
        raise ApplicationError(
            "SearchInput.query must be non-empty.",
            type="YouValidationError",
            non_retryable=True,
        )
    try:
        async with you_client(cfg) as you:
            res = await you.search_async(
                query=inp.query,
                count=inp.count,
                freshness=inp.freshness,
                country=inp.country,
                language=inp.language,  # type: ignore[arg-type]
                safesearch=inp.safesearch,
                livecrawl=inp.livecrawl,
                livecrawl_formats=inp.livecrawl_formats,  # type: ignore[arg-type]
            )
        return res.model_dump(mode="json")
    except Exception as exc:
        raise to_temporal_error(exc) from exc


@activity.defn(name="youdotcom_research")
async def youdotcom_research(inp: ResearchInput) -> dict[str, Any]:
    cfg = _cfg()
    try:
        effort = models.ResearchEffort(inp.research_effort)
    except ValueError as exc:
        raise ApplicationError(
            f"Invalid research_effort '{inp.research_effort}'; "
            "allowed: lite, standard, deep, exhaustive.",
            type="YouValidationError",
            non_retryable=True,
        ) from exc
    try:
        async with you_client(cfg) as you:
            res = await you.research_async(input=inp.input, research_effort=effort)
        return res.model_dump(mode="json")
    except Exception as exc:
        raise to_temporal_error(exc) from exc


@activity.defn(name="youdotcom_contents")
async def youdotcom_contents(inp: ContentsInput) -> dict[str, Any]:
    cfg = _cfg()
    raw_formats = inp.formats or ["markdown"]
    try:
        formats = [models.ContentsFormats(f) for f in raw_formats]
    except ValueError as exc:
        raise ApplicationError(
            f"Invalid contents format in {raw_formats}; allowed: html, markdown, metadata.",
            type="YouValidationError",
            non_retryable=True,
        ) from exc
    try:
        async with you_client(cfg) as you:
            res = await you.contents_async(
                urls=inp.urls,
                formats=formats,
                crawl_timeout=inp.crawl_timeout,
            )
        return {"results": [r.model_dump(mode="json") for r in res]}
    except Exception as exc:
        raise to_temporal_error(exc) from exc


def you_activities() -> list[Any]:
    return [youdotcom_search, youdotcom_research, youdotcom_contents]

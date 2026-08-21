from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SearchInput:
    query: str
    count: int | None = None
    freshness: str | None = None
    offset: int | None = None
    country: str | None = None
    language: str | None = None
    safesearch: str | None = None
    livecrawl: str | None = None
    livecrawl_formats: list[str] | None = None
    extraction: dict[str, Any] | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    boost_domains: list[str] | None = None
    crawl_timeout: int | None = None


@dataclass
class ResearchInput:
    input: str
    research_effort: str = "standard"
    background: bool = False
    source_control: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    # Only used by youdotcom_research_background: max seconds to wait for
    # SSE streaming before falling back to polling. Default 120s, use
    # 14400 (4h) for frontier tasks.
    timeout_s: float | None = None


@dataclass
class ContentsInput:
    urls: list[str]
    formats: list[str] | None = None
    crawl_timeout: int = 10
    max_age: int | None = None


@dataclass
class AnswerInput:
    query: str
    freshness: str | None = None
    country: str | None = None
    language: str | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    boost_domains: list[str] | None = None


@dataclass
class FinanceResearchInput:
    input: str
    research_effort: str = "deep"

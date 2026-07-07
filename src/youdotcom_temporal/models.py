from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchInput:
    query: str
    count: int | None = None
    freshness: str | None = None
    country: str | None = None
    language: str | None = None
    safesearch: str | None = None
    livecrawl: str | None = None
    livecrawl_formats: list[str] | None = None


@dataclass
class ResearchInput:
    input: str
    research_effort: str = "lite"


@dataclass
class ContentsInput:
    urls: list[str]
    formats: list[str] | None = None
    crawl_timeout: int = 10

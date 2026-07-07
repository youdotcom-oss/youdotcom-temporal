from __future__ import annotations

from youdotcom_temporal.models import ContentsInput, ResearchInput, SearchInput


def test_search_input_defaults():
    inp = SearchInput(query="test")
    assert inp.query == "test"
    assert inp.count is None
    assert inp.freshness is None
    assert inp.country is None
    assert inp.language is None
    assert inp.safesearch is None
    assert inp.livecrawl is None
    assert inp.livecrawl_formats is None


def test_search_input_all_fields():
    inp = SearchInput(
        query="test",
        count=5,
        freshness="week",
        country="US",
        language="en",
        safesearch="moderate",
        livecrawl="always",
        livecrawl_formats=["markdown"],
    )
    assert inp.count == 5
    assert inp.livecrawl == "always"
    assert inp.livecrawl_formats == ["markdown"]


def test_research_input_default_effort():
    inp = ResearchInput(input="what is python")
    assert inp.research_effort == "lite"


def test_research_input_custom_effort():
    inp = ResearchInput(input="what is python", research_effort="deep")
    assert inp.research_effort == "deep"


def test_contents_input_defaults():
    inp = ContentsInput(urls=["https://example.com"])
    assert inp.formats is None
    assert inp.crawl_timeout == 10


def test_contents_input_all_fields():
    inp = ContentsInput(
        urls=["https://example.com"],
        formats=["html", "markdown"],
        crawl_timeout=30,
    )
    assert inp.formats == ["html", "markdown"]
    assert inp.crawl_timeout == 30

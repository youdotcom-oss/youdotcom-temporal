from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from youdotcom_temporal import activities
from youdotcom_temporal.activities import (
    you_activities,
    youdotcom_contents,
    youdotcom_research,
    youdotcom_search,
)
from youdotcom_temporal.models import ContentsInput, ResearchInput, SearchInput


@pytest.fixture
def env() -> ActivityEnvironment:
    return ActivityEnvironment()


@pytest.fixture(autouse=True)
def reset_config():
    activities.set_config(None)
    yield
    activities.set_config(None)


@pytest.fixture(autouse=True)
def set_test_key(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")


class _MockSearchResponse:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"results": [{"title": "Test Result", "url": "https://example.com"}]}


class _MockResearchResponse:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"answer": "Python is a programming language.", "sources": []}


class _MockContentsResponse:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"url": "https://example.com", "markdown": "# Example"}


def _mock_you_client(*_args: Any, **_kwargs: Any):
    mock_you = MagicMock()

    search_result = _MockSearchResponse()
    mock_you.search.unified_async = AsyncMock(return_value=search_result)

    research_result = _MockResearchResponse()
    mock_you.research_async = AsyncMock(return_value=research_result)

    contents_result = [_MockContentsResponse()]
    mock_you.contents.generate_async = AsyncMock(return_value=contents_result)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_you)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm


async def test_search_activity_success(env: ActivityEnvironment):
    with patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client):
        result = await env.run(youdotcom_search, SearchInput(query="python", count=5))
    assert isinstance(result, dict)
    assert "results" in result


async def test_search_activity_empty_query(env: ActivityEnvironment):
    with pytest.raises(ApplicationError) as exc_info:
        await env.run(youdotcom_search, SearchInput(query=""))
    assert exc_info.value.type == "YouValidationError"
    assert exc_info.value.non_retryable is True


async def test_search_activity_whitespace_query(env: ActivityEnvironment):
    with pytest.raises(ApplicationError) as exc_info:
        await env.run(youdotcom_search, SearchInput(query="   "))
    assert exc_info.value.type == "YouValidationError"


async def test_missing_api_key(env: ActivityEnvironment, monkeypatch):
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    activities.set_config(None)
    with pytest.raises(ApplicationError) as exc_info:
        await env.run(youdotcom_search, SearchInput(query="test"))
    assert exc_info.value.type == "YouAuthError"
    assert exc_info.value.non_retryable is True


async def test_research_activity_success(env: ActivityEnvironment):
    with patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client):
        result = await env.run(youdotcom_research, ResearchInput(input="what is python"))
    assert isinstance(result, dict)
    assert "answer" in result


async def test_research_activity_invalid_effort(env: ActivityEnvironment):
    with pytest.raises(ApplicationError) as exc_info:
        await env.run(
            youdotcom_research,
            ResearchInput(input="test", research_effort="invalid"),
        )
    assert exc_info.value.type == "YouValidationError"
    assert exc_info.value.non_retryable is True


async def test_contents_activity_success(env: ActivityEnvironment):
    with patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client):
        result = await env.run(
            youdotcom_contents,
            ContentsInput(urls=["https://example.com"]),
        )
    assert isinstance(result, dict)
    assert "results" in result
    assert len(result["results"]) == 1


async def test_contents_activity_invalid_format(env: ActivityEnvironment):
    with pytest.raises(ApplicationError) as exc_info:
        await env.run(
            youdotcom_contents,
            ContentsInput(urls=["https://example.com"], formats=["xml"]),
        )
    assert exc_info.value.type == "YouValidationError"
    assert exc_info.value.non_retryable is True


def test_you_activities_returns_three():
    acts = you_activities()
    assert len(acts) == 3

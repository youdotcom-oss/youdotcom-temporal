from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment
from youdotcom import errors as yerr
from youdotcom import models

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
    mock_you.search_async = AsyncMock(return_value=search_result)

    research_result = _MockResearchResponse()
    mock_you.research_async = AsyncMock(return_value=research_result)

    contents_result = [_MockContentsResponse()]
    mock_you.contents_async = AsyncMock(return_value=contents_result)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_you)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm


def _capturing_you_client() -> tuple[MagicMock, Any]:
    """Return (mock_you, factory). Inspect mock_you.<method>.call_args after running."""
    mock_you = MagicMock()
    mock_you.search_async = AsyncMock(return_value=_MockSearchResponse())
    mock_you.research_async = AsyncMock(return_value=_MockResearchResponse())
    mock_you.contents_async = AsyncMock(return_value=[_MockContentsResponse()])

    def _factory(*_args: Any, **_kwargs: Any):
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_you)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        return mock_cm

    return mock_you, _factory


def _mock_you_client_raising(exc: Exception):
    """Factory: returns a callable that mocks you_client and raises exc from the SDK call."""

    def _factory(*_args: Any, **_kwargs: Any):
        mock_you = MagicMock()
        mock_you.search_async = AsyncMock(side_effect=exc)
        mock_you.research_async = AsyncMock(side_effect=exc)
        mock_you.contents_async = AsyncMock(side_effect=exc)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_you)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        return mock_cm

    return _factory


def _make_sdk_error(cls: type[yerr.YouError], status: int) -> yerr.YouError:
    raw = httpx.Response(
        status_code=status,
        request=httpx.Request("GET", "https://api.you.com/v1/test"),
    )
    return cls(data=None, raw_response=raw, body=f"HTTP {status}")  # type: ignore[arg-type]


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


async def test_search_activity_maps_sdk_auth_error(env: ActivityEnvironment):
    """SDK auth error raised inside the activity must be mapped to YouAuthError."""
    sdk_err = _make_sdk_error(yerr.SearchUnauthorizedError, 401)
    with patch(
        "youdotcom_temporal.activities.you_client",
        side_effect=_mock_you_client_raising(sdk_err),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(youdotcom_search, SearchInput(query="test"))
    assert exc_info.value.type == "YouAuthError"
    assert exc_info.value.non_retryable is True


async def test_search_activity_maps_sdk_quota_error(env: ActivityEnvironment):
    """SDK 402 error raised inside the activity must be mapped to YouQuotaExhausted."""
    sdk_err = yerr.YouDefaultError(
        "Payment Required",
        raw_response=httpx.Response(
            status_code=402,
            request=httpx.Request("GET", "https://api.you.com/v1/test"),
        ),
        body="Payment Required",
    )
    with patch(
        "youdotcom_temporal.activities.you_client",
        side_effect=_mock_you_client_raising(sdk_err),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(youdotcom_search, SearchInput(query="test"))
    assert exc_info.value.type == "YouQuotaExhausted"
    assert exc_info.value.non_retryable is True


async def test_research_activity_maps_sdk_auth_error(env: ActivityEnvironment):
    """SDK auth error in research activity must be mapped to YouAuthError."""
    sdk_err = _make_sdk_error(yerr.ResearchUnauthorizedError, 401)
    with patch(
        "youdotcom_temporal.activities.you_client",
        side_effect=_mock_you_client_raising(sdk_err),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(youdotcom_research, ResearchInput(input="test"))
    assert exc_info.value.type == "YouAuthError"
    assert exc_info.value.non_retryable is True


async def test_contents_activity_maps_sdk_auth_error(env: ActivityEnvironment):
    """SDK auth error in contents activity must be mapped to YouAuthError."""
    sdk_err = _make_sdk_error(yerr.ContentsUnauthorizedError, 401)
    with patch(
        "youdotcom_temporal.activities.you_client",
        side_effect=_mock_you_client_raising(sdk_err),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(
                youdotcom_contents,
                ContentsInput(urls=["https://example.com"]),
            )
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


async def test_search_passes_every_param_to_sdk(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    inp = SearchInput(
        query="python",
        count=5,
        freshness="pw",
        country="US",
        language="en",
        safesearch="strict",
        livecrawl="always",
        livecrawl_formats=["markdown"],
    )
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_search, inp)
    assert mock_you.search_async.call_args.kwargs == {
        "query": "python",
        "count": 5,
        "freshness": "pw",
        "country": "US",
        "language": "en",
        "safesearch": "strict",
        "livecrawl": "always",
        "livecrawl_formats": ["markdown"],
    }


async def test_research_passes_effort_enum_to_sdk(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_research, ResearchInput(input="q", research_effort="deep"))
    assert mock_you.research_async.call_args.kwargs == {
        "input": "q",
        "research_effort": models.ResearchEffort.DEEP,
    }


async def test_contents_passes_formats_and_timeout_to_sdk(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    inp = ContentsInput(urls=["https://a"], formats=["html", "markdown"], crawl_timeout=25)
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_contents, inp)
    assert mock_you.contents_async.call_args.kwargs == {
        "urls": ["https://a"],
        "formats": [models.ContentsFormats.HTML, models.ContentsFormats.MARKDOWN],
        "crawl_timeout": 25,
    }


async def test_contents_defaults_to_markdown_format(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_contents, ContentsInput(urls=["https://a"]))
    assert mock_you.contents_async.call_args.kwargs["formats"] == [
        models.ContentsFormats.MARKDOWN
    ]


def test_you_activities_returns_three():
    acts = you_activities()
    assert len(acts) == 3

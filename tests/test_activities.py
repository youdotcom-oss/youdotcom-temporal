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
    youdotcom_answer,
    youdotcom_contents,
    youdotcom_finance_research,
    youdotcom_research,
    youdotcom_research_background,
    youdotcom_search,
)
from youdotcom_temporal.models import (
    AnswerInput,
    ContentsInput,
    FinanceResearchInput,
    ResearchInput,
    SearchInput,
)


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


class _MockAnswerResponse:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"answer": "The answer is 42.", "citations": [{"source": "https://example.com"}]}


class _MockFinanceResearchResponse:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"output": {"content": "Revenue grew 114%.", "sources": []}}


class _MockTaskDetail:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"id": "task-123", "status": "completed", "result": {"output": {"content": "Done."}}}


def _mock_you_client(*_args: Any, **_kwargs: Any):
    mock_you = MagicMock()

    mock_you.search_async = AsyncMock(return_value=_MockSearchResponse())
    mock_you.research_async = AsyncMock(return_value=_MockResearchResponse())
    mock_you.contents_async = AsyncMock(return_value=[_MockContentsResponse()])
    mock_you.answer_async = AsyncMock(return_value=_MockAnswerResponse())
    mock_you.finance_research_async = AsyncMock(return_value=_MockFinanceResearchResponse())

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
    mock_you.answer_async = AsyncMock(return_value=_MockAnswerResponse())
    mock_you.finance_research_async = AsyncMock(return_value=_MockFinanceResearchResponse())

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
        mock_you.answer_async = AsyncMock(side_effect=exc)
        mock_you.finance_research_async = AsyncMock(side_effect=exc)
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


# ---------------------------------------------------------------------------
# Search activity
# ---------------------------------------------------------------------------


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
    sdk_err = _make_sdk_error(yerr.UnauthorizedResponseError, 401)
    with patch(
        "youdotcom_temporal.activities.you_client",
        side_effect=_mock_you_client_raising(sdk_err),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(youdotcom_search, SearchInput(query="test"))
    assert exc_info.value.type == "YouAuthError"
    assert exc_info.value.non_retryable is True


async def test_search_activity_maps_sdk_quota_error(env: ActivityEnvironment):
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


async def test_search_passes_every_param_to_sdk(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    inp = SearchInput(
        query="python",
        count=5,
        freshness="pw",
        offset=2,
        country="US",
        language="en",
        safesearch="strict",
        livecrawl="always",
        livecrawl_formats=["markdown"],
        include_domains=["python.org"],
        exclude_domains=["reddit.com"],
        boost_domains=["stackoverflow.com"],
        crawl_timeout=15,
    )
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_search, inp)
    assert mock_you.search_async.call_args.kwargs == {
        "query": "python",
        "count": 5,
        "freshness": "pw",
        "offset": 2,
        "country": "US",
        "language": "en",
        "safesearch": "strict",
        "livecrawl": "always",
        "livecrawl_formats": ["markdown"],
        "include_domains": ["python.org"],
        "exclude_domains": ["reddit.com"],
        "boost_domains": ["stackoverflow.com"],
        "crawl_timeout": 15,
    }


# ---------------------------------------------------------------------------
# Research activity
# ---------------------------------------------------------------------------


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


async def test_research_activity_maps_sdk_auth_error(env: ActivityEnvironment):
    sdk_err = _make_sdk_error(yerr.ResearchUnauthorizedError, 401)
    with patch(
        "youdotcom_temporal.activities.you_client",
        side_effect=_mock_you_client_raising(sdk_err),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(youdotcom_research, ResearchInput(input="test"))
    assert exc_info.value.type == "YouAuthError"
    assert exc_info.value.non_retryable is True


async def test_research_passes_effort_enum_to_sdk(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_research, ResearchInput(input="q", research_effort="deep"))
    assert mock_you.research_async.call_args.kwargs == {
        "input": "q",
        "research_effort": models.ResearchEffort.DEEP,
        "background": False,
        "source_control": None,
        "output_schema": None,
    }


async def test_research_passes_source_control_and_schema(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    inp = ResearchInput(
        input="q",
        research_effort="standard",
        background=True,
        source_control={"include_domains": ["arxiv.org"]},
        output_schema={"type": "object", "properties": {}},
    )
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_research, inp)
    kwargs = mock_you.research_async.call_args.kwargs
    assert kwargs["background"] is True
    assert isinstance(kwargs["source_control"], models.SourceControl)
    assert kwargs["source_control"].include_domains == ["arxiv.org"]
    assert kwargs["output_schema"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# Contents activity
# ---------------------------------------------------------------------------


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


async def test_contents_activity_maps_sdk_auth_error(env: ActivityEnvironment):
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


async def test_contents_passes_formats_and_timeout_to_sdk(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    inp = ContentsInput(
        urls=["https://a"], formats=["html", "markdown"], crawl_timeout=25, max_age=3600
    )
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_contents, inp)
    assert mock_you.contents_async.call_args.kwargs == {
        "urls": ["https://a"],
        "formats": [models.ContentsFormats.HTML, models.ContentsFormats.MARKDOWN],
        "crawl_timeout": 25,
        "max_age": 3600,
    }


async def test_contents_defaults_to_markdown_format(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_contents, ContentsInput(urls=["https://a"]))
    assert mock_you.contents_async.call_args.kwargs["formats"] == [
        models.ContentsFormats.MARKDOWN
    ]


# ---------------------------------------------------------------------------
# Answer activity
# ---------------------------------------------------------------------------


async def test_answer_activity_success(env: ActivityEnvironment):
    with patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client):
        result = await env.run(
            youdotcom_answer,
            AnswerInput(query="What is the meaning of life?"),
        )
    assert isinstance(result, dict)
    assert "answer" in result


async def test_answer_activity_empty_query(env: ActivityEnvironment):
    with pytest.raises(ApplicationError) as exc_info:
        await env.run(youdotcom_answer, AnswerInput(query=""))
    assert exc_info.value.type == "YouValidationError"
    assert exc_info.value.non_retryable is True


async def test_answer_activity_maps_sdk_auth_error(env: ActivityEnvironment):
    sdk_err = _make_sdk_error(yerr.UnauthorizedResponseError, 401)
    with patch(
        "youdotcom_temporal.activities.you_client",
        side_effect=_mock_you_client_raising(sdk_err),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(youdotcom_answer, AnswerInput(query="test"))
    assert exc_info.value.type == "YouAuthError"
    assert exc_info.value.non_retryable is True


async def test_answer_passes_every_param_to_sdk(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    inp = AnswerInput(
        query="test query",
        freshness="week",
        country="US",
        language="EN",
        include_domains=["fda.gov"],
        exclude_domains=["reddit.com"],
        boost_domains=["nih.gov"],
    )
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(youdotcom_answer, inp)
    assert mock_you.answer_async.call_args.kwargs == {
        "query": "test query",
        "freshness": "week",
        "country": "US",
        "language": "EN",
        "include_domains": ["fda.gov"],
        "exclude_domains": ["reddit.com"],
        "boost_domains": ["nih.gov"],
    }


# ---------------------------------------------------------------------------
# Finance Research activity
# ---------------------------------------------------------------------------


async def test_finance_research_activity_success(env: ActivityEnvironment):
    with patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client):
        result = await env.run(
            youdotcom_finance_research,
            FinanceResearchInput(input="NVIDIA revenue growth"),
        )
    assert isinstance(result, dict)
    assert "output" in result


async def test_finance_research_activity_invalid_effort(env: ActivityEnvironment):
    with pytest.raises(ApplicationError) as exc_info:
        await env.run(
            youdotcom_finance_research,
            FinanceResearchInput(input="test", research_effort="lite"),
        )
    assert exc_info.value.type == "YouValidationError"
    assert exc_info.value.non_retryable is True


async def test_finance_research_activity_maps_sdk_auth_error(env: ActivityEnvironment):
    sdk_err = _make_sdk_error(yerr.FinanceResearchUnauthorizedError, 401)
    with patch(
        "youdotcom_temporal.activities.you_client",
        side_effect=_mock_you_client_raising(sdk_err),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(
                youdotcom_finance_research,
                FinanceResearchInput(input="test"),
            )
    assert exc_info.value.type == "YouAuthError"
    assert exc_info.value.non_retryable is True


async def test_finance_research_passes_effort_enum_to_sdk(env: ActivityEnvironment):
    mock_you, factory = _capturing_you_client()
    with patch("youdotcom_temporal.activities.you_client", side_effect=factory):
        await env.run(
            youdotcom_finance_research,
            FinanceResearchInput(input="q", research_effort="exhaustive"),
        )
    assert mock_you.finance_research_async.call_args.kwargs == {
        "input": "q",
        "research_effort": models.FinanceResearchEffort.EXHAUSTIVE,
    }


# ---------------------------------------------------------------------------
# Background Research activity
# ---------------------------------------------------------------------------


async def test_research_background_activity_success(env: ActivityEnvironment):
    with (
        patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client),
        patch(
            "youdotcom_temporal.activities.research_and_wait_async",
            new_callable=AsyncMock,
            return_value=_MockTaskDetail(),
        ),
    ):
        result = await env.run(
            youdotcom_research_background,
            ResearchInput(input="complex question"),
        )
    assert isinstance(result, dict)
    assert result["status"] == "completed"


async def test_research_background_activity_invalid_effort(env: ActivityEnvironment):
    with pytest.raises(ApplicationError) as exc_info:
        await env.run(
            youdotcom_research_background,
            ResearchInput(input="test", research_effort="invalid"),
        )
    assert exc_info.value.type == "YouValidationError"
    assert exc_info.value.non_retryable is True


async def test_research_background_maps_sdk_auth_error(env: ActivityEnvironment):
    sdk_err = _make_sdk_error(yerr.ResearchUnauthorizedError, 401)

    async def _raising_wait(*_a: Any, **_kw: Any):
        raise sdk_err

    with (
        patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client),
        patch(
            "youdotcom_temporal.activities.research_and_wait_async",
            new_callable=AsyncMock,
            side_effect=_raising_wait,
        ),
    ):
        with pytest.raises(ApplicationError) as exc_info:
            await env.run(
                youdotcom_research_background,
                ResearchInput(input="test"),
            )
    assert exc_info.value.type == "YouAuthError"
    assert exc_info.value.non_retryable is True


async def test_research_background_passes_params_to_helper(env: ActivityEnvironment):
    inp = ResearchInput(
        input="complex question",
        research_effort="frontier",
        source_control={"include_domains": ["arxiv.org"]},
        output_schema={"type": "object", "properties": {}},
    )
    with (
        patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client),
        patch(
            "youdotcom_temporal.activities.research_and_wait_async",
            new_callable=AsyncMock,
            return_value=_MockTaskDetail(),
        ) as mock_wait,
    ):
        await env.run(youdotcom_research_background, inp)

    call_kwargs = mock_wait.call_args.kwargs
    assert call_kwargs["input"] == "complex question"
    assert call_kwargs["research_effort"] == models.ResearchEffort.FRONTIER
    assert isinstance(call_kwargs["source_control"], models.SourceControl)
    assert call_kwargs["source_control"].include_domains == ["arxiv.org"]
    assert call_kwargs["output_schema"] == {"type": "object", "properties": {}}
    # Default timeout_s when not specified by user
    assert call_kwargs["timeout_s"] == 120.0


async def test_research_background_passes_custom_timeout(env: ActivityEnvironment):
    inp = ResearchInput(input="q", research_effort="frontier", timeout_s=14400.0)
    with (
        patch("youdotcom_temporal.activities.you_client", side_effect=_mock_you_client),
        patch(
            "youdotcom_temporal.activities.research_and_wait_async",
            new_callable=AsyncMock,
            return_value=_MockTaskDetail(),
        ) as mock_wait,
    ):
        await env.run(youdotcom_research_background, inp)
    assert mock_wait.call_args.kwargs["timeout_s"] == 14400.0


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def test_you_activities_returns_six():
    acts = you_activities()
    assert len(acts) == 6

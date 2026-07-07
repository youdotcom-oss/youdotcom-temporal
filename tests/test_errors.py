from __future__ import annotations

import httpx
import pytest
from temporalio.exceptions import ApplicationError
from youdotcom import errors as yerr

from youdotcom_temporal._errors import QUOTA_CTA, to_temporal_error


def _mock_response(status: int) -> httpx.Response:
    req = httpx.Request("GET", "https://api.you.com/v1/test")
    return httpx.Response(status_code=status, request=req)


def _make_error(cls: type[yerr.YouError], status: int) -> yerr.YouError:
    raw = _mock_response(status)
    return cls(data=None, raw_response=raw, body=f"HTTP {status}")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "error_cls",
    [
        yerr.SearchUnauthorizedError,
        yerr.SearchForbiddenError,
        yerr.ResearchUnauthorizedError,
        yerr.ResearchForbiddenError,
        yerr.ContentsUnauthorizedError,
        yerr.ContentsForbiddenError,
    ],
)
def test_auth_errors_non_retryable(error_cls):
    err = _make_error(error_cls, 401)
    result = to_temporal_error(err)
    assert isinstance(result, ApplicationError)
    assert result.type == "YouAuthError"
    assert result.non_retryable is True


def test_unprocessable_entity_non_retryable():
    err = _make_error(yerr.UnprocessableEntityError, 422)
    result = to_temporal_error(err)
    assert isinstance(result, ApplicationError)
    assert result.type == "YouValidationError"
    assert result.non_retryable is True


def test_quota_exhausted_non_retryable():
    raw = _mock_response(402)
    err = yerr.YouDefaultError(
        "Payment Required", raw_response=raw, body="Payment Required"
    )
    result = to_temporal_error(err)
    assert isinstance(result, ApplicationError)
    assert result.type == "YouQuotaExhausted"
    assert result.non_retryable is True
    assert QUOTA_CTA in result.message


def test_rate_limit_passthrough():
    raw = _mock_response(429)
    err = yerr.YouDefaultError(
        "Too Many Requests", raw_response=raw, body="Too Many Requests"
    )
    result = to_temporal_error(err)
    assert result is err


def test_server_error_passthrough():
    raw = _mock_response(500)
    err = yerr.YouDefaultError(
        "Internal Server Error", raw_response=raw, body="Internal Server Error"
    )
    result = to_temporal_error(err)
    assert result is err


def test_unknown_error_passthrough():
    err = RuntimeError("something went wrong")
    result = to_temporal_error(err)
    assert result is err


@pytest.mark.parametrize(
    "error_cls",
    [
        yerr.SearchInternalServerError,
        yerr.ResearchInternalServerError,
        yerr.ContentsInternalServerError,
    ],
)
def test_typed_internal_server_errors_passthrough(error_cls):
    # Typed 500 subclasses extend YouError directly, not YouDefaultError,
    # so they fall through to the final return-exc branch (retryable).
    err = _make_error(error_cls, 500)
    result = to_temporal_error(err)
    assert result is err

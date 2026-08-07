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


_AUTH_ERROR_CLASSES = [
    # Generic (search, answer)
    yerr.UnauthorizedResponseError,
    yerr.ForbiddenResponseError,
    # Research
    yerr.ResearchUnauthorizedError,
    yerr.ResearchForbiddenError,
    # Contents
    yerr.ContentsUnauthorizedError,
    yerr.ContentsForbiddenError,
    # Finance Research
    yerr.FinanceResearchUnauthorizedError,
    yerr.FinanceResearchForbiddenError,
    # Background research polling / streaming
    yerr.GetResearchTaskUnauthorizedError,
    yerr.GetResearchTaskForbiddenError,
    yerr.StreamResearchTaskUnauthorizedError,
    yerr.StreamResearchTaskForbiddenError,
]


@pytest.mark.parametrize("error_cls", _AUTH_ERROR_CLASSES)
def test_auth_errors_non_retryable(error_cls):
    err = _make_error(error_cls, 401)
    result = to_temporal_error(err)
    assert isinstance(result, ApplicationError)
    assert result.type == "YouAuthError"
    assert result.non_retryable is True


_VALIDATION_ERROR_CLASSES = [
    yerr.UnprocessableEntityResponseError,
    yerr.ResearchUnprocessableEntityError,
    yerr.FinanceResearchUnprocessableEntityError,
]


@pytest.mark.parametrize("error_cls", _VALIDATION_ERROR_CLASSES)
def test_validation_errors_non_retryable(error_cls):
    err = _make_error(error_cls, 422)
    result = to_temporal_error(err)
    assert isinstance(result, ApplicationError)
    assert result.type == "YouValidationError"
    assert result.non_retryable is True


def test_payment_required_non_retryable():
    err = _make_error(yerr.PaymentRequiredResponseError, 402)
    result = to_temporal_error(err)
    assert isinstance(result, ApplicationError)
    assert result.type == "YouQuotaExhausted"
    assert result.non_retryable is True
    assert QUOTA_CTA in result.message


def test_422_via_default_error_non_retryable():
    """422 from YouDefaultError (e.g. search/contents) must also map to YouValidationError."""
    raw = _mock_response(422)
    err = yerr.YouDefaultError(
        "Unprocessable Entity", raw_response=raw, body="Unprocessable Entity"
    )
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


_INTERNAL_SERVER_ERROR_CLASSES = [
    yerr.InternalServerErrorResponse,
    yerr.ResearchInternalServerError,
    yerr.ContentsInternalServerError,
    yerr.FinanceResearchInternalServerError,
    yerr.GetResearchTaskInternalServerError,
    yerr.StreamResearchTaskInternalServerError,
]


@pytest.mark.parametrize("error_cls", _INTERNAL_SERVER_ERROR_CLASSES)
def test_typed_internal_server_errors_passthrough(error_cls):
    # Typed 500 subclasses extend YouError directly, not YouDefaultError,
    # so they pass through as retryable.
    err = _make_error(error_cls, 500)
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


def test_http_timeout_maps_to_retryable_error():
    err = httpx.ReadTimeout("timed out")
    result = to_temporal_error(err)
    assert isinstance(result, ApplicationError)
    assert result.type == "YouTimeoutError"
    assert result.non_retryable is False

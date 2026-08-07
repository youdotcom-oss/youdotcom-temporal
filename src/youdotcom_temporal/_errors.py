from __future__ import annotations

from temporalio.exceptions import ApplicationError
from youdotcom import errors as yerr

QUOTA_CTA = "You.com quota exhausted. Check your usage and plan options at https://you.com/platform."

_AUTH_ERRORS = (
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
    # Background research task polling / streaming
    yerr.GetResearchTaskUnauthorizedError,
    yerr.GetResearchTaskForbiddenError,
    yerr.StreamResearchTaskUnauthorizedError,
    yerr.StreamResearchTaskForbiddenError,
)

_VALIDATION_ERRORS = (
    yerr.UnprocessableEntityResponseError,
    yerr.ResearchUnprocessableEntityError,
    yerr.FinanceResearchUnprocessableEntityError,
)

_INTERNAL_SERVER_ERRORS = (
    yerr.InternalServerErrorResponse,
    yerr.ResearchInternalServerError,
    yerr.ContentsInternalServerError,
    yerr.FinanceResearchInternalServerError,
    yerr.GetResearchTaskInternalServerError,
    yerr.StreamResearchTaskInternalServerError,
)


def to_temporal_error(exc: Exception) -> Exception:
    if isinstance(exc, _AUTH_ERRORS):
        return ApplicationError("You.com auth failed", type="YouAuthError", non_retryable=True)
    if isinstance(exc, yerr.PaymentRequiredResponseError):
        return ApplicationError(QUOTA_CTA, type="YouQuotaExhausted", non_retryable=True)
    if isinstance(exc, _VALIDATION_ERRORS):
        return ApplicationError(
            "You.com rejected the request", type="YouValidationError", non_retryable=True
        )
    if isinstance(exc, _INTERNAL_SERVER_ERRORS):
        return exc
    if isinstance(exc, yerr.YouDefaultError):
        status = getattr(exc, "status_code", None)
        if status == 429:
            return exc
        if status == 402:
            return ApplicationError(QUOTA_CTA, type="YouQuotaExhausted", non_retryable=True)
        if status == 422:
            return ApplicationError(
                "You.com rejected the request", type="YouValidationError", non_retryable=True
            )
        return exc
    return exc

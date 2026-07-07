from __future__ import annotations

from temporalio.exceptions import ApplicationError
from youdotcom import errors as yerr

QUOTA_CTA = "You.com quota exhausted. See https://you.com/platform/api-keys for plan limits."


def to_temporal_error(exc: Exception) -> Exception:
    if isinstance(
        exc,
        (
            yerr.SearchUnauthorizedError,
            yerr.SearchForbiddenError,
            yerr.ResearchUnauthorizedError,
            yerr.ResearchForbiddenError,
            yerr.ContentsUnauthorizedError,
            yerr.ContentsForbiddenError,
        ),
    ):
        return ApplicationError("You.com auth failed", type="YouAuthError", non_retryable=True)
    if isinstance(exc, yerr.UnprocessableEntityError):
        return ApplicationError(
            "You.com rejected the request", type="YouValidationError", non_retryable=True
        )
    if isinstance(exc, yerr.YouDefaultError):
        status = getattr(exc, "status_code", None)
        if status == 429:
            return exc
        if status == 402:
            return ApplicationError(QUOTA_CTA, type="YouQuotaExhausted", non_retryable=True)
        return exc
    return exc

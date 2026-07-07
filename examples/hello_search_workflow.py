from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from youdotcom_temporal import SearchInput, youdotcom_search


@workflow.defn
class HelloSearch:
    @workflow.run
    async def run(self, query: str) -> dict:
        return await workflow.execute_activity(
            youdotcom_search,
            SearchInput(query=query, count=5),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                maximum_attempts=5,
                maximum_interval=timedelta(seconds=60),
                non_retryable_error_types=[
                    "YouAuthError",
                    "YouValidationError",
                    "YouQuotaExhausted",
                ],
            ),
        )

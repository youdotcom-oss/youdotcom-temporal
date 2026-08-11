"""Long-running research workflow — `youdotcom_research_background`.

This workflow uses the background research activity for tasks that may take
minutes (deep, exhaustive) or up to 4 hours (frontier). Two things matter:

1. The activity's ``StartToClose`` timeout must outlast the longest expected
   task. The SDK's ``research_and_wait_async`` helper defaults to a 600s SSE
   stream timeout and falls back to polling on timeout. The plugin's default
   ``timeout_s`` of 120s makes it fall back to polling faster; bump it for
   ``frontier`` tasks.
2. ``ResearchInput.timeout_s`` is the helper's stream timeout; the workflow's
   ``StartToClose`` is the wall-clock ceiling for the activity.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from youdotcom_temporal import ResearchInput, youdotcom_research_background


@workflow.defn
class HelloBackgroundResearch:
    @workflow.run
    async def run(self, question: str) -> dict:
        # Lite effort typically completes in 5-30 seconds.
        # For frontier tasks, bump timeout_s to 14400 and StartToClose accordingly.
        return await workflow.execute_activity(
            youdotcom_research_background,
            ResearchInput(
                input=question,
                research_effort="lite",
                timeout_s=120.0,  # SSE stream timeout; falls back to polling
            ),
            # Wall-clock ceiling for the activity. Lite: 5min is plenty.
            # Frontier: bump to 4h+ and set ResearchInput.timeout_s=14400.
            start_to_close_timeout=timedelta(minutes=5),
            summary=f"you.com research: {question}",
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                maximum_interval=timedelta(seconds=60),
                non_retryable_error_types=[
                    "YouAuthError",
                    "YouValidationError",
                    "YouQuotaExhausted",
                ],
            ),
        )

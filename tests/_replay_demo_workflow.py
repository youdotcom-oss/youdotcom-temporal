"""The Workflow used by ``test_replay_safety``.

Lives in its own module because the sandbox re-imports the module a Workflow is
defined in. While this lived in the test module, that re-import re-executed the
module-level ``shutil.which("temporal")`` in the file's ``skipif`` marker, which
the sandbox blocks -- so the test could only ever pass by being skipped.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from youdotcom_temporal import SearchInput, youdotcom_search


@workflow.defn
class ReplayDemo:
    @workflow.run
    async def run(self, query: str) -> dict[str, Any]:
        return await workflow.execute_activity(
            youdotcom_search,
            SearchInput(query=query, count=3),
            start_to_close_timeout=timedelta(seconds=30),
            summary=f"you.com search: {query}",
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

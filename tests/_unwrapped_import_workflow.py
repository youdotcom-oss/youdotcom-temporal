"""A Workflow that imports this package the way a user naturally would.

Lives in its own module because the workflow sandbox re-imports the module a
Workflow is defined in; defining it inside a test module would drag pytest into
the sandbox.

The import below is deliberately *not* wrapped in
``workflow.unsafe.imports_passed_through()``. That is the point: Python imports
the parent package before a submodule body runs, so an eager import in
``youdotcom_temporal/__init__`` cannot be covered by a passthrough block placed
anywhere downstream of it.

The Activity is referenced by name rather than imported. Importing the Activity
*function* would load the You.com SDK on any import scheme, lazy or not, since
that is the module the function lives in -- so a Workflow that wants to avoid
the SDK entirely refers to its Activities by name, which Temporal supports.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow

from youdotcom_temporal import SearchInput


@workflow.defn
class UnwrappedImportWorkflow:
    @workflow.run
    async def run(self, query: str) -> dict[str, Any]:
        return await workflow.execute_activity(
            "youdotcom_search",
            SearchInput(query=query, count=3),
            start_to_close_timeout=timedelta(seconds=30),
            result_type=dict,
        )

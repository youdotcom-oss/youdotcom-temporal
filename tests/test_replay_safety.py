from __future__ import annotations

import shutil
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

with workflow.unsafe.imports_passed_through():
    from youdotcom_temporal import SearchInput, YouPlugin, youdotcom_search
    from youdotcom_temporal.plugin import _you_workflow_runner

pytestmark = pytest.mark.skipif(
    shutil.which("temporal") is None,
    reason="replay-safety test needs the local Temporal dev server CLI",
)


class _MockSearchResponse:
    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"results": [{"title": "T", "url": "https://example.com"}]}


def _mock_you_client(*_a: Any, **_kw: Any) -> Any:
    mock_you = MagicMock()
    mock_you.search_async = AsyncMock(return_value=_MockSearchResponse())
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_you)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@workflow.defn
class _ReplayDemo:
    @workflow.run
    async def run(self, query: str) -> dict:
        return await workflow.execute_activity(
            youdotcom_search,
            SearchInput(query=query, count=3),
            start_to_close_timeout=timedelta(seconds=30),
            summary=f"you.com search: {query}",
            retry_policy=RetryPolicy(maximum_attempts=2),
        )


async def test_activity_not_re_invoked_on_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activities must not re-execute on replay (no duplicate side effects).

    Runs a workflow once against a local dev server with a mocked SDK client,
    records that the SDK was called exactly once, then replays the recorded
    history and asserts the SDK was NOT called again. This is the property the
    Temporal AI partner review standards call out under "testing plugins for
    side effects".
    """
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    cli_path = shutil.which("temporal")
    env = await WorkflowEnvironment.start_local(dev_server_existing_path=cli_path or None)
    async with env:
        with patch(
            "youdotcom_temporal.activities.you_client", side_effect=_mock_you_client
        ) as mock_factory:
            async with Worker(
                env.client,
                task_queue="replay-safety",
                workflows=[_ReplayDemo],
                plugins=[YouPlugin()],
            ):
                result = await env.client.execute_workflow(
                    _ReplayDemo.run,
                    "hello",
                    id="replay-safety-wf",
                    task_queue="replay-safety",
                )
            assert isinstance(result, dict)
            # Exactly one live SDK call during the initial run.
            assert mock_factory.call_count == 1
            history = await env.client.get_workflow_handle(
                "replay-safety-wf"
            ).fetch_history()

        # Replaying the recorded history reconstructs the workflow without
        # re-executing activities, so the SDK factory must NOT be called again.
        # Use the plugin's sandbox runner so replay matches production.
        replayer = Replayer(
            workflows=[_ReplayDemo],
            workflow_runner=_you_workflow_runner(SandboxedWorkflowRunner()),
        )
        replay = await replayer.replay_workflow(history, raise_on_replay_failure=False)
        assert replay.replay_failure is None
        assert mock_factory.call_count == 1

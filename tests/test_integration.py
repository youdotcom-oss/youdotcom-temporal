from __future__ import annotations

import os
import shutil
from datetime import timedelta

import pytest
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    from youdotcom_temporal import (
        YouPlugin,
        youdotcom_contents,
        youdotcom_research,
        youdotcom_search,
    )
    from youdotcom_temporal.models import ContentsInput, ResearchInput, SearchInput

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("YDC_API_KEY"),
        reason="integration test requires YDC_API_KEY and hits the real You.com API",
    ),
]

_TASK_QUEUE = "youdotcom-temporal-it"


@workflow.defn
class _DemoWorkflow:
    @workflow.run
    async def run(self, query: str) -> dict:
        search = await workflow.execute_activity(
            youdotcom_search,
            SearchInput(query=query, count=2),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        research = await workflow.execute_activity(
            youdotcom_research,
            ResearchInput(input=query),
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        contents = await workflow.execute_activity(
            youdotcom_contents,
            ContentsInput(urls=["https://en.wikipedia.org/wiki/Paris"]),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        return {"search": search, "research": research, "contents": contents}


async def test_plugin_runs_all_activities_against_local_server():
    """Full path: local Temporal server + YouPlugin worker + real You.com API calls."""
    cli_path = shutil.which("temporal")
    env = await WorkflowEnvironment.start_local(dev_server_existing_path=cli_path or None)
    async with env:
        async with Worker(
            env.client,
            task_queue=_TASK_QUEUE,
            workflows=[_DemoWorkflow],
            plugins=[YouPlugin()],
        ):
            result = await env.client.execute_workflow(
                _DemoWorkflow.run,
                "what is the capital of france",
                id=_TASK_QUEUE,
                task_queue=_TASK_QUEUE,
            )

    assert isinstance(result["search"]["results"], dict)
    assert result["research"]["output"]
    assert len(result["contents"]["results"]) == 1

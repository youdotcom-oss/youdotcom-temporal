from __future__ import annotations

import os
import shutil
from datetime import timedelta

import pytest
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    from youdotcom_temporal import (
        YouPlugin,
        youdotcom_answer,
        youdotcom_contents,
        youdotcom_finance_research,
        youdotcom_research,
        youdotcom_research_background,
        youdotcom_search,
    )
    from youdotcom_temporal.models import (
        AnswerInput,
        ContentsInput,
        FinanceResearchInput,
        ResearchInput,
        SearchInput,
    )

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("YDC_API_KEY"),
        reason="integration test requires YDC_API_KEY and hits the real You.com API",
    ),
]

_TASK_QUEUE = "youdotcom-temporal-it"


# ---------------------------------------------------------------------------
# Individual activity tests (ActivityEnvironment — no Temporal server needed)
# ---------------------------------------------------------------------------


@pytest.fixture
def activity_env() -> ActivityEnvironment:
    return ActivityEnvironment()


async def test_integration_search(activity_env: ActivityEnvironment):
    """Real search call: verify response has web results with titles and URLs."""
    result = await activity_env.run(
        youdotcom_search,
        SearchInput(query="capital of france", count=3),
    )
    assert isinstance(result, dict)
    assert "results" in result
    web = result["results"].get("web", [])
    assert len(web) > 0
    assert all("title" in w and "url" in w for w in web)


async def test_integration_search_with_domain_filters(activity_env: ActivityEnvironment):
    """Real search with include_domains: verify all results are from allowed domains."""
    result = await activity_env.run(
        youdotcom_search,
        SearchInput(
            query="artificial intelligence",
            count=5,
            include_domains=["wikipedia.org"],
        ),
    )
    web = result["results"].get("web", [])
    assert len(web) > 0
    for w in web:
        assert "wikipedia.org" in w["url"]


async def test_integration_answer(activity_env: ActivityEnvironment):
    """Real answer call: verify answer text and citations."""
    result = await activity_env.run(
        youdotcom_answer,
        AnswerInput(query="What is the capital of France?"),
    )
    assert isinstance(result, dict)
    assert "answer" in result
    assert len(result["answer"]) > 0
    citations = result.get("citations") or []
    assert len(citations) > 0
    assert all("source" in c for c in citations)


async def test_integration_research(activity_env: ActivityEnvironment):
    """Real research call (lite): verify output has content and sources."""
    result = await activity_env.run(
        youdotcom_research,
        ResearchInput(input="What is Python?", research_effort="lite"),
    )
    assert isinstance(result, dict)
    assert "output" in result
    assert len(result["output"].get("content", "")) > 0


async def test_integration_contents(activity_env: ActivityEnvironment):
    """Real contents call: verify markdown extraction from a known URL."""
    result = await activity_env.run(
        youdotcom_contents,
        ContentsInput(urls=["https://en.wikipedia.org/wiki/Python_(programming_language)"]),
    )
    assert isinstance(result, dict)
    assert "results" in result
    pages = result["results"]
    assert len(pages) == 1
    assert pages[0].get("markdown") or pages[0].get("html")


async def test_integration_finance_research(activity_env: ActivityEnvironment):
    """Real finance research call (deep): verify output has financial content."""
    result = await activity_env.run(
        youdotcom_finance_research,
        FinanceResearchInput(
            input="What were NVIDIA's revenue and growth in fiscal year 2025?",
            research_effort="deep",
        ),
    )
    assert isinstance(result, dict)
    assert "output" in result
    content = result["output"].get("content", "")
    assert len(content) > 0


async def test_integration_research_background(activity_env: ActivityEnvironment):
    """Real background research call (lite): verify task completes with result."""
    result = await activity_env.run(
        youdotcom_research_background,
        ResearchInput(input="What is Python?", research_effort="lite", timeout_s=30.0),
    )
    assert isinstance(result, dict)
    assert result.get("status") == "completed"
    assert result.get("result") is not None


# ---------------------------------------------------------------------------
# Full workflow test (WorkflowEnvironment — local Temporal server required)
# ---------------------------------------------------------------------------


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
        answer = await workflow.execute_activity(
            youdotcom_answer,
            AnswerInput(query=query),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        contents = await workflow.execute_activity(
            youdotcom_contents,
            ContentsInput(urls=["https://en.wikipedia.org/wiki/Paris"]),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        return {"search": search, "answer": answer, "contents": contents}


async def test_plugin_workflow_against_local_server():
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
    assert len(result["answer"]["answer"]) > 0
    assert len(result["contents"]["results"]) == 1

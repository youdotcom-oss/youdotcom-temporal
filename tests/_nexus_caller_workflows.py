"""Caller-side Workflows for the Nexus round-trip test.

These stand in for a consumer in another Namespace: they reach You.com only
through the Nexus Endpoint, and the Worker that runs them registers no
``YouPlugin`` and no Activities. Imports here are unwrapped on purpose --
that is the shape a real caller has.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

from youdotcom_temporal.contract import (
    AnswerRequest,
    AnswerResponse,
    ContentsOutput,
    ContentsRequest,
    FinanceResearchRequest,
    FinanceResearchResponse,
    ResearchRequest,
    ResearchResponse,
    SearchRequest,
    SearchResponse,
    TaskDetail,
    YouDotComService,
)
from youdotcom_temporal.models import (
    AnswerInput,
    ContentsInput,
    FinanceResearchInput,
    ResearchInput,
    SearchInput,
)

ENDPOINT = "you-nexus-test-endpoint"
_TIMEOUT = timedelta(minutes=2)


def _client() -> workflow.NexusClient[YouDotComService]:
    return workflow.create_nexus_client(service=YouDotComService, endpoint=ENDPOINT)


@workflow.defn
class CallSearch:
    @workflow.run
    async def run(self, query: str) -> SearchResponse:
        return await _client().execute_operation(
            YouDotComService.search,
            SearchRequest(input=SearchInput(query=query, count=3)),
            schedule_to_close_timeout=_TIMEOUT,
        )


@workflow.defn
class CallSearchIdempotent:
    """Search carrying a caller-supplied idempotency key."""

    @workflow.run
    async def run(self, args: list[str]) -> SearchResponse:
        query, key = args
        return await _client().execute_operation(
            YouDotComService.search,
            SearchRequest(input=SearchInput(query=query, count=3), idempotency_key=key),
            schedule_to_close_timeout=_TIMEOUT,
        )


@workflow.defn
class CallAnswer:
    @workflow.run
    async def run(self, query: str) -> AnswerResponse:
        return await _client().execute_operation(
            YouDotComService.answer,
            AnswerRequest(input=AnswerInput(query=query)),
            schedule_to_close_timeout=_TIMEOUT,
        )


@workflow.defn
class CallContents:
    @workflow.run
    async def run(self, url: str) -> ContentsOutput:
        return await _client().execute_operation(
            YouDotComService.contents,
            ContentsRequest(input=ContentsInput(urls=[url])),
            schedule_to_close_timeout=_TIMEOUT,
        )


@workflow.defn
class CallContentsMany:
    """`contents` at fan-out -- the Operation with the largest result payload."""

    @workflow.run
    async def run(self, urls: list[str]) -> ContentsOutput:
        return await _client().execute_operation(
            YouDotComService.contents,
            ContentsRequest(input=ContentsInput(urls=urls)),
            schedule_to_close_timeout=_TIMEOUT,
        )


@workflow.defn
class CallResearch:
    @workflow.run
    async def run(self, question: str) -> ResearchResponse:
        return await _client().execute_operation(
            YouDotComService.research,
            ResearchRequest(input=ResearchInput(input=question)),
            schedule_to_close_timeout=_TIMEOUT,
        )


@workflow.defn
class CallFinanceResearch:
    @workflow.run
    async def run(self, question: str) -> FinanceResearchResponse:
        return await _client().execute_operation(
            YouDotComService.finance_research,
            FinanceResearchRequest(input=FinanceResearchInput(input=question)),
            schedule_to_close_timeout=_TIMEOUT,
        )


@workflow.defn
class CallResearchBackground:
    @workflow.run
    async def run(self, question: str) -> TaskDetail:
        return await _client().execute_operation(
            YouDotComService.research_background,
            ResearchRequest(input=ResearchInput(input=question, research_effort="lite")),
            schedule_to_close_timeout=_TIMEOUT,
        )


def caller_workflows() -> list[type]:
    return [
        CallSearch,
        CallSearchIdempotent,
        CallAnswer,
        CallContents,
        CallContentsMany,
        CallResearch,
        CallFinanceResearch,
        CallResearchBackground,
    ]

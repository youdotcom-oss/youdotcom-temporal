"""The Nexus Service contract: request types, result types, and the Service.

This is what a caller in another Namespace imports. Results are the You.com SDK's
own response models, so callers get accurate, fully nested types that the SDK
team maintains, rather than types hand-rolled here that would drift::

    out = await client.execute_operation(YouDotComService.search, req, ...)
    out.results.web[0].title      # typed all the way down

Callers must configure Temporal's pydantic converter on their Client and Worker,
since the SDK models are pydantic::

    from temporalio.contrib.pydantic import pydantic_data_converter
    client = await Client.connect(..., data_converter=pydantic_data_converter)

Sandbox note:
    The SDK import below is wrapped in ``imports_passed_through()`` so a caller
    Workflow can import this module directly without needing its own escape
    hatch. The SDK has resolved its exports lazily (PEP 562) since 3.1.2, so
    ``import youdotcom`` no longer pulls ``urllib.request`` or ``httpx`` into
    ``sys.modules``; the wrapper is belt-and-braces rather than load-bearing.
"""

from __future__ import annotations

from dataclasses import dataclass

import nexusrpc
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from youdotcom.models import (
        AnswerResponse,
        ContentsResponse,
        FinanceResearchResponse,
        ResearchResponse,
        SearchResponse,
        TaskDetail,
    )

from youdotcom_temporal.models import (
    AnswerInput,
    ContentsInput,
    FinanceResearchInput,
    ResearchInput,
    SearchInput,
)

__all__ = [
    "AnswerRequest",
    "AnswerResponse",
    "ContentsOutput",
    "ContentsRequest",
    "ContentsResponse",
    "FinanceResearchRequest",
    "FinanceResearchResponse",
    "ResearchRequest",
    "ResearchResponse",
    "SearchRequest",
    "SearchResponse",
    "TaskDetail",
    "YouDotComService",
]


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
#
# Each Operation takes the Activity input plus an optional idempotency key.
#
# Temporal's guidance is that a backing Workflow Id should be business-
# meaningful and travel in the Operation input, because Workflow Ids are what
# deduplicate Workflow starts. Without one, a retried Nexus StartOperation
# request starts a second Workflow and a second billable You.com call. Only the
# caller knows what makes two requests the "same" request, so only the caller
# can supply it.
#
# The key is optional; omitting it leaves starts non-idempotent, which is the
# right default for genuinely one-off calls.


@dataclass
class SearchRequest:
    input: SearchInput
    idempotency_key: str | None = None


@dataclass
class AnswerRequest:
    input: AnswerInput
    idempotency_key: str | None = None


@dataclass
class ContentsRequest:
    input: ContentsInput
    idempotency_key: str | None = None


@dataclass
class ResearchRequest:
    input: ResearchInput
    idempotency_key: str | None = None


@dataclass
class FinanceResearchRequest:
    input: FinanceResearchInput
    idempotency_key: str | None = None


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
#
# Five Operations return the SDK response model directly. `contents` is the
# exception: the SDK returns a bare list, and a list is a poor Nexus result type
# because it cannot carry additional fields later without breaking callers. It
# gets a thin envelope; the elements inside are still SDK models.


@dataclass
class ContentsOutput:
    """One `ContentsResponse` per requested URL, in request order."""

    results: list[ContentsResponse]


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


@nexusrpc.service
class YouDotComService:
    """Nexus Service contract for You.com search, answer, contents, research.

    Every Operation is asynchronous and backed by a Workflow on the handler
    side. Callers reach these through a Nexus Endpoint pointing at the handler's
    Namespace and Task Queue.
    """

    search: nexusrpc.Operation[SearchRequest, SearchResponse]
    answer: nexusrpc.Operation[AnswerRequest, AnswerResponse]
    contents: nexusrpc.Operation[ContentsRequest, ContentsOutput]
    research: nexusrpc.Operation[ResearchRequest, ResearchResponse]
    finance_research: nexusrpc.Operation[
        FinanceResearchRequest, FinanceResearchResponse
    ]
    research_background: nexusrpc.Operation[ResearchRequest, TaskDetail]

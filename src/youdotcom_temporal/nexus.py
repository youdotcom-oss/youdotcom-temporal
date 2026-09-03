"""Temporal Nexus Service exposing You.com calls as cross-Namespace Operations.

This is the Nexus layer on top of the Activity layer in
:mod:`youdotcom_temporal.activities`. A Nexus Service lets other teams call
You.com search, answer, contents, and research through a durable contract
across Namespace boundaries.

Every Operation is asynchronous and backed by a Workflow from
:mod:`youdotcom_temporal.workflows`. Nexus synchronous operations must finish
within the 10-second handler deadline, but several You.com calls routinely
exceed that (full-page search, multi-URL contents, research, background
research up to 4 hours). Backing every Operation with a Workflow removes that
cliff and gives the caller durable, observable execution.

Caller-side note:
    Callers should import from :mod:`youdotcom_temporal.contract`, not from
    here::

        from youdotcom_temporal.contract import SearchRequest, YouDotComService
        from youdotcom_temporal.models import SearchInput

    ``YouDotComService`` is re-exported below for convenience, but importing it
    from this module also pulls in the handler: the backing Workflows and, in
    turn, the Activity layer. A caller needs none of that. The contract module
    carries the types and nothing else.

    Either import is safe inside a Workflow sandbox without an escape hatch, as
    the contract wraps its own SDK import. It does load the You.com SDK, which
    is deliberate -- results are the SDK's response models. The SDK has resolved
    its exports lazily (PEP 562) since 3.1.2, so that import no longer pulls the
    HTTP stack with it.

Cancellation:
    Cancelling an Operation cancels the backing Workflow, but not the upstream
    work. The You.com API exposes no cancellation: the research surface is
    ``POST /v1/research`` to submit plus two GETs to poll or stream, with no
    DELETE, and the SDK has no cancel method. Once a request is submitted it
    runs to completion and is billed, so no client-side mechanism can call it
    back. This is a property of the API rather than something the plugin can
    fix; cancelling frees the Workflow and the Worker slot, nothing more.

Register the handler and the backing Workflows on the same Worker that runs
the Activities (the ``YouPlugin`` registers the Activities and the sandbox
passthrough)::

    from temporalio.client import Client
    from temporalio.worker import Worker
    from youdotcom_temporal import YouPlugin
    from youdotcom_temporal.nexus import you_nexus_service_handler
    from youdotcom_temporal.workflows import you_nexus_workflows

    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue="you-nexus",
        workflows=you_nexus_workflows(),
        nexus_service_handlers=[you_nexus_service_handler()],
        plugins=[YouPlugin()],
    )
    await worker.run()
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from typing import Any

import nexusrpc
from temporalio import nexus
from temporalio.common import WorkflowIDConflictPolicy

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
from youdotcom_temporal.workflows import (
    YouAnswerWorkflow,
    YouContentsWorkflow,
    YouFinanceResearchWorkflow,
    YouResearchBackgroundWorkflow,
    YouResearchWorkflow,
    YouSearchWorkflow,
)

__all__ = [
    "YouDotComService",
    "YouDotComServiceHandler",
    "you_nexus_service_handler",
]


@nexusrpc.handler.service_handler(service=YouDotComService)
class YouDotComServiceHandler:
    """Nexus Service handler that backs each Operation with a Workflow.

    Every Operation starts a Workflow from :mod:`youdotcom_temporal.workflows`,
    which runs the corresponding Activity with a per-Activity
    ``start_to_close_timeout``. The Workflow result is delivered back to the
    Nexus caller when it completes.

    Idempotency is the caller's to opt into. Supplying
    ``idempotency_key`` on the request makes the backing Workflow Id
    deterministic, so a retried Nexus StartOperation request attaches to the
    Workflow already running instead of starting a second one and paying for a
    second You.com call. Without a key the Id is random and starts are not
    deduplicated, which is the right behaviour for genuinely one-off calls.
    """

    @staticmethod
    def _workflow_id(prefix: str, idempotency_key: str | None, inp: Any) -> str:
        """Deterministic when the caller supplies a key, unique otherwise.

        The key alone is not enough. Callers pick their own key strings and
        nothing stops two of them choosing the same one -- ``"order-123"`` is an
        obvious collision waiting to happen -- and with
        ``WorkflowIDConflictPolicy.USE_EXISTING`` a collision means the second
        caller attaches to the first caller's Workflow and receives *their*
        results. Binding the request into the Id keeps a key idempotent for the
        request it was issued for and inert across different ones.

        The digest covers the full key as well as the request, so two long keys
        sharing a prefix cannot collide once the readable part is truncated.
        """
        if idempotency_key is None:
            return f"{prefix}-{uuid.uuid4()}"

        canonical = json.dumps(dataclasses.asdict(inp), sort_keys=True, default=str)
        digest = hashlib.sha256(
            f"{idempotency_key}\0{canonical}".encode()
        ).hexdigest()[:16]
        # Keep a readable slice of the key so the Id is still recognisable in the
        # UI, and bound it so an oversized key cannot push past Temporal's limit.
        return f"{prefix}-{idempotency_key[:64]}-{digest}"

    @nexus.workflow_run_operation
    async def search(
        self, ctx: nexus.WorkflowRunOperationContext, req: SearchRequest
    ) -> nexus.WorkflowHandle[SearchResponse]:
        return await ctx.start_workflow(
            YouSearchWorkflow.run,
            req.input,
            id=self._workflow_id("you-search", req.idempotency_key, req.input),
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )

    @nexus.workflow_run_operation
    async def answer(
        self, ctx: nexus.WorkflowRunOperationContext, req: AnswerRequest
    ) -> nexus.WorkflowHandle[AnswerResponse]:
        return await ctx.start_workflow(
            YouAnswerWorkflow.run,
            req.input,
            id=self._workflow_id("you-answer", req.idempotency_key, req.input),
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )

    @nexus.workflow_run_operation
    async def contents(
        self, ctx: nexus.WorkflowRunOperationContext, req: ContentsRequest
    ) -> nexus.WorkflowHandle[ContentsOutput]:
        return await ctx.start_workflow(
            YouContentsWorkflow.run,
            req.input,
            id=self._workflow_id("you-contents", req.idempotency_key, req.input),
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )

    @nexus.workflow_run_operation
    async def research(
        self, ctx: nexus.WorkflowRunOperationContext, req: ResearchRequest
    ) -> nexus.WorkflowHandle[ResearchResponse]:
        return await ctx.start_workflow(
            YouResearchWorkflow.run,
            req.input,
            id=self._workflow_id("you-research", req.idempotency_key, req.input),
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )

    @nexus.workflow_run_operation
    async def finance_research(
        self, ctx: nexus.WorkflowRunOperationContext, req: FinanceResearchRequest
    ) -> nexus.WorkflowHandle[FinanceResearchResponse]:
        return await ctx.start_workflow(
            YouFinanceResearchWorkflow.run,
            req.input,
            id=self._workflow_id("you-finance-research", req.idempotency_key, req.input),
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )

    @nexus.workflow_run_operation
    async def research_background(
        self, ctx: nexus.WorkflowRunOperationContext, req: ResearchRequest
    ) -> nexus.WorkflowHandle[TaskDetail]:
        return await ctx.start_workflow(
            YouResearchBackgroundWorkflow.run,
            req.input,
            id=self._workflow_id("you-research-bg", req.idempotency_key, req.input),
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )


def you_nexus_service_handler() -> YouDotComServiceHandler:
    """Construct the :class:`YouDotComServiceHandler` for ``Worker(nexus_service_handlers=...)``."""
    return YouDotComServiceHandler()

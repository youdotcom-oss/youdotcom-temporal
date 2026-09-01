"""End-to-end Nexus round trip against a real Temporal server.

Everything else in the suite checks the pieces in isolation: that the contract
has the right shape, that the Workflows register under the sandbox, that the
timeouts and retry policies are what we think. None of that invokes Nexus.

This does. A real Endpoint, a handler Worker hosting the Service, and a
*separate* caller Worker that registers no plugin and no Activities -- the split
a consumer in another Namespace actually has. Each Operation is driven from the
caller side through the Endpoint, down to the Activity, and back.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import temporalio.api.nexus.v1 as nx
import temporalio.api.operatorservice.v1 as op
import temporalio.api.workflowservice.v1 as ws
from _nexus_caller_workflows import (
    ENDPOINT,
    CallAnswer,
    CallContents,
    CallFinanceResearch,
    CallResearch,
    CallResearchBackground,
    CallSearch,
    CallSearchIdempotent,
    caller_workflows,
)
from google.protobuf import duration_pb2
from temporalio.client import Client, WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError, NexusOperationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from youdotcom_temporal import YouPlugin
from youdotcom_temporal.nexus import you_nexus_service_handler
from youdotcom_temporal.workflows import you_nexus_workflows

pytestmark = pytest.mark.skipif(
    shutil.which("temporal") is None,
    reason="Nexus round trip needs the local Temporal dev server CLI",
)

HANDLER_QUEUE = "you-nexus-handler"
CALLER_QUEUE = "you-nexus-caller"


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return self._payload


def _mock_you_client(*_a: Any, **_kw: Any) -> Any:
    """A You client returning realistically shaped, identifiable payloads.

    The shapes mirror the real API so the typed result objects populate the same
    way they do in production; the marker string identifies which Operation the
    caller actually reached.
    """
    you = MagicMock()
    you.search_async = AsyncMock(
        return_value=_Resp(
            {
                "results": {
                    "web": [
                        {
                            "url": "https://example.com",
                            "title": "search",
                            "description": "d",
                            "snippets": ["s"],
                        }
                    ]
                },
                "metadata": {"search_uuid": "u", "query": "search", "latency": 1.0},
            }
        )
    )
    you.answer_async = AsyncMock(
        return_value=_Resp({"answer": "answer", "citations": [{"source": "s"}]})
    )
    you.contents_async = AsyncMock(
        return_value=[
            _Resp(
                {
                    "url": "https://example.com",
                    "title": "contents",
                    "markdown": "contents",
                }
            )
        ]
    )
    you.research_async = AsyncMock(
        return_value=_Resp(
            {
                "output": {
                    "content": "research",
                    "content_type": "text",
                    "sources": [],
                },
                "warnings": [],
            }
        )
    )
    you.finance_research_async = AsyncMock(
        return_value=_Resp(
            {
                "output": {
                    "content": "finance_research",
                    "content_type": "text",
                    "sources": [],
                }
            }
        )
    )
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=you)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


async def _research_and_wait(*_a: Any, **_kw: Any) -> Any:
    return _Resp(
        {
            "id": "task-1",
            "task_type": "research",
            "status": "completed",
            "created_at": "2026-08-19T00:00:00Z",
            "updated_at": "2026-08-19T00:00:00Z",
            "result": {"content": "research_background"},
        }
    )


# (caller Workflow, argument, marker, how to read it off the typed result)
_CASES = [
    (CallSearch, "a query", "search", lambda r: r.results.web[0].title),
    (CallAnswer, "a question", "answer", lambda r: r.answer),
    (CallContents, "https://example.com", "contents", lambda r: r.results[0].markdown),
    (CallResearch, "a topic", "research", lambda r: r.output.content),
    (CallFinanceResearch, "a ticker", "finance_research", lambda r: r.output.content),
    (CallResearchBackground, "a topic", "research_background", lambda r: r.result.content),
]


async def _start_server() -> WorkflowEnvironment:
    return await WorkflowEnvironment.start_local(
        dev_server_existing_path=shutil.which("temporal"),
        dev_server_extra_args=["--dynamic-config-value", "system.enableNexus=true"],
        # SDK response models are pydantic, so both sides need this converter.
        data_converter=pydantic_data_converter,
    )


async def _create_endpoint(client: Client, namespace: str, task_queue: str) -> None:
    await client.operator_service.create_nexus_endpoint(
        op.CreateNexusEndpointRequest(
            spec=nx.EndpointSpec(
                name=ENDPOINT,
                target=nx.EndpointTarget(
                    worker=nx.EndpointTarget.Worker(
                        namespace=namespace, task_queue=task_queue
                    )
                ),
            )
        )
    )


async def _register_namespace(client: Client, name: str) -> None:
    """Register a Namespace and wait for it to become usable.

    Registration is asynchronous server-side, so connecting immediately after
    the RPC returns is a race.
    """
    retention = duration_pb2.Duration()
    retention.FromTimedelta(timedelta(days=1))
    await client.service_client.workflow_service.register_namespace(
        ws.RegisterNamespaceRequest(
            namespace=name, workflow_execution_retention_period=retention
        )
    )
    for _ in range(80):
        try:
            await client.service_client.workflow_service.describe_namespace(
                ws.DescribeNamespaceRequest(namespace=name)
            )
            return
        except Exception:  # noqa: BLE001 - propagation delay, keep polling
            await asyncio.sleep(0.25)
    raise AssertionError(f"namespace {name!r} never became available")


@pytest.fixture
async def nexus_env(monkeypatch):
    """Dev server + registered Endpoint + handler Worker + caller Worker."""
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    env = await _start_server()
    async with env:
        await _create_endpoint(env.client, env.client.namespace, HANDLER_QUEUE)
        with patch(
            "youdotcom_temporal.activities.you_client", side_effect=_mock_you_client
        ), patch(
            "youdotcom_temporal.activities.research_and_wait_async",
            new=_research_and_wait,
        ):
            # Handler side: hosts the Service, the backing Workflows, and (via
            # the plugin) the Activities.
            async with Worker(
                env.client,
                task_queue=HANDLER_QUEUE,
                workflows=you_nexus_workflows(),
                nexus_service_handlers=[you_nexus_service_handler()],
                plugins=[YouPlugin()],
            ):
                # Caller side: no plugin, no Activities, no Nexus handler. It
                # can only reach You.com through the Endpoint.
                async with Worker(
                    env.client,
                    task_queue=CALLER_QUEUE,
                    workflows=caller_workflows(),
                ):
                    yield env


@pytest.mark.parametrize(
    "caller,arg,expected,read", _CASES, ids=[c[2] for c in _CASES]
)
async def test_operation_round_trips_through_a_nexus_endpoint(
    nexus_env, caller, arg, expected, read
):
    """Each Operation resolves caller -> Endpoint -> Workflow -> Activity -> caller.

    The marker is read off a *typed* field of the result, so an Operation wired
    to the wrong backing Workflow fails rather than passing on a shape match.
    """
    result = await nexus_env.client.execute_workflow(
        caller.run,
        arg,
        id=f"nexus-{expected}-{uuid.uuid4()}",
        task_queue=CALLER_QUEUE,
    )
    assert read(result) == expected


async def test_operation_starts_a_backing_workflow(nexus_env):
    """The Operation must be workflow-backed, not answered inline.

    This is the whole design premise -- if an Operation ever resolved without a
    backing Workflow it would be subject to the 10s sync handler deadline.
    """
    wf_id = f"nexus-backing-{uuid.uuid4()}"
    await nexus_env.client.execute_workflow(
        CallSearch.run, "a query", id=wf_id, task_queue=CALLER_QUEUE
    )

    backing = [
        wf
        async for wf in nexus_env.client.list_workflows(
            'WorkflowType = "YouSearchWorkflow"'
        )
    ]
    assert backing, "no YouSearchWorkflow was started; Operation was not workflow-backed"
    assert backing[0].task_queue == HANDLER_QUEUE


async def test_operation_crosses_a_real_namespace_boundary(monkeypatch):
    """The headline claim: a caller in a *different* Namespace can call this.

    The other tests use one Namespace with two Task Queues, which exercises the
    Endpoint but not the boundary. Here the caller and handler are genuinely
    separate Namespaces with separate Clients, and the caller holds no You.com
    credentials of its own.
    """
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    handler_ns, caller_ns = "you-handler-test", "you-caller-test"

    env = await _start_server()
    async with env:
        host = env.client.service_client.config.target_host
        await _register_namespace(env.client, handler_ns)
        await _register_namespace(env.client, caller_ns)

        handler_client = await Client.connect(
            host, namespace=handler_ns, data_converter=pydantic_data_converter
        )
        caller_client = await Client.connect(
            host, namespace=caller_ns, data_converter=pydantic_data_converter
        )
        # The point of this test: guard against it being quietly collapsed
        # back to a single Namespace, which would still pass everything below.
        assert handler_client.namespace != caller_client.namespace
        await _create_endpoint(handler_client, handler_ns, HANDLER_QUEUE)

        with patch(
            "youdotcom_temporal.activities.you_client", side_effect=_mock_you_client
        ):
            async with Worker(
                handler_client,
                task_queue=HANDLER_QUEUE,
                workflows=you_nexus_workflows(),
                nexus_service_handlers=[you_nexus_service_handler()],
                plugins=[YouPlugin()],
            ):
                async with Worker(
                    caller_client,
                    task_queue=CALLER_QUEUE,
                    workflows=caller_workflows(),
                ):
                    result = await caller_client.execute_workflow(
                        CallSearch.run,
                        "a query",
                        id=f"nexus-xns-{uuid.uuid4()}",
                        task_queue=CALLER_QUEUE,
                    )

    assert result.results.web[0].title == "search"


@pytest.fixture
async def failing_nexus_env(monkeypatch):
    """Same topology, but the Activity fails with a mapped, non-retryable error."""
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    env = await _start_server()
    async with env:
        await _create_endpoint(env.client, env.client.namespace, HANDLER_QUEUE)
        async with Worker(
            env.client,
            task_queue=HANDLER_QUEUE,
            workflows=you_nexus_workflows(),
            nexus_service_handlers=[you_nexus_service_handler()],
            plugins=[YouPlugin()],
        ):
            async with Worker(
                env.client, task_queue=CALLER_QUEUE, workflows=caller_workflows()
            ):
                yield env


async def test_activity_failure_reaches_the_caller_with_its_type(failing_nexus_env):
    """A mapped error must survive the Nexus boundary with its type intact.

    The Activity layer classifies failures (``YouAuthError``,
    ``YouValidationError``, ``YouQuotaExhausted``) so callers can branch on
    them. That is only useful if the classification survives being carried
    across Nexus, which is several failure wrappers deep.
    """
    with pytest.raises(WorkflowFailureError) as caught:
        await failing_nexus_env.client.execute_workflow(
            CallSearch.run,
            "a query",
            id=f"nexus-fail-{uuid.uuid4()}",
            task_queue=CALLER_QUEUE,
        )

    chain, err = [], caught.value
    while err is not None:
        chain.append(err)
        err = err.__cause__

    assert any(isinstance(e, NexusOperationError) for e in chain), (
        f"failure did not surface as a Nexus operation failure: "
        f"{[type(e).__name__ for e in chain]}"
    )
    app = next((e for e in chain if isinstance(e, ApplicationError)), None)
    assert app is not None, [type(e).__name__ for e in chain]
    assert app.type == "YouAuthError", app.type
    assert app.non_retryable


async def test_idempotency_key_deduplicates_the_backing_workflow(nexus_env):
    """The same key must resolve to one backing Workflow, not two.

    Without this, a retried Nexus StartOperation request starts a second
    Workflow and pays for a second You.com call. The key makes the backing
    Workflow Id deterministic, so the retry attaches to the run already in
    flight instead.
    """
    key = f"order-{uuid.uuid4()}"

    # Two callers, same key, issued concurrently -- the shape a StartOperation
    # retry takes.
    await asyncio.gather(
        *[
            nexus_env.client.execute_workflow(
                CallSearchIdempotent.run,
                ["a query", key],
                id=f"nexus-idem-{i}-{uuid.uuid4()}",
                task_queue=CALLER_QUEUE,
            )
            for i in range(2)
        ]
    )

    # Assert the behaviour, not the Id format: same key and same request must
    # resolve to a single backing Workflow.
    backing = [
        wf
        async for wf in nexus_env.client.list_workflows(
            'WorkflowType = "YouSearchWorkflow"'
        )
    ]
    assert len(backing) == 1, (
        f"expected one backing Workflow for key {key!r}, found {len(backing)}: "
        f"{[w.id for w in backing]}"
    )
    assert key[:64] in backing[0].id, (
        f"Id {backing[0].id!r} should still carry the key for recognisability"
    )


async def test_without_a_key_each_call_gets_its_own_workflow(nexus_env):
    """The default stays non-idempotent, which is right for one-off calls."""
    await asyncio.gather(
        *[
            nexus_env.client.execute_workflow(
                CallSearch.run,
                "a query",
                id=f"nexus-nokey-{i}-{uuid.uuid4()}",
                task_queue=CALLER_QUEUE,
            )
            for i in range(2)
        ]
    )
    backing = [
        wf
        async for wf in nexus_env.client.list_workflows(
            'WorkflowType = "YouSearchWorkflow"'
        )
    ]
    assert len(backing) == 2, f"expected two distinct Workflows, found {len(backing)}"


async def _malformed_research_and_wait(*_a: Any, **_kw: Any) -> Any:
    """A background research task whose payload TaskDetail cannot accept.

    TaskDetail has required fields, unlike SearchResponse whose fields are all
    optional, so it is the model that actually exercises a parse failure.
    """
    return _Resp({"unexpected": "shape"})


@pytest.fixture
async def malformed_nexus_env(monkeypatch):
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    env = await _start_server()
    async with env:
        await _create_endpoint(env.client, env.client.namespace, HANDLER_QUEUE)
        with patch(
            "youdotcom_temporal.activities.you_client", side_effect=_mock_you_client
        ), patch(
            "youdotcom_temporal.activities.research_and_wait_async",
            new=_malformed_research_and_wait,
        ):
            async with Worker(
                env.client,
                task_queue=HANDLER_QUEUE,
                workflows=you_nexus_workflows(),
                nexus_service_handlers=[you_nexus_service_handler()],
                plugins=[YouPlugin()],
            ):
                async with Worker(
                    env.client, task_queue=CALLER_QUEUE, workflows=caller_workflows()
                ):
                    yield env


async def test_unparseable_response_fails_the_caller_instead_of_hanging(
    malformed_nexus_env,
):
    """An unexpected response shape must surface, not spin.

    Parsing happens in the Workflow, and a bare pydantic error there is a
    Workflow task failure -- which Temporal retries forever. The caller would
    wait out its whole schedule_to_close on a request that can never succeed.
    It has to come back as a real, non-retryable error instead.
    """
    with pytest.raises(WorkflowFailureError) as caught:
        await malformed_nexus_env.client.execute_workflow(
            CallResearchBackground.run,
            "a topic",
            id=f"nexus-malformed-{uuid.uuid4()}",
            task_queue=CALLER_QUEUE,
        )

    chain, err = [], caught.value
    while err is not None:
        chain.append(err)
        err = err.__cause__
    app = next((e for e in chain if isinstance(e, ApplicationError)), None)
    assert app is not None, [type(e).__name__ for e in chain]
    assert app.type == "YouResponseShapeError", app.type
    assert app.non_retryable


async def test_same_key_different_input_does_not_cross_wire_results(nexus_env):
    """A key must not hand one caller another caller's results.

    The backing Workflow Id is derived from the caller-supplied key. Two callers
    that pick the same key string for *different* requests would otherwise
    collide, and USE_EXISTING would attach the second to the first's Workflow --
    returning the first caller's answer to the second.
    """
    key = f"shared-{uuid.uuid4()}"

    first, second = await asyncio.gather(
        nexus_env.client.execute_workflow(
            CallSearchIdempotent.run,
            ["query-one", key],
            id=f"nexus-collide-a-{uuid.uuid4()}",
            task_queue=CALLER_QUEUE,
        ),
        nexus_env.client.execute_workflow(
            CallSearchIdempotent.run,
            ["query-two", key],
            id=f"nexus-collide-b-{uuid.uuid4()}",
            task_queue=CALLER_QUEUE,
        ),
    )

    backing = [
        wf
        async for wf in nexus_env.client.list_workflows(
            'WorkflowType = "YouSearchWorkflow"'
        )
    ]
    assert len(backing) == 2, (
        f"different inputs shared a backing Workflow: {[w.id for w in backing]} -- "
        "one caller received another caller's results"
    )
    assert first is not None and second is not None

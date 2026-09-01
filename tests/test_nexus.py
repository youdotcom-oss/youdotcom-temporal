"""Unit tests for the Nexus Service contract and handler.

These validate the :class:`YouDotComService` definition and the
:class:`YouDotComServiceHandler` without a Temporal server: the service has
six Operations with the right names and typed inputs, the handler constructs,
the helper functions return the right Workflow classes, and the backing
Workflows survive the sandbox preparation that ``Worker.__init__`` performs.

End-to-end Nexus execution (a real Endpoint, a caller in a second Namespace)
is not covered anywhere yet -- see the draft checklist in the PR.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from datetime import timedelta

import nexusrpc
import pytest
from pydantic import BaseModel
from temporalio import workflow
from temporalio.exceptions import ApplicationError
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

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
from youdotcom_temporal.nexus import (
    YouDotComServiceHandler,
    you_nexus_service_handler,
)
from youdotcom_temporal.plugin import _you_workflow_runner
from youdotcom_temporal.workflows import (
    _BACKGROUND_TIMEOUT_S,
    _BACKGROUND_TIMEOUT_S_BY_EFFORT,
    YouAnswerWorkflow,
    YouContentsWorkflow,
    YouFinanceResearchWorkflow,
    YouResearchBackgroundWorkflow,
    YouResearchWorkflow,
    YouSearchWorkflow,
    you_nexus_workflows,
)

# operation -> (request type, result type)
_EXPECTED_OPS = {
    "search": (SearchRequest, SearchResponse),
    "answer": (AnswerRequest, AnswerResponse),
    "contents": (ContentsRequest, ContentsOutput),
    "research": (ResearchRequest, ResearchResponse),
    "finance_research": (FinanceResearchRequest, FinanceResearchResponse),
    "research_background": (ResearchRequest, TaskDetail),
}

_BACKING_WORKFLOWS = {
    "search": YouSearchWorkflow,
    "answer": YouAnswerWorkflow,
    "contents": YouContentsWorkflow,
    "research": YouResearchWorkflow,
    "finance_research": YouFinanceResearchWorkflow,
    "research_background": YouResearchBackgroundWorkflow,
}


# Minimal payloads that satisfy each SDK response model. The Workflow now parses
# the Activity's dict into a typed model, so a fake Activity has to return
# something the model accepts -- these tests are about timeouts and retries, not
# parsing, so keep them to the required fields only.
_OUTPUT = {"content": "x", "content_type": "text", "sources": []}
_VALID_PAYLOAD = {
    "youdotcom_search": {},
    "youdotcom_answer": {"answer": "a"},
    "youdotcom_contents": {"results": []},
    "youdotcom_research": {"output": _OUTPUT},
    "youdotcom_finance_research": {"output": _OUTPUT},
    "youdotcom_research_background": {
        "id": "t",
        "task_type": "research",
        "status": "completed",
        "created_at": "2026-08-19T00:00:00Z",
        "updated_at": "2026-08-19T00:00:00Z",
    },
}


def _payload_for(activity) -> dict:
    return _VALID_PAYLOAD[activity.__name__]


def test_service_definition_has_six_operations():
    defn = nexusrpc.get_service_definition(YouDotComService)
    assert defn is not None
    assert defn.name == "YouDotComService"
    assert set(defn.operation_definitions) == set(_EXPECTED_OPS)


def test_operation_names_match_method_names():
    """Each Operation's wire name equals its handler method name."""
    defn = nexusrpc.get_service_definition(YouDotComService)
    for op_name, op_defn in defn.operation_definitions.items():
        assert op_defn.name == op_name
        assert op_defn.method_name == op_name


def test_operation_input_types_are_typed():
    defn = nexusrpc.get_service_definition(YouDotComService)
    for op_name, (request_type, _) in _EXPECTED_OPS.items():
        assert defn.operation_definitions[op_name].input_type is request_type, op_name


def test_operation_output_types_are_typed_results():
    """Results are declared types, not bare dicts.

    A cross-Namespace contract whose outputs are ``dict[str, Any]`` gives the
    caller no field names and no signal when a shape changes.
    """
    defn = nexusrpc.get_service_definition(YouDotComService)
    for op_name, (_, result_type) in _EXPECTED_OPS.items():
        assert defn.operation_definitions[op_name].output_type is result_type, op_name
        assert result_type is not dict, op_name


def test_result_types_are_sdk_models_or_thin_envelopes():
    """Results are the SDK's own response models wherever one exists.

    Using them means callers get accurate, fully nested types the SDK team
    maintains. `contents` is the one exception: the SDK returns a bare list,
    which cannot gain fields later without breaking callers, so it keeps a thin
    envelope whose elements are still SDK models.
    """
    for op_name, (_, result_type) in _EXPECTED_OPS.items():
        if op_name == "contents":
            assert dataclasses.is_dataclass(result_type)
        else:
            assert issubclass(result_type, BaseModel), op_name


def test_contents_result_elements_are_the_contents_endpoint_model():
    """`contents` elements must carry the fields the contents API returns.

    The contents endpoint returns `ContentsResponse` elements (`url`, `title`,
    `html`, `markdown`, `metadata`). The SDK's `Contents` model is the search
    extraction shape (`html`, `markdown`, `highlights`) -- validating against
    it silently dropped `url`, `title`, and `metadata` from every result.
    """
    from typing import get_type_hints

    from youdotcom.models import ContentsResponse

    assert get_type_hints(ContentsOutput)["results"].__args__[0] is ContentsResponse


async def test_contents_workflow_preserves_the_full_response_shape(monkeypatch):
    """Every field the contents endpoint returns must survive the Workflow.

    A validation model that is a subset of the real response drops fields
    silently -- the caller receives elements with no `url`, `title`, or
    `metadata` and no error anywhere.
    """
    element = {
        "url": "https://example.com",
        "title": "Example",
        "html": "<p>hi</p>",
        "markdown": "# hi",
        "metadata": {"site_name": "Example"},
    }

    async def _fake_execute_activity(_activity, _inp, **_kwargs):
        return {"results": [dict(element)]}

    monkeypatch.setattr(workflow, "execute_activity", _fake_execute_activity)
    out = await YouContentsWorkflow().run(
        ContentsInput(urls=["https://example.com"])
    )
    dumped = out.results[0].model_dump(mode="json")
    assert dumped["url"] == "https://example.com"
    assert dumped["title"] == "Example"
    assert dumped["html"] == "<p>hi</p>"
    assert dumped["markdown"] == "# hi"
    assert dumped["metadata"]["site_name"] == "Example"


def test_result_types_are_serializable_by_the_pydantic_converter():
    """The contract only works if Temporal can carry these types.

    SDK models are pydantic, so callers must configure
    ``temporalio.contrib.pydantic.pydantic_data_converter``; this pins that the
    types are ones that converter actually handles.
    """
    for op_name, (_, result_type) in _EXPECTED_OPS.items():
        if op_name == "contents":
            continue
        assert hasattr(result_type, "model_validate"), op_name
        assert hasattr(result_type, "model_dump"), op_name


def test_service_handler_carries_service_definition():
    defn = nexusrpc.get_service_definition(YouDotComServiceHandler)
    assert defn is not None
    assert set(defn.operation_definitions) == set(_EXPECTED_OPS)


def test_service_handler_constructs():
    handler = you_nexus_service_handler()
    assert isinstance(handler, YouDotComServiceHandler)


def test_nexus_workflows_list_covers_every_operation():
    """Each Operation must have a distinct backing Workflow in the Worker list.

    A missing entry here means the Operation starts a Workflow the Worker never
    registered, which fails only at runtime against a real server.
    """
    wfs = you_nexus_workflows()
    assert len(set(wfs)) == len(wfs), "duplicate Workflow in the registration list"
    assert set(wfs) == set(_BACKING_WORKFLOWS.values())
    assert set(_BACKING_WORKFLOWS) == set(_EXPECTED_OPS)


async def test_backing_workflows_prepare_under_the_plugin_sandbox():
    """Worker registration must succeed with YouPlugin's passthrough applied.

    ``Worker.__init__`` runs ``prepare_workflow`` for every registered Workflow.
    These Workflows import the You.com SDK, so this is the check that catches a
    sandbox restriction before it reaches a running Worker.
    """
    runner = _you_workflow_runner(SandboxedWorkflowRunner())
    for wf in you_nexus_workflows():
        runner.prepare_workflow(workflow._Definition.must_from_class(wf))


async def test_backing_workflows_prepare_without_the_plugin():
    """Registration must not depend on YouPlugin's sandbox passthrough.

    ``youdotcom_temporal/__init__`` resolves its public names lazily, so the
    parent package import no longer drags in the You.com SDK and
    ``workflows.py`` can cover the SDK with its own
    ``imports_passed_through()`` block. Without that, Python imports the parent
    package first and the block never gets the chance.
    """
    runner = SandboxedWorkflowRunner()
    for wf in you_nexus_workflows():
        runner.prepare_workflow(workflow._Definition.must_from_class(wf))


async def test_caller_workflows_prepare_without_passthrough():
    """A caller in another Namespace must not need YouPlugin or a passthrough.

    ``tests/_nexus_caller_workflows`` imports the contract at module scope with
    no sandbox escape, which is how the README documents the caller side. A
    caller Namespace has no YouPlugin to inherit passthrough from, so this has
    to hold on its own.

    These are the same Workflows the round-trip tests drive against a real
    server, so this cannot drift away from the shape that actually runs -- an
    earlier standalone copy did exactly that, passing here while carrying a
    request shape the contract would have rejected.
    """
    from _nexus_caller_workflows import caller_workflows

    runner = SandboxedWorkflowRunner()
    for wf in caller_workflows():
        runner.prepare_workflow(workflow._Definition.must_from_class(wf))


def test_importing_the_package_does_not_load_the_sdk():
    """The invariant behind both sandbox fixes, checked directly.

    If any eager import creeps back into ``__init__``, the sandbox failures
    return -- and they return at Worker construction, far from this package.
    """
    code = (
        "import sys; import youdotcom_temporal; "
        "mods = set(sys.modules); "
        "print(int(any(m == 'youdotcom' or m.startswith('youdotcom.') for m in mods)), "
        "int('urllib.request' in mods))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    sdk_loaded, urllib_loaded = out.stdout.split()
    assert sdk_loaded == "0", "importing youdotcom_temporal pulled in the You.com SDK"
    assert urllib_loaded == "0", "importing youdotcom_temporal pulled in urllib.request"


async def test_background_research_mirrors_the_sdk_deadline_constants(monkeypatch):
    """The mirrored deadline constants must match what the SDK actually derives.

    ``_BACKGROUND_TIMEOUT_S`` and ``_BACKGROUND_TIMEOUT_S_BY_EFFORT`` exist only
    to size the ceiling, but they are a copy of the SDK's own values. If the SDK
    raises frontier past 4 hours and this copy is not updated, the ceiling
    silently stops covering the deadline. Read the real values back from the SDK
    so that drift fails here rather than in production.
    """
    from youdotcom import research_helpers

    assert research_helpers._DEFAULT_POLL_TIMEOUT_S == _BACKGROUND_TIMEOUT_S
    assert (
        research_helpers._FRONTIER_TIMEOUT_S
        == _BACKGROUND_TIMEOUT_S_BY_EFFORT["frontier"]
    )


async def test_research_workflows_do_not_retry(monkeypatch):
    """Research Activities must not retry; the fast ones must.

    Every research attempt submits a new billable You.com task, and the previous
    attempt keeps running because the Activities do not heartbeat, so a retry
    multiplies cost instead of recovering.
    """
    attempts: dict[str, int] = {}

    async def _fake_execute_activity(activity, _inp, **kwargs):
        attempts[activity.__name__] = kwargs["retry_policy"].maximum_attempts
        return _payload_for(activity)

    monkeypatch.setattr(workflow, "execute_activity", _fake_execute_activity)
    await YouResearchWorkflow().run(ResearchInput(input="q"))
    await YouFinanceResearchWorkflow().run(FinanceResearchInput(input="q"))
    await YouResearchBackgroundWorkflow().run(ResearchInput(input="q"))
    await YouSearchWorkflow().run(SearchInput(query="q"))
    await YouAnswerWorkflow().run(AnswerInput(query="q"))
    await YouContentsWorkflow().run(ContentsInput(urls=["https://example.com"]))

    assert attempts["youdotcom_research"] == 1
    assert attempts["youdotcom_finance_research"] == 1
    assert attempts["youdotcom_research_background"] == 1
    assert attempts["youdotcom_search"] > 1
    assert attempts["youdotcom_answer"] > 1
    assert attempts["youdotcom_contents"] > 1


async def test_background_ceiling_outlasts_the_activity_wait(monkeypatch):
    """The Workflow ceiling must expire *after* the Activity's own wait.

    ``research_and_wait_async`` issues a final GET once its internal timeout
    expires, so its wall time is strictly longer than ``timeout_s``. If the
    ceiling merely equals that wait, Temporal kills the attempt before the
    Activity can report what happened and the Workflow fails with an opaque
    activity timeout instead of the real outcome.
    """
    captured: dict[str, timedelta] = {}

    async def _fake_execute_activity(_activity, inp, **kwargs):
        # timeout_s must arrive untouched: the Activity forwards it to the SDK,
        # which derives the deadline from research_effort. A value substituted
        # anywhere on this path takes over a decision the SDK makes correctly,
        # and capped frontier tasks at two minutes when it last happened.
        assert inp.timeout_s is None
        captured[inp.research_effort] = kwargs["start_to_close_timeout"]
        return _payload_for(_activity)

    monkeypatch.setattr(workflow, "execute_activity", _fake_execute_activity)
    for effort in ("lite", "standard", "deep", "exhaustive", "frontier"):
        await YouResearchBackgroundWorkflow().run(
            ResearchInput(input="q", research_effort=effort)
        )

    assert set(captured) == {"lite", "standard", "deep", "exhaustive", "frontier"}
    for effort, ceiling in captured.items():
        wait_s = _BACKGROUND_TIMEOUT_S_BY_EFFORT.get(effort, _BACKGROUND_TIMEOUT_S)
        assert wait_s < ceiling.total_seconds(), (
            f"{effort}: activity waits {wait_s}s but the ceiling is "
            f"{ceiling.total_seconds()}s -- the attempt is killed first"
        )


async def test_background_research_respects_an_explicit_timeout(monkeypatch):
    """A caller-supplied timeout_s must win over the effort-based default."""

    async def _fake_execute_activity(_activity, inp, **_kwargs):
        _fake_execute_activity.inp = inp
        return _payload_for(_activity)

    monkeypatch.setattr(workflow, "execute_activity", _fake_execute_activity)
    await YouResearchBackgroundWorkflow().run(
        ResearchInput(input="q", research_effort="frontier", timeout_s=30.0)
    )
    assert _fake_execute_activity.inp.timeout_s == 30.0


def test_validation_error_names_fields_but_not_values():
    """A parse failure must not carry You.com content across the boundary.

    ``_validate``'s message becomes the caller's failure and lands in Workflow
    history. Pydantic renders the offending input inline by default, so a
    malformed response would otherwise spill upstream content to whoever called
    the Operation.
    """
    from youdotcom.models import TaskDetail

    from youdotcom_temporal.workflows import _validate

    secret = "CONFIDENTIAL-RESPONSE-CONTENT"
    with pytest.raises(ApplicationError) as caught:
        _validate(TaskDetail, {"id": "x", "leaked": secret})

    message = str(caught.value)
    assert secret not in message
    assert "CONFIDENTIAL" not in message
    # still diagnostic: it says which fields were wrong
    assert "task_type" in message
    assert "Field required" in message


def test_validation_error_is_non_retryable():
    """A shape mismatch will not fix itself, so it must not spin."""
    from youdotcom.models import TaskDetail

    from youdotcom_temporal.workflows import _validate

    with pytest.raises(ApplicationError) as caught:
        _validate(TaskDetail, {})
    assert caught.value.type == "YouResponseShapeError"
    assert caught.value.non_retryable


async def test_contents_workflow_rejects_a_response_without_results(monkeypatch):
    """A missing 'results' key must fail cleanly, not raise KeyError.

    A KeyError inside a Workflow is a Workflow task failure, which Temporal
    retries indefinitely -- the same hang _validate exists to prevent.
    """

    async def _fake_execute_activity(_activity, _inp, **_kwargs):
        return {"unexpected": "shape"}

    monkeypatch.setattr(workflow, "execute_activity", _fake_execute_activity)
    with pytest.raises(ApplicationError) as caught:
        await YouContentsWorkflow().run(ContentsInput(urls=["https://example.com"]))
    assert caught.value.type == "YouResponseShapeError"
    assert caught.value.non_retryable


def test_contract_import_does_not_pull_in_the_handler():
    """A caller needs the types, not the implementation.

    Importing the contract must not load the backing Workflows or the Activity
    layer. Those exist only on the handler side, and a caller in another
    Namespace has no use for them. Checked in a subprocess because this test
    session has already imported both.
    """
    code = (
        "import sys; import youdotcom_temporal.contract as c; m = set(sys.modules); "
        "print(int('youdotcom_temporal.workflows' in m), "
        "int('youdotcom_temporal.activities' in m))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    workflows_loaded, activities_loaded = out.stdout.split()
    assert workflows_loaded == "0", "contract import pulled in the backing Workflows"
    assert activities_loaded == "0", "contract import pulled in the Activity layer"


class TestWorkflowIdDerivation:
    """Properties the idempotency key depends on.

    The backing Workflow Id *is* the deduplication mechanism, so these are
    correctness guarantees rather than implementation detail.
    """

    _id = staticmethod(YouDotComServiceHandler._workflow_id)

    def test_same_key_and_request_is_stable(self):
        inp = SearchInput(query="q", count=3)
        assert self._id("p", "k", inp) == self._id("p", "k", inp)

    def test_same_key_different_request_differs(self):
        """The property that stops one caller receiving another's results."""
        assert self._id("p", "k", SearchInput(query="one")) != self._id(
            "p", "k", SearchInput(query="two")
        )

    def test_different_key_same_request_differs(self):
        inp = SearchInput(query="q")
        assert self._id("p", "a", inp) != self._id("p", "b", inp)

    def test_no_key_is_unique_per_call(self):
        inp = SearchInput(query="q")
        assert self._id("p", None, inp) != self._id("p", None, inp)

    def test_dict_key_order_does_not_change_the_id(self):
        """Serialization has to be canonical or dedup silently stops working."""
        a = ResearchInput(input="q", source_control={"a": 1, "b": 2})
        b = ResearchInput(input="q", source_control={"b": 2, "a": 1})
        assert self._id("p", "k", a) == self._id("p", "k", b)

    def test_long_keys_stay_within_temporal_limits(self):
        """An oversized key must not push the Id past what the server accepts."""
        assert len(self._id("you-search", "x" * 5000, SearchInput(query="q"))) < 200

    def test_keys_sharing_a_prefix_do_not_collide(self):
        """The readable part is truncated, so the digest must cover the full key."""
        inp = SearchInput(query="q")
        assert self._id("p", "x" * 64 + "A", inp) != self._id("p", "x" * 64 + "B", inp)

    def test_awkward_payloads_do_not_raise(self):
        """A crash here fails the Operation start, so it must handle real inputs."""
        for inp in (
            SearchInput(query="café — \x00 😀"),
            ResearchInput(input="q", output_schema={"type": "object"}),
            ContentsInput(urls=["https://a.com", "https://b.com"]),
        ):
            assert self._id("p", "k", inp)


async def test_research_operation_rejects_background_mode(monkeypatch):
    """`research` must refuse `background=True` before any billable call.

    `ResearchInput.background` exists for the Activity layer, but with
    `background=True` the SDK returns a task handle (TaskResponse), which can
    never validate as this Operation's `ResearchResponse` result. Without this
    check the caller pays for the research task and then receives an opaque
    `YouResponseShapeError`. `research_background` is the Operation for that
    mode, and it waits for and returns the completed task.
    """

    async def _fake_execute_activity(_activity, _inp, **_kwargs):
        raise AssertionError("the Activity must not run")

    monkeypatch.setattr(workflow, "execute_activity", _fake_execute_activity)
    with pytest.raises(ApplicationError) as caught:
        await YouResearchWorkflow().run(ResearchInput(input="q", background=True))
    assert caught.value.type == "YouValidationError"
    assert caught.value.non_retryable
    assert "research_background" in str(caught.value)

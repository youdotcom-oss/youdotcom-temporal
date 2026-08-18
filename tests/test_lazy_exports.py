"""The package must be importable from inside a Temporal Workflow file.

``youdotcom_temporal/__init__`` used to import the Activity layer eagerly, which
pulls in the You.com SDK and ``urllib.request``. The workflow sandbox rejects
``urllib.request``, and because Python imports a parent package before any
submodule body runs, no downstream ``workflow.unsafe.imports_passed_through()``
block could cover it. Worker construction failed with
``RestrictedWorkflowAccessError``.

Public names now resolve through a module ``__getattr__`` (PEP 562), so the SDK
loads on first attribute access instead of at import time.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio import workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

import youdotcom_temporal


async def test_workflow_importing_the_package_prepares_under_the_sandbox():
    """The regression test: no passthrough, no plugin, must still register.

    ``prepare_workflow`` is the path ``Worker.__init__`` takes for every
    registered Workflow, so this fails exactly where a real Worker would.
    """
    from _unwrapped_import_workflow import UnwrappedImportWorkflow

    runner = SandboxedWorkflowRunner()
    runner.prepare_workflow(
        workflow._Definition.must_from_class(UnwrappedImportWorkflow)
    )


def test_importing_the_package_does_not_load_the_sdk():
    """The invariant underneath the fix, checked in a clean interpreter.

    Runs in a subprocess because this test session has already imported the SDK
    via other tests. If an eager import creeps back into ``__init__``, this
    fails here rather than at Worker construction in a downstream service.
    """
    code = (
        "import sys; import youdotcom_temporal; m = set(sys.modules); "
        "print(int(any(x == 'youdotcom' or x.startswith('youdotcom.') for x in m)), "
        "int('urllib.request' in m))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    sdk_loaded, urllib_loaded = out.stdout.split()
    assert sdk_loaded == "0", "importing youdotcom_temporal pulled in the You.com SDK"
    assert urllib_loaded == "0", "importing youdotcom_temporal pulled in urllib.request"


def test_public_names_still_resolve():
    """Lazy resolution must not change the public API surface."""
    for name in youdotcom_temporal.__all__:
        assert hasattr(youdotcom_temporal, name), name

    from youdotcom_temporal import (  # noqa: F401
        SearchInput,
        YouConfig,
        YouPlugin,
        you_activities,
        youdotcom_search,
    )

    assert youdotcom_temporal.YouPlugin is YouPlugin
    assert sorted(dir(youdotcom_temporal)) == sorted(youdotcom_temporal.__all__)


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


@pytest.mark.skipif(
    shutil.which("temporal") is None,
    reason="needs the local Temporal dev server CLI",
)
async def test_real_worker_runs_a_workflow_that_imports_the_package(monkeypatch):
    """End-to-end against a real server, with no plugin and no passthrough.

    ``prepare_workflow`` exercises the right code path, but only a real Worker
    proves the whole thing. This registers the Activity explicitly rather than
    through ``YouPlugin``, so nothing supplies a sandbox passthrough -- exactly
    the shape a caller in another Namespace has. On the pre-fix code this fails
    with "Failed validating workflow" and a restricted ``urllib.request``.
    """
    monkeypatch.setenv("YDC_API_KEY", "test-key")
    from _unwrapped_import_workflow import UnwrappedImportWorkflow

    from youdotcom_temporal.activities import youdotcom_search

    env = await WorkflowEnvironment.start_local(
        dev_server_existing_path=shutil.which("temporal")
    )
    async with env:
        with patch(
            "youdotcom_temporal.activities.you_client", side_effect=_mock_you_client
        ):
            async with Worker(
                env.client,
                task_queue="lazy-exports-e2e",
                workflows=[UnwrappedImportWorkflow],
                activities=[youdotcom_search],  # note: no plugins=[YouPlugin()]
            ):
                result = await env.client.execute_workflow(
                    UnwrappedImportWorkflow.run,
                    "hello",
                    id="lazy-exports-e2e-wf",
                    task_queue="lazy-exports-e2e",
                )

    assert result["results"][0]["url"] == "https://example.com"


def test_unknown_attribute_still_raises_attribute_error():
    """__getattr__ must not turn typos into silent successes."""
    try:
        youdotcom_temporal.does_not_exist
    except AttributeError as exc:
        assert "does_not_exist" in str(exc)
    else:
        raise AssertionError("expected AttributeError for an unknown attribute")

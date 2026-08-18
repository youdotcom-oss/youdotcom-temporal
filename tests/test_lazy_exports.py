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

import subprocess
import sys

from temporalio import workflow
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


def test_unknown_attribute_still_raises_attribute_error():
    """__getattr__ must not turn typos into silent successes."""
    try:
        youdotcom_temporal.does_not_exist
    except AttributeError as exc:
        assert "does_not_exist" in str(exc)
    else:
        raise AssertionError("expected AttributeError for an unknown attribute")

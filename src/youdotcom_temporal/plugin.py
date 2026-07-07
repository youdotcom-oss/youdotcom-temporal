from __future__ import annotations

from dataclasses import replace

from temporalio.plugin import SimplePlugin
from temporalio.worker import WorkflowRunner
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

from .activities import you_activities

_PASSTHROUGH_MODULES = [
    "youdotcom",
    "httpx",
    "httpcore",
    "pydantic",
    "pydantic_core",
    "certifi",
    "anyio",
    "sniffio",
]


def _you_workflow_runner(runner: WorkflowRunner | None) -> WorkflowRunner:
    if isinstance(runner, SandboxedWorkflowRunner):
        return replace(
            runner,
            restrictions=runner.restrictions.with_passthrough_modules(*_PASSTHROUGH_MODULES),
        )
    return runner  # type: ignore[return-value]


class YouPlugin(SimplePlugin):
    def __init__(self) -> None:
        super().__init__(
            name="youdotcom.YouPlugin",
            activities=you_activities(),
            workflow_runner=_you_workflow_runner,
        )

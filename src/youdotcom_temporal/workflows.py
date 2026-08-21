"""Thin Temporal Workflows that wrap each You.com Activity.

These exist so a Nexus Operation can back the Activities with an asynchronous
Workflow. Nexus synchronous operations must finish within the 10-second handler
deadline, which is the wrong shape for this API: several of these calls are
long-running by design, and the rest accept parameters that make their duration
a caller's choice.

- ``youdotcom_research`` / ``youdotcom_finance_research`` -- multi-step research,
  measured in tens of seconds to minutes by design
- ``youdotcom_research_background`` -- up to 4 hours for ``frontier`` effort
- ``youdotcom_search`` / ``youdotcom_contents`` -- ``livecrawl`` and
  ``crawl_timeout`` fetch pages live, and ``crawl_timeout`` alone accepts up to
  60 seconds per URL, so one route covers two very different operations
- ``youdotcom_answer`` -- the shortest of the six, and a synthesis step over
  retrieved sources rather than a lookup

That matters because a sync handler which misses the deadline fails as a
retryable error, and five consecutive retryable errors trip a circuit breaker
that blocks *every* Operation on the caller/Endpoint pair for 60 seconds.
Routing every Operation through a Workflow removes the cliff: the Activity runs
with its own ``start_to_close_timeout`` and Temporal's retries, and the caller
gets durable, observable execution. Cancellation is a partial story -- see the
note in :mod:`youdotcom_temporal.nexus`.

Each Workflow is a one-line wrapper around ``workflow.execute_activity``. The
ceilings are workflow-side defaults; a Nexus caller still sets
``schedule_to_close_timeout`` on the operation call, and that caller timeout
should exceed the handler-side worst case (ceiling times attempts).

Sandbox note:
    This module imports the Activity layer, which imports the You.com SDK, so
    the import lives in an ``imports_passed_through()`` block. That block only
    works because ``youdotcom_temporal/__init__`` resolves its public names
    lazily -- Python imports the parent package first, and an eager import
    there would escape the block and fail under the sandbox.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, TypeVar

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel, ValidationError

    from youdotcom_temporal.activities import (
        youdotcom_answer,
        youdotcom_contents,
        youdotcom_finance_research,
        youdotcom_research,
        youdotcom_research_background,
        youdotcom_search,
    )
    from youdotcom_temporal.contract import (
        AnswerResponse,
        Contents,
        ContentsOutput,
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

# Per-Activity start_to_close ceilings. These are *per attempt*: the wall-clock
# ceiling is the value below times the retry policy's maximum_attempts.
#
# A ceiling is a backstop, not a latency target: it is where the Activity gives
# up and lets Temporal retry, so it wants generous headroom over what a healthy
# call takes. Undersized, it turns slow-but-fine calls into failures; oversized,
# a genuinely stuck call ties up a Worker slot longer than it should.
#
# The two crawling routes are sized off the parameters they accept. `search` and
# `contents` fetch pages live under `livecrawl`/`crawl_timeout`, and
# `crawl_timeout` alone accepts up to 60s per URL, so a caller can legitimately
# ask for a long call:
#
#   _SEARCH_STC    2x the 60s maximum a caller can request
#   _CONTENTS_STC  3x it, since `contents` accepts up to 10 URLs per request
#
# answer/search/contents sit *below* the client's own HTTP timeout
# (YouConfig.timeout_seconds, default 300s); research/finance_research sit above
# it. That asymmetry is intentional. For the shorter Activities, failing at the
# ceiling beats waiting out the full 300s, and the cost is that the abandoned
# HTTP call keeps running -- the You.com API has no cancellation, so nothing can
# call a submitted request back, and a retry runs alongside it. For the research
# Activities the client errors first, so the Activity reports the real failure
# instead of an opaque activity timeout; that is also why they do not retry.
_SEARCH_STC = timedelta(seconds=120)
_ANSWER_STC = timedelta(seconds=60)
_CONTENTS_STC = timedelta(seconds=180)
_RESEARCH_STC = timedelta(minutes=10)
_FINANCE_RESEARCH_STC = timedelta(minutes=30)

# The Activity layer already raises these as non-retryable ApplicationErrors;
# listing them keeps the intent visible at the call site and matches the retry
# policies in examples/.
_NON_RETRYABLE = ["YouAuthError", "YouValidationError", "YouQuotaExhausted"]

# search/answer/contents: the ceilings above sit far enough above a healthy call
# that reaching one means something is genuinely broken rather than merely slow,
# so a retry is likely to succeed. Worst case is maximum_attempts abandoned HTTP
# calls running concurrently, which is acceptable for these three.
_RETRY = RetryPolicy(
    maximum_attempts=3,
    maximum_interval=timedelta(seconds=60),
    non_retryable_error_types=_NON_RETRYABLE,
)

# Research Activities: each attempt submits a new billable research task, and
# the previous attempt keeps running, because the You.com API has no way to
# cancel it. Retry would multiply cost and wall-clock rather than recover, so do
# not retry.
#
# No non_retryable_error_types here: at maximum_attempts=1 nothing is ever
# retried, so listing them would read as a safeguard while doing nothing.
_RETRY_RESEARCH = RetryPolicy(maximum_attempts=1)

# The deadline research_and_wait_async derives from research_effort when
# ResearchInput.timeout_s is None. Mirrored here only to size the ceiling below;
# the Activity forwards timeout_s untouched, so the SDK remains the one place
# that decides the deadline. If the SDK's own values change, these follow.
_BACKGROUND_TIMEOUT_S = 600.0
_BACKGROUND_TIMEOUT_S_BY_EFFORT = {"frontier": 14400.0}

# The Activity's own wait has to expire before this ceiling does, or Temporal
# kills the attempt before the Activity can report what happened and the
# Workflow fails with an opaque activity timeout. research_and_wait_async also
# issues a final GET after its internal wait, so the ceiling needs headroom
# rather than an exact match. Derived from the waits above so the two cannot
# drift apart.
_BACKGROUND_MARGIN = timedelta(minutes=15)
_RESEARCH_BACKGROUND_STC = (
    timedelta(
        seconds=max([_BACKGROUND_TIMEOUT_S, *_BACKGROUND_TIMEOUT_S_BY_EFFORT.values()])
    )
    + _BACKGROUND_MARGIN
)  # 4h15m: frontier's 4h wait plus headroom


_T = TypeVar("_T", bound=BaseModel)


def _validate(model: type[_T], payload: dict[str, Any]) -> _T:
    """Parse an Activity payload into its SDK model, failing cleanly if it cannot.

    A bare ``model_validate`` raising inside a Workflow is a Workflow task
    failure, which Temporal retries indefinitely -- an unexpected upstream
    response shape would hang the Operation rather than surface. Converting it
    to a non-retryable ApplicationError means the caller gets a real error, and
    it reaches them through the same failure chain as any other Activity error.

    The message reports which fields failed and why, but never the values. A
    pydantic error renders the offending input inline, and this message travels
    across the Nexus boundary into the caller's failure and the Workflow
    history -- so a malformed response would otherwise spill You.com content to
    whoever called the Operation.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise ApplicationError(
            f"You.com response did not match {model.__name__}: {problems}",
            type="YouResponseShapeError",
            non_retryable=True,
        ) from exc


@workflow.defn
class YouSearchWorkflow:
    @workflow.run
    async def run(self, inp: SearchInput) -> SearchResponse:
        payload = await workflow.execute_activity(
            youdotcom_search,
            inp,
            start_to_close_timeout=_SEARCH_STC,
            retry_policy=_RETRY,
            summary=f"you.com search: {inp.query}",
        )
        return _validate(SearchResponse, payload)


@workflow.defn
class YouAnswerWorkflow:
    @workflow.run
    async def run(self, inp: AnswerInput) -> AnswerResponse:
        payload = await workflow.execute_activity(
            youdotcom_answer,
            inp,
            start_to_close_timeout=_ANSWER_STC,
            retry_policy=_RETRY,
            summary=f"you.com answer: {inp.query}",
        )
        return _validate(AnswerResponse, payload)


@workflow.defn
class YouContentsWorkflow:
    @workflow.run
    async def run(self, inp: ContentsInput) -> ContentsOutput:
        payload = await workflow.execute_activity(
            youdotcom_contents,
            inp,
            start_to_close_timeout=_CONTENTS_STC,
            retry_policy=_RETRY,
            summary=f"you.com contents: {len(inp.urls)} url(s)",
        )
        # The Activity builds this envelope itself, but reach for the key
        # defensively: a KeyError here would be a Workflow task failure, which
        # retries forever, and that is exactly what _validate exists to avoid.
        documents = payload.get("results")
        if not isinstance(documents, list):
            raise ApplicationError(
                "You.com contents response had no 'results' list",
                type="YouResponseShapeError",
                non_retryable=True,
            )
        return ContentsOutput(results=[_validate(Contents, c) for c in documents])


@workflow.defn
class YouResearchWorkflow:
    @workflow.run
    async def run(self, inp: ResearchInput) -> ResearchResponse:
        payload = await workflow.execute_activity(
            youdotcom_research,
            inp,
            start_to_close_timeout=_RESEARCH_STC,
            retry_policy=_RETRY_RESEARCH,
            summary=f"you.com research ({inp.research_effort})",
        )
        return _validate(ResearchResponse, payload)


@workflow.defn
class YouFinanceResearchWorkflow:
    @workflow.run
    async def run(self, inp: FinanceResearchInput) -> FinanceResearchResponse:
        payload = await workflow.execute_activity(
            youdotcom_finance_research,
            inp,
            start_to_close_timeout=_FINANCE_RESEARCH_STC,
            retry_policy=_RETRY_RESEARCH,
            summary=f"you.com finance research ({inp.research_effort})",
        )
        return _validate(FinanceResearchResponse, payload)


@workflow.defn
class YouResearchBackgroundWorkflow:
    @workflow.run
    async def run(self, inp: ResearchInput) -> TaskDetail:
        payload = await workflow.execute_activity(
            youdotcom_research_background,
            inp,
            start_to_close_timeout=_RESEARCH_BACKGROUND_STC,
            retry_policy=_RETRY_RESEARCH,
            summary=f"you.com background research ({inp.research_effort})",
        )
        return _validate(TaskDetail, payload)


def you_nexus_workflows() -> list[type]:
    """All Nexus-backing Workflows, for passing to ``Worker(workflows=...)``."""
    return [
        YouSearchWorkflow,
        YouAnswerWorkflow,
        YouContentsWorkflow,
        YouResearchWorkflow,
        YouFinanceResearchWorkflow,
        YouResearchBackgroundWorkflow,
    ]

# youdotcom-temporal

Durable [You.com](https://you.com) search, answer, research, and contents Activities for [Temporal](https://temporal.io).

Exposes You.com API calls as Temporal Activities with proper error mapping, retry semantics, and workflow sandbox support. Ships as a `SimplePlugin` for one-line setup, or as standalone activity functions for manual worker wiring. An optional Nexus Service (`youdotcom_temporal.nexus`) exposes the same calls as cross-Namespace Operations for teams that want a durable service contract on top of the Activities.

## Installation

```bash
pip install youdotcom-temporal
```

Requires Python 3.10+. Uses the official [`youdotcom`](https://pypi.org/project/youdotcom/) Python SDK (>=3.0.0) and [`temporalio`](https://pypi.org/project/temporalio/) (>=1.27.0).

## Quickstart

Set your You.com API key (get one at [you.com/platform](https://you.com/platform)):

```bash
export YDC_API_KEY=your-key-here
```

Start a local Temporal server:

```bash
temporal server start-dev
```

### Plugin path (recommended)

```python
from temporalio.client import Client
from temporalio.worker import Worker
from youdotcom_temporal import YouPlugin

from hello_search_workflow import HelloSearch  # see examples/

async def main():
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue="you-search",
        workflows=[HelloSearch],
        plugins=[YouPlugin()],
    )
    await worker.run()
```

The plugin auto-registers all activities and adds the SDK's runtime modules to the workflow sandbox passthrough.

### Manual path

If you prefer to manage your own worker wiring:

```python
from temporalio.worker import Worker
from youdotcom_temporal import you_activities

worker = Worker(
    client,
    task_queue="you-search",
    workflows=[HelloSearch],
    activities=you_activities(),
)
```

## Activities

| Activity | Input | Description |
|---|---|---|
| `youdotcom_search` | `SearchInput` | Web and news search results |
| `youdotcom_answer` | `AnswerInput` | Synthesized answer with inline citations |
| `youdotcom_research` | `ResearchInput` | Multi-step research with citations |
| `youdotcom_research_background` | `ResearchInput` | Long-running background research (submits, streams, polls until complete) |
| `youdotcom_finance_research` | `FinanceResearchInput` | Finance-focused research with citations |
| `youdotcom_contents` | `ContentsInput` | Webpage content as HTML or markdown |

All activities return JSON-serializable dicts (via `model_dump(mode="json")`).

### SearchInput

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | (required) | Search query |
| `count` | `int \| None` | `None` | Max results per section (1-100) |
| `freshness` | `str \| None` | `None` | `day`, `week`, `month`, `year`, or date range |
| `offset` | `int \| None` | `None` | Pagination offset |
| `country` | `str \| None` | `None` | ISO 3166-1 alpha-2 country code |
| `language` | `str \| None` | `None` | BCP 47 language code |
| `safesearch` | `str \| None` | `None` | `off`, `moderate`, or `strict` |
| `livecrawl` | `str \| None` | `None` | Deprecated; use `extraction`. `web`, `news`, or `all` |
| `livecrawl_formats` | `list[str] \| None` | `None` | Deprecated; use `extraction`. `html` and/or `markdown` |
| `extraction` | `dict \| None` | `None` | Extraction config: `{"extraction_mode": "highlights" \| "full_page", "full_page": {"extraction_formats": [...]}}`. Takes priority over `livecrawl` / `livecrawl_formats` |
| `include_domains` | `list[str] \| None` | `None` | Restrict to these domains (max 500) |
| `exclude_domains` | `list[str] \| None` | `None` | Exclude these domains (max 500) |
| `boost_domains` | `list[str] \| None` | `None` | Boost these domains in ranking (max 500) |
| `crawl_timeout` | `int \| None` | `None` | Livecrawl timeout in seconds (1-60) |

### AnswerInput

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | (required) | Question to answer (max 400 chars) |
| `freshness` | `str \| None` | `None` | `day`, `week`, `month`, `year`, or date range |
| `country` | `str \| None` | `None` | ISO 3166-1 alpha-2 country code |
| `language` | `str \| None` | `None` | BCP 47 language code |
| `include_domains` | `list[str] \| None` | `None` | Restrict to these domains (max 500) |
| `exclude_domains` | `list[str] \| None` | `None` | Exclude these domains (max 500) |
| `boost_domains` | `list[str] \| None` | `None` | Boost these domains in ranking (max 500) |

### ResearchInput

| Field | Type | Default | Description |
|---|---|---|---|
| `input` | `str` | (required) | Research question (max 40,000 chars) |
| `research_effort` | `str` | `"standard"` | `lite`, `standard`, `deep`, `exhaustive`, or `frontier` |
| `background` | `bool` | `False` | Queue as background task (returns task handle) |
| `source_control` | `dict \| None` | `None` | Domain filters: `include_domains`, `exclude_domains`, `boost_domains`, `freshness`, `country` |
| `output_schema` | `dict \| None` | `None` | JSON Schema for structured output (standard/deep/exhaustive only) |
| `timeout_s` | `float \| None` | `None` | (background activity only) Max seconds to wait for SSE streaming before falling back to polling. Defaults to 120s; use 14400 (4h) for frontier tasks |

`youdotcom_research_background` accepts the same `ResearchInput` but always runs in background mode. It uses the SDK's `research_and_wait_async` helper to submit, stream, and poll until the task completes. For `frontier` effort, set `timeout_s=14400` and an appropriate `StartToClose` timeout on the workflow side.

### FinanceResearchInput

| Field | Type | Default | Description |
|---|---|---|---|
| `input` | `str` | (required) | Financial research question |
| `research_effort` | `str` | `"deep"` | `deep` or `exhaustive` |

### ContentsInput

| Field | Type | Default | Description |
|---|---|---|---|
| `urls` | `list[str]` | (required) | URLs to fetch (max 10) |
| `formats` | `list[str] \| None` | `None` | `markdown`, `html`, and/or `metadata` (default: `["markdown"]`) |
| `crawl_timeout` | `int` | `10` | Per-URL timeout in seconds (1-60) |
| `max_age` | `int \| None` | `None` | Max cache age in seconds (0 = always re-fetch) |

## Nexus Service

`youdotcom_temporal.nexus.YouDotComService` is a [Temporal Nexus](https://docs.temporal.io/nexus) Service that exposes all six Activities as Operations callable across Namespace boundaries through a Nexus Endpoint. It is an opt-in layer on top of the Activities, so importing it does not affect Activity-only users.

Every Operation is asynchronous and backed by a Workflow (`youdotcom_temporal.workflows`). Nexus synchronous operations must finish within a 10-second handler deadline, which is the wrong shape for these calls: `research` and `finance_research` are multi-step research runs measured in tens of seconds to minutes by design, background research runs up to 4 hours for `frontier`, and `search` and `contents` accept `livecrawl` and `crawl_timeout` (up to 60s per URL), so a caller can legitimately ask for a long call.

A sync handler that misses the deadline fails as a retryable error, and five consecutive retryable errors trip a circuit breaker that blocks *every* Operation on that caller/Endpoint pair for 60 seconds. Routing each Operation through a Workflow removes the cliff and gives the caller durable, observable execution.

Register the handler, the backing Workflows, and the Activities (via `YouPlugin`) on one Worker in the handler Namespace. `YouPlugin` is what registers the Activities the backing Workflows call, so the handler Worker needs it.

Operations return the You.com SDK's own pydantic response models, so both the handler and every caller need Temporal's pydantic data converter.

```python
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker
from youdotcom_temporal import YouPlugin
from youdotcom_temporal.nexus import you_nexus_service_handler
from youdotcom_temporal.workflows import you_nexus_workflows

async def main():
    client = await Client.connect(
        "localhost:7233",
        namespace="you-handler",
        data_converter=pydantic_data_converter,
    )
    worker = Worker(
        client,
        task_queue="you-nexus",
        workflows=you_nexus_workflows(),
        nexus_service_handlers=[you_nexus_service_handler()],
        plugins=[YouPlugin()],
    )
    await worker.run()
```

Create a Nexus Endpoint targeting that Worker, then call an Operation from a caller Workflow in another Namespace. Callers import from `youdotcom_temporal.contract`, which carries the types and none of the handler. No plugin and no sandbox escape are needed — the contract wraps its own SDK import — so these are safe at module scope:

```python
from datetime import timedelta
from temporalio import workflow

from youdotcom_temporal.contract import SearchRequest, SearchResponse, YouDotComService
from youdotcom_temporal.models import SearchInput

NEXUS_ENDPOINT = "you-nexus-endpoint"

@workflow.defn
class CallerWorkflow:
    @workflow.run
    async def run(self, query: str) -> SearchResponse:
        nexus_client = workflow.create_nexus_client(
            service=YouDotComService, endpoint=NEXUS_ENDPOINT
        )
        out = await nexus_client.execute_operation(
            YouDotComService.search,
            SearchRequest(
                input=SearchInput(query=query, count=10),
                # Optional. With a key, a retried StartOperation attaches to the
                # Workflow already running instead of starting a second one and
                # paying for a second You.com call.
                idempotency_key=f"search:{query}",
            ),
            # Must exceed the handler-side worst case: the Activity ceiling
            # times the retry policy's maximum_attempts (120s x 3 for search).
            schedule_to_close_timeout=timedelta(minutes=10),
        )
        out.results.web[0].title   # typed all the way down
        return out
```

| Operation | Request | Result | Backing Workflow |
|---|---|---|---|
| `search` | `SearchRequest` | `SearchResponse` | `YouSearchWorkflow` |
| `answer` | `AnswerRequest` | `AnswerResponse` | `YouAnswerWorkflow` |
| `contents` | `ContentsRequest` | `ContentsOutput` | `YouContentsWorkflow` |
| `research` | `ResearchRequest` | `ResearchResponse` | `YouResearchWorkflow` |
| `finance_research` | `FinanceResearchRequest` | `FinanceResearchResponse` | `YouFinanceResearchWorkflow` |
| `research_background` | `ResearchRequest` | `TaskDetail` | `YouResearchBackgroundWorkflow` |

Every request carries the matching Activity input plus an optional `idempotency_key`. Results are the You.com SDK's own response models, imported from `youdotcom_temporal.contract`, so callers get accurate nested types the SDK maintains. `contents` is the exception: the SDK returns a bare list, which could not gain fields later without breaking callers, so it keeps a thin `ContentsOutput` envelope whose elements are still SDK `Contents` models.

Each backing Workflow runs the Activity with a per-Activity `start_to_close_timeout`. A ceiling is a backstop rather than a latency target — it is where the Activity gives up and lets Temporal retry — so each carries generous headroom. `search` is 120s and `contents` 180s, sized off the 60s per-URL maximum a caller can request via `crawl_timeout` (`contents` gets more, since it accepts up to 10 URLs per request); `answer` is 60s; `research` is 10 minutes, `finance_research` 30 minutes, and `research_background` 4h15m.

That ceiling is **per attempt** — `search`, `answer`, and `contents` retry up to 3 times, so size the caller's `schedule_to_close_timeout` against the ceiling times the attempt count. The research Operations do not retry: each attempt submits a new billable research task, and the previous one keeps running.

See the [Temporal Python Nexus quickstart](https://docs.temporal.io/develop/python/nexus/quickstart) for Endpoint and caller-Namespace setup, and `examples/run_nexus_worker.py` for a runnable handler-side Worker.

**Known limits (draft):**

- **Cancellation does not reach You.com, and cannot.** The You.com API exposes no cancellation — the research surface is `POST /v1/research` plus two GETs to poll or stream, with no DELETE — so a submitted request runs to completion and is billed regardless. Cancelling an Operation frees the backing Workflow and the Worker slot, nothing upstream.
- **Idempotency is opt-in and bounded.** Supplying `idempotency_key` deduplicates against a Workflow that is still *running*, which covers the StartOperation-retry case. A key reused after the first Operation completed starts a fresh run. Without a key, starts are not deduplicated at all.
- **An unparseable response fails the Operation.** Results are parsed into SDK models on the handler side; a response that does not match raises a non-retryable `YouResponseShapeError` rather than hanging the caller.

## Error handling

| HTTP status | Error type | Retryable? |
|---|---|---|
| 401, 403 | `YouAuthError` | No |
| 422 | `YouValidationError` | No |
| 402 | `YouQuotaExhausted` | No |
| 429 | (passthrough) | Yes, Temporal backs off |
| 5xx | (passthrough) | Yes, Temporal backs off |
| HTTP timeout | `YouTimeoutError` | Yes, Temporal backs off |

The SDK's built-in HTTP retries are disabled (`retry_config=None`) so Temporal is the single retry authority. Set `RetryPolicy` on `workflow.execute_activity` to control backoff and max attempts. See `examples/hello_search_workflow.py` for a complete example.

The default HTTP timeout is 300s (`YouConfig.timeout_seconds`). This covers deep/exhaustive inline research calls. Override via `YouConfig(timeout_seconds=...)` if needed.

## Security

Never pass your API key as a workflow or activity argument. Workflow inputs are recorded in Temporal history in plaintext. The key must come from the worker environment (`YDC_API_KEY`) or `YouConfig` set on the worker side.

```python
from youdotcom_temporal import set_config, YouConfig

set_config(YouConfig(api_key="your-key"))  # worker-side only
```

## Examples

See the [`examples/`](examples/) directory:

- `hello_search_workflow.py` - a simple search workflow with `RetryPolicy`
- `hello_background_research_workflow.py` - long-running research via `youdotcom_research_background` (use `timeout_s=14400` and a multi-hour `start_to_close_timeout` for `frontier` effort)
- `run_worker.py` - starts a worker with `YouPlugin`
- `run_workflow.py` - executes the search workflow
- `run_background_research_workflow.py` - executes the background research workflow
- `run_nexus_worker.py` - handler-side Worker hosting the `YouDotCom` Nexus Service

```bash
# Terminal 1
temporal server start-dev

# Terminal 2
python examples/run_worker.py

# Terminal 3 (search example)
python examples/run_workflow.py

# Terminal 3 (background research example)
python examples/run_background_research_workflow.py
```

## Development

```bash
uv sync --group dev
uv run ruff check
uv run mypy src
uv run pytest                          # unit tests (no network)
uv run pytest -m integration           # integration tests (needs YDC_API_KEY + local Temporal server)
```

## License

MIT

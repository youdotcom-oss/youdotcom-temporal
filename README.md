# youdotcom-temporal

Durable [You.com](https://you.com) search, answer, research, and contents Activities for [Temporal](https://temporal.io).

Exposes You.com API calls as Temporal Activities with proper error mapping, retry semantics, and workflow sandbox support. Ships as a `SimplePlugin` for one-line setup, or as standalone activity functions for manual worker wiring.

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
    client = await Client.connect("localhost:7233", plugins=[YouPlugin()])
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
| `livecrawl` | `str \| None` | `None` | `web`, `news`, or `all` |
| `livecrawl_formats` | `list[str] \| None` | `None` | `html` and/or `markdown` |
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

## Error handling

| HTTP status | Error type | Retryable? |
|---|---|---|
| 401, 403 | `YouAuthError` | No |
| 422 | `YouValidationError` | No |
| 402 | `YouQuotaExhausted` | No |
| 429 | (passthrough) | Yes, Temporal backs off |
| 5xx | (passthrough) | Yes, Temporal backs off |

The SDK's built-in HTTP retries are disabled (`retry_config=None`) so Temporal is the single retry authority. Set `RetryPolicy` on `workflow.execute_activity` to control backoff and max attempts. See `examples/hello_search_workflow.py` for a complete example.

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

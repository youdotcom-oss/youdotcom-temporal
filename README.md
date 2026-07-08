# youdotcom-temporal

Durable [You.com](https://you.com) search, research, and contents Activities for [Temporal](https://temporal.io).

Exposes You.com API calls as Temporal Activities with proper error mapping, retry semantics, and workflow sandbox support. Ships as a `SimplePlugin` for one-line setup, or as standalone activity functions for manual worker wiring.

## Installation

```bash
pip install youdotcom-temporal
```

Requires Python 3.10+. Uses the official [`youdotcom`](https://pypi.org/project/youdotcom/) Python SDK (>=2.3.0) and [`temporalio`](https://pypi.org/project/temporalio/) (>=1.27.0).

## Quickstart

Set your You.com API key (get one at [you.com/platform/api-keys](https://you.com/platform/api-keys)):

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
| `youdotcom_research` | `ResearchInput` | Multi-step research with citations |
| `youdotcom_contents` | `ContentsInput` | Webpage content as HTML or markdown |

All activities return JSON-serializable dicts (via `model_dump(mode="json")`).

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
- `run_worker.py` - starts a worker with `YouPlugin`
- `run_workflow.py` - executes the search workflow

```bash
# Terminal 1
temporal server start-dev

# Terminal 2
python examples/run_worker.py

# Terminal 3
python examples/run_workflow.py
```

## Development

```bash
uv sync --all-extras
uv run ruff check
uv run mypy src
uv run pytest                          # unit tests (no network)
uv run pytest -m integration           # integration tests (needs YDC_API_KEY + local Temporal server)
```

## License

MIT

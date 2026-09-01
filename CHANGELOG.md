# Changelog

All notable changes to `youdotcom-temporal` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nexus Service support: `youdotcom_temporal.nexus.YouDotComService` exposes all six Activities as asynchronous, workflow-backed Nexus Operations callable across Namespace boundaries through a Nexus Endpoint
- `youdotcom_temporal.contract` holds the Nexus contract: a request type per Operation carrying the Activity input plus an optional `idempotency_key`, and result types that are the You.com SDK's own response models, so callers get accurate nested types the SDK maintains. `contents` keeps a thin `ContentsOutput` envelope because the SDK returns a bare list; its elements are `ContentsResponse` models, not the search-extraction `Contents` model, which would have silently dropped `url`, `title`, and `metadata` from every element. Callers must configure `temporalio.contrib.pydantic.pydantic_data_converter`
- Supplying `idempotency_key` makes the backing Workflow Id deterministic and starts it with `WorkflowIDConflictPolicy.USE_EXISTING`, so a retried Nexus StartOperation request attaches to the run already in flight instead of starting a second Workflow and paying for a second You.com call. Deduplication holds against a *running* Workflow; without a key, starts are not deduplicated
- `youdotcom_temporal.workflows` ships six thin backing Workflows (`YouSearchWorkflow`, `YouAnswerWorkflow`, `YouContentsWorkflow`, `YouResearchWorkflow`, `YouFinanceResearchWorkflow`, `YouResearchBackgroundWorkflow`), each wrapping its Activity with a per-Activity `start_to_close_timeout` carrying generous headroom, since a ceiling is a retry backstop rather than a latency target. `search` and `contents` are sized off the 60s per-URL maximum a caller can request via `crawl_timeout`
- The `research` Operation rejects `background=True` with a non-retryable `YouValidationError`. With `background=True` the SDK returns a task handle, which can never validate as the Operation's `ResearchResponse` result—the caller would have paid for the research task and then received an opaque `YouResponseShapeError`. `research_background` is the Operation for background mode
- `you_nexus_service_handler()` and `you_nexus_workflows()` helpers for Worker registration
- `examples/run_nexus_worker.py` handler-side Worker example
- Unit tests covering the Nexus Service contract and handler
- Cross-Namespace round-trip tests against a local dev server (mocked You.com) and live round-trip tests for the fast Operations (`pytest -m integration`)

### Notes
- Nexus is an opt-in layer: importing `youdotcom_temporal.nexus` does not affect Activity-only users
- Every Operation is async/workflow-backed because Nexus sync operations have a 10-second handler deadline that several You.com calls exceed
- The handler Worker needs `YouPlugin` because it registers the Activities the backing Workflows call. Caller Workflows in other Namespaces need neither the plugin nor a sandbox escape
- The research Operations do not retry: each attempt submits a new billable research task, and the previous one keeps running because the You.com API has no way to cancel a submitted request
- Known limits, tracked before release: cancelling an Operation does not stop the in-flight You.com call
- Responses are parsed into SDK models on the handler side. A response that does not match raises a non-retryable `YouResponseShapeError`, because an unguarded parse error inside a Workflow is a Workflow task failure that Temporal would retry indefinitely, hanging the caller

## [1.1.0] — 2026-08-21

### Added
- `SearchInput.extraction` field accepts the SDK's new `extraction` object (`{"extraction_mode": "highlights" | "full_page", ...}`). When set, it takes priority over the deprecated `livecrawl` / `livecrawl_formats` fields and is passed to `you.search_async(extraction=...)` instead, avoiding the SDK's `ValueError` on dual-set. The legacy fields remain accepted for backward compatibility

### Changed
- Python SDK floor bumped to `youdotcom>=3.1.2,<4` (was `>=3.0.0,<4`). The 3.1.2 release ships the `X-Client-Info` attribution header and the `app_name` / `app_version` / `app_title` / `app_url` constructor kwargs on `You`
- The plugin now passes `app_name="youdotcom-temporal"` and `app_version=<package version>` to the `You(...)` constructor instead of mutating `client.sdk_configuration.user_agent` post-construction. Each outbound request carries `X-Client-Info: sdk; client=youdotcom-temporal/<version>; ua=python/<v> httpx/<v>`; the SDK's own `user-agent` stays as `youdotcom-python-sdk/<v>`. The `_USER_AGENT` constant is removed
- `youdotcom_research_background` now forwards `timeout_s` as-is (including `None`) to `research_and_wait_async` instead of substituting `120.0`. When `timeout_s` is `None`, the SDK derives an effort-based default (600s for standard, 14400s for frontier) via `_resolve_default_timeout()`. Previously the `120.0` fallback prevented that derivation, capping every effort tier at 120s

## [1.0.1] — 2026-08-18

### Fixed
- `youdotcom_temporal/__init__.py` resolves its public names lazily (PEP 562) instead of importing the Activity layer eagerly. Importing the package no longer pulls in the You.com SDK or `urllib.request`, so a Workflow file can import from `youdotcom_temporal` at module scope without `workflow.unsafe.imports_passed_through()` and without registering `YouPlugin`. Previously this failed at Worker construction with `RestrictedWorkflowAccessError`, and no passthrough block could fix it because Python imports a parent package before the submodule body runs. Public imports are unchanged. Note that importing an Activity *function* still loads the SDK, since that is the module it lives in — reference Activities by name to keep a Workflow SDK-free
- `tests/test_replay_safety.py` could never pass: its Workflow was defined in the test module, and the sandbox re-imports that module, re-executing the module-level `shutil.which("temporal")` in the file's own skip marker. The Workflow now lives in its own module, and the test runs

### Changed
- CI installs the Temporal CLI, so the tests needing a local dev server actually execute instead of skipping silently on every run

## [1.0.0] — 2026-08-07

### Added
- New activity `youdotcom_answer` and new `AnswerInput` dataclass for the Answer API (`you.answer_async()`)
- New activity `youdotcom_finance_research` and new `FinanceResearchInput` dataclass for the Finance Research API (`you.finance_research_async()`, tiers: `deep`, `exhaustive`)
- New activity `youdotcom_research_background` using the SDK's `research_helpers.research_and_wait_async()`; submits and polls long-running tasks until completion. Accepts the same `ResearchInput` plus a `timeout_s` field that controls how long to wait for SSE streaming before falling back to polling (defaults to 120s; set to 14400 for `frontier`)
- New params on `SearchInput`: `offset`, `include_domains`, `exclude_domains`, `boost_domains`, `crawl_timeout`
- New param on `ContentsInput`: `max_age` (cache freshness control in seconds; `0` always re-fetches)
- New params on `ResearchInput`: `background`, `source_control`, `output_schema`, `timeout_s` (background only)
- Integration tests covering all 6 activities against the real You.com API and a local Temporal server (`pytest -m integration`)
- `py.typed` marker so consumers get type checking on the public API
- `httpx.TimeoutException` mapped to retryable `YouTimeoutError` ApplicationError for cleaner Temporal UI

### Changed
- `youdotcom_search` now calls `you.search_async()` directly (was `you.search.unified_async()`)
- `youdotcom_contents` now calls `you.contents_async()` directly (was `you.contents.generate_async()`)
- `ResearchInput.research_effort` default changed from `"lite"` to `"standard"` to match the SDK default
- `ResearchInput.research_effort` validation now accepts `frontier` (was: `lite`, `standard`, `deep`, `exhaustive`)
- `pyproject.toml` dependency bumped: `youdotcom>=3.0.0,<4` (was: `>=2.3.0,<3`)
- `YouConfig.timeout_seconds` default increased from 30s to 300s (deep/exhaustive inline research can take 60-300s; Temporal's `start_to_close_timeout` is still the wall-clock ceiling)
- Dev tooling consolidated under `[dependency-groups]` (removed duplicate `[project.optional-dependencies]`)

### Fixed
- Error mappings updated to the SDK 3.0.0 class names: `UnauthorizedResponseError`, `ForbiddenResponseError`, `UnprocessableEntityResponseError`, `InternalServerErrorResponse`, `PaymentRequiredResponseError`
- `examples/run_workflow.py` now generates a unique workflow id per invocation so re-runs work under the default `WorkflowIDReusePolicy`
- `examples/run_worker.py` now registers both `HelloSearch` and `HelloBackgroundResearch` so the same worker serves both example workflows
- README "Plugin path" example no longer shows an unnecessary `YouPlugin()` on `Client.connect` (only the worker needs it)
- CI and publish workflows updated to `uv sync --group dev` after dropping `[project.optional-dependencies]`

## [0.1.0a1] — 2026-08-03

### Added
- Initial Alpha release
- `youdotcom_search`, `youdotcom_research`, `youdotcom_contents` activities pinned to `youdotcom>=2.3.0,<3`
- `YouPlugin` (Temporal `SimplePlugin`) registering all activities and adding the SDK's runtime modules to the workflow sandbox passthrough
- Error mapping module (`_errors.py`) for 401/403 → `YouAuthError`, 422 → `YouValidationError`, 402 → `YouQuotaExhausted`, 5xx passthrough
- Unit tests covering success paths, validation, and error mapping

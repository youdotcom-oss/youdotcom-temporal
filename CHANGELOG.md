# Changelog

All notable changes to `youdotcom-temporal` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Python SDK floor bumped to `youdotcom>=3.1.2,<4` (was `>=3.0.0,<4`). The 3.1.2 release ships the `X-Client-Info` attribution header and the `app_name` / `app_version` / `app_title` / `app_url` constructor kwargs on `You`
- The plugin now passes `app_name="youdotcom-temporal"` and `app_version=<package version>` to the `You(...)` constructor instead of mutating `client.sdk_configuration.user_agent` post-construction. Each outbound request carries `X-Client-Info: sdk; client=youdotcom-temporal/<version>; ua=python/<v> httpx/<v>`; the SDK's own `user-agent` stays as `youdotcom-python-sdk/<v>`. The `_USER_AGENT` constant is removed

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

# Changelog

## [Unreleased]

### Added

### Changed

### Deprecated

### Breaking Changes

### Fixed

### Security

## [0.1.0] - 2026-07-07

### Added

- Initial release: `YouPlugin` (SimplePlugin) with three durable activities
  (`youdotcom_search`, `youdotcom_research`, `youdotcom_contents`) wrapping the
  You.com Python SDK for Temporal workflows.
- `YouConfig` frozen dataclass with env-based resolution (`YDC_API_KEY`,
  `YDC_SERVER_URL`) and programmatic override via `set_config()`.
- `to_temporal_error()` maps SDK errors to Temporal `ApplicationError`
  (auth errors non-retryable, 422 non-retryable, 402 non-retryable,
  429 and 5xx passthrough for retry).
- Sandboxed workflow runner with passthrough modules for SDK dependencies.
- 42 unit tests covering config, error mapping, activities, and plugin.

# Contributing

Thanks for your interest in contributing to `youdotcom-temporal`.

## Development setup

```bash
git clone git@github.com:youdotcom-oss/youdotcom-temporal.git
cd youdotcom-temporal
uv sync --all-extras
```

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

## Running checks

```bash
uv run ruff check        # lint
uv run mypy src          # type check
uv run pytest            # tests
```

All three must pass before submitting a PR.

## Commits

Use [conventional commits](https://www.conventionalcommits.org/):

- `feat:` new feature
- `fix:` bug fix
- `refactor:` code restructuring
- `test:` test additions or changes
- `docs:` documentation
- `chore:` tooling, deps, CI

## Adding or changing activities

1. Add the input dataclass to `src/youdotcom_temporal/models.py`
2. Implement the activity in `src/youdotcom_temporal/activities.py`
3. Add it to the `you_activities()` list
4. Add error mapping in `src/youdotcom_temporal/_errors.py` if the SDK has new error types
5. Write tests in `tests/test_activities.py`
6. Update `__init__.py` exports if adding new public symbols

## Testing

Tests use mocked You.com clients (no network calls). Integration tests that hit the real API are gated behind `YDC_API_KEY` being set and are skipped in CI by default.

Activity tests use `temporalio.testing.ActivityEnvironment` to run activities in isolation. See existing tests for patterns.

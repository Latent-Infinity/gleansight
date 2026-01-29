# gleansight
A local-first research paper analysis platform that discovers, ingests, and extracts structured, queryable insights from academic literature using LLM-powered prompts.

Core stack highlights:
- Metadata store: Piccolo ORM (SQLite backend)
- Vector index: LanceDB
- Blobs: local filesystem

## Development setup (uv)

Best practices:
- Use `pyproject.toml` as the single source of truth for dependencies.
- Commit `uv.lock` to make installs reproducible.
- Use a local `.venv` for isolation.

Quickstart:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv sync --group dev
```

## Quality tools

```bash
# Lint
ruff check .

# Type check (Astral ty via uvx)
uvx ty check

# Tests + coverage (>=90%)
uv run pytest -q

# Integration tests (real dependencies)
uv run pytest -m integration -q --no-cov
```

## Dependency workflow

- Add/update deps in `pyproject.toml`
- Run `uv lock` to refresh `uv.lock`
- Run `uv sync --group dev` to install dev tooling

## Retry backoff parameters

Job retries use exponential backoff:

- Base delay: 60s
- Delay = `60 * (2 ** attempts)`
- Max delay: 3600s (1 hour)

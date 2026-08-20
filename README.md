# gleansight

Local-first **NS/QD-inspired discovery platform** with an **executable paper evidence pipeline** (discover, import, convert, extract, search).

**Maturity:** The paper evidence pipeline is executable (`papers` CLI/UI). The discovery baseline is also executable (`python -m nsqd skeleton` and `python -m nsqd harvest`); calibration data, live paper projection, and later map/archive phases remain pending.

Product thesis: [`docs/product-gleansight.md`](docs/product-gleansight.md)
Framework PRD: [`docs/prd-ns-qd.md`](docs/prd-ns-qd.md) · Requirements: [`docs/requirements-ns-qd.md`](docs/requirements-ns-qd.md) · Discovery plan: [`docs/development-plan-ns-qd.md`](docs/development-plan-ns-qd.md)
Evidence-layer closeout: [`docs/development-plan-open-work.md`](docs/development-plan-open-work.md)
Discovery review tracker: [`docs/review-nsqd-action-items.md`](docs/review-nsqd-action-items.md)

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
uv sync --group dev --group infra
```

## Configuration (.env)

On startup the app loads a `.env` file from the repo root (if present). Use it to store
LLM and API credentials so you do not pass them on the command line.

Example `.env`:

```
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=replace-me
SEMANTIC_SCHOLAR_API_KEY=
UNPAYWALL_EMAIL=
```

## CLI

Run the CLI entrypoint:

```bash
uv run python -m papers.cli --help
```

Use values from `.env` (shell loads and forwards to CLI options):

```bash
set -a
source .env
set +a
uv run python -m papers.cli \
  --llm-base-url "$LLM_BASE_URL" \
  --llm-api-key "$LLM_API_KEY"
```

## UI

Launch the UI:

```bash
set -a
source .env
set +a
uv run python - <<'PY'
import os
from papers.ui.__main__ import main

main(
    llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8000"),
    llm_api_key=os.environ.get("LLM_API_KEY"),
)
PY
```

## Quality tools

Repository-standard gate (same as the plans):

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

`pyproject.toml` `fail_under` is **91.90** (combined coverage on `src`, omitting `src/papers/ui/*`).

```bash
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

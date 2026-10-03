#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

groups=(--group dev --group infra --group research)
uv sync --locked "${groups[@]}"
uv run --locked "${groups[@]}" ruff format --check .
uv run --locked "${groups[@]}" ruff check .
uv run --locked "${groups[@]}" ty check
uv run --locked "${groups[@]}" python scripts/check_hash_bound_format.py
uv run --locked "${groups[@]}" pytest -q

# Python standards in gleansight

This is the repository adoption of [Python Code Standards, revision 2026-10-02](</Users/firestrand/Library/CloudStorage/Dropbox/Projects/Software-Standards/Python Code Standards.md>). Read that guide for the full rules and examples. Its **MUST** rules are acceptance requirements; **SHOULD** recommendations allow a brief, reasoned deviation. The checked-in project configuration and commands below define how this repository applies the guide.

## Supported environment

- `pyproject.toml` declares Python `>=3.12,<3.15`. `.python-version` sets the local default to 3.12.14. CI tests 3.12, 3.13, and 3.14 with `UV_PYTHON` overriding that local pin.
- Use uv 0.12.18, the committed `uv.lock`, and the explicit `dev`, `infra`, and `research` groups. `uv lock` is an intentional dependency update; verification uses `--locked` so stale metadata fails.
- Ruff targets Python 3.12. ty checks the minimum supported version. The project uses `pytest-asyncio` with asyncio auto mode and function-scoped loops.

## Required verification

```bash
bash scripts/verify.sh
```

The script syncs all three locked groups, then checks Ruff formatting, Ruff lint, ty, the hash-bound formatting inventory, and the full pytest suite. The existing combined coverage floor is 91.90% on `src`, excluding `src/papers/ui/*`. Run focused tests while editing, then run the full gate on the integrated change. Report the command, result, and any blocked or skipped check.

Tests must be deterministic and isolated from hosted models, live services, production credentials, and wall-clock timing. The marked Docling PDF integration test uses local model artifacts. On a cold machine, use the [README provisioning command](../README.md#quality-tools) before running tests with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; CI provisions those models before the offline test step. Keep real integration assertions and the hash-bound archive checks intact.

## Code and runtime boundaries

**Required:** Type public APIs and shared boundaries honestly. Validate untrusted JSON, configuration, paths, and tool output before using them as domain values; annotations and casts are not runtime validation. Make mutation explicit, preserve exception causes when translating errors, keep resource cleanup and retries bounded, and use lazy logging without secrets. Bound active and pending concurrency, keep blocking work off the asyncio event loop, and propagate cancellation after cleanup. Use parameterized SQL and argument arrays for subprocesses.

**Recommended:** Accept `Sequence`, `Mapping`, or `Iterable` when those operations fit the caller contract; concrete mutable types remain appropriate when mutation is part of the API. Prefer immutable shared state, `itertools.batched` for synchronous fixed-size batches, `Path` internally, and `asyncio.TaskGroup` for related tasks with a shared failure lifetime. These choices are contextual, not blanket rewrites of working code. Profile representative hot paths before claiming a speedup or adding a heavy numeric dependency.

## Dependency, packaging, and review policy

Declare runtime dependencies, groups, and build requirements in `pyproject.toml`; review new package identity, license, provenance, and the manifest plus lock diff together. Keep imports free of network calls, migrations, and process startup. The CI workflow uses reviewed full action SHAs and a read-only token for pull requests.

Because this is an installed `src/` package, CI builds both wheel and source distribution, rebuilds a wheel from the source distribution, installs each wheel in a clean environment outside the checkout, and smoke-tests imports, entry points, and packaged defaults. Changes to package data or startup configuration must pass that installed-artifact check.

Add behavior-focused regression tests for changed contracts and relevant failure paths. Preserve immutable evidence and historical digests; the hash-bound checker enforces the documented formatting exception inventory. Apply the current standard to new code and affected behavior without forcing unrelated legacy migrations.

An intentional deviation from a **MUST** rule needs `OVERRIDE(rule-name): reason` near the affected code or configuration, plus an owner and review date for a temporary exception. Critical security, integrity, or stability exceptions require the responsible technical owner's review. Broad type suppressions, weakened tests, and self-approved exceptions do not satisfy the gate.

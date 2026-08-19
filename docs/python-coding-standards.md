# Idiomatic Python Coding Standards

**Python 3.12+ Baseline**

> If it “works” but can’t be reasoned about under load, the issue is the design: data flow, I/O, and algorithmic shape — not the interpreter.

Python’s strengths are **expressiveness, batteries-included primitives, and high leverage APIs**. In production, Python performance and reliability hinge less on “micro-optimizing” and more on: **algorithmic complexity, object churn, I/O patterns, concurrency boundaries, and using C-accelerated built-ins and stdlib**.

This guide turns those ideas into enforceable standards with MUST/SHOULD/AVOID directives, plus patterns and anti-patterns.

---

## Baseline Features We Rely On

Because the baseline is **Python 3.12+**, this document assumes:

* **Stdlib batching:** `itertools.batched` exists and is the default batching primitive. ([Python documentation][1])
* **Modern typing syntax:** type parameters and `type` aliases (PEP 695). ([Python Enhancement Proposals (PEPs)][2])
* **Explicit override annotations:** `typing.override` (PEP 698). ([Python documentation][3])
* **Relaxed f-string parsing:** more flexible f-string grammar (PEP 701). ([Stack Overflow][4])
* **Pathlib directory traversal:** `Path.walk()` exists and is preferred over `os.walk()` for `Path`-native code. ([Python documentation][5])
* **Structured async concurrency:** `asyncio.TaskGroup` is available and is the preferred concurrency primitive for groups of tasks. ([Python documentation][6])

---

## Operating Principles

* **MUST** target **Python 3.12+** across production and CI (runtime, tooling, type checking).
* **MUST** profile and/or benchmark **before and after** any performance change on hot paths; record results in the PR.
* **MUST** treat **algorithmic complexity, I/O, object allocations, and interpreter overhead** as first-class design constraints.
* **MUST** keep code **readable by default**; micro-optimizations require measurement and justification.
* **SHOULD** identify “hot paths” (criteria in **Section 16**) and apply stricter standards to them.

---

## Quick Reference: Do / Don’t

| Topic     | Prefer                                            | Avoid                                              |
| --------- | ------------------------------------------------- | -------------------------------------------------- |
| APIs      | `Iterable` / `Sequence` / `Mapping` in signatures | Hard-coding `list`/`dict` without need             |
| Copies    | Immutability, views, reuse buffers                | “Just copy it” (`list(x)`, `dict(x)`) in hot paths |
| Counting  | `Counter`, `defaultdict`, `set` membership        | Manual dict plumbing in loops                      |
| Queues    | `deque`                                           | `list.pop(0)`                                      |
| Batching  | `itertools.batched`                               | Hand-rolled batch loops                            |
| Strings   | `join`, f-strings at boundaries                   | `+` concatenation in loops                         |
| Logging   | `logger.info("x=%s", x)`                          | f-strings inside logger calls                      |
| Async     | `TaskGroup`, bounded concurrency                  | `create_task` “fire-and-forget”                    |
| CPU-bound | Process pool / native libs / vectorization        | Threads expecting parallel CPU speedups            |
| Tooling   | `uv`, `ruff`, `ty`                                | Mixed toolchains / inconsistent configs            |

---

## 1. Data Model: Bindings, Mutability, and Copy Costs

**Python variables are bindings to objects.** Most “copies” you see in code are either:

* **New containers** (costly for large data), or
* **New objects** (costly and increases GC pressure).

### Standards

* **MUST** assume containers are passed by reference; mutation affects all aliases.
* **MUST** make mutation explicit in API design (mutating vs non-mutating functions).
* **SHOULD** prefer immutable data (`tuple`, `frozenset`, “frozen” dataclasses) for shared state.
* **AVOID** defensive copying in hot paths unless correctness requires it.

### Anti-pattern: Hidden aliasing + accidental mutation

```python
from collections.abc import MutableSequence

def add_sentinel(items: MutableSequence[int]) -> None:
    items.append(-1)

xs = [1, 2, 3]
ys = xs           # alias, not a copy
add_sentinel(ys)
assert xs == [1, 2, 3, -1]
```

### Prefer: Choose immutability or copy explicitly

```python
from collections.abc import Sequence

def with_sentinel(items: Sequence[int]) -> tuple[int, ...]:
    return (*items, -1)
```

---

## 2. API Design: Shape Signatures to How Callers Use Data

### Standards

* **MUST** accept the *widest* reasonable interface:

  * read-only sequences → `Sequence[T]`
  * streaming inputs → `Iterable[T]` / `Iterator[T]`
  * key-value inputs → `Mapping[K, V]`
* **MUST** return the *most specific* useful type (often `list[T]` at boundaries).
* **SHOULD** use `Path | str` for filesystem APIs (and normalize internally).
* **AVOID** forcing callers to materialize iterables (e.g., `list(...)`) unless you truly need random access.

### Prefer

```python
from collections.abc import Iterable, Mapping

def render_headers(headers: Mapping[str, str]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in headers.items())

def ingest(records: Iterable[bytes]) -> int:
    return sum(1 for _ in records)
```

---

## 3. Collection Selection and Immutability

### Standards

* **MUST** use:

  * `list` for ordered collections
  * `tuple` for fixed-size, immutable records
  * `set` for membership tests
  * `dict` for key-value indexing
* **SHOULD** use `frozenset` for immutable set constants (safe to share).
* **SHOULD** use:

  * `collections.Counter` for frequency counting
  * `collections.deque` for FIFO/LIFO queue workloads
* **AVOID** `list.pop(0)` or front-removals (O(n)).

### Pattern: Immutable set constants

```python
VALID_STATUSES: frozenset[str] = frozenset({"pending", "active", "completed"})
```

### Pattern: Counter beats manual counting

```python
from collections import Counter
from collections.abc import Iterable

def top_words(words: Iterable[str], n: int = 10) -> list[tuple[str, int]]:
    counts = Counter(words)
    return counts.most_common(n)
```

### Pattern: deque for queues

```python
from collections import deque

q: deque[str] = deque()
q.append("a")
q.append("b")
first = q.popleft()  # O(1)
```

---

## 4. Iteration and Lazy Pipelines

Python is fast when you:

* use **C-accelerated built-ins** (`sum`, `any`, `all`, `min`, `max`, `sorted`)
* keep transforms **single-pass**
* avoid intermediate lists unless needed

### Standards

* **MUST** avoid materializing intermediate lists in hot paths.
* **SHOULD** prefer generator expressions and iterator-based pipelines.
* **MUST** use `itertools.batched` for batching. ([Python documentation][1])

### Anti-pattern: intermediate allocations

```python
positives = [x for x in xs if x > 0]
doubled = [x * 2 for x in positives]
total = sum(doubled)
```

### Prefer: one pass

```python
total = sum(x * 2 for x in xs if x > 0)
```

### Pattern: Batching with stdlib

```python
from collections.abc import Iterable
from itertools import batched

def process_in_batches(items: Iterable[str], batch_size: int = 100) -> None:
    for batch in batched(items, batch_size):
        send_to_api(batch)
```

---

## 5. String Handling and Formatting

### Standards

* **MUST** use `str.join` for concatenating many strings.
* **SHOULD** use f-strings for **human-facing** strings at boundaries (exceptions, UI output).
* **MUST** avoid f-strings inside logger calls; use lazy formatting (Section 8).
* **AVOID** `+` concatenation in loops.

### Pattern: join for concatenation

```python
def csv_line(fields: list[str]) -> str:
    return ",".join(fields)
```

### Python 3.12+ f-string flexibility (useful, but still eager)

```python
user = {"name": "Ada"}
msg = f"User {user["name"]} logged in"  # valid under relaxed parsing rules
```

(PEP 701 changed f-string parsing.) ([Stack Overflow][4])

---

## 6. I/O, Files, and Paths

### Standards

* **MUST** stream large files (chunked reads/writes); never `read()` whole multi-GB files.
* **MUST** use `pathlib.Path` internally; accept `Path | str` at boundaries.
* **SHOULD** use `Path.walk()` for `Path`-native directory traversal. ([Python documentation][5])

### Pattern: Chunked binary processing

```python
from pathlib import Path

CHUNK_SIZE: int = 1024 * 1024

def process_file_chunked(path: Path | str, chunk_size: int = CHUNK_SIZE) -> None:
    p = Path(path)
    with p.open("rb") as f:
        while chunk := f.read(chunk_size):
            process(chunk)
```

### Pattern: Directory traversal with `Path.walk()`

```python
from pathlib import Path

def find_py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, _dirnames, filenames in root.walk():
        for name in filenames:
            p = dirpath / name
            if p.suffix == ".py":
                out.append(p)
    return out
```

(`Path.walk()` is added in Python 3.12.) ([Python documentation][5])

---

## 7. Error Handling: Exceptions, EAFP vs LBYL

Python’s idiom is usually **EAFP** (“try it, catch the exception”). But exceptions are not free; if you expect failures to be *common* in a hot loop, checking first may win.

### Standards

* **MUST** define small, meaningful exception types at module boundaries.
* **MUST NOT** use bare `except:` (use specific exceptions).
* **SHOULD** prefer EAFP when failure is rare.
* **SHOULD** prefer LBYL in hot loops when failures are common (measure).
* **AVOID** `return None` to signal errors when exceptions are clearer and safer.

### EAFP: missing keys are rare

```python
def get_user_name(users: dict[int, "User"], user_id: int) -> str:
    try:
        return users[user_id].name
    except KeyError:
        return "Unknown"
```

### LBYL: missing keys are common in a hot loop

```python
from collections.abc import Iterable

def sum_valid_scores(scores: dict[str, int], keys: Iterable[str]) -> int:
    total = 0
    for k in keys:
        if k in scores:
            total += scores[k]
    return total
```

---

## 8. Logging and Observability

### Standards

* **MUST** use the `logging` module (or a team-approved wrapper) — no `print` in services.
* **MUST** use lazy formatting:

  * `logger.info("user_id=%s", user_id)`
* **SHOULD** use consistent key-value patterns for queryable logs.
* **AVOID** f-strings in logger calls (they format even if the level is disabled).

### Anti-pattern: eager formatting

```python
logger.debug(f"expensive={compute()}")  # compute() always runs
```

### Prefer: lazy formatting

```python
logger.debug("expensive=%s", compute())  # compute still runs
```

If you want to avoid computing unless enabled:

```python
if logger.isEnabledFor(10):  # DEBUG
    logger.debug("expensive=%s", compute())
```

---

## 9. Concurrency: Threads, Processes, and the GIL

### Standards

* **MUST** assume threads do **not** provide parallel CPU speedups for Python bytecode (GIL).
* **SHOULD** use threads for I/O-bound concurrency (`ThreadPoolExecutor`).
* **SHOULD** use processes (or native/vectorized libraries) for CPU-bound workloads.
* **MUST** bound concurrency (max workers, queue sizes).
* **AVOID** spawning unbounded tasks/threads per request.

### Pattern: bounded thread pool

```python
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterable, Iterator

def fetch_all(urls: Iterable[str]) -> Iterator["Response"]:
    with ThreadPoolExecutor(max_workers=32) as ex:
        yield from ex.map(fetch, urls)
```

---

## 10. Async/Await Patterns

### Standards

* **MUST** use `asyncio.TaskGroup` for groups of tasks (structured concurrency). ([Python documentation][6])
* **MUST** bound concurrency (semaphores, pools).
* **SHOULD** use timeouts for external calls.
* **AVOID** “fire-and-forget” tasks in request handlers.

### Pattern: Structured concurrency with `TaskGroup`

```python
import asyncio
from collections.abc import Sequence

async def fetch_all_structured(urls: Sequence[str]) -> list["Response"]:
    tasks: list[asyncio.Task["Response"]] = []
    async with asyncio.TaskGroup() as tg:
        for url in urls:
            tasks.append(tg.create_task(fetch(url)))
    return [t.result() for t in tasks]
```

---

## 11. Data and Numeric Workloads

### Standards

* **MUST** avoid Python-level loops for heavy numeric workloads when a vectorized/native option exists.
* **SHOULD** use `array`, `memoryview`, `struct`, `numpy`, etc., when justified by profiling.
* **AVOID** premature heavy dependencies — introduce them when the workload demands it.

### Example: Python loop vs vectorized

```python
def normalize_python(values: list[float]) -> list[float]:
    total = sum(values)
    return [v / total for v in values]
```

```python
import numpy as np

def normalize_numpy(values: np.ndarray) -> np.ndarray:
    return values / values.sum()
```

---

## 12. Typing Standards

We standardize on:

* `ruff` for lint + formatting
* `ty` for type checking
* Python 3.12 typing features as baseline

### Standards

* **MUST** type all public APIs, boundary layers, and shared libraries.
* **MUST** keep types honest: don’t “paper over” with `Any` unless unavoidable at boundaries.
* **SHOULD** use Python 3.12+ type parameter syntax for new generics. ([Python Enhancement Proposals (PEPs)][2])
* **SHOULD** use `typing.override` for overrides. ([Python documentation][3])

### Pattern: Type parameter syntax (preferred)

```python
from collections.abc import Sequence

def first[T](items: Sequence[T]) -> T | None:
    return items[0] if items else None
```

### Pattern: `type` aliases (PEP 695)

```python
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
```

([Python Enhancement Proposals (PEPs)][2])

### Pattern: Explicit overrides

```python
from typing import override

class BaseHandler:
    def handle(self, data: bytes) -> None:
        raise NotImplementedError

class JsonHandler(BaseHandler):
    @override
    def handle(self, data: bytes) -> None:
        process_json(data)
```

([Python documentation][3])

---

## 13. Control Flow and Pattern Matching

### Standards

* **MUST** use guard clauses / early returns to keep the happy path flat.
* **SHOULD** use `match` for structured branching on stable shapes.
* **AVOID** deep nesting of `if/elif` when matching structured data.

### Pattern: match/case for protocol responses

```python
def handle_status(status: int) -> str:
    match status:
        case 200:
            return "ok"
        case 404:
            raise NotFoundError
        case _:
            raise UnexpectedStatusError(status)
```

---

## 14. Testing Standards

### Standards

* **MUST** have unit tests for correctness-critical logic and hot paths.
* **MUST** name tests as `test_<unit>_<scenario>`.
* **SHOULD** use parametrization for scenario coverage.
* **MUST** test async code with `pytest-asyncio` configuration (see pyproject). ([pytest-asyncio.readthedocs.io][7])

### Pattern: Async test that actually tests behavior

```python
import pytest

@pytest.mark.asyncio
async def test_fetch_all_returns_empty_for_empty_input() -> None:
    result = await fetch_all_structured([])
    assert result == []
```

---

## 15. Benchmarking and Profiling Discipline

### Standards

* **MUST** benchmark hot-path changes and include results in PRs.
* **SHOULD** use:

  * `cProfile` / `pstats` for CPU
  * allocation tracking when needed (runtime or external tooling)
* **AVOID** “feels faster” without measurements.

---

## 16. Identifying Hot Paths

Treat a path as “hot” if any are true:

* Executed per request / message / event in a service
* Executed per item in a large batch (>1k items)
* Top 10% in CPU time or allocation churn during profiling
* Influences p95/p99 latency or memory peaks

---

## 17. Tooling, Lints, and Standards Enforcement

We standardize on:

* **uv** for project/env management and tool execution ([Astral Docs][8])
* **ruff** for formatting + linting ([Astral Docs][9])
* **ty** for type checking ([Astral Docs][10])

### Required local commands

```bash
uv sync --locked --all-extras --dev
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

(The `uv sync --locked --all-extras --dev` pattern is documented for GitHub Actions usage.) ([Astral Docs][11])

---

## 18. `pyproject.toml` Skeleton

```toml
[project]
name = "myproject"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.24",
  "ruff>=0.11",
  "ty>=0.0.14",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "PTH", "ASYNC"]
ignore = ["E501"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ty.environment]
python-version = "3.12"

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

* Ruff supports configuring via `pyproject.toml` and related files. ([Astral Docs][9])
* Ruff’s `ASYNC` rules exist (derived from flake8-async). ([Astral Docs][12])
* ty supports `[tool.ty]` configuration and a `python-version` environment setting. ([Astral Docs][13])
* pytest-asyncio documents loop-scope configuration options. ([pytest-asyncio.readthedocs.io][7])

---

## 19. Code Review Checklist

* [ ] **APIs** accept `Iterable/Sequence/Mapping` appropriately (not over-specific).
* [ ] **Copies**: no accidental `list(...)`, `dict(...)`, `deepcopy(...)` in hot paths.
* [ ] **Collections**: correct structure (`deque` for queues, `set` for membership, `Counter` for counts).
* [ ] **Batching** uses `itertools.batched` where applicable.
* [ ] **Strings**: no `+` concatenation in loops; no f-strings in logger calls.
* [ ] **Async**: uses `TaskGroup`; concurrency is bounded.
* [ ] **Typing**: public APIs typed; overrides marked where meaningful.
* [ ] **Tests**: real assertions; async tests run and cover failure modes.
* [ ] **Perf**: hot-path changes include before/after evidence.

---

## 20. Pull Request Template

Create `.github/pull_request_template.md`:

```md
## Summary
What does this change do and why?

## Design Notes
- Key design decisions:
- Alternatives considered:
- Tradeoffs:

## Risk / Rollout
- [ ] Backward compatible
- [ ] Requires coordinated deploy/migration
- Rollout plan:

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Async tests added/updated (if applicable)

## Performance (required for hot paths)
- Hot path? (per standards): yes/no
- Baseline numbers:
- New numbers:
- Notes on measurement methodology:

## Checklist
- [ ] `uv sync --locked --all-extras --dev`
- [ ] `uv run ruff format --check .`
- [ ] `uv run ruff check .`
- [ ] `uv run ty check`
- [ ] `uv run pytest`
```

---

## 21. GitHub Actions CI Skeleton

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  ci:
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]

    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Sync (locked)
        run: uv sync --locked --all-extras --dev

      - name: Format check (ruff)
        run: uv run ruff format --check .

      - name: Lint (ruff)
        run: uv run ruff check .

      - name: Type check (ty)
        run: uv run ty check

      - name: Tests (pytest)
        run: uv run pytest

      # Optional: keep cache lean in CI
      - name: Prune uv cache
        run: uv cache prune --ci
```

* The uv docs recommend `astral-sh/setup-uv@v7` and show `uv sync --locked --all-extras --dev` in GitHub Actions examples. ([Astral Docs][14])
* `actions/setup-python` supports `python-version` and recommends pinning explicitly. ([GitHub][15])
* uv recommends `uv cache prune --ci` to improve CI cache efficiency. ([Astral Docs][16])
* `ty check` is the canonical CLI entry point for type checking. ([Astral Docs][10])

---

## 22. Closing Principles

Python code wins when it:

1. Chooses the right **data structures** and **algorithms**
2. Uses **stdlib and built-ins** aggressively (often C-optimized)
3. Controls **I/O**, **object churn**, and **concurrency fan-out**
4. Enforces correctness with **typing + tests + linters**
5. Measures hot paths and treats performance as a **design property**

[1]: https://docs.python.org/3/library/itertools.html?utm_source=chatgpt.com "itertools — Functions creating iterators for efficient looping"
[2]: https://peps.python.org/pep-0695/ "PEP 695 – Type Parameter Syntax | peps.python.org"
[3]: https://docs.python.org/3/whatsnew/3.12.html "What’s New In Python 3.12 — Python 3.14.2 documentation"
[4]: https://stackoverflow.com/questions/78388333/nested-quotes-in-f-string-with-python-3-12-vs-older-versions?utm_source=chatgpt.com "Nested quotes in f-string with Python 3.12 vs older versions"
[5]: https://docs.python.org/3/library/pathlib.html "pathlib — Object-oriented filesystem paths — Python 3.14.2 documentation"
[6]: https://docs.python.org/3/whatsnew/3.11.html?utm_source=chatgpt.com "What's New In Python 3.11 — Python 3.14.2 documentation"
[7]: https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html?utm_source=chatgpt.com "Configuration — pytest-asyncio 1.3.0 documentation"
[8]: https://docs.astral.sh/uv/getting-started/features/?utm_source=chatgpt.com "Features | uv - Astral Docs"
[9]: https://docs.astral.sh/ruff/configuration/ "Configuring Ruff | Ruff"
[10]: https://docs.astral.sh/ty/reference/cli/?utm_source=chatgpt.com "CLI | ty - Astral Docs"
[11]: https://docs.astral.sh/uv/guides/integration/github/?utm_source=chatgpt.com "Using uv in GitHub Actions - Astral Docs"
[12]: https://docs.astral.sh/ruff/rules/run-process-in-async-function/?utm_source=chatgpt.com "run-process-in-async-function (ASYNC221) | Ruff - Astral Docs"
[13]: https://docs.astral.sh/ty/reference/configuration/ "Configuration | ty"
[14]: https://docs.astral.sh/uv/guides/integration/github/ "Using uv in GitHub Actions | uv"
[15]: https://github.com/actions/setup-python?utm_source=chatgpt.com "actions/setup-python: Set up your ..."
[16]: https://docs.astral.sh/uv/concepts/cache/?utm_source=chatgpt.com "Caching | uv - Astral Docs"

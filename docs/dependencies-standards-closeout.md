# Dependency and standards update — 2026-10-02

This update adopts the live Python Code Standards revision 2026-10-02 and refreshes all
direct dependencies and their compatible transitive dependencies from PyPI. The supported
Python range is 3.12–3.14. The local interpreter is 3.12.14 and uv is pinned to 0.12.18.

## Dependency baseline

| Dependency | Locked version |
| --- | --- |
| setuptools | 84.0.0 |
| pydantic | 2.13.5 |
| xxhash | 4.0.1 |
| piccolo | 1.36.0 |
| jsonschema | 4.26.0 |
| typer | 0.26.8 |
| rich | 15.0.0 |
| flet, flet-desktop, flet-web | 1.0.3 |
| PyYAML | 6.0.3 |
| httpx | 0.28.1 |
| pytest | 9.1.1 |
| pytest-cov | 7.1.0 |
| ruff | 0.16.10 |
| ty | 0.0.84 |
| pytest-asyncio | 1.4.0 |
| lancedb | 0.39.0 |
| docling | 2.132.0 |
| sentence-transformers | 6.1.0 |
| torch | 2.14.1 |
| numpy | 2.5.3 |

The lock resolves 170 packages across supported environments. HTTPX is declared as a runtime
dependency because application imports use it directly. Flet's desktop and web extras are
explicit so both supported interfaces have their runtime packages.

Seven installed releases remain below the newest PyPI release because their upstream
dependencies constrain compatibility:

| Release | Upstream constraint |
| --- | --- |
| typer 0.26.8 | Docling slim/core require `<0.27.0` |
| huggingface-hub 1.33.0 | Sentence Transformers, Tokenizers and Docling require `<2` |
| websockets 16.1.1 | Docling slim requires `<17.0` |
| semchunk 3.2.5 | Docling core's chunking extras require `<4.0.0` |
| mpmath 1.3.0 | SymPy requires `<1.4` |
| antlr4-python3-runtime 4.9.3 | OmegaConf requires `==4.9.*` |
| pydantic-core 2.46.5 | Pydantic requires this exact release |

These constraints are preserved in the resolver; no incompatible override or additional
package index was introduced.

## Correctness and enforcement

- Both LanceDB indexes distinguish a catalog-confirmed missing table from storage failure.
  Corrupt tables and failed catalog/drop operations propagate their errors. Real temporary
  corrupted-manifest regressions failed before the fix and pass afterward.
- Search and Query abstract expansion updates Flet 1's `TextButton.content`. Interaction
  regressions check both the displayed label and abstract visibility.
- Production and test type contracts are checked without the former UI exclusions or
  blanket test and optional-import diagnostic suppressions. Read-only interfaces and typed
  test fixtures preserve behavior while exposing incorrect contracts.
- Docling's format options, Sentence Transformers' dimension API, and Piccolo engine/column
  mappings match their updated libraries.
- Remaining text reads/writes use explicit UTF-8. The scoring threshold annotation includes
  the already supported `None` value used to disable the threshold in evaluation fixtures.
- Built distributions include the default configuration file. Clean-install checks exercise
  imports, CLI entry points and default configuration loading outside the checkout.
- The hash-bound format checker retains archive digest/exception checks and scans text
  files without treating unrelated binary screenshots as text.

The shared gate is `bash scripts/verify.sh`. It uses locked dependencies with the `dev`,
`infra` and `research` groups, Ruff format/lint checks, ty, archive format checks and pytest.
CI applies the same gate to every supported Python minor, provisions Docling PDF models
before offline tests, verifies both distributions, and pins its actions to reviewed commit
SHAs with a read-only token.

## Verification

The complete offline test suite passes on every supported Python minor:

| Interpreter | Result | Combined coverage |
| --- | --- | --- |
| Python 3.12.14 | 2,775 passed, 2 skipped | 92.3790% |
| Python 3.13.13 | 2,775 passed, 2 skipped | 92.3790% |
| Python 3.14.8 | 2,775 passed, 2 skipped | 92.3745% |

All runs exceed the 91.90% combined coverage requirement. The Python 3.12 run
also covers NSQD at 92.7223%, above its 90% floor. The final matrix includes the
approved Operator F typing and historical-binding changes. Its evidence is
`verify-oracle-3.12.14.log`, `pytest-oracle-3.13.13.log`,
`pytest-oracle-3.14.8.log`, and their `coverage-oracle-*.json` files under
`output/dependencies-standards-final/`. All three processes exited successfully.
Earlier runner attempts used an unsuitable temporary root and are superseded.

Ruff lint and formatting, the locked dependency check, the hash-bound formatting
inventory, and patch whitespace checks pass. The reusable gate sets both model
offline flags itself. Final wheel and sdist builds succeed; the wheel contains
the packaged configuration defaults and the current UTF-8 artifact writers.
Wheel and sdist-rebuilt wheel installation smoke tests passed outside the checkout.

The shared standards gate now passes, including `ty` with zero diagnostics. The
[revision-3 proposal](../.omo/proposals/operator-f-type-binding-2026-10-02.md) was
approved by the [independent oracle](../.omo/evidence/operator-f-proposal-oracle-round-3.md)
after the first review identified the archive destination restriction and a later
focused run found a second historical source-hash assertion. The implemented
two-line patch imports `TrackId` and annotates the metric test helper accordingly.
Both historical checks bind the original bytes through
`tests/fixtures/source-history/nsqd/operator-f/redundancy-semantics-2026-09-12.py.txt`,
whose preserved SHA-256 is
`3b369b478ccdc2f04cc49607563d13d8b5a4341b9d9927079e09c81baba8e688`.
The changed live test's SHA-256 is
`862128854feedeaec5a3b842038c7fbb5bd3b076cbc10ee4260309b5202cdee9`.
The separate current-source validator checks all 18
live source bindings and retains the formula, trust, scope, and false-authority
requirements.

The validated maintenance packet is published under
`output/operator-f-typing-binding/20261003T024620Z/`; its packet digest is
`8e672b4a46fd82d77ab2358f4b5d4c067072a81083e50e6773bae7f7daf832ea`.
It remains `review_pending` and `report_only`, with absent trust and all authority
flags false. Historical review seals confer no approval on this maintenance
report. All 370 archive files and all 19 previously staged blobs retain their
exact bytes; no archive files were added.

The 31 new validator cases cover current and historical source integrity and
reject resealed semantic tampering, corrupted snapshots or source files, wrong
bindings, and detached seals. The full focused suite passes 115 tests, including
in a clean copy without `.omo/` or generated output. The published packet also
passes the validator against the actual checkout. Implementation details and
red/green receipts are in the
[typing resolution ledger](../.omo/evidence/operator-f-typing-resolution-2026-10-03/README.md).

Exact matrix logs, coverage JSON, packaging, and proposed-fix checks are under
`output/dependencies-standards-final/`. Browser QA exercised all 18 routes at
two sizes (36 renders), and both browser and native macOS Search/Query controls
completed collapsed, expanded, and recollapsed states without rendering errors.

Completed focused evidence includes 32 LanceDB tests, 202 NSQD tests, 99 UI tests, the real
Docling PDF conversion with network downloads disabled, and wheel configuration loading
from a clean environment outside the checkout.

## Provenance

All 36 newly named lockfile releases were checked against exact-version PyPI artifact
hashes. Sixteen conditional NVIDIA dependencies were checked through PEP 658 metadata
hashes and package identity. Fifteen publish license metadata; the `cuda-toolkit` 13.0.3.0
metapackage contains only metadata and no packaged license text. The vendor publishes
[CUDA 13.0.3 terms](https://docs.nvidia.com/cuda/archive/13.0.3/eula/index.html) separately.
These conditional CUDA packages are not installed in the macOS verification environments.

Detailed local evidence is recorded under `.omo/evidence/` in the dependency backend/UI
reports and the `ui-compatibility` and `verification-gate-2026-10-02` directories. Temporary
databases and installations were used for destructive corruption and packaging checks.

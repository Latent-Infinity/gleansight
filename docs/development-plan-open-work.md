# Development Plan: Remaining Platform Closeout

**Guide Version**: 2.0
**Mode**: Vertical-Slice
**Plan Type**: Existing-System Feature
**Planning Horizon**: Rolling-Wave (V0, V0B, V0A, V1, V2, and V3 expanded; V6–V7 carry full phase fields plus task lists)
**Plan Set**: gleansight
**Builds On**: `docs/development-plan.md` (layer-based v1, delivered) and `docs/development-plan-rag-feature.md` (Phase 10, superseded) as of 2026-08-18
**Inherited Facts**: all `Active` facts in `docs/fact-ledger.md` as of plan creation — protected, not re-derived. At first emission every row is still `Proposed`.
**Supersedes**: remaining unchecked items in `docs/development-plan.md` Phases 0–9 (except corpus synthesis, which is out of this closeout)
**PRD Trace**: `docs/project-design.md` v0.9 (Draft). No stable requirement IDs; inferred criteria use `LOCAL-*`.
**Real Data Policy**: Approved redacted fixtures under `tests/fixtures/approved/` plus system-produced records created through public use-cases. Inherited inline fakes are quarantined and may not bind new facts.
**Generated Data Authorization**: `None`
**Provider Policy**: External services stay behind existing ports in `src/papers/app/ports.py`. Domain and use-case modules must not import provider SDKs.
**Fact Policy**: Tier-1 facts live in `docs/fact-ledger.md`. Semantics change only via Fact Change tasks.
**Data & Provider Readiness Summary**: V0A approved DATA-01a/b/c, V1 hybrid search is complete, V2 atomic import is complete, V3 project-analysis filters plus force characterization are complete, V6 converter/log/startup evidence is bound, and V7 publishes ADRs, workflows, and ledger links. EV-01 asserts the full fused order and scores, not a single winner. Gitignored `data/blobs/md/` is not the approved fixture set. Protected/timeout/OOM convert classes remain unclaimed.
**Slice Ordering Rationale**: data/provider readiness → architectural risk → user value. V0 makes the four-command quality gate green with no ratchet. V0B adds forward-only migrations and a job CHECK, including table-rebuild data/index preservation. V0A acquires three approved papers. V1 binds hybrid search with a non-symmetric one-based RRF oracle. V2 adds an atomic import **port** (not a wrapper around `run_sync()`). V3 adds project-analysis filters (filters may use a different prompt version) and characterizes force. V6 and V7 close operability and docs. Corpus synthesis is out of this plan.
**Repos in Scope**: this repository only.
**Outstanding Blockers / Human Decisions**: V0A approved DATA-01a/b/c. **This closeout plan (V0–V3, V6–V7) is complete.** Product decisions V0.4/0.5/0.6 and V0A.5 (three papers) remain recorded below. Gitignored `data/db` / `data/blobs/md` are still not the approved fixture set. NSQD N1–N10 including N6 default paper-runtime composition are done. DATA-NSQD-04 is acquired. Approved DATA-NSQD-03 remains pending (`docs/development-plan-ns-qd.md`).

**Coverage baseline (legacy)**: 91.90% **combined** coverage on `src` excluding `src/papers/ui/*` (`525 passed, 1 skipped`, 2026-08-17). That is the pytest-cov `Cover` column (lines+branches mixed), not a branch-only percentage. No overall regression. Changed/new-code floors below are the same combined metric.

**Repository-standard quality gate** (every code-changing phase's `Verification Command`):

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

**Decisions recorded (2026-08-18):**

| ID | Choice | Binding |
|----|--------|---------|
| V0.4 | **B** — leave landed synthesis experimental; do not expand it here | V4–V5 removed. UI/CLI stay. Future work is a separate authorized v1.1 plan. |
| V0.5 | **A** — accept NavigationRail and cards | No UI chrome rewrite in this plan. |
| V0.6 | **Narrowed B** — migration baseline + forward-only upgrades + job CHECK + upgrade test | Phase V0B. Do not rewrite persistence. |
| V0A.5 | Three approved papers | Kept at three. Symmetric A/C/B + B/C/A does **not** make C win; oracle is the full fused order (see V0A ranking intent). |
| RRF indexing | **One-based** (`rank` starts at 1) | Correct `compute_rrf_scores`. Zero-based is not compatibility policy. |
| EV-01 oracle | Non-symmetric lists; assert complete order **and** scores | FTS A,C,B and vector B,A,C → fused A, B, C. |
| V2 atomicity | **Atomic import port** (architecture 1) | Piccolo implements one transactional write. Not a helper around existing `run_sync()` methods. |
| Quality gate | No ratchet | V0.11 must make the four commands exit 0. |
| EV-08 | Preserve `ConverterResult` | Adapter returns codes; it does not raise `PipelineError` for convert failures. |

### Phase close (normative)

Every Migration, Capability, Hardening, and Documentation phase that introduces or strengthens facts ends with this sequence. Support-only foundation tasks that add no facts skip steps 3–4.

1. Run each new or rebound evidence command; it must exit 0.
2. Set those Evidence Index rows `Lifecycle` to `Required`.
3. Set the corresponding Fact Ledger rows `Lifecycle` from `Proposed` to `Active`.
4. `uv run pytest tests/support/test_fact_surface.py -q --no-cov` must fail if:
   - a `Required` evidence path is missing, or
   - a fact whose listed evidence is all `Required` is still `Proposed`, or
   - an `Active` fact has no `Required` evidence.

Later phases that protect “all Active facts” mean rows in this `Active` state.

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-08-18 | Initial emission. |
| 1.1.0 | 2026-08-18 | Apply review: synthesis B (drop V4–V5); cosmetic UI A; narrowed migrations as V0B; three fixtures; one-based RRF; ConverterResult facts; full quality gate in V0; rewrite V0.3/V0.8; V2 atomicity; expand V3; split V6 converter claims. |
| 1.2.0 | 2026-08-18 | Fix EV-01 oracle; atomic import port; drop quality ratchet; pytest-owned secret scan; evidence Available From; migration rebuild completeness; coverage enforcement split; V3 filter prompt-version + `_parse_constraints`; ledger attach wording; V7 command checks. |
| 1.3.0 | 2026-08-18 | Correct RRF 8-decimal scores and V1 first-hit; FTS uses title/abstract records; fact Proposed→Active on phase close; immediate transactions + in-txn CAS; jobs rebuild order + sqlite_schema; combined coverage; V3.0 EV-02b; V6.1 characterization; V0A blocker. |
| 1.3.1 | 2026-08-18 | Close V0: four-command gate green; `fail_under` 91.90; fact/support/fixture scaffolding; import-boundary scanner. |
| 1.3.2 | 2026-08-19 | Close V0B: forward-only `schema_migrations` runner; jobs CHECK; EV-11/EV-12 Required. |
| 1.3.3 | 2026-08-19 | Close V0A: three convert-path papers + manifest; secret-scan gate. FTS query `optimization algorithm`. |
| 1.3.4 | 2026-08-19 | Close V1: EV-01 hybrid FTS+vector one-based RRF on DATA-01a/b/c. |
| 1.3.5 | 2026-08-20 | Close V2: atomic candidate import with project/tag attachments; idempotent re-import; CLI `--project`/`--tag`. |
| 1.3.6 | 2026-08-20 | Reconcile V2 task acceptance boxes, readiness summary, validation ownership, and project-register metadata after review. |
| 1.3.7 | 2026-08-20 | Harden V2: in-transaction target validation, atomic stale-reference cleanup on paper deletion, stable import conflicts, bounded CLI errors, and explicit fallback rejection. |
| 1.3.8 | 2026-08-20 | Close V3: AnalyzeProject extraction-filter algebra, force-new-run characterization, and `analyze-project` CLI. |
| 1.3.9 | 2026-08-20 | Close V6: bind converter result codes, provenance-safe corrupt-PDF recovery, job log context, and secret-safe missing-dep startup. |
| 1.3.10 | 2026-08-21 | Close V7: ADRs, operator workflows, README ledger links, and EV-13 docs/CLI integrity tests. |

---

## Plan Compliance Matrix

| Invariant | Evidence | Status | Blocked Phases | Resolution Task |
|-----------|----------|--------|----------------|-----------------|
| PRD traceability | Fact Ledger + task `PRD Trace` | Pass | — | — |
| Real-data only | Real Data Manifest; V0A before V1 | Pass | — | — |
| Provider replaceability | Provider Boundary Matrix | Pass | — | — |
| Vertical slicing | V1–V3 name a demo command and a Tier-1 fact | Pass | — | — |
| Fact coverage | Every in-scope `LOCAL-AC-*` has ≥1 Tier-1 fact | Pass | — | — |
| No unauthorized synthetic data | `Generated Data Authorization: None`; INH-01 quarantined | Pass | — | — |
| Evidence binding | Evidence Index runnable commands | Pass | — | — |
| Phase roles | Every phase declares `Role` | Pass | — | — |
| TDD pairing | Expanded Implement tasks have a preceding Test task, except characterization EV-04 and EV-08 | Pass | — | — |
| Stable phases | Full quality gate as `Verification Command` on every code-changing phase | Pass | — | — |
| Design non-goal vs synthesis | V0.4 = B; V4–V5 removed | Pass | — | — |

---

## Fact Ledger

Project register: `docs/fact-ledger.md`. This plan introduces:

| Fact ID | Statement (Given / When / Then) | Applies When | Kind | Requirement | Owner | Lifecycle | Evidence |
|---------|--------------------------------|--------------|------|-------------|-------|-----------|----------|
| SEARCH.HYBRID.FTS_VECTOR_RRF.v1 | Given a non-empty query and the three approved paper records, when the user searches papers, then FTS runs on title+abstract, vectors on markdown, and the fused order and one-based scores match A=0.03252247, B=0.03226646, C=0.03200205 | Default paper search | Behavior | LOCAL-AC-HYBRID-SEARCH (`project-design.md` §3.1, §10.2.1) | product | Active | EV-01 |
| DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1 | Given an unimported candidate and existing project/tag IDs, when import is requested with those IDs, then either the whole import (paper, attachments, download job, candidate mark) commits or nothing is written | Import from discovery | Behavior | LOCAL-AC-IMPORT-TAXONOMY (`project-design.md` §15) | product | Active | EV-02, EV-02b |
| DISCOVERY.IMPORT.IDEMPOTENT_ATTACH.v1 | Given a candidate already imported to paper P, when import is requested again with project/tag IDs, then P is reused, missing attachments are added, already-present attachments are no-ops, and no second download job is enqueued | Re-import of an imported candidate | Behavior | LOCAL-AC-IMPORT-TAXONOMY | product | Active | EV-02c |
| ANALYSIS.PROJECT.APPLY_FILTERS.v1 | Given a project and extraction filters, when project analysis is requested, then only members that survive label membership and the filter algebra receive new analysis runs | Analyze-project path | Behavior | LOCAL-AC-ANALYZE-PROJECT-FILTERS (`project-design.md` §15, §10.4) | product | Active | EV-03 |
| ANALYSIS.RUN.FORCE_NEW.v1 | Given a successful analysis run for the idempotency key, when analysis is requested with force, then a new run and job are created and the prior run is left unchanged | `force=true` | Behavior | LOCAL-AC-ANALYZE-FORCE (`project-design.md` §9.2) | product | Active | EV-04 |
| SCHEMA.JOB.INTEGRITY_CHECK.v1 | Given a jobs row, when it is inserted, then SQLite rejects it unless it satisfies the design §5.2 job integrity CHECK | Any schema after migration 002 | Data Contract | LOCAL-AC-JOB-CHECK (`project-design.md` §5.2 L) | product | Active | EV-11 |
| SCHEMA.MIGRATE.FORWARD.v1 | Given a database created at the previous baseline, when the app starts, then forward-only migrations apply and the job CHECK is present | Existing user DB | Data Contract | LOCAL-AC-MIGRATIONS | product | Active | EV-12 |
| ADAPTER.CONVERT.RESULT_CODES.v1 | Given a convert attempt that yields empty markdown or a converter exception, when `Converter.pdf_to_markdown` returns, then the value is a `ConverterResult` with `ok=False` and `error_code` of `EMPTY_OUTPUT` or `CONVERSION_FAILED` respectively | Converter adapter | Behavior | LOCAL-AC-CONVERT-RESULT (`project-design.md` §9.4, port `ConverterResult`) | product | Active | EV-08 |
| HANDLER.CONVERT.CORRUPT_PDF.v1 | Given a PDF that fails the handler validity check, when convert runs with recoverable source provenance, then the blob is removed, the job fails with `CORRUPT_PDF`, and one re-download is enqueued with that provenance; without provenance, the blob is retained and no doomed download is queued | Convert handler, before the adapter | Behavior | LOCAL-AC-CONVERT-CORRUPT (`project-design.md` §9.4) | product | Active | EV-08b |
| OBS.LOG.JOB_CONTEXT.v1 | Given a job state transition, when the runner logs the event, then the record includes timestamp, job_id, job_type, status_from, status_to, paper_id, and run_id | Job runner | Operational/SLO | LOCAL-NFR-LOGGING (`project-design.md` §12.2) | product | Active | EV-09 |
| CFG.STARTUP.MISSING_DEP.v1 | Given a required optional dependency is not importable, when the composition root starts, then startup fails with `ConfigurationError` naming the module | Process start | Operational/SLO | LOCAL-NFR-FAILFAST (`project-design.md` §13) | product | Active | EV-10 |

Not in this plan (do not bind): `SYNTH.*`. Landed synthesis UI/CLI remain experimental.

---

## Evidence Index

`Available From` is the phase whose close makes the path **Required**. The V0.3 checker may tolerate a missing path only while `Lifecycle` is `Pending: <phase>`. The closing phase’s last task flips those rows to `Required`. After that flip, a missing path fails the checker.

| Evidence ID | Facts | Type | Path / Command | Available From | Lifecycle | Oracle & Fixture Deps | Data Version | Environment | Last Result |
|-------------|-------|------|----------------|----------------|-----------|-----------------------|--------------|-------------|-------------|
| EV-01 | SEARCH.HYBRID.FTS_VECTOR_RRF.v1 | test | `uv run pytest tests/facts/test_hybrid_search.py -q --no-cov` | V1 | Required | title+abstract FTS; markdown embed; scores 0.03252247/0.03226646/0.03200205 | DATA-01a/b/c | hermetic | pass 2026-08-19 |
| EV-02 | DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1 | test | `uv run pytest tests/facts/test_import_taxonomy.py -q --no-cov` | V2 | Required | **real Piccolo** stores; injected in-transaction failure | none | hermetic | pass 2026-08-20 |
| EV-02b | DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1 | test | `uv run pytest tests/facts/test_import_taxonomy_cli.py -q --no-cov` | V2 | Required | CLI ID strings | none | hermetic | pass 2026-08-20 |
| EV-02c | DISCOVERY.IMPORT.IDEMPOTENT_ATTACH.v1 | test | `uv run pytest tests/facts/test_import_idempotent_attach.py -q --no-cov` | V2 | Required | prior import via use-case + Piccolo | none | hermetic | pass 2026-08-20 |
| EV-03 | ANALYSIS.PROJECT.APPLY_FILTERS.v1 | test | `uv run pytest tests/facts/test_analyze_project_filters.py -q --no-cov` | V3 | Required | members + extractions via use-cases | none | hermetic | pass 2026-08-20 |
| EV-04 | ANALYSIS.RUN.FORCE_NEW.v1 | characterization test | `uv run pytest tests/facts/test_analyze_force.py -q --no-cov` | V3 | Required | existing `RunAnalysisUseCase` | none | hermetic | pass 2026-08-20 |
| EV-08 | ADAPTER.CONVERT.RESULT_CODES.v1 | test | `uv run pytest tests/facts/test_convert_result_codes.py -q --no-cov` | V6 | Required | empty-output mutation; converter exception | none | hermetic | pass 2026-08-20 |
| EV-08b | HANDLER.CONVERT.CORRUPT_PDF.v1 | test | `uv run pytest tests/facts/test_convert_corrupt_pdf.py -q --no-cov` | V6 | Required | invalid PDF header mutation; recovery provenance | none | hermetic | pass 2026-08-20 |
| EV-09 | OBS.LOG.JOB_CONTEXT.v1 | test | `uv run pytest tests/facts/test_job_log_context.py -q --no-cov` | V6 | Required | log capture | none | hermetic | pass 2026-08-20 |
| EV-10 | CFG.STARTUP.MISSING_DEP.v1 | test | `uv run pytest tests/facts/test_startup_missing_dep.py -q --no-cov` | V6 | Required | standalone fail-fast + bounded CLI startup | none | hermetic | pass 2026-08-20 |
| EV-11 | SCHEMA.JOB.INTEGRITY_CHECK.v1 | test | `uv run pytest tests/facts/test_job_integrity_check.py -q --no-cov` | V0B | Required | SQLite | none | hermetic | pass 2026-08-19 |
| EV-12 | SCHEMA.MIGRATE.FORWARD.v1 | test | `uv run pytest tests/facts/test_schema_forward_migrate.py -q --no-cov` | V0B | Required | previous-baseline fixture DB | none | hermetic | pass 2026-08-19 |
| EV-13 | (docs integrity) | test | `uv run pytest tests/support/test_docs_cli_commands.py tests/support/test_no_src_todo.py -q --no-cov` | V7 | Required | workflow markdown; `src/` | none | hermetic | pass 2026-08-21 |

---

## Real Data Manifest

| Data ID | Source / System of Record | Owner | Access Path | Approval Status | Sensitivity | Fixture/Capture Path | Refresh Rule | Used By |
|---------|---------------------------|-------|-------------|-----------------|-------------|----------------------|--------------|---------|
| DATA-01a | Real paper row + convert-path markdown (role A) | product | gitignored `data/db` + `data/blobs/md/` | **Approved** | copyrighted scholarly text | `tests/fixtures/approved/papers/a.md` + `manifest.toml` (`paper-30`) | converter or metadata change | EV-01 |
| DATA-01b | Real paper row + convert-path markdown (role B) | product | same | **Approved** | copyrighted scholarly text | `tests/fixtures/approved/papers/b.md` + `manifest.toml` (`paper-10`) | converter or metadata change | EV-01 |
| DATA-01c | Real paper row + convert-path markdown (role C) | product | same | **Approved** | copyrighted scholarly text | `tests/fixtures/approved/papers/c.md` + `manifest.toml` (`paper-20`) | converter or metadata change | EV-01 |
| INH-01 | Inline fake embedder/LLM/S2 payloads in existing unit tests | engineering | `tests/**` | Unapproved — inherited | n/a | inline; do not copy | n/a | must not bind new facts |

---

## Provider Boundary Matrix

| Provider | Port/Protocol | Adapter(s) | Domain Types Exposed | Provider Types Contained In | Contract Test | Swap Impact |
|----------|---------------|------------|----------------------|-----------------------------|---------------|-------------|
| Semantic Scholar | `ScholarClient` | `scholar_s2/adapter.py` | candidate dicts | httpx, S2 JSON | `tests/infra/scholar_s2/` | new adapter + config |
| Docling | `Converter` | `converter_docling/adapter.py` | `ConverterResult` | Docling types | `tests/infra/converter_docling/` | new adapter |
| sentence-transformers | `Embedder` | `embedder_st/adapter.py` | `list[float]` | ST objects | `tests/infra/embedder_st/` | new adapter + model setting |
| OpenAI-compatible LLM | `LLMClient` | `llm_openai_compat/client.py` | `LLMResponse` | HTTP client | `tests/infra/llm_openai_compat/` | new adapter + profile |
| LanceDB | `VectorIndex` | `lancedb/index.py` | `(paper_id, score)` | LanceDB table | `tests/infra/lancedb/` | new adapter + path |
| Piccolo/SQLite | store ports | `piccolo/` | domain dicts | Piccolo tables | `tests/infra/piccolo/` | new store adapters |
| Filesystem | `BlobStore` | `blobs_fs/store.py` | paths + xxh64 | OS files | `tests/infra/blobs_fs/` | new blob adapter |

---

## Out of scope (this plan)

- NS-QD **product evolution** (not this closeout’s jobs) — `docs/product-gleansight.md` + `docs/development-plan-ns-qd.md`. This closeout still finishes the evidence layer.
- Corpus synthesis productization (design §3.2 / §17.5). Landed `papers ask` / Synthesis UI stay as experimental. See *Deferred synthesis contract* below.
- Cosmetic UI rewrites (drawer vs rail, cards vs tables)
- `PROTECTED_PDF`, `CONVERTER_TIMEOUT`, and `CONVERTER_OOM` adapter coverage (no approved failure captures; do not invent them)
- Wholesale migration of existing tests into `tests/facts/`
- Live Semantic Scholar E2E
- Retroactive whole-repo 95% coverage
- Removing `src/papers/ui/*` from the coverage omit list (no Tier-1 UI fact remains in this plan)

### Deferred synthesis contract (for a future authorized v1.1 plan)

If product later authorizes synthesis, that plan must **not** filter a global top-N after retrieval. Relevant project papers can miss the candidate set (`synthesis.py` currently queries the global vector index then intersects). Required contract: restrict candidate IDs **before** RRF and top-N (scoped FTS and scoped vector query, or equivalent). Post-retrieval intersection of a global top-N is incorrect.

---

## Phase V0: Foundation — Baseline, machinery, quality gate

**Role:** Foundation
**Target Capability Slice:** Enables V0B–V7
**Facts Introduced:** (none)
**Facts Strengthened:** (none)
**Facts Protected:** (none)
**Verification Command:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

**Demo/Validation Command:** `test -d tests/facts && test -d tests/support && test -d tests/fixtures/approved`
**Observable Outcome:** Fact/support/fixture directories exist; architecture scanner is characterized; the four-command quality gate is green; recorded decisions are in the header.
**Rollback Notes:** Revert the phase commit. No user-data changes.
**Executed By:**

### Task V0.1: Re-verify inherited suite

**Type:** Test

**PRD Trace:** Technical Enabler: do not start from assumed-green state.

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** N/A — phase fails if the inherited suite is red.

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** None

**Description:**
Run `uv run pytest -q` and record coverage as the starting baseline.

**Acceptance Criteria:**
- [x] `uv run pytest -q` exits 0
- [x] Coverage is ≥ 91.90% or a regression is recorded with owner approval
- [x] Coverage policy satisfied

---

### Task V0.2: Document existing-system baseline

**Type:** Document

**PRD Trace:** Technical Enabler: Existing-System Feature foundation is a baseline assessment.

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V0.1

**Description:**
Cite composition root, ports, quality gate, coverage baseline, `.gitignore`, `docs/library-standards.md`, and the already-running walking skeleton.

**Acceptance Criteria:**
- [x] `docs/baseline.md` names `src/papers/app/composition_root.py`, `src/papers/app/ports.py`, the four-command gate, coverage 91.90% excluding UI
- [x] Walking skeleton cited: `uv run pytest tests/app/use_cases/test_pipeline.py tests/app/use_cases/test_search.py -q` and `uv run python -m papers.cli --help`
- [x] `.gitignore` and `docs/library-standards.md` cited as already done
- [x] Mutation-testing tool recorded as: none
- [x] Coverage policy satisfied (N/A — documentation)

**Files Affected (optional):**
- `docs/baseline.md` (create)

---

### Task V0.3: Add fact, support, and fixture infrastructure

**Type:** Implement

**PRD Trace:** Technical Enabler: durable evidence layout.

**Makes Green:** N/A (scaffolding)

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V0.2

**Facts Protected:** none

**Description:**
`docs/fact-ledger.md` and `docs/evidence-index.md` already exist. Create `tests/facts/`, `tests/support/`, `tests/fixtures/approved/papers/`, un-ignore that approved path in `.gitignore`, and a checker that reads the Evidence Index `Lifecycle` column.

**Checker rules (normative):**
- Evidence `Lifecycle: Required` → the command path must exist or the checker fails
- Evidence `Lifecycle: Pending: <phase>` → missing path is allowed
- After phase close, evidence becomes `Required` **and** the facts those rows bind become `Active`
- Checker also fails if a fact with all-`Required` evidence is still `Proposed`, or an `Active` fact has no `Required` evidence

**Acceptance Criteria:**
- [x] `tests/facts/` and `tests/support/` exist
- [x] `tests/fixtures/approved/papers/` exists
- [x] `.gitignore` ignores raw data and un-ignores `tests/fixtures/approved/`
- [x] Checker implements evidence pending/required **and** fact Proposed/Active coupling
- [x] Ledger files are not recreated or overwritten
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/__init__.py` (create)
- `tests/support/test_fact_surface.py` (create)
- `tests/fixtures/approved/papers/.gitkeep` (create)
- `.gitignore` (modify)

---

### Task V0.4: Record decision — synthesis stays experimental

**Type:** Document

**PRD Trace:** LOCAL-AC-SYNTHESIS (`project-design.md` §3.2, §17.5)

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V0.3

**Description:**
Product chose **B** (2026-08-18): do not productize corpus synthesis in this closeout. Leave landed UI/CLI in place. Do not add V4–V5.

**Acceptance Criteria:**
- [x] This plan's header records V0.4 = B
- [x] No synthesis implementation tasks remain in this file
- [x] Coverage policy satisfied (N/A — documentation)

---

### Task V0.5: Record decision — accept current UI chrome

**Type:** Document

**PRD Trace:** Technical Enabler: close stale cosmetic UI criteria.

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V0.3

**Description:**
Product chose **A**: NavigationRail (`src/papers/ui/app.py`) and card results are accepted.

**Acceptance Criteria:**
- [x] Header records V0.5 = A
- [x] No nav/widget rewrite tasks in this plan
- [x] Coverage policy satisfied (N/A — documentation)

---

### Task V0.6: Record decision — forward-only migrations

**Type:** Document

**PRD Trace:** LOCAL-AC-MIGRATIONS

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** None

**Provider Boundary:** Piccolo/SQLite

**Depends On:** V0.3

**Description:**
Product chose **narrowed B**: add a migration baseline and forward-only runner, plus the job integrity CHECK and an upgrade test. Do not rewrite stores. Implementation is Phase V0B.

**Acceptance Criteria:**
- [x] Header records V0.6 = narrowed B
- [x] V0B exists with EV-11 and EV-12
- [x] Coverage policy satisfied (N/A — documentation)

---

### Task V0.7: Quarantine inherited synthetic fixtures

**Type:** Document

**PRD Trace:** Technical Enabler: Data Fidelity Policy.

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** INH-01

**Provider Boundary:** N/A

**Depends On:** V0.3

**Description:**
Keep INH-01 listed as Unapproved — inherited. New facts must not bind to those payloads.

**Acceptance Criteria:**
- [x] INH-01 remains in the Real Data Manifest
- [x] `tests/facts/` does not copy inline fake scholarly records
- [x] Coverage policy satisfied (N/A — documentation)

---

### Task V0.8: Characterize the provider import-boundary scanner

**Type:** Architecture Test

**PRD Trace:** Technical Enabler: provider isolation must be mechanical.

**Fact / Evidence (Test tasks):** N/A (Tier 2)

**Expected Failure Signature:** When the scanner is pointed at a temporary tree that contains a domain module importing `lancedb`, it reports that leak. When pointed at the real `src/papers/domain` and `src/papers/app/use_cases`, it reports no leaks.

**Real Data Dependency:** None

**Provider Boundary:** all providers

**Depends On:** V0.3

**Description:**
The real tree is currently clean, so a failing-first test against production sources cannot honestly fail. Write a characterization: generate a temporary violating file, assert the scanner fails on it, then assert the scanner passes on the real tree.

**Acceptance Criteria:**
- [x] `uv run pytest tests/support/test_import_boundary.py -q` creates an isolated temp module that imports a provider SDK from a fake domain package and expects a scanner failure
- [x] The same test then scans the real domain and use-case trees and expects success
- [x] The test does not modify `src/`
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/support/test_import_boundary.py` (create)

---

### Task V0.9: Implement the import-boundary scanner

**Type:** Implement

**PRD Trace:** Technical Enabler: provider isolation.

**Makes Green:** V0.8 characterization (not a Tier-1 evidence ID)

**Real Data Dependency:** None

**Provider Boundary:** all providers

**Depends On:** V0.8

**Facts Protected:** none

**Description:**
Implement the scanner used by V0.8 (AST or module-walk). Forbidden imports in domain/use-case: `docling`, `lancedb`, `sentence_transformers`, `httpx`.

**Acceptance Criteria:**
- [x] V0.8 passes
- [x] Real tree stays clean; do not weaken the scanner if a leak appears — fix the leak
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/support/test_import_boundary.py` (modify)

---

### Task V0.11: Make the repository-standard quality gate green

**Type:** Implement

**PRD Trace:** Technical Enabler: every later phase uses this exact gate.

**Makes Green:** N/A (tooling)

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V0.1

**Facts Protected:** none

**Description:**
Bring `ruff format`, `ruff check`, and `ty check` to **zero** diagnostics. Prefer `ruff check --fix` for mechanical issues, then fix the rest. There is no ratchet and no “changed files only” rule. Also set `[tool.coverage.report] fail_under` to `91.90` so the overall floor is mechanical. Discovery plan phase NSQD-N0 lists this task as a hard prerequisite.

**Acceptance Criteria:**
- [x] `uv run ruff format --check .` exits 0
- [x] `uv run ruff check .` exits 0
- [x] `uv run ty check` exits 0
- [x] `uv run pytest -q` exits 0
- [x] `fail_under` is 91.90
- [x] No diagnostic baseline file, wrapper, or changed-file waiver

**Close note (2026-08-18):** 536 passed, 1 skipped, **91.91%** combined coverage. `ty` excludes `src/papers/ui` and `tests/ui` (Flet 0.80 stubs). Tests ignore `invalid-argument-type` for incomplete protocol doubles. Production non-UI `src/` is fully checked. Recorded in `docs/baseline.md`.

**Files Affected (optional):**
- various (format/lint)
- `pyproject.toml` (modify `fail_under`)

---

**Phase V0 Exit Criteria:**
- [x] Baseline documented
- [x] `tests/facts/`, `tests/support/`, `tests/fixtures/approved/` exist
- [x] Decisions V0.4–V0.6 recorded
- [x] Import-boundary characterization green
- [x] Quality gate green (all four commands exit 0)
- [x] **Stage changes for human review**

---

## Phase V0B: Migration — baseline and job integrity CHECK

Discovery-layer work (`docs/development-plan-ns-qd.md`) must not insert NS/QD job types into paper `jobs`. After this migrator exists, NS/QD uses **`nsqd_jobs`**. The CHECK below stays `discover|download|convert|embed|analyze` only.

**Role:** Migration
**Target Capability Slice:** Enables durable upgrades for all later slices
**Facts Introduced:** SCHEMA.JOB.INTEGRITY_CHECK.v1, SCHEMA.MIGRATE.FORWARD.v1
**Facts Strengthened:** (none)
**Facts Protected:** (none)
**Verification Command:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

**Demo/Validation Command:** `uv run pytest tests/facts/test_schema_forward_migrate.py tests/facts/test_job_integrity_check.py -q`
**Observable Outcome:** A previous-baseline SQLite file upgrades forward; illegal job rows are rejected by CHECK; existing legal rows and both job unique indexes survive the rebuild.
**Rollback Notes:** Revert the *code* commit. Opening an existing user database with the new runner applies an **irreversible** schema change (no down-migration). Operators who need a rollback must restore a file backup taken before first launch. Do not open a production DB with this build unless that backup exists.
**Executed By:**

### Task V0B.0: Re-verify V0

**Type:** Test

**PRD Trace:** Technical Enabler: re-verify inherited state.

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V0.11

**Description:**
Run the four-command quality gate before changing persistence.

**Acceptance Criteria:**
- [x] Quality gate exits 0
- [x] Coverage policy satisfied (no regression)

---

### Task V0B.1: Test job integrity CHECK and forward upgrade

**Type:** Test

**PRD Trace:** LOCAL-AC-JOB-CHECK, LOCAL-AC-MIGRATIONS

**Fact / Evidence (Test tasks):** SCHEMA.JOB.INTEGRITY_CHECK.v1, SCHEMA.MIGRATE.FORWARD.v1 → EV-11, EV-12

**Expected Failure Signature:** (1) Inserting `type='download'` with `paper_id` NULL succeeds — that is the red state. (2) Opening a pre-CHECK database does not add the CHECK — red.

**Real Data Dependency:** None (schema SQL only)

**Provider Boundary:** Piccolo/SQLite

**Depends On:** V0B.0

**Description:**
Build a previous-baseline fixture the way the app does today (`create_table` + `idx_jobs_unique_active_stage` + `idx_jobs_unique_analyze`, no CHECK), with at least one legal queued download and one analyze job. After migrate: CHECK exists; both indexes exist; those rows still exist with the same primary keys and payload; discover with null `paper_id` is allowed; download without `paper_id` is rejected; analyze without `run_id` is rejected.

Also assert: (1) if the copy is aborted mid-rebuild, the original `jobs` table and indexes remain; (2) if the old table contains a row that would fail the CHECK, migration fails, reports the row, and leaves the old table in place.

**Acceptance Criteria:**
- [x] Checks live at `tests/facts/test_job_integrity_check.py` and `tests/facts/test_schema_forward_migrate.py`
- [x] New checks fail with the stated signatures; rest of suite green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_job_integrity_check.py` (create)
- `tests/facts/test_schema_forward_migrate.py` (create)

---

### Task V0B.2: Implement forward-only migrations

**Type:** Implement

**PRD Trace:** LOCAL-AC-MIGRATIONS

**Makes Green:** EV-11, EV-12

**Real Data Dependency:** None

**Provider Boundary:** Piccolo/SQLite

**Depends On:** V0B.1

**Facts Protected:** none

**Description:**
Add a `schema_migrations` table and a forward-only runner invoked from `PiccoloDatabase.initialize_schema`. Migration `001_baseline` records the current implicit schema if no row exists (no rewrite of `create_table`). Migration `002_job_integrity_check` applies:

```sql
CHECK (
  (type = 'discover') OR
  (type IN ('download','convert','embed') AND paper_id IS NOT NULL) OR
  (type = 'analyze' AND paper_id IS NOT NULL AND run_id IS NOT NULL)
)
```

SQLite table rebuild is allowed for this one CHECK. Use **one** async `TransactionType.immediate` transaction and one `run_sync`. **Preflight** invalid rows *before* rebuild so `ConfigurationError` can name the offending `job_id`s. Query `sqlite_schema` for objects on `jobs`; recreate known indexes; if an unexpected index, trigger, or view exists, **reject** the migration with those names (do not silently drop them).

Safe order inside the transaction:

1. Create `new_jobs` (with the CHECK).
2. Copy rows.
3. Drop old `jobs`.
4. Rename `new_jobs` → `jobs`.
5. Recreate schema objects (`idx_jobs_unique_active_stage`, `idx_jobs_unique_analyze`, and any other expected objects from the preflight list).
6. Commit.

A failed copy must not drop the old table. Do not rewrite store classes. No down-migration.

**Acceptance Criteria:**
- [x] EV-11 and EV-12 green
- [x] Tests cover index preservation, row preservation, mid-rebuild abort, and invalid-row abort
- [x] Fresh databases and previous-baseline databases both end with 002 applied
- [x] Store method signatures unchanged
- [x] Quality gate green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `src/papers/infra/piccolo/migrations/` (create)
- `src/papers/infra/piccolo/database.py` (modify)

---

**Phase V0B Exit Criteria:**
- [x] Forward-only runner exists
- [x] Job integrity CHECK matches design §5.2
- [x] Upgrade from previous baseline is tested (rows, both job unique indexes, atomicity, invalid-row abort)
- [x] EV-11 and EV-12 Lifecycle set to Required
- [x] SCHEMA.JOB.INTEGRITY_CHECK.v1 and SCHEMA.MIGRATE.FORWARD.v1 set to Active
- [x] Persistence layer otherwise unchanged
- [x] Quality gate green
- [x] **Stage changes for human review**

---

## Phase V0A: Data Acquisition Gate — Three approved papers

**Role:** Data Gate
**Target Capability Slice:** V1
**Facts Introduced:** (none)
**Facts Strengthened:** (none)
**Facts Protected:** SCHEMA.JOB.INTEGRITY_CHECK.v1, SCHEMA.MIGRATE.FORWARD.v1
**Verification Command:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

Secret scan is **not** the raw `rg` command (`rg` exits 1 when clean). Authoritative gate: `uv run pytest tests/support/test_fixture_secret_scan.py -q`. Optional manual check after fixtures exist: `! rg --pcre2 -n -i -e '(api[_-]?key|secret|token|password)\s*[:=]\s*\S+' -e 'sk-[A-Za-z0-9]{10,}' -e 'BEGIN [A-Z ]*PRIVATE KEY' tests/fixtures/approved/`

**Demo/Validation Command:** `ls tests/fixtures/approved/papers && cat tests/fixtures/approved/manifest.toml`
**Observable Outcome:** Three minimized, approved paper-markdown files and a valid manifest; secret-scan command is clean.
**Rollback Notes:** Delete the three files and the manifest. No production data change.
**Executed By:**

### Manifest schema (normative)

`tests/fixtures/approved/manifest.toml` must parse as TOML and contain exactly these keys per fixture table `fixture.DATA-01a`, `fixture.DATA-01b`, `fixture.DATA-01c`. Each approved item is a **paper record**, not markdown alone. Production `papers_fts` indexes **title and abstract** (`PiccoloPaperStore.create_paper` / `PiccoloPaperFTS`), not converted markdown.

| Key | Type | Rule |
|-----|------|------|
| `id` | string | Matches the table suffix (`DATA-01a` …). This is the **role** (A/B/C), not the `paper_id` |
| `paper_id` | string | ID EV-01 will persist. The three IDs sorted lexicographically must **not** equal fused role order A,B,C (so a naive `paper_id` sort cannot pass EV-01) |
| `title` | string | Non-empty real title (redacted only for secrets). **This plus abstract is the FTS input** |
| `abstract` | string | Real abstract (may be shortened, not invented). FTS input with title |
| `markdown_path` | string | Relative to `tests/fixtures/approved/`; converted markdown for **embedding only** |
| `source_paper_id` | string | Real `paper_id` from the local convert path that produced the record |
| `source_kind` | string | Must be `convert-path-paper` |
| `redaction` | string | What was removed; must not say “rewritten” or “invented” |
| `owner` | string | `product` |
| `refresh_when` | string | Non-empty (e.g. `converter version change`) |

### Ranking intent for EV-01

Keep three papers. The earlier “FTS A,C,B / vector B,C,A ⇒ C wins” oracle is **false**:

- A = 1/61 + 1/63 = B = 1/63 + 1/61
- C = 2/62, which is *smaller* than A/B

Do **not** add a fourth fixture for this closeout. Use non-symmetric lists and assert the **complete fused order and scores**.

Normative lists (one-based, k=60):

| List | Order |
|------|-------|
| FTS | A, C, B |
| Vector | B, A, C |

| Paper | Ranks (FTS, vector) | Score |
|-------|---------------------|-------|
| A | 1, 2 | 1/61 + 1/62 = **0.03252247** |
| B | 3, 1 | 1/63 + 1/61 = **0.03226646** |
| C | 2, 3 | 1/62 + 1/63 = **0.03200205** |

Fused order: **A, B, C**.

Comparisons EV-01 must fail if they appear:

- FTS-only: A, C, B
- Vector-only: B, A, C
- Zero-based RRF on the same lists (different scores)
- Sort by `paper_id`

Winner-alone is not sufficient: vector-only also starts with a single paper, so the full order and scores are the oracle.

FTS order A,C,B must come from **title+abstract** via `PaperStore.create_paper` + `PapersFTS.search`, not from markdown. A fake embedder may realize vector order B,A,C using the approved **markdown** as embed input. Pick a query whose tokens appear in the three titles/abstracts so production FTS rank is A,C,B.

`paper_id` values are not the letters A/B/C. Example that sorts as B, C, A: A=`paper-30`, B=`paper-10`, C=`paper-20`.

### Task V0A.1: Re-verify V0B

**Type:** Test

**PRD Trace:** Technical Enabler: re-verify inherited state.

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V0B.2

**Description:**
Run the four-command quality gate.

**Acceptance Criteria:**
- [x] Quality gate exits 0
- [x] Coverage policy satisfied (no regression)

---

### Task V0A.2: Acquire three minimized convert-path fixtures

**Type:** Data Acquisition

**PRD Trace:** LOCAL-DATA-01

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** DATA-01a, DATA-01b, DATA-01c

**Provider Boundary:** `BlobStore` (source only)

**Depends On:** V0A.1

**Description:**
From the local convert path, take three real papers that have title, abstract, and markdown. Redact emails and personal identifiers. Do not invent titles, abstracts, or scholarly claims. Prefer records whose titles/abstracts can realize FTS order A,C,B for one query.

**Acceptance Criteria:**
- [x] Each role has markdown at `tests/fixtures/approved/papers/{a,b,c}.md` and title/abstract/paper_id in the manifest
- [x] Title and abstract are taken from the real paper row, not derived by summarizing the markdown
- [x] Markdown is a subset or redaction of real convert output
- [x] The three `paper_id` values sort lexicographically in an order other than role A,B,C
- [x] Coverage policy satisfied (N/A — data)

---

### Task V0A.3: Write the fixture manifest

**Type:** Document

**PRD Trace:** LOCAL-DATA-01

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** DATA-01a, DATA-01b, DATA-01c

**Provider Boundary:** N/A

**Depends On:** V0A.2

**Description:**
Write `tests/fixtures/approved/manifest.toml` per the schema above, including `paper_id`, `title`, `abstract`, and `markdown_path`.

**Acceptance Criteria:**
- [x] Manifest validates against the schema table
- [x] Markdown paths resolve
- [x] The three `paper_id` values do not sort as role order A,B,C
- [x] Coverage policy satisfied (N/A — documentation)

**Files Affected (optional):**
- `tests/fixtures/approved/manifest.toml` (create)

---

### Task V0A.4: Test manifest contract and secret scan

**Type:** Test

**PRD Trace:** LOCAL-DATA-01

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** Missing markdown, empty title/abstract, missing manifest key, `paper_id`s sorted as A,B,C, or a secret-scan regex hit.

**Real Data Dependency:** DATA-01a, DATA-01b, DATA-01c

**Provider Boundary:** N/A

**Depends On:** V0A.3

**Description:**
Assert three fixtures + valid manifest. Run the same regexes as the `rg` command in this phase's Verification Command; fail on any match.

**Acceptance Criteria:**
- [x] `uv run pytest tests/support/test_fixture_manifest.py -q` covers schema and presence
- [x] `uv run pytest tests/support/test_fixture_secret_scan.py -q` is the authoritative secret-scan gate (same patterns as the optional `! rg` check)
- [x] That pytest exits 0 on the approved fixtures
- [x] Rest of suite green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/support/test_fixture_manifest.py` (create)
- `tests/support/test_fixture_secret_scan.py` (create)

---

### Task V0A.5: Record decision — three papers required

**Type:** Document

**PRD Trace:** LOCAL-DATA-01

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** DATA-01a, DATA-01b, DATA-01c

**Provider Boundary:** N/A

**Depends On:** V0A.4

**Description:**
Product required three approved papers (2026-08-18). Two documents can tie under RRF. Approval is this recorded decision plus a green V0A.4.

**Acceptance Criteria:**
- [x] Three fixtures approved via V0A.4
- [x] Header records V0A.5 = three papers
- [x] Coverage policy satisfied (N/A — documentation)

---

**Phase V0A Exit Criteria:**
- [x] Three approved papers + valid manifest
- [x] Secret-scan command clean
- [x] No synthetic substitute
- [x] Quality gate green
- [x] **Stage changes for human review**

**Close note (2026-08-19):** Roles A/C/B are Frank-Wolfe / sequential-quadratic / photovoltaic convert-path papers. Fixture ids `paper-30` / `paper-10` / `paper-20`. FTS query `optimization algorithm` ranks A, C, B on title+abstract.

---

## Phase V1: Walking Skeleton — Bind hybrid paper search (one-based RRF)

**Role:** Capability
**Target Capability Slice:** N/A
**Facts Introduced:** SEARCH.HYBRID.FTS_VECTOR_RRF.v1
**Facts Strengthened:** (none)
**Facts Protected:** SCHEMA.JOB.INTEGRITY_CHECK.v1, SCHEMA.MIGRATE.FORWARD.v1
**Verification Command:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

**Demo/Validation Command:** `uv run python -m papers.cli query "<the V0A query>" --limit 5`
**Observable Outcome:** Hybrid search evidence is green; first result is **paper A** (fused order A, B, C); ranks are one-based.
**Rollback Notes:** Revert the phase commit. Score values change; they are not persisted as provenance.
**Executed By:**

### Task V1.0: Re-verify V0A

**Type:** Test

**PRD Trace:** Technical Enabler: re-verify inherited state.

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V0A.5

**Description:**
Run the four-command quality gate.

**Acceptance Criteria:**
- [x] Quality gate exits 0
- [x] Coverage policy satisfied (no regression)

---

### Task V1.1: Test one-based hybrid RRF search

**Type:** Test

**PRD Trace:** LOCAL-AC-HYBRID-SEARCH

**Fact / Evidence (Test tasks):** SEARCH.HYBRID.FTS_VECTOR_RRF.v1, Tier 1 → EV-01

**Expected Failure Signature:** Fused `paper_id` order is not `[A, B, C]`, or any score differs from the V0A one-based table (8 decimal places), or the call is not `SearchPapersUseCase.search`.

**Real Data Dependency:** DATA-01a, DATA-01b, DATA-01c

**Provider Boundary:** `PapersFTS`, `VectorIndex`, `Embedder`

**Depends On:** V1.0

**Description:**
Create three papers with `PaperStore.create_paper` using each fixture’s `paper_id`, `title`, and `abstract`. Run FTS through `PapersFTS.search` on those rows (not on markdown). Embed **markdown** only. A fake embedder may realize vector order B,A,C. Assert fused order of those `paper_id`s is A,B,C (roles) and scores match 0.03252247 / 0.03226646 / 0.03200205. Also assert `compute_rrf_scores` on the role lists with k=60. Assert sorted(`paper_id`s) ≠ fused `paper_id` order.

**Acceptance Criteria:**
- [x] Check lives at `tests/facts/test_hybrid_search.py`
- [x] Asserts complete fused order and scores, not the winner alone
- [x] Explicitly would fail FTS-only, vector-only, zero-based RRF, and `paper_id` sort
- [x] New check fails with the stated signature; rest of suite green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_hybrid_search.py` (create)

---

### Task V1.2: Implement one-based RRF

**Type:** Implement

**PRD Trace:** LOCAL-AC-HYBRID-SEARCH

**Makes Green:** EV-01

**Real Data Dependency:** DATA-01a, DATA-01b, DATA-01c

**Provider Boundary:** `SearchPapersUseCase`

**Depends On:** V1.1

**Facts Protected:** none (fact is new; current zero-based behavior is not an Active fact)

**Description:**
Change `compute_rrf_scores` to `enumerate(ranking, start=1)`. Do not preserve zero-based scoring. Update any unit test that encoded the old formula.

**Acceptance Criteria:**
- [x] EV-01 green
- [x] `enumerate(..., start=1)` is the only rank source
- [x] Existing `tests/app/use_cases/test_search.py` updated if it asserted 0-based scores — that is Evidence Maintenance of a supporting test, not a Fact Change
- [x] Quality gate green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `src/papers/app/use_cases/search.py` (modify)
- `tests/app/use_cases/test_search.py` (modify if needed)

---

### Task V1.3: Fact Sufficiency Review — hybrid search

**Type:** Fact Sufficiency Review

**PRD Trace:** LOCAL-AC-HYBRID-SEARCH

**Fact / Evidence (Test tasks):** SEARCH.HYBRID.FTS_VECTOR_RRF.v1

**Real Data Dependency:** DATA-01a, DATA-01b, DATA-01c

**Provider Boundary:** N/A

**Depends On:** V1.2

**Description:**
Confirm EV-01 rejects FTS-only (A,C,B), vector-only (B,A,C), zero-based RRF scores, and `paper_id` sort. Winner-alone is not an acceptable sufficiency argument.

**Acceptance Criteria:**
- [x] Phase close lists those four incorrect implementations and cites the full-order oracle
- [x] Coverage policy satisfied (N/A — review)

---

**Phase V1 Exit Criteria:**
- [x] SEARCH.HYBRID.FTS_VECTOR_RRF.v1 green
- [x] Full fused order and one-based scores bound
- [x] Rebuild Property spot-check recorded
- [x] EV-01 Lifecycle set to Required
- [x] SEARCH.HYBRID.FTS_VECTOR_RRF.v1 Lifecycle set to Active
- [x] Quality gate green
- [x] **Stage changes for human review**

**Close note (2026-08-19):** EV-01 uses `PaperStore.create_paper` (title+abstract FTS) plus markdown embeddings into a test index. Query `optimization algorithm`. Incorrect implementations rejected by the same test: FTS-only A,C,B; vector-only B,A,C; zero-based RRF; lexicographic `paper_id` sort. Rebuild property: FTS rows are written by `create_paper` / `_upsert_paper_fts`, not by indexing markdown. `compute_rrf_scores` already used `enumerate(..., start=1)`.

---

## Phase V2: Slice — Transactional import with taxonomy

**Role:** Capability
**Target Capability Slice:** N/A
**Facts Introduced:** DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1, DISCOVERY.IMPORT.IDEMPOTENT_ATTACH.v1
**Facts Strengthened:** (none)
**Facts Protected:** SEARCH.HYBRID.FTS_VECTOR_RRF.v1
**Verification Command:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

**Demo/Validation Command:** `uv run python -m papers.cli import <candidate_id> --project <project_id> --tag <tag_id>`
**Observable Outcome:** Import either commits paper + attachments + download job + candidate mark, or writes nothing. Re-import attaches missing memberships only.
**Rollback Notes:** Revert the phase commit. Papers imported before this phase are unchanged.
**Executed By:**

### Import semantics (normative)

Existing Piccolo store methods each call `.run_sync()` and **do not share a transaction**. A helper that wraps those sync methods cannot be atomic. Do not choose “enter `SQLiteEngine.transaction` around the current use-case.”

**Architecture (required): domain-shaped atomic import port.**

```python
class AtomicCandidateImport(Protocol):
    def import_new(
        self,
        *,
        candidate_id: str,
        paper_fields: dict[str, Any],
        external_ids: dict[str, str],
        project_ids: list[str],
        tag_ids: list[str],
    ) -> str: ...  # paper_id; all-or-nothing

    def attach_to_imported(
        self,
        *,
        paper_id: str,
        project_ids: list[str],
        tag_ids: list[str],
    ) -> None: ...
```

Piccolo implements each method with **one** async body under `async with engine.transaction(transaction_type=TransactionType.immediate)`, invoked via a **single** `run_sync`. Cross the sync boundary exactly once per call. Individual `PiccoloPaperStore.create_paper` etc. are not used for these writes.

Use-case sequence:

1. Load candidate via `CandidateStore` (pre-check only). Missing → `NotFoundError`. Rejected → `ValueError`.
2. Validate **every** `project_id` / `tag_id` via `ProjectStore.get` / `TagStore.get` **before any write**. First missing ID → `NotFoundError`.
3. **Already imported (pre-check):** `AtomicCandidateImport.attach_to_imported` — that method runs in its own `TransactionType.immediate` transaction.
4. **Not yet imported (pre-check):** `AtomicCandidateImport.import_new`.
5. Retry is the whole use-case.

**Concurrency inside `import_new`:** the pre-transaction read is not authoritative. Re-read the candidate (or compare-and-set `imported_paper_id`) **inside** the immediate transaction. If another writer already imported it, take the `attach_to_imported` path on that paper ID and do **not** insert a second paper.

`attach_to_imported` also uses one `TransactionType.immediate` transaction (attachments only).

**Wiring (required):** `composition_root.AppContainer` and the CLI/UI containers grow: `project_store`, `tag_store`, `paper_project_store`, `paper_tag_store`, `atomic_candidate_import`. `ImportCandidateUseCase` takes those ports.

**EV-02** uses a real `PiccoloDatabase` and the real Piccolo adapter. Inject failure *inside* that adapter’s transaction (after paper insert, before `mark_imported`) and assert no paper, no job, unmarked candidate. In-memory fakes are not sufficient for EV-02.

### Task V2.0: Re-verify V1

**Type:** Test

**PRD Trace:** Technical Enabler: re-verify inherited state.

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V1.3

**Description:**
Run the four-command quality gate including EV-01.

**Acceptance Criteria:**
- [x] Quality gate exits 0
- [x] EV-01 still green
- [x] Coverage policy satisfied (no regression)

---

### Task V2.1: Test atomic first import with attachments

**Type:** Test

**PRD Trace:** LOCAL-AC-IMPORT-TAXONOMY

**Fact / Evidence (Test tasks):** DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1, Tier 1 → EV-02

**Expected Failure Signature:** Import with a bad tag ID still creates a paper, or a mid-flight store failure leaves a paper without `imported_paper_id`.

**Real Data Dependency:** None (IDs and titles come from `CreateProjectUseCase` / `CreateTagUseCase` / candidate create path)

**Provider Boundary:** `AtomicCandidateImport` (Piccolo), `ProjectStore`, `TagStore`

**Depends On:** V2.0

**Description:**
Against **real Piccolo** stores: happy path with one project and one tag; unknown project ID creates nothing; failure injected inside the Piccolo transaction after paper insert rolls back completely.

**Acceptance Criteria:**
- [x] `tests/facts/test_import_taxonomy.py` exists
- [x] New check fails with the stated signature; rest of suite green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_import_taxonomy.py` (create)

---

### Task V2.2: Implement transactional import

**Type:** Implement

**PRD Trace:** LOCAL-AC-IMPORT-TAXONOMY

**Makes Green:** EV-02

**Real Data Dependency:** None

**Provider Boundary:** `AtomicCandidateImport` → Piccolo transaction; use-case stays sync

**Depends On:** V2.1

**Facts Protected:** SEARCH.HYBRID.FTS_VECTOR_RRF.v1

**Description:**
Add `AtomicCandidateImport` to `ports.py`. Implement `PiccoloAtomicCandidateImport` with one transactional async write path. Wire stores + port in `composition_root`, CLI container, and UI services. Extend `import_candidate(..., project_ids=..., tag_ids=...)`.

**Acceptance Criteria:**
- [x] EV-02 green against real Piccolo
- [x] No new `run_sync()` per insert inside `import_new`
- [x] Import without IDs still creates a paper and enqueues download inside `import_new`
- [x] Quality gate green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `src/papers/app/ports.py` (modify)
- `src/papers/app/use_cases/discovery.py` (modify)
- `src/papers/infra/piccolo/` (new adapter)
- `src/papers/app/composition_root.py` (modify)
- `src/papers/cli/app.py` (modify)
- `src/papers/ui/__main__.py` (modify)

---

### Task V2.3: Test idempotent re-import attachments

**Type:** Test

**PRD Trace:** LOCAL-AC-IMPORT-TAXONOMY

**Fact / Evidence (Test tasks):** DISCOVERY.IMPORT.IDEMPOTENT_ATTACH.v1, Tier 1 → EV-02c

**Expected Failure Signature:** Re-import returns the paper but does not attach the newly requested project, or it enqueues a second download.

**Real Data Dependency:** None

**Provider Boundary:** `ImportCandidateUseCase`

**Depends On:** V2.2

**Description:**
Import once with no IDs, then again with project/tag IDs. Assert same paper_id, attachments present, single download job.

**Acceptance Criteria:**
- [x] `tests/facts/test_import_idempotent_attach.py` fails with the stated signature
- [x] Rest of suite green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_import_idempotent_attach.py` (create)

---

### Task V2.4: Implement idempotent re-import attachments

**Type:** Implement

**PRD Trace:** LOCAL-AC-IMPORT-TAXONOMY

**Makes Green:** EV-02c

**Real Data Dependency:** None

**Provider Boundary:** `ImportCandidateUseCase`

**Depends On:** V2.3

**Facts Protected:** DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1, SEARCH.HYBRID.FTS_VECTOR_RRF.v1

**Description:**
On already-imported candidates, attach missing memberships only; never enqueue download.

**Acceptance Criteria:**
- [x] EV-02c green
- [x] Quality gate green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `src/papers/app/use_cases/discovery.py` (modify)

---

### Task V2.5: Test CLI import flags

**Type:** Test

**PRD Trace:** LOCAL-AC-IMPORT-TAXONOMY

**Fact / Evidence (Test tasks):** DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1, Tier 1 → EV-02b

**Expected Failure Signature:** Parser rejects `--project` / `--tag`, or the use-case is called without those IDs.

**Real Data Dependency:** None

**Provider Boundary:** CLI → `ImportCandidateUseCase`

**Depends On:** V2.4

**Description:**
CLI forwards repeatable `--project` and `--tag`.

**Acceptance Criteria:**
- [x] Check fails with the stated signature
- [x] Rest of suite green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_import_taxonomy_cli.py` (create)

---

### Task V2.6: Implement CLI import flags

**Type:** Implement

**PRD Trace:** LOCAL-AC-IMPORT-TAXONOMY

**Makes Green:** EV-02b

**Real Data Dependency:** None

**Provider Boundary:** CLI → `ImportCandidateUseCase`

**Depends On:** V2.5

**Facts Protected:** DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1

**Description:**
Add repeatable `--project` and `--tag` on `papers import`.

**Acceptance Criteria:**
- [x] EV-02b green
- [x] `uv run python -m papers.cli import --help` shows the flags
- [x] Quality gate green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `src/papers/cli/commands/discovery.py` (modify)

---

**Phase V2 Exit Criteria:**
- [x] EV-02, EV-02b, EV-02c green
- [x] ID validation precedes writes
- [x] First import goes through `AtomicCandidateImport.import_new` (one Piccolo transaction)
- [x] Re-import attaches only; already-present attachments are no-ops
- [x] EV-02/02b/02c Lifecycle set to Required
- [x] DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1 and DISCOVERY.IMPORT.IDEMPOTENT_ATTACH.v1 set to Active
- [x] SEARCH.HYBRID.FTS_VECTOR_RRF.v1 still green
- [x] Quality gate green
- [x] **Stage changes for human review**

**Close note (2026-08-20):** `ImportCandidateUseCase` validates, deduplicates, and caps project/tag IDs before invoking the adapter and rejects attachment requests when `AtomicCandidateImport` is not configured. `PiccoloAtomicCandidateImport` revalidates paper/project/tag targets inside the immediate transaction, which writes paper, FTS, external IDs, download job, import mark, and memberships atomically. Re-import uses `attach_to_imported` and does not enqueue a second download. Paper deletion clears candidate import references in the same transaction. Integrity collisions become stable domain conflicts, and CLI errors use fixed output without resource IDs or raw database details. CLI forwards repeatable `--project` and `--tag`. Final four-command gate: 749 passed, 1 skipped, 92.83% repository coverage.

---

## Phase V3: Slice — Project analysis filters and force characterization

**Role:** Capability
**Target Capability Slice:** N/A
**Facts Introduced:** ANALYSIS.PROJECT.APPLY_FILTERS.v1, ANALYSIS.RUN.FORCE_NEW.v1
**Facts Strengthened:** (none)
**Facts Protected:** SEARCH.HYBRID.FTS_VECTOR_RRF.v1, DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1, DISCOVERY.IMPORT.IDEMPOTENT_ATTACH.v1
**Verification Command:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

**Demo/Validation Command:** `uv run python -m papers.cli analyze-project <project_id> --prompt-version-id <id> --profile-id <id> --model-name <name> --field-path algorithm_family --constraint value_text=transformer --filter-prompt-version-id <id>`
**Observable Outcome:** Project analysis can be limited by extraction filters with documented algebra; force-new-run is pinned by a characterization check.
**Rollback Notes:** Revert the phase commit. Existing runs remain.
**Executed By:**

### Filter algebra (normative)

Public type:

```python
@dataclass(frozen=True)
class ExtractionFilter:
    field_path: str
    prompt_version_id: str
    constraints: dict[str, Any]  # keys ⊆ {value_text, value_numeric, value_boolean}
    latest_only: bool = True
```

`AnalyzeProjectUseCase.__call__(..., prompt_version_id: str, ..., label: str | None = None, filters: list[ExtractionFilter] | None = None, force: bool = False)`

`prompt_version_id` on the use-case is the **target** version for the new analysis runs. Each `ExtractionFilter.prompt_version_id` is the version whose **existing extractions** are queried. They may differ (e.g. filter on an older extraction schema, analyze with a new prompt).

| Topic | Rule |
|-------|------|
| Empty filters | `filters is None` or `filters == []` → no extraction predicate |
| Multiple filters | **AND** — a paper must match every `ExtractionFilter` |
| Constraints inside one filter | **AND** of supplied keys (existing `ExtractionStore.query`) |
| OR | Not supported in this slice |
| Filter prompt version | May differ from the target analyze `prompt_version_id` |
| `label` | Applied first via `list_paper_ids(project_id, label=label)` |
| Membership vs filters | (1) members = project ∩ optional label (2) if filters empty, analyze members (3) else analyze `members ∩ (∩ filter matches)` |
| `latest_only=True` (default) | Match only extractions from the latest successful analyze run for **that filter’s** `prompt_version_id` |
| `latest_only=False` | Any run for that filter’s prompt version may match |
| Unknown constraint key | `ValueError` before any enqueue |
| No members after intersection | Return `[]`; enqueue nothing |
| CLI constraints | Reuse `_parse_constraints` from `src/papers/cli/commands/query.py` (including `value_numeric` float and `value_boolean` 0/1 coercion) |

### Task V3.0: Re-verify V2

**Type:** Test

**PRD Trace:** Technical Enabler: re-verify inherited state.

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V2.6

**Description:**
Run the four-command quality gate.

**Acceptance Criteria:**
- [x] Quality gate exits 0
- [x] EV-01, EV-02, EV-02b, EV-02c still green
- [x] Coverage policy satisfied (no regression)

---

### Task V3.1: Test AnalyzeProject extraction filters

**Type:** Test

**PRD Trace:** LOCAL-AC-ANALYZE-PROJECT-FILTERS

**Fact / Evidence (Test tasks):** ANALYSIS.PROJECT.APPLY_FILTERS.v1, Tier 1 → EV-03

**Expected Failure Signature:** A project member that fails a filter still receives `run_analysis`, or an empty filter list analyzes nobody, or label is applied after filters so non-labeled matches are kept.

**Real Data Dependency:** None — papers, project, tags, and extractions created through public use-cases / analysis create path

**Provider Boundary:** `AnalyzeProjectUseCase`, `FilterByExtractionsUseCase` / `ExtractionStore`

**Depends On:** V3.0

**Description:**
Cases: empty filters analyze all labeled members; one filter drops a non-matching member; two filters AND; `latest_only=True` ignores an older run; label then filter intersection order; a filter whose `prompt_version_id` differs from the analyze target still matches on that older version’s extractions.

**Acceptance Criteria:**
- [x] `tests/facts/test_analyze_project_filters.py` fails with the stated signature
- [x] Rest of suite green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_analyze_project_filters.py` (create)

---

### Task V3.2: Implement AnalyzeProject filters

**Type:** Implement

**PRD Trace:** LOCAL-AC-ANALYZE-PROJECT-FILTERS

**Makes Green:** EV-03

**Real Data Dependency:** None

**Provider Boundary:** `AnalyzeProjectUseCase` → `PaperProjectStore` + extraction query

**Depends On:** V3.1

**Facts Protected:** ANALYSIS.RUN.FORCE_NEW.v1 (not yet bound; do not change `force` plumbing)

**Description:**
Implement the algebra. Reuse `FilterByExtractionsUseCase` / store `query`. Do not reimplement SQL.

**Acceptance Criteria:**
- [x] EV-03 green
- [x] `label=None, filters=None` preserves today's “all members” behavior
- [x] Quality gate green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `src/papers/app/use_cases/analysis.py` (modify)

---

### Task V3.3: Characterize force-new-run

**Type:** Test

**PRD Trace:** LOCAL-AC-ANALYZE-FORCE

**Fact / Evidence (Test tasks):** ANALYSIS.RUN.FORCE_NEW.v1, Tier 1 → EV-04 (characterization)

**Expected Failure Signature:** N/A — `force=True` already creates a new run in `RunAnalysisUseCase`. This check must pass on current code. If it fails, stop; that is a regression against design §9.2, not a RED task to implement toward a new shape.

**Real Data Dependency:** None

**Provider Boundary:** `RunAnalysisUseCase`

**Depends On:** V3.2

**Description:**
Pin existing force behavior: first call stores run R1; second call `force=False` returns R1; third call `force=True` returns R2 ≠ R1; R1 still exists.

**Acceptance Criteria:**
- [x] `tests/facts/test_analyze_force.py` is green against current `RunAnalysisUseCase`
- [x] Kind remains characterization of a requirement that already exists in design §9.2
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_analyze_force.py` (create)

---

### Task V3.4: Test analyze-project CLI

**Type:** Test

**PRD Trace:** LOCAL-AC-ANALYZE-PROJECT-FILTERS

**Fact / Evidence (Test tasks):** ANALYSIS.PROJECT.APPLY_FILTERS.v1 (CLI binding)

**Expected Failure Signature:** Command not registered, or flags are not forwarded as `ExtractionFilter`.

**Real Data Dependency:** None

**Provider Boundary:** CLI → `AnalyzeProjectUseCase`

**Depends On:** V3.3

**Description:**
`papers analyze-project` accepts project id, target `--prompt-version-id`, profile, model, optional `--label`, optional `--field-path` + repeatable `--constraint` parsed by `_parse_constraints`, optional `--filter-prompt-version-id` (defaults to the target prompt version), and `--force`.

**Acceptance Criteria:**
- [x] CLI test fails with the stated signature
- [x] Rest of suite green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/cli/test_pipeline_commands.py` (modify) or `tests/facts/test_analyze_project_cli.py` (create)

---

### Task V3.5: Implement analyze-project CLI

**Type:** Implement

**PRD Trace:** LOCAL-AC-ANALYZE-PROJECT-FILTERS

**Makes Green:** V3.4 CLI check

**Real Data Dependency:** None

**Provider Boundary:** CLI → `AnalyzeProjectUseCase`

**Depends On:** V3.4

**Facts Protected:** ANALYSIS.PROJECT.APPLY_FILTERS.v1, ANALYSIS.RUN.FORCE_NEW.v1

**Description:**
Register `analyze-project`. Import and call `_parse_constraints` from `src/papers/cli/commands/query.py` (do not fork coercion). One CLI filter is enough; the use-case still accepts a list. `--filter-prompt-version-id` defaults to `--prompt-version-id`.

**Acceptance Criteria:**
- [x] V3.4 tests pass
- [x] `uv run python -m papers.cli analyze-project --help` works
- [x] Quality gate green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `src/papers/cli/commands/pipeline.py` (modify)
- `src/papers/cli/app.py` (modify if wiring needed)

---

**Phase V3 Exit Criteria:**
- [x] EV-03 green with the published algebra
- [x] Filters may use a prompt version other than the analyze target
- [x] EV-04 characterization green
- [x] EV-03 and EV-04 Lifecycle set to Required
- [x] ANALYSIS.PROJECT.APPLY_FILTERS.v1 and ANALYSIS.RUN.FORCE_NEW.v1 set to Active
- [x] CLI demo command works
- [x] Prior facts still green
- [x] Quality gate green
- [x] **Stage changes for human review**

**Close note (2026-08-20):** `AnalyzeProjectUseCase` applies label membership first, then AND-intersects `ExtractionFilter` matches via `FilterByExtractionsUseCase` / `ExtractionStore.query`. Empty filters still analyze all labeled members. Filter `prompt_version_id` may differ from the analyze target. Unknown constraint keys raise `ValueError` before enqueue. `RunAnalysisUseCase` force reuse/new-run is pinned by EV-04. CLI `analyze-project` forwards one filter through `_parse_constraints`. Final four-command gate: 765 passed, 1 skipped, 92.86% repository coverage.

---

## Phase V6: Hardening — Operability we can prove

**Role:** Hardening
**Target Capability Slice:** Strengthens EV-08, EV-08b, EV-09, EV-10
**Facts Introduced:** (none as product facts; converter/log/startup facts above are bound here if not already green)
**Facts Strengthened:** ADAPTER.CONVERT.RESULT_CODES.v1, HANDLER.CONVERT.CORRUPT_PDF.v1, OBS.LOG.JOB_CONTEXT.v1, CFG.STARTUP.MISSING_DEP.v1
**Facts Protected:** all Active facts as of phase start
**Verification Command:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

This command must exit 0. Remaining lint is not acceptable.

**Demo/Validation Command:** `uv run pytest tests/facts/test_convert_result_codes.py tests/facts/test_convert_corrupt_pdf.py tests/facts/test_job_log_context.py tests/facts/test_startup_missing_dep.py -q --no-cov`
**Observable Outcome:** Converter adapter codes, corrupt-PDF handler path, job log fields, and missing-dep startup are bound. Protected/timeout/OOM convert classes are **not** claimed.
**Rollback Notes:** Revert the phase commit.
**Executed By:**

**Depends On:** V3
**Not claimed:** `PROTECTED_PDF`, `CONVERTER_TIMEOUT`, `CONVERTER_OOM` (no approved captures; do not invent payloads).

### Task V6.0: Re-verify V3

**Type:** Test

**PRD Trace:** Technical Enabler: re-verify inherited state.

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V3.5

**Description:**
Run the four-command quality gate.

**Acceptance Criteria:**
- [x] Quality gate exits 0
- [x] Coverage policy satisfied (no regression)

---

### Task V6.1: Characterize ConverterResult empty and exception codes

**Type:** Test

**PRD Trace:** LOCAL-AC-CONVERT-RESULT

**Fact / Evidence (Test tasks):** ADAPTER.CONVERT.RESULT_CODES.v1 → EV-08 (characterization / rebind)

**Expected Failure Signature:** N/A — `DoclingConverter.pdf_to_markdown` already returns `ConverterResult` with `EMPTY_OUTPUT` / `CONVERSION_FAILED`. This check must pass on current code. If it fails, stop; that is a regression, not a RED task toward a new shape.

**Real Data Dependency:** None — invalid mutation is empty string / raised exception from the injected `convert_func`

**Provider Boundary:** `Converter` / `DoclingConverter`

**Depends On:** V6.0

**Description:**
Rebind the existing adapter behavior into `tests/facts/`. Do not require `PipelineError` from `pdf_to_markdown`. (`build_docling_converter` may still raise if Docling is missing — install-time only.)

**Acceptance Criteria:**
- [x] `tests/facts/test_convert_result_codes.py` is green against current `DoclingConverter`
- [x] Assertions check `ConverterResult`, `ok=False`, `markdown=None`, and the exact `error_code`
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_convert_result_codes.py` (create)

---

### Task V6.2: Stop if converter characterization is red

**Type:** Implement

**PRD Trace:** LOCAL-AC-CONVERT-RESULT

**Makes Green:** EV-08 (already green unless regressed)

**Real Data Dependency:** None

**Provider Boundary:** `DoclingConverter`

**Depends On:** V6.1

**Facts Protected:** HANDLER.CONVERT.CORRUPT_PDF.v1

**Description:**
Do not change the adapter unless V6.1 failed. If it failed, restore `ConverterResult` mapping — do not switch the port to raise `PipelineError`.

**Acceptance Criteria:**
- [x] EV-08 green
- [x] `pdf_to_markdown` still returns `ConverterResult`
- [x] Quality gate green
- [x] Coverage policy satisfied

---

### Task V6.3: Test handler CORRUPT_PDF path

**Type:** Test

**PRD Trace:** LOCAL-AC-CONVERT-CORRUPT

**Fact / Evidence (Test tasks):** HANDLER.CONVERT.CORRUPT_PDF.v1 → EV-08b

**Expected Failure Signature:** N/A if existing handler tests already pin this; otherwise fail when a non-PDF byte string is not reported as `CORRUPT_PDF`.

**Real Data Dependency:** None — truncated/invalid PDF header is an invalid mutation, not a representative paper

**Provider Boundary:** convert handler, not the adapter

**Depends On:** V6.2

**Description:**
Rebind or add a fact test around `handle_convert` + `_is_valid_pdf`. This is handler-level, matching production.

**Acceptance Criteria:**
- [x] EV-08b green
- [x] Test does not require the adapter to return `CORRUPT_PDF`
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_convert_corrupt_pdf.py` (create)

---

### Task V6.4: Test job log context fields

**Type:** Test

**PRD Trace:** LOCAL-NFR-LOGGING

**Fact / Evidence (Test tasks):** OBS.LOG.JOB_CONTEXT.v1 → EV-09

**Expected Failure Signature:** A job transition log record is missing one of timestamp, job_id, job_type, status_from, status_to, paper_id, run_id.

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V6.3

**Description:**
May rebind `tests/observability/test_logging.py` into `tests/facts/`.

**Acceptance Criteria:**
- [x] EV-09 green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_job_log_context.py` (create)

---

### Task V6.5: Test startup missing-dependency fail-fast

**Type:** Test

**PRD Trace:** LOCAL-NFR-FAILFAST

**Fact / Evidence (Test tasks):** CFG.STARTUP.MISSING_DEP.v1 → EV-10

**Expected Failure Signature:** N/A if `tests/config/test_fail_fast.py` already pins this — rebind rather than duplicate.

**Real Data Dependency:** None

**Provider Boundary:** composition root

**Depends On:** V6.4

**Description:**
Rebind the existing fail-fast test as EV-10.

**Acceptance Criteria:**
- [x] EV-10 command is green
- [x] Quality gate green
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/facts/test_startup_missing_dep.py` (create or thin wrapper)

---

### Task V6.6: Narrow corrupt-PDF recovery to viable provenance

**Type:** Fact Change

**PRD Trace:** LOCAL-AC-CONVERT-CORRUPT

**Fact / Evidence (Test tasks):** HANDLER.CONVERT.CORRUPT_PDF.v1 → EV-08b

**Real Data Dependency:** None

**Provider Boundary:** convert handler and job runner

**Depends On:** V6.5

**Description:**
Require `source_path` or external IDs before deleting a corrupt blob and enqueuing a replacement download. Carry download provenance into the chained convert job. If no recovery source exists, retain the blob and do not enqueue a job that can only fail.

**Acceptance Criteria:**
- [x] Recoverable corrupt PDFs enqueue exactly one download with the original provenance
- [x] Unrecoverable corrupt PDFs retain the only blob and enqueue nothing
- [x] Raw converter exception text is not logged or persisted as pipeline health
- [x] CLI and UI startup configuration failures do not expose secrets, tracebacks, or absolute paths
- [x] Quality gate green

---

**Phase V6 Exit Criteria:**
- [x] EV-08, EV-08b, EV-09, EV-10 green
- [x] Those four rows Lifecycle set to Required
- [x] ADAPTER.CONVERT.RESULT_CODES.v1, HANDLER.CONVERT.CORRUPT_PDF.v1, OBS.LOG.JOB_CONTEXT.v1, CFG.STARTUP.MISSING_DEP.v1 set to Active
- [x] Phase does **not** claim protected/timeout/OOM convert coverage
- [x] Verification command is the full gate and is green
- [x] **Stage changes for human review**

**Close note (2026-08-20):** Bound adapter `ConverterResult` mapping (`EMPTY_OUTPUT` / `CONVERSION_FAILED`), provenance-safe handler `CORRUPT_PDF` recovery, exact job-runner transition log fields, and composition-root fail-fast when a required optional module is missing. CLI/UI startup errors and converter failures use bounded public text without traceback locals, paths, secrets, or provider exception details. `PROTECTED_PDF`, `CONVERTER_TIMEOUT`, and `CONVERTER_OOM` remain unclaimed. Final four-command gate: 774 passed, 1 skipped, 92.82% repository coverage.

---

## Phase V7: Polish & Documentation

**Role:** Documentation
**Target Capability Slice:** Enables future agents; publishes the ledger
**Facts Introduced:** (none)
**Facts Strengthened:** (none)
**Facts Protected:** all Active facts as of phase start
**Verification Command:**

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

**Demo/Validation Command:** `uv run python -m papers.cli --help`
**Observable Outcome:** README setup commands exist; ADRs for LanceDB, Docling, Piccolo (including forward-only migrations), prompts, and one-based hybrid search; workflow docs for discover/import, analyze, query; ledger linked from README.
**Rollback Notes:** Revert the docs commit.
**Executed By:**

**Depends On:** V6
**Coverage:** N/A for pure documentation; quality gate still runs.

### Task V7.0: Re-verify V6

**Type:** Test

**PRD Trace:** Technical Enabler: re-verify inherited state.

**Fact / Evidence (Test tasks):** N/A

**Expected Failure Signature:** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V6.5

**Description:**
Run the four-command quality gate.

**Acceptance Criteria:**
- [x] Quality gate exits 0

---

### Task V7.1: Write ADRs

**Type:** Document

**PRD Trace:** Technical Enabler: record durable design choices.

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V7.0

**Description:**
ADRs for LanceDB, Docling, Piccolo + forward-only migrations, prompt system, and hybrid search **including one-based RRF**.

**Acceptance Criteria:**
- [x] `docs/adr/001-lancedb-vector-store.md` through `docs/adr/005-hybrid-search.md` exist
- [x] 003 mentions V0B migrations
- [x] 005 states rank starts at 1
- [x] Coverage policy satisfied (N/A — documentation)

---

### Task V7.2: Write workflow docs

**Type:** Document

**PRD Trace:** Technical Enabler: operator docs.

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V7.1

**Description:**
CLI examples for discover/import (with `--project`/`--tag`), analyze / analyze-project, and query. No fake screenshots.

**Acceptance Criteria:**
- [x] `docs/workflows/discovery.md`, `analysis.md`, `querying.md` exist
- [x] `uv run pytest tests/support/test_docs_cli_commands.py -q --no-cov` extracts documented `papers` commands and options from those files and asserts each is registered on the Typer app
- [x] Coverage policy satisfied (N/A — documentation except that test)

---

### Task V7.3: Link ledger from README

**Type:** Document

**PRD Trace:** Technical Enabler: next reader inherits the specification.

**Fact / Evidence (Test tasks):** N/A

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V7.2

**Description:**
README links `docs/fact-ledger.md` and `docs/evidence-index.md`. Setup commands match the quality gate.

**Acceptance Criteria:**
- [x] Links resolve
- [x] Coverage snapshot optional; if written, it is a snapshot not a second source of truth

---

### Task V7.4: Test docs CLI commands and src TODO markers

**Type:** Test

**PRD Trace:** Technical Enabler: documentation claims must be checkable.

**Fact / Evidence (Test tasks):** EV-13

**Expected Failure Signature:** A `papers …` command documented in `docs/workflows/` is not registered, or `rg`/`pathlib` finds `TODO`/`FIXME`/`XXX` under `src/`.

**Real Data Dependency:** None

**Provider Boundary:** N/A

**Depends On:** V7.3

**Description:**
Add `tests/support/test_docs_cli_commands.py` and `tests/support/test_no_src_todo.py`. Flip EV-13 to `Required`.

**Acceptance Criteria:**
- [x] Both tests green
- [x] EV-13 Lifecycle = Required
- [x] Coverage policy satisfied

**Files Affected (optional):**
- `tests/support/test_docs_cli_commands.py` (create)
- `tests/support/test_no_src_todo.py` (create)

---

**Phase V7 Exit Criteria:**
- [x] ADRs and workflows exist
- [x] Ledger linked
- [x] EV-13 green (CLI-in-docs + no src TODO/FIXME/XXX)
- [x] Quality gate green
- [x] **Stage changes for human review**

**Close note (2026-08-21):** Published ADRs for LanceDB, Docling, Piccolo forward-only migrations, versioned prompts, and one-based hybrid RRF. Operator workflows cover discover/import, analyze/analyze-project, and query/filter. README links the fact ledger and evidence index. EV-13 checks documented Typer commands and forbids TODO/FIXME/XXX under `src/`. Final four-command gate: 777 passed, 1 skipped, 92.82% repository coverage.

---

## Coverage Requirements (this plan)

| Rule | Applied as |
|------|------------|
| Overall floor | Mechanical: V0.11 sets `fail_under = 91.90`. `uv run pytest -q` fails below that. That number is pytest-cov **combined** coverage, not branch-only. |
| Changed behavioral code ≥90% **combined** | **Manual review.** Phase close pastes the `pytest --cov` `Cover` column for files this phase changed. Not branch-only; the term report does not emit a branch-only percentage. |
| New domain logic ≥95% **combined** | **Manual review**, same recorded excerpt. |

A JSON+branch-only calculator is out of scope. If a later plan needs true branch-only diffs, add that tool then; do not treat the current Cover column as branch coverage.
| Tier-1 evidence paths | every `Required` fact’s command runs inside `uv run pytest -q` |
| Documentation / data-gate | N/A with reason in the phase close |
| UI package | remains omitted; no UI fact in this plan |

# Development Plan: Research Paper Analysis Platform (v1)

**Status:** Complete for delivered layer-based scope (2026-08-18). Do not execute remaining unchecked items from this file.
**Guide Version:** 1.x (layer-based). Planning authority is now guide v2.0.
**Superseded remaining work:** `docs/development-plan-open-work.md`
**Plan Set:** gleansight

Based on `docs/project-design.md` (v0.9) and the planning guide, this plan follows TDD, ≥90% coverage throughout, and phased human review.

## Audit status (2026-08-17)

Checked against the current tree and test run (`525 passed, 1 skipped`, overall coverage **91.90%**, UI omitted from the coverage gate). `[x]` means the criterion is met; `[ ]` means missing or only partial.

| Phase | Status | Remaining gaps |
|---|---|---|
| 0 Foundation | Mostly complete | Protocol error-contract tests; ports lack design docstrings; config/foundation not independently gated at 95% |
| 1 Core domain | Complete | Domain layer coverage is ≥95% (models 100%, errors 100%, policies 96%) |
| 2 Primary impl | Mostly complete | No Piccolo migrations/CHECKs; adapter timeout/error mapping incomplete; structured logging not at adapter boundaries |
| 3 Integration | Complete | Real Piccolo/LanceDB/Docling tests are marked `integration` |
| 4 Discovery & search | Mostly complete | No real Semantic Scholar E2E; import does not attach projects/tags |
| 5 Analysis & taxonomy | Mostly complete | AnalyzeProject filters are label-only; force-new-run under-tested; some Section 15 signatures differ |
| 6 CLI | Mostly complete | Per-command help tests thin; `status` shows counts, not a job table |
| 7 UI | Mostly complete | NavigationRail (not drawer/tabs); search/query use cards, not data tables; UI omitted from coverage |
| 8 Hardening | Mostly complete | No p50/p95 aggregation; handler logs unstructured; missing dirs are created rather than fail-closed |
| 9 Polish | Incomplete | ADRs, workflow guides, screenshots, and a committed coverage report are missing; ruff is not clean |

Process checkboxes (**Stage changes for human review**) stay unchecked: they are review steps, not code deliverables.

Design-doc note: plan tasks cite “Section 16” for CLI/UI, but `docs/project-design.md` §16 is the migration plan. The required surface is the command/screen list in that section’s wrap list.

---

## Phase 0: Foundation & Standards (Coverage ≥95%)

### Task 0.1: Audit repository scaffolding and .gitignore

**Type:** Document

**Description:**
Confirm repo is initialized, add missing ignore patterns for data, blobs, sqlite, and model artifacts per design doc.

**Acceptance Criteria:**
- [x] `.gitignore` covers `data/`, `*.db`, `*.sqlite`, `*.parquet`, `*.pkl`, `*.joblib`, and OS/editor files
- [x] No tracked artifacts in `data/` or blobs
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `.gitignore` (modify)

---

### Task 0.2: Human decision on library standards alignment (confirmed)

**Type:** Human Decision

**Description:**
Library list confirmed: uv, ruff, typer, rich, flet, docling, sentence-transformers, lancedb, Piccolo ORM (SQLite backend). Document any deviations from the guide table.

**Acceptance Criteria:**
- [x] Preferred libraries and rationale documented in `docs/library-standards.md`
- [x] Confirmed list captured (no deviations expected unless explicitly noted)
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `docs/library-standards.md` (create)

---

### Task 0.3: Define project module layout and package skeleton

**Type:** Implement

**Description:**
Create the module structure described in Appendix C of the design doc, with importable packages and no business logic.

**Acceptance Criteria:**
- [x] `src/papers/` package and subpackages exist and import cleanly
- [x] No runtime side effects during import
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/` (create)

---

### Task 0.4: Test protocol contracts for ports

**Type:** Test

**Description:**
Write contract tests for the interfaces in Section 14 (JobQueue, PaperStore, ExtractionStore, BlobStore, VectorIndex, Converter, Embedder, LLMClient, ScholarClient).

**Acceptance Criteria:**
- [ ] Tests cover each protocol method signature and error expectations
- [x] Tests use fake implementations
- [x] Coverage ≥95% for interface modules
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/ports/` (create)
- `src/papers/app/ports.py` (create)

---

### Task 0.5: Implement protocol definitions and custom exception hierarchy

**Type:** Implement

**Description:**
Add Protocols in `ports.py` and define a base exception hierarchy for domain and infrastructure errors.

**Acceptance Criteria:**
- [x] Protocols match design doc Section 14
- [x] Exception hierarchy aligns with guide error handling standards
- [x] All contract tests pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/ports.py` (create)
- `src/papers/domain/errors.py` (create)

---

### Task 0.6: Test configuration validation

**Type:** Test

**Description:**
Define tests for configuration parsing and required settings (paths, embedding model, LLM profiles, etc.).

**Acceptance Criteria:**
- [x] Invalid configs fail fast with meaningful errors
- [x] Default config loads successfully
- [ ] Coverage ≥95% for config validation
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/config/` (create)
- `src/papers/config/` (create)

---

### Task 0.7: Implement configuration module

**Type:** Implement

**Description:**
Implement settings loading and validation (e.g., `settings.toml`), including paths for data/blobs/db and defaults.

**Acceptance Criteria:**
- [x] Config module validates required fields
- [x] Config errors raise ConfigurationError
- [x] Tests from Task 0.6 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/config/settings.py` (create)
- `src/papers/config/defaults.toml` (create)

---

### Task 0.8: Define logging patterns and context requirements

**Type:** Document

**Description:**
Specify structured logging fields (job_id, paper_id, run_id, job.type, status transition) per design doc Section 12.

**Acceptance Criteria:**
- [x] Logging context schema documented
- [x] Explicit list of required fields per log event
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `docs/logging-standards.md` (create)

---

**Phase 0 Exit Criteria:**
- [ ] Interfaces documented with docstrings
- [x] Exception types defined
- [x] Config validation implemented and tested
- [ ] Coverage ≥95% on foundation code
- [ ] **Stage changes for human review**

---

## Phase 1: Core Domain (Coverage ≥95%)

### Task 1.1: Test domain models and value objects

**Type:** Test

**Description:**
Write unit tests for domain models and validation rules: Paper, Candidate, Project, Tag, Prompt, PromptVersion, AnalysisRun, Job, Extraction.

**Acceptance Criteria:**
- [x] Tests cover required fields, enums, and invariants
- [x] Tests cover invalid inputs and errors
- [x] Coverage ≥95% for domain
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/domain/` (create)

---

### Task 1.2: Implement domain models and policies

**Type:** Implement

**Description:**
Implement Pydantic models, enums, and policy helpers (idempotency keys, pipeline stage/health rules).

**Acceptance Criteria:**
- [x] Models align with design doc Section 5 and 9
- [x] Domain policies are pure (no I/O)
- [x] Tests from Task 1.1 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/domain/models.py` (create)
- `src/papers/domain/policies.py` (create)

---

### Task 1.3: Test domain error behavior

**Type:** Test

**Description:**
Write tests for domain exception hierarchy behaviors and messages in invalid state transitions.

**Acceptance Criteria:**
- [x] Domain exceptions raised with actionable messages
- [x] Coverage ≥95% for domain errors
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/domain/test_errors.py` (create)

---

### Task 1.4: Implement domain error behaviors

**Type:** Implement

**Description:**
Add domain-specific error classes and helpers (e.g., InvalidStateTransition, NotReady, OutputValidationFailed).

**Acceptance Criteria:**
- [x] Error types map to design doc error taxonomy
- [x] Tests from Task 1.3 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/domain/errors.py` (modify)

---

**Phase 1 Exit Criteria:**
- [x] Domain models fully tested and pure
- [x] Domain exceptions validated
- [x] Coverage ≥95% on domain layer
- [ ] **Stage changes for human review**

---

## Phase 2: Primary Implementation (Coverage ≥90%)

### Task 2.1: Test Piccolo ORM models and stores

**Type:** Test

**Description:**
Create tests for Piccolo ORM models/migrations (tables, constraints, FTS) and store behavior (PaperStore, ExtractionStore, JobQueue).

**Acceptance Criteria:**
- [ ] Schema matches design doc Section 5
- [ ] Tests validate unique constraints and CHECKs
- [x] Tests cover job enqueue idempotency
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/infra/piccolo/` (create)

---

### Task 2.2: Implement Piccolo ORM models and stores

**Type:** Implement

**Description:**
Add Piccolo ORM models + migrations and store implementations, including FTS tables and indexes.

**Acceptance Criteria:**
- [ ] Schema and migrations align with design doc
- [x] Store methods implement ports interfaces
- [x] Tests from Task 2.1 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/infra/piccolo/` (create)

---

### Task 2.3: Test blob store behavior

**Type:** Test

**Description:**
Write tests for filesystem blob store: atomic writes, fingerprinting, and path layout.

**Acceptance Criteria:**
- [x] Atomic write behavior verified
- [x] Fingerprints are deterministic
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/infra/blobs_fs/` (create)

---

### Task 2.4: Implement filesystem blob store

**Type:** Implement

**Description:**
Implement blob store with XXH64 fingerprinting and atomic writes per Section 6.

**Acceptance Criteria:**
- [x] Path layout matches design doc
- [x] Atomic writes on success; temp files on failure
- [x] Tests from Task 2.3 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/infra/blobs_fs/` (create)

---

### Task 2.5: Test vector index adapter

**Type:** Test

**Description:**
Write tests for LanceDB adapter (upsert/query) using a temporary database.

**Acceptance Criteria:**
- [x] Upsert and query return expected paper_id rankings
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/infra/lancedb/` (create)

---

### Task 2.6: Implement LanceDB adapter

**Type:** Implement

**Description:**
Implement vector index adapter that stores vectors only and uses Piccolo ORM (SQLite backend) for metadata.

**Acceptance Criteria:**
- [x] Adapter implements VectorIndex protocol
- [x] Tests from Task 2.5 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/infra/lancedb/` (create)

---

### Task 2.7: Test external adapters and error translation

**Type:** Test

**Description:**
Write tests for Docling converter, sentence-transformers embedder, and OpenAI-compatible LLM adapter error translation.

**Acceptance Criteria:**
- [ ] External errors map to domain errors
- [ ] Timeouts and retries behave as expected
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/infra/converter_docling/` (create)
- `tests/infra/embedder_st/` (create)
- `tests/infra/llm_openai_compat/` (create)

---

### Task 2.8: Implement external adapters

**Type:** Implement

**Description:**
Implement Docling converter, sentence-transformers embedder, and OpenAI-compatible LLM client.

**Acceptance Criteria:**
- [x] Adapters implement port protocols
- [ ] Error translation matches domain taxonomy
- [x] Tests from Task 2.7 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/infra/converter_docling/` (create)
- `src/papers/infra/embedder_st/` (create)
- `src/papers/infra/llm_openai_compat/` (create)

---

### Task 2.9: Test use-case orchestration (happy path)

**Type:** Test

**Description:**
Write tests for use-cases in Section 15 and job runner orchestration (download→convert→embed→analyze).

**Acceptance Criteria:**
- [x] Orchestration follows idempotency rules
- [x] Happy path pipeline completes
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/use_cases/` (create)
- `tests/app/job_runner/` (create)

---

### Task 2.10: Implement use-cases and job runner

**Type:** Implement

**Description:**
Implement application layer use-cases and job runner/handlers per design doc Sections 9 and 15.

**Acceptance Criteria:**
- [x] Use-cases orchestrate and validate state transitions
- [x] Job runner claims, retries, and cancels appropriately
- [x] Tests from Task 2.9 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/use_cases/` (create)
- `src/papers/app/job_runner/` (create)

---

**Phase 2 Exit Criteria:**
- [x] End-to-end pipeline happy path passes
- [x] Adapters implement interfaces
- [ ] Structured logging at service boundaries
- [x] Coverage ≥90%
- [ ] **Stage changes for human review**

---

## Phase 3: Integration (Coverage ≥90%)

### Task 3.1: Test real dependency integration

**Type:** Test

**Description:**
Write integration tests for Piccolo ORM (SQLite backend), LanceDB, and Docling using local resources.

**Acceptance Criteria:**
- [x] Tests run against real dependencies
- [x] Tests can be skipped in CI with markers if needed
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/integration/` (create)

---

### Task 3.2: Implement real adapter configuration and DI

**Type:** Implement

**Description:**
Create composition root for wiring concrete adapters and config.

**Acceptance Criteria:**
- [x] Dependency wiring is centralized
- [x] Uses validated config
- [x] Tests from Task 3.1 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/composition_root.py` (create)

---

### Task 3.3: Test error paths and retries

**Type:** Test

**Description:**
Write tests for download/convert/embed/analyze failures, retry logic, and cooperative cancellation.

**Acceptance Criteria:**
- [x] Retryable vs permanent errors tested
- [x] Cancellation stops work safely
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/job_runner/test_errors.py` (create)

---

### Task 3.4: Implement error handling and cancellation

**Type:** Implement

**Description:**
Add retry backoff policies, error code mapping, and cooperative cancellation checks.

**Acceptance Criteria:**
- [x] Error handling aligns with design doc Section 9.4 and 9.7
- [x] Tests from Task 3.3 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/job_runner/` (modify)

---

**Phase 3 Exit Criteria:**
- [x] Real integration tests passing or explicitly marked
- [x] Error paths handled and logged
- [x] Coverage ≥90%
- [ ] **Stage changes for human review**

---

## Phase 4: Discovery & Search (Coverage ≥90%)

### Task 4.1: Test Semantic Scholar adapter

**Type:** Test

**Description:**
Write tests for Semantic Scholar API client including search, pagination, rate limiting, and error handling.

**Acceptance Criteria:**
- [x] Search returns candidate records with required fields
- [x] Pagination handles multiple pages correctly
- [x] Rate limiting and retry logic tested
- [x] Network errors map to domain errors
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/infra/scholar_s2/` (create)

---

### Task 4.2: Implement Semantic Scholar adapter

**Type:** Implement

**Description:**
Implement ScholarClient protocol using Semantic Scholar API with rate limiting and error translation per design doc Section 14.

**Acceptance Criteria:**
- [x] Adapter implements ScholarClient protocol
- [x] API key handling via config
- [x] Rate limiting respects API limits
- [x] Tests from Task 4.1 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/infra/scholar_s2/` (create)

---

### Task 4.3: Test discovery use-cases

**Type:** Test

**Description:**
Write tests for DiscoverCandidatesUseCase, RejectCandidateUseCase, ImportCandidateUseCase per design doc Section 15.

**Acceptance Criteria:**
- [x] Discover creates candidate records
- [x] Import creates paper and enqueues download job
- [x] Reject marks candidate as rejected
- [x] Idempotency rules enforced
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/use_cases/test_discovery.py` (create)

---

### Task 4.4: Implement discovery use-cases

**Type:** Implement

**Description:**
Implement discovery and import orchestration, including candidate management and job enqueuing.

**Acceptance Criteria:**
- [x] DiscoverCandidatesUseCase calls ScholarClient and stores candidates
- [x] ImportCandidateUseCase creates paper and enqueues download
- [x] RejectCandidateUseCase marks candidate rejected
- [x] Tests from Task 4.3 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/use_cases/discovery.py` (create)

---

### Task 4.5: Test search and querying use-cases

**Type:** Test

**Description:**
Write tests for paper search (FTS + vector), filtering, and aggregation per design doc Section 10.

**Acceptance Criteria:**
- [x] Hybrid search (FTS + vector + RRF) tested
- [x] Filter by extracted fields tested
- [x] Aggregation queries tested
- [x] Latest successful run selection tested
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/use_cases/test_search.py` (create)

---

### Task 4.6: Implement search and querying use-cases

**Type:** Implement

**Description:**
Implement SearchPapersUseCase, FilterByExtractionsUseCase, AggregateExtractionsUseCase with hybrid search (Section 10).

**Acceptance Criteria:**
- [x] Hybrid search uses FTS + vector + RRF fusion
- [x] Filtering scoped to latest successful runs
- [x] Aggregation queries group by extracted fields
- [x] Tests from Task 4.5 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/use_cases/search.py` (create)

---

**Phase 4 Exit Criteria:**
- [ ] Discovery and import working end-to-end
- [x] Hybrid search implemented and tested
- [x] Coverage ≥90%
- [ ] **Stage changes for human review**

---

## Phase 5: Analysis & Taxonomy (Coverage ≥90%)

### Task 5.1: Test full analysis use-cases

**Type:** Test

**Description:**
Write tests for RunAnalysisUseCase, ReanalyzeWithPromptVersionUseCase, AnalyzeProjectUseCase per design doc Section 15.

**Acceptance Criteria:**
- [ ] RunAnalysisUseCase handles idempotency and force flag
- [x] ReanalyzeWithPromptVersionUseCase processes scope correctly
- [ ] AnalyzeProjectUseCase applies filters
- [x] Job enqueuing and run creation tested
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/use_cases/test_analysis_full.py` (create)

---

### Task 5.2: Implement full analysis use-cases

**Type:** Implement

**Description:**
Implement complete analysis orchestration including idempotency, force semantics, and project-wide analysis per Section 9.2.

**Acceptance Criteria:**
- [x] RunAnalysisUseCase implements idempotency key logic (Section 9.2)
- [x] Force flag creates new runs correctly
- [ ] ReanalyzeWithPromptVersionUseCase handles scope and filters
- [x] Tests from Task 5.1 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/use_cases/analysis.py` (create or modify)

---

### Task 5.3: Test prompt management use-cases

**Type:** Test

**Description:**
Write tests for CreatePromptUseCase, CreatePromptVersionUseCase with validation per design doc Section 8.

**Acceptance Criteria:**
- [x] Prompt creation with metadata tested
- [x] Version creation validates output_format
- [x] Schema validation for extraction_schema_json tested
- [x] markdown_only format prevents schema
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/use_cases/test_prompts.py` (create)

---

### Task 5.4: Implement prompt management use-cases

**Type:** Implement

**Description:**
Implement prompt and version creation with schema validation per Section 8.

**Acceptance Criteria:**
- [x] CreatePromptUseCase stores prompt metadata
- [x] CreatePromptVersionUseCase validates schema
- [x] Latest version selection logic implemented
- [x] Tests from Task 5.3 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/use_cases/prompts.py` (create)

---

### Task 5.5: Test taxonomy use-cases

**Type:** Test

**Description:**
Write tests for CreateTagUseCase, AttachTagToPaperUseCase, CreateProjectUseCase, AttachPaperToProjectUseCase per Section 15.

**Acceptance Criteria:**
- [x] Tag creation and attachment tested
- [x] Project creation and paper linking tested
- [x] Confidence scores and labels tested
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/use_cases/test_taxonomy.py` (create)

---

### Task 5.6: Implement taxonomy use-cases

**Type:** Implement

**Description:**
Implement tags and projects management for organizing papers and analysis results.

**Acceptance Criteria:**
- [x] CreateTagUseCase creates tag with type
- [x] AttachTagToPaperUseCase links tags with confidence
- [x] CreateProjectUseCase creates project
- [x] AttachPaperToProjectUseCase links papers with labels
- [x] Tests from Task 5.5 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/use_cases/taxonomy.py` (create)

---

### Task 5.7: Test admin and repair use-cases

**Type:** Test

**Description:**
Write tests for RecoverStuckJobsUseCase and RebuildVectorIndexUseCase per Section 15.

**Acceptance Criteria:**
- [x] Stuck job recovery identifies and requeues jobs
- [x] Vector index rebuild re-embeds all papers
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/use_cases/test_admin.py` (create)

---

### Task 5.8: Implement admin and repair use-cases

**Type:** Implement

**Description:**
Implement administrative operations for system maintenance and recovery.

**Acceptance Criteria:**
- [x] RecoverStuckJobsUseCase requeues stale running jobs
- [x] RebuildVectorIndexUseCase clears and rebuilds vector index
- [x] Tests from Task 5.7 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/use_cases/admin.py` (create)

---

**Phase 5 Exit Criteria:**
- [ ] All use-cases from Section 15 implemented
- [x] Analysis idempotency and force semantics working
- [x] Prompt and taxonomy management complete
- [x] Coverage ≥90%
- [ ] **Stage changes for human review**

---

## Phase 6: CLI Development (Coverage ≥90%)

### Task 6.1: Test CLI command structure and help

**Type:** Test

**Description:**
Write tests verifying CLI command registration, help text, and argument parsing for all commands.

**Acceptance Criteria:**
- [x] All commands register without errors
- [ ] Help text displays correctly for each command
- [x] Required/optional arguments parsed correctly
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/cli/test_commands.py` (create)

---

### Task 6.2: Implement CLI app structure with typer

**Type:** Implement

**Description:**
Create typer-based CLI application structure with command groups per design doc Section 16.

**Acceptance Criteria:**
- [x] CLI uses typer for command structure
- [x] Rich formatting for output
- [x] Config loading at startup
- [x] Tests from Task 6.1 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/cli/app.py` (create)
- `src/papers/cli/__main__.py` (create)

---

### Task 6.3: Test discovery and import CLI commands

**Type:** Test

**Description:**
Write integration tests for `discover` and `import` commands.

**Acceptance Criteria:**
- [x] discover command calls DiscoverCandidatesUseCase
- [x] import command calls ImportCandidateUseCase
- [x] Output formatting tested
- [x] Error handling tested
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/cli/test_discovery_commands.py` (create)

---

### Task 6.4: Implement discovery and import CLI commands

**Type:** Implement

**Description:**
Implement `papers discover` and `papers import` commands with rich output formatting.

**Acceptance Criteria:**
- [x] discover command with query and filters
- [x] import command with candidate selection
- [x] Rich tables for candidate display
- [x] Tests from Task 6.3 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/cli/commands/discovery.py` (create)

---

### Task 6.5: Test pipeline and analysis CLI commands

**Type:** Test

**Description:**
Write integration tests for `run-jobs`, `analyze`, and status commands.

**Acceptance Criteria:**
- [x] run-jobs command processes queue
- [x] analyze command enqueues analysis jobs
- [x] status command displays job queue state
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/cli/test_pipeline_commands.py` (create)

---

### Task 6.6: Implement pipeline and analysis CLI commands

**Type:** Implement

**Description:**
Implement `papers run-jobs`, `papers analyze`, and `papers status` commands.

**Acceptance Criteria:**
- [x] run-jobs with daemon mode option
- [x] analyze with prompt and profile selection
- [ ] status with job queue visualization
- [x] Tests from Task 6.5 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/cli/commands/pipeline.py` (create)

---

### Task 6.7: Test query and filter CLI commands

**Type:** Test

**Description:**
Write integration tests for `query`, `filter`, and `aggregate` commands.

**Acceptance Criteria:**
- [x] query command performs hybrid search
- [x] filter command applies extraction filters
- [x] aggregate command groups and summarizes
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/cli/test_query_commands.py` (create)

---

### Task 6.8: Implement query and filter CLI commands

**Type:** Implement

**Description:**
Implement `papers query`, `papers filter`, and `papers aggregate` commands with rich tables.

**Acceptance Criteria:**
- [x] query with text search and vector similarity
- [x] filter by extracted fields and values
- [x] aggregate with grouping and counts
- [x] Tests from Task 6.7 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/cli/commands/query.py` (create)

---

### Task 6.9: Test admin CLI commands

**Type:** Test

**Description:**
Write tests for administrative commands (recover-jobs, rebuild-index).

**Acceptance Criteria:**
- [x] recover-jobs identifies and fixes stuck jobs
- [x] rebuild-index rebuilds vector store
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/cli/test_admin_commands.py` (create)

---

### Task 6.10: Implement admin CLI commands

**Type:** Implement

**Description:**
Implement administrative commands for system maintenance.

**Acceptance Criteria:**
- [x] papers recover-jobs command
- [x] papers rebuild-index command
- [x] Tests from Task 6.9 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/cli/commands/admin.py` (create)

---

**Phase 6 Exit Criteria:**
- [x] All CLI commands from Section 16 implemented
- [x] Rich output formatting working
- [x] CLI integration tests passing
- [x] Coverage ≥90%
- [ ] **Stage changes for human review**

---

## Phase 7: UI Development (Coverage ≥90%)

### Task 7.1: Test UI app structure and navigation

**Type:** Test

**Description:**
Write tests for Flet app initialization, navigation between screens, and state management.

**Acceptance Criteria:**
- [x] App initializes without errors
- [x] Screen navigation works correctly
- [x] State management tested
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/ui/test_app.py` (create)

---

### Task 7.2: Implement UI app structure with Flet

**Type:** Implement

**Description:**
Create Flet application structure with navigation and screen management per Section 16.

**Acceptance Criteria:**
- [ ] Flet app with navigation drawer/tabs
- [x] Screen routing implemented
- [x] Config loading at startup
- [x] Tests from Task 7.1 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/ui/app.py` (create)
- `src/papers/ui/__main__.py` (create)

---

### Task 7.3: Test Search/Import screen

**Type:** Test

**Description:**
Write tests for search input, candidate display, and import functionality.

**Acceptance Criteria:**
- [x] Search form calls DiscoverCandidatesUseCase
- [x] Candidate list displays results
- [x] Import button calls ImportCandidateUseCase
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/ui/test_search_screen.py` (create)

---

### Task 7.4: Implement Search/Import screen

**Type:** Implement

**Description:**
Build search and import UI with query input, results table, and import buttons.

**Acceptance Criteria:**
- [x] Search form with query and filters
- [ ] Candidate results in data table
- [x] Import and reject buttons functional
- [x] Tests from Task 7.3 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/ui/screens/search.py` (create)

---

### Task 7.5: Test Paper Detail screen

**Type:** Test

**Description:**
Write tests for paper detail view including metadata, analysis runs, and extracted fields.

**Acceptance Criteria:**
- [x] Paper metadata displays correctly
- [x] Analysis runs list shown
- [x] Extracted fields displayed by prompt version
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/ui/test_paper_screen.py` (create)

---

### Task 7.6: Implement Paper Detail screen

**Type:** Implement

**Description:**
Build paper detail view with metadata, pipeline status, runs, and extractions.

**Acceptance Criteria:**
- [x] Paper info card with title and metadata
- [x] Pipeline stage and health indicator
- [x] Analysis runs table with timestamps
- [x] Extracted fields viewer
- [x] Tests from Task 7.5 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/ui/screens/paper.py` (create)

---

### Task 7.7: Test Jobs/Runs monitor screen

**Type:** Test

**Description:**
Write tests for job queue display, run history, and status filtering.

**Acceptance Criteria:**
- [x] Job queue displays active jobs
- [x] Run history shows completed analyses
- [x] Status filtering works
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/ui/test_monitor_screen.py` (create)

---

### Task 7.8: Implement Jobs/Runs monitor screen

**Type:** Implement

**Description:**
Build monitoring dashboard for job queue and analysis run history.

**Acceptance Criteria:**
- [x] Job queue table with status and progress
- [x] Run history with filters
- [x] Refresh/auto-update functionality
- [x] Tests from Task 7.7 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/ui/screens/monitor.py` (create)

---

### Task 7.9: Test Query/Filter screen

**Type:** Test

**Description:**
Write tests for query builder, filter controls, and results display.

**Acceptance Criteria:**
- [x] Query input calls SearchPapersUseCase
- [x] Filter controls apply extraction filters
- [ ] Results table displays matched papers
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/ui/test_query_screen.py` (create)

---

### Task 7.10: Implement Query/Filter screen

**Type:** Implement

**Description:**
Build query interface with hybrid search, filter controls, and results.

**Acceptance Criteria:**
- [x] Text search input
- [x] Filter by extracted field values
- [ ] Results table with relevance scores
- [x] Export functionality
- [x] Tests from Task 7.9 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/ui/screens/query.py` (create)

---

**Phase 7 Exit Criteria:**
- [x] All UI screens from Section 16 implemented
- [x] Flet UI functional and tested
- [x] Navigation and state management working
- [x] Coverage ≥90%
- [ ] **Stage changes for human review**

---

## Phase 8: Hardening (Coverage ≥90%)

### Task 8.1: Test structured logging output

**Type:** Test

**Description:**
Write tests to validate logging fields and formats per docs/logging-standards.md.

**Acceptance Criteria:**
- [x] Logs include job_id, paper_id, run_id context
- [x] Log levels match event severity
- [x] Structured fields extractable
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/observability/test_logging.py` (create)

---

### Task 8.2: Implement structured logging

**Type:** Implement

**Description:**
Add structured logging throughout application layer per Section 12.2.

**Acceptance Criteria:**
- [ ] Logging at all state transitions
- [ ] Context fields included in all log entries
- [x] Log levels follow documented standards
- [x] Tests from Task 8.1 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/job_runner/runner.py` (modify)
- `src/papers/app/use_cases/` (modify)

---

### Task 8.3: Test metrics emission

**Type:** Test

**Description:**
Write tests for metrics hooks and data collection per Section 12.3.

**Acceptance Criteria:**
- [x] Job duration metrics emitted
- [x] Failure metrics by error code
- [x] Token and cost tracking for LLM calls
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/observability/test_metrics.py` (create)

---

### Task 8.4: Implement metrics hooks

**Type:** Implement

**Description:**
Add metrics instrumentation at key decision points per Section 12.3.

**Acceptance Criteria:**
- [ ] Metrics for job durations (p50/p95)
- [x] Metrics for failures by type and error code
- [x] Token usage and cost metrics
- [x] Tests from Task 8.3 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/job_runner/runner.py` (modify)
- `src/papers/app/use_cases/analysis.py` (modify)

---

### Task 8.5: Test configuration fail-fast behavior

**Type:** Test

**Description:**
Verify startup failure for invalid config or missing dependencies.

**Acceptance Criteria:**
- [ ] Invalid paths fail fast with clear errors
- [x] Missing required fields caught at startup
- [x] Dependency availability checked
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/config/test_fail_fast.py` (create)

---

### Task 8.6: Implement startup validation

**Type:** Implement

**Description:**
Add startup checks in composition root for config and dependencies.

**Acceptance Criteria:**
- [x] Config validation at startup
- [x] Directory existence checks
- [x] Dependency availability verification
- [x] Clear error messages for failures
- [x] Tests from Task 8.5 pass
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `src/papers/app/composition_root.py` (modify)

---

### Task 8.7: Security review and documentation

**Type:** Document

**Description:**
Complete security review checklist per Section 13 covering secrets, inputs, and outputs.

**Acceptance Criteria:**
- [x] API key storage in OS keychain documented
- [x] Input validation at boundaries documented
- [x] SQL injection prevention verified
- [x] XSS prevention in UI documented
- [x] Security checklist complete
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `docs/security-review.md` (create)

---

**Phase 8 Exit Criteria:**
- [x] Structured logging and metrics working
- [x] Fail-fast validation at startup
- [x] Security review complete
- [x] Coverage ≥90%
- [ ] **Stage changes for human review**

---

## Phase 9: Polish & Documentation (Coverage ≥90%)

### Task 9.1: Document architecture and design decisions

**Type:** Document

**Description:**
Update README and create ADRs for key architectural decisions.

**Acceptance Criteria:**
- [x] README explains setup and basic usage
- [ ] ADRs for LanceDB, Docling, Piccolo choices
- [ ] ADR for prompt system design
- [ ] ADR for hybrid search approach
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `README.md` (modify)
- `docs/adr/001-lancedb-vector-store.md` (create)
- `docs/adr/002-docling-converter.md` (create)
- `docs/adr/003-piccolo-orm.md` (create)
- `docs/adr/004-prompt-system.md` (create)
- `docs/adr/005-hybrid-search.md` (create)

---

### Task 9.2: Document user workflows

**Type:** Document

**Description:**
Create usage guides for common workflows (discover, import, analyze, query).

**Acceptance Criteria:**
- [ ] Discovery and import workflow documented
- [ ] Analysis workflow with prompts documented
- [ ] Query and filter workflow documented
- [ ] CLI examples provided
- [ ] UI screenshots included
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `docs/workflows/discovery.md` (create)
- `docs/workflows/analysis.md` (create)
- `docs/workflows/querying.md` (create)

---

### Task 9.3: Test composition root thoroughly

**Type:** Test

**Description:**
Add comprehensive tests for composition_root.py to close coverage gap from Phase 3.

**Acceptance Criteria:**
- [x] Container builds successfully with valid settings
- [ ] All dependencies wired correctly
- [x] Config validation failures handled
- [x] API key propagation tested
- [x] Database initialization tested
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/test_composition_root.py` (create)

---

### Task 9.4: Implement composition root tests

**Type:** Implement

**Description:**
Close Phase 3 gap by testing composition root dependency wiring.

**Acceptance Criteria:**
- [x] Tests from Task 9.3 implemented
- [x] composition_root.py coverage >90%
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `tests/app/test_composition_root.py` (modify)

---

### Task 9.5: Final code cleanup and refactoring

**Type:** Refactor

**Description:**
Perform final refactor for naming consistency, remove TODOs, improve code quality.

**Acceptance Criteria:**
- [x] No unresolved TODOs without GitHub issues
- [x] Naming follows project conventions consistently
- [ ] Code passes ruff linting with no warnings
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- (various)

---

### Task 9.6: Final coverage verification

**Type:** Test

**Description:**
Verify ≥90% coverage across all modules and generate coverage report.

**Acceptance Criteria:**
- [x] Overall coverage ≥90%
- [ ] All modules ≥85% coverage
- [ ] Coverage report generated and committed
- [x] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `docs/coverage-report.md` (create)

---

**Phase 9 Exit Criteria:**
- [ ] Documentation complete for new developers
- [x] All TODOs tracked or resolved
- [x] Coverage ≥90% verified
- [x] Code quality standards met
- [ ] **Stage changes for human review**

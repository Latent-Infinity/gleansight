# Research Paper Analysis Platform — Design Doc (v0.9)

> **Product direction (2026-08-18):** gleansight is becoming a **general NS/QD-inspired discovery platform**. This document remains the **evidence layer** (papers, jobs, extractions, hybrid search). Discovery jobs will use a separate `nsqd_jobs` table so the paper `jobs` CHECK (discover/download/convert/embed/analyze only) stays valid. See `docs/product-gleansight.md`, `docs/glossary-nsqd.md`, `docs/algorithm-contract-nsqd.md`.

## Document Info
- **Status:** Draft (evidence layer; still in force for `src/papers`)
- **Version:** 0.9
- **Last Updated:** 2026-01-27 (banner 2026-08-18)
- **Target:** Desktop, single-user, local-first
- **Language:** Python 3.12+
- **UI:** Flet (thin client)
- **CLI:** typer + rich (thin client)
- **Storage (Rule of Three):**
  - **Metadata/relationships/job persistence:** Piccolo ORM (SQLite backend)
  - **Vector index:** LanceDB (derived/rebuildable)
  - **Blobs:** local filesystem (PDF/MD/analysis artifacts)
- **PDF → Text:** Docling (converter)
- **Embeddings:** sentence-transformers (default), configurable
- **LLM:** OpenAI-compatible endpoints (adapter)
- **ORM:** Piccolo (SQLite backend)
- **Tooling:** uv + ruff

---

## 0) Core Guiding Principles (Canonical)

### 0.1 Favor Composition over “God” Classes (SOLID)
- Avoid monolithic services. Each component does one thing and exposes narrow Protocols.
- **Rule of Three:** Metadata, Vectors, Blobs are distinct stores.
- **Action:** If a class needs **>3–4 infrastructure dependencies**, split it into smaller composable use-cases.

### 0.2 The Use-Case is the Source of Truth (DRY)
- Orchestration, validation, state transitions, idempotency rules live in the **Application Layer**.
- Thin clients: UI/CLI capture intent and call use-cases.
- No leaky logic: UI/CLI never hashes files, writes DB rows, or calls external APIs directly.

### 0.3 Modern, High-Performance Tooling (KISS)
- uv for dependency/env management
- ruff for linting/formatting
- typer for CLI structure; rich for output

### 0.4 Deterministic & Recoverable Pipelines
- Durable job rows are the system of record for work.
- Every unit of work is a job row; crash recovery is automatic.
- Idempotency: rerunning on unchanged inputs is a no-op.

### 0.5 Hybrid Content Addressing (Performance-First)
- PDFs are content-addressed by **XXH64** (xxHash) for throughput.
- Derived artifacts are keyed by logical IDs for UX convenience **AND** store fingerprints where needed for idempotency/integrity.
- Dedup relies on external IDs first, then PDF fingerprint.
- Traceability: every AnalysisRun links to prompt_version_id and snapshots endpoint settings at run time.

---

## 1) Terminology (Glossary)
- **Candidate:** Paper returned by discovery; not yet in corpus.
- **Corpus Paper (Paper):** Explicitly imported; participates in pipeline/jobs/projects/tags/analysis.
- **Pipeline stage:** Highest milestone achieved: `imported|downloaded|converted|embedded|analyzed` (monotonic).
- **Job:** Durable unit of work: `discover|download|convert|embed|analyze`.
- **AnalysisRun:** Durable record tying `paper_id + prompt_version_id + profile + model` to outputs.
- **Structured output portion:** The part intended for parsing (YAML block, JSON block, JSON-only).
- **Extraction:** Queryable values parsed from the structured output portion.
- **Field path:** Deterministic string key for extracted values (dot/bracket notation).
- **Endpoint Profile:** Named OpenAI-compatible endpoint configuration; secrets stored in keychain.

---

## 2) Overview
The platform:
- discovers papers (Semantic Scholar search + graph expansion),
- persists discovery results for recoverability,
- imports selected papers into a corpus with projects/tags,
- downloads PDFs, converts to Markdown/text, embeds and indexes content,
- runs prompt-driven analysis with OpenAI-compatible endpoints,
- stores artifacts, provenance, structured extractions, and reproducible metadata,
- exposes a desktop UX + CLI.

---

## 3) Goals / Non-Goals

### 3.1 Goals (v1)
- Topic-agnostic platform: domain-specific prompts are user-defined and selectable per run.
- Deterministic, resumable pipeline with durable job state.
- Multi-project membership and manual tagging.
- Prompt versioning with reproducible runs.
- Text search (FTS) + semantic search (LanceDB) + hybrid fusion (RRF).
- Structured extraction from analysis output:
  - `yaml_block | json_block | json_only | markdown_only`

### 3.2 Non-Goals (v1)
- OCR for scanned PDFs
- Paywall bypass automation
- Multi-user collaboration/auth
- Analysis chaining / dependent analyses (deferred)
- Corpus-level synthesis and contradiction detection (deferred)

---

## 4) Architecture (KISS + SOLID boundaries)

### A) Application Layer
- Use-cases + JobRunner + job handlers.
- Owns orchestration, validation, idempotency, state transitions.

### B) Ports (Protocols)
- Narrow interfaces for stores, queue, blob store, vector index, converter, embedder, LLM client, scholar client.

### C) Infrastructure Adapters
- Piccolo ORM stores (SQLite backend)
- LanceDB vector index
- filesystem blob store
- docling converter
- sentence-transformers embedder
- OpenAI-compatible LLM adapter
- Semantic Scholar adapter

### D) Thin Clients
- Flet UI calls use-cases
- CLI calls use-cases

---

## 5) Data Model (SQLite via Piccolo ORM) — Implementation-Ready

### 5.1 ID + timestamp conventions
- All entity IDs are ULID strings unless noted:
  - `candidate_id, paper_id, project_id, tag_id, prompt_id, prompt_version_id, run_id, job_id, profile_id, extraction_id`
- All tables include `created_at` (UTC). Mutable tables include `updated_at` (UTC).
- Domain timestamps (in addition): `analysis_runs.started_at/finished_at`, `jobs.run_after`, `candidates.imported_at`.

### 5.2 Tables

#### A) `candidates`
- `candidate_id` (PK, NOT NULL)
- `source` (NOT NULL)
- `source_paper_id` (NOT NULL)
- `title` (NOT NULL)
- `year` (NULL)
- `venue` (NULL)
- `authors_json` (NOT NULL default `'[]'`)
- `abstract` (NULL)
- `external_ids_json` (NULL)
- `rejected_at` (NULL)
- `imported_paper_id` (NULL)
- `imported_at` (NULL)
- `created_at` (NOT NULL)
- `updated_at` (NOT NULL)

Constraints:
- `UNIQUE(source, source_paper_id)`

#### B) `papers`
Core:
- `paper_id` (PK, NOT NULL)
- `title` (NOT NULL)
- `year` (NULL)
- `venue` (NULL)
- `authors_json` (NOT NULL default `'[]'`)
- `abstract` (NULL)

Pipeline milestone (monotonic):
- `pipeline_stage` (NOT NULL): `imported|downloaded|converted|embedded|analyzed`

Pipeline health (non-monotonic):
- `pipeline_health` (NOT NULL): `ok|error`
- `last_error_job_id` (NULL): best-effort reference; **not** a FK (job retention)
- `last_error_code` (NULL): uses error taxonomy values (Section 12.1)
- `last_error_message` (NULL)
- `last_error_at` (NULL)

Important: `pipeline_health` is affected only by stage-advancing failures:
- `download/convert/embed` failures may set `pipeline_health='error'`
- analyze failures (`LLM_ERROR`, `LLM_TIMEOUT`, `OUTPUT_PARSE_FAILED`, `OUTPUT_VALIDATION_FAILED`) do **not** set `pipeline_health='error'` by default (tracked per-run)

Artifacts/provenance:
- `pdf_fingerprint_xxh64` (NULL)
- `md_fingerprint_xxh64` (NULL)
- `md_source_pdf_fingerprint_xxh64` (NULL)
- `md_converter` (NULL)
- `md_converter_version` (NULL)

Embedding provenance (SQLite backend is source of truth via Piccolo ORM):
- `embedding_model` (NULL)
- `embedding_dimension` (NULL)
- `text_slice_strategy` (NULL)
- `embedded_from_md_fingerprint_xxh64` (NULL)

- `created_at` (NOT NULL)
- `updated_at` (NOT NULL)

#### C) `paper_external_ids`
- `paper_external_id_id` (PK, NOT NULL)
- `paper_id` (NOT NULL)
- `kind` (NOT NULL): `doi|arxiv|s2|url|...`
- `value` (NOT NULL)
- `created_at` (NOT NULL)

Constraints / indexes:
- `UNIQUE(kind, value)`
- `INDEX(paper_id)`

#### D) `projects`
- `project_id` (PK, NOT NULL)
- `name` (NOT NULL, UNIQUE)
- `description` (NULL)
- `created_at` (NOT NULL)
- `updated_at` (NOT NULL)

#### E) `tags`
- `tag_id` (PK, NOT NULL)
- `name` (NOT NULL, UNIQUE)
- `type` (NOT NULL): `subject|method|application|custom`
- `created_at` (NOT NULL)
- `updated_at` (NOT NULL)

#### F) `paper_projects`
- `paper_id` (NOT NULL)
- `project_id` (NOT NULL)
- `label` (NULL)
- `created_at` (NOT NULL)

Constraints:
- `PRIMARY KEY(paper_id, project_id)`

#### G) `paper_tags`
- `paper_id` (NOT NULL)
- `tag_id` (NOT NULL)
- `confidence` (NULL)
- `created_at` (NOT NULL)

Constraints:
- `PRIMARY KEY(paper_id, tag_id)`

#### H) `prompts` (multi-domain organization)
- `prompt_id` (PK, NOT NULL)
- `name` (NOT NULL)
- `description` (NULL)
- `domain` (NULL): e.g., `"stochastic_optimization"`, `"nlp"`
- `tags_json` (NULL): list of strings for prompt organization
- `created_at` (NOT NULL)
- `updated_at` (NOT NULL)

#### I) `prompt_versions` (generalized output/extraction contract)
- `prompt_version_id` (PK, NOT NULL)
- `prompt_id` (NOT NULL)
- `version` (NOT NULL, int increasing per prompt_id)
- `body` (NOT NULL)

Output/extraction contract:
- `output_format` (NOT NULL enum): `yaml_block | json_block | json_only | markdown_only`
- `extraction_schema_json` (NULL): JSON Schema for structured portion (if any)

Rules:
- `markdown_only`:
  - `extraction_schema_json` **MUST** be `NULL` (validated at `CreatePromptVersionUseCase`)
  - **no** `analysis_extractions` rows are created
  - run can still succeed and advance `pipeline_stage` to `analyzed` (Section 9.6)

Constraints:
- `UNIQUE(prompt_id, version)`

Latest prompt version rule:
- Latest = `MAX(version)` for prompt_id.
- If no versions exist, `RunAnalysisUseCase` raises `NoPromptVersionError`.

#### J) `endpoint_profiles`
- `profile_id` (PK, NOT NULL)
- `name` (NOT NULL, UNIQUE)
- `base_url` (NOT NULL)
- `default_model` (NULL)
- `is_active` (NOT NULL default true)

Optional pricing metadata (for cost calculation):
- `input_price_per_1k_tokens` (NULL, REAL)
- `output_price_per_1k_tokens` (NULL, REAL)

- `created_at` (NOT NULL)
- `updated_at` (NOT NULL)

Deletion rule:
- Profiles referenced by `analysis_runs` cannot be deleted (**ON DELETE RESTRICT**). Retire via `is_active=false`.

Keychain:
- `paper-manager/endpoint/{profile_name}`

#### K) `analysis_runs`
- `run_id` (PK, NOT NULL)
- `paper_id` (NOT NULL)
- `prompt_version_id` (NOT NULL)
- `profile_id` (NOT NULL)
- `model_name` (NOT NULL)

Artifacts:
- `output_blob_path_md` (NULL until written)
- `output_blob_path_json` (NULL)

Diagnostics:
- `validation_issues_json` (NULL): JSON array of `{path, severity, message, value_preview}`
- `error_message` (NULL)

Usage:
- `tokens_in` (NULL)
- `tokens_out` (NULL)
- `cost_usd` (NULL)

- `created_at` (NOT NULL)
- `started_at` (NULL)
- `finished_at` (NULL)

Status is derived from jobs:
- run status = `jobs.status` where `jobs.type='analyze'` and `jobs.run_id = analysis_runs.run_id`

Note on duplication:
- `validation_issues` is stored in both `analysis_runs.validation_issues_json` (SQL access) and `meta.json.validation_issues` (artifact access). This duplication is intentional.

#### L) `jobs`
- `job_id` (PK, NOT NULL)
- `type` (NOT NULL): `discover|download|convert|embed|analyze`
- `status` (NOT NULL): `queued|running|succeeded|failed|canceled`
- `paper_id` (NULL for discover; NOT NULL for others)
- `run_id` (NULL; required for analyze)
- `payload_json` (NOT NULL)
- `attempts` (NOT NULL)
- `max_attempts` (NOT NULL)
- `run_after` (NULL)
- `last_error` (NULL)
- `created_at` (NOT NULL)
- `updated_at` (NOT NULL)

Database-level correctness constraint (recommended):
```sql
CHECK (
  (type = 'discover') OR
  (type IN ('download','convert','embed') AND paper_id IS NOT NULL) OR
  (type = 'analyze' AND paper_id IS NOT NULL AND run_id IS NOT NULL)
)
```

Recommended unique constraints:
- Unique active stage job per `(type, paper_id)` for `download/convert/embed`:
  - `UNIQUE(type, paper_id) WHERE status IN ('queued','running') AND type IN ('download','convert','embed')`
- Unique analyze job per run:
  - `UNIQUE(run_id) WHERE type='analyze'`

#### M) `analysis_extractions` (generalized; nested/array; multi-entity-ready)
Columns:
- `extraction_id` (PK, NOT NULL)
- `run_id` (NOT NULL, FK `analysis_runs.run_id`)
- `paper_id` (NOT NULL) — denormalized
- `prompt_version_id` (NOT NULL) — denormalized
- `entity_type` (NOT NULL default `'paper'`)
- `entity_ref` (NULL)
- `field_path` (NOT NULL)
- `value_text` (NULL)
- `value_numeric` (NULL)
- `value_boolean` (NULL) — `0/1`
- `created_at` (NOT NULL)

`entity_type` values:
- v1: only `'paper'` is used
- Reserved for future: `'cited_paper'`, `'method'`, `'comparison'`, `'corpus'`
- Application **SHOULD** validate `entity_type` against allowed values per version.
- Unknown values are stored but may not be queryable in UI.

Constraints / indexes:
- `UNIQUE(run_id, entity_type, IFNULL(entity_ref,''), field_path)`
- `INDEX(paper_id, field_path)`
- `INDEX(field_path, value_text)`
- `INDEX(field_path, value_numeric) WHERE value_numeric IS NOT NULL`
- `INDEX(entity_type, entity_ref)`

### 5.3 Full-Text Search (FTS5) — decided (no options)

#### A) `papers_fts` (title/abstract)
```sql
CREATE VIRTUAL TABLE papers_fts USING fts5(
  title,
  abstract,
  paper_id UNINDEXED
);
```
Sync rule:
- PaperStore upserts `papers_fts` rows on insert/update.

#### B) `extractions_fts` (prompt-scoped free-text extracted fields)
```sql
CREATE VIRTUAL TABLE extractions_fts USING fts5(
  value_text,
  paper_id UNINDEXED,
  prompt_version_id UNINDEXED,
  entity_type UNINDEXED,
  entity_ref UNINDEXED,
  field_path UNINDEXED
);
```

SEARCHABLE_TEXT_FIELDS configuration:
- Global application config.
- Default (v1): empty set (no extraction fields indexed in FTS).
- Recommended for cross-pollination prompts:
  - `{"cross_pollination_summary", "delta_innovation_summary", "inconsistencies"}`
- Stored in config file (e.g., `config/settings.toml`) or via environment variable override.

Cleanup on re-analysis:
- Runs are immutable; re-analysis creates new runs (see Section 9.2).
- Old `analysis_extractions` and `extractions_fts` entries remain for auditability.
- “Latest” queries must select the most recent successful run (Section 10.3).

### 5.4 Extraction `field_path` encoding (nested + arrays)
- Nested objects: dot notation
  - `evaluation.rigor_rating`
- Arrays: bracket notation
  - `datasets_used[0]`
- Arrays of objects: bracket + dot
  - `comparisons[0].name`

Flattening rule:
- Store leaf scalar values (string/number/bool/null) as separate rows.
- If a leaf is unexpectedly an object/array, store JSON string in `value_text` and record a validation warning.

---

## 6) Blob Store and Atomic Writes

### 6.1 Blob layout
- PDFs: `data/blobs/pdf/{pdf_xxh64}.pdf`
- Markdown: `data/blobs/md/{paper_id}.md`
- Analysis: `data/blobs/analysis/{run_id}/`
  - `output.md`
  - `output.json` (optional)
  - `meta.json` (required)

### 6.2 Atomic writes
- Handlers write to temp paths and atomically move on success.
- Crash recovery does not clean temp files; retries overwrite with new temp names.

---

## 7) Vector Index (LanceDB) — vectors only (no duplicated metadata)

Table: `paper_embeddings`
- `paper_id` (unique)
- `embedding` (vector)
- `updated_at` (UTC timestamp)

Embedding metadata source of truth is SQLite (via Piccolo ORM) `papers.*` embedding columns.

---

## 8) Prompt System

### 8.1 Prompt body templating (v1: literal substitution)
Supported placeholders:
- `{paper_id}`
- `{title}`
- `{abstract}`
- `{authors}` (comma-separated)
- `{year}`
- `{venue}`
- `{markdown}`
- `{markdown_truncated:N}`

NULL handling:
- If a placeholder value is NULL, substitute empty string `""`.
- If `{markdown}` is required but markdown is unavailable (paper not converted), handler fails with `PAPER_NOT_READY` before calling LLM.

`{markdown_truncated:N}` semantics:
- `N` is an integer representing maximum **characters** (not tokens).
- Example: `{markdown_truncated:5000}` → first 5000 characters of markdown.
- If markdown length ≤ N, full markdown is used.
- Truncation is deterministic; no word-boundary rounding in v1.

Schema validation at creation time:
- `CreatePromptVersionUseCase` validates:
  - `output_format` is allowed
  - if `output_format == markdown_only` → `extraction_schema_json MUST be NULL`
  - if `extraction_schema_json` is present → it must be valid JSON Schema (pick one draft and enforce)

Malformed `extraction_schema_json`:
- `CreatePromptVersionUseCase` raises `InvalidExtractionSchemaError`.

---

## 9) Pipeline & Jobs

### 9.1 Job types
- `discover`: fetch discovery results and upsert candidates
- `download`: resolve + download PDF, fingerprint, store blob, update paper stage
- `convert`: PDF → MD, compute md_fingerprint, store MD, update paper stage
- `embed`: compute embedding for chosen slice, upsert LanceDB, update paper stage
- `analyze`: call LLM, store output, parse structured portion based on output_format, validate, insert analysis_extractions, update run diagnostics, advance pipeline_stage→analyzed on first success

### 9.2 Analyze idempotency and force semantics (clarified)
Idempotency key:
- `(paper_id, prompt_version_id, profile_id, model_name)`

Without `force`:
- If there exists a successful run for that key, `RunAnalysisUseCase` returns that existing `run_id` and does not create a new run/job.

With `force=True`:
- Always creates a new `analysis_run` with a new `run_id` and enqueues a new analyze job.
- Old runs remain immutable (audit trail).
- “Latest successful run” queries select `MAX(created_at)` among succeeded runs for that key.

### 9.3 Idempotency keys (including discover)
- `discover`: always executes; upsert candidates by `(source, source_paper_id)`; may refresh metadata.
- `download`: if `papers.pdf_fingerprint_xxh64` exists and blob exists → SUCCESS no-op.
- `convert`: key = `(pdf_fingerprint_xxh64, md_converter, md_converter_version_used)`; if matching MD exists → SUCCESS no-op.
- `embed`: key = `(md_fingerprint_xxh64, embedding_model, embedding_dimension, text_slice_strategy)`; if embedded_from_md matches → SUCCESS no-op.
- `analyze`: key above; no-op if successful run exists and `force=False`.

### 9.4 Convert failure classification
Error codes and retry policy:
- `CORRUPT_PDF`: permanent
- `PROTECTED_PDF`: permanent
- `EMPTY_OUTPUT`: permanent
- `CONVERTER_TIMEOUT`: retryable (backoff)
- `CONVERTER_OOM`: retryable (backoff)
- `CONVERSION_FAILED`: retryable only if transient indication; otherwise permanent

Minimum output threshold:
- If extracted text length < `MIN_MD_CHARS` (e.g., 100–500), treat as `EMPTY_OUTPUT` unless converter reports a clear failure.

### 9.5 Discover pagination and concurrency
Pagination payload:
- `request.max_results`
- `request.page_size`
- `context.continuation_token` (nullable)
- `result.candidates_found`

Policy:
- One discover job fetches pages until max_results or no more pages.
- On failure, retry from the beginning (safe due to candidate upsert idempotency).

Concurrent discover:
- Multiple discover jobs for the same query may run concurrently.
- Safe due to upsert idempotency.
- No deduplication of discover jobs is enforced.

### 9.6 Analyze handler parsing/extraction (generalized) + edge cases

Output parsing by `output_format`:
- `yaml_block`: parse first fenced ```yaml block
- `json_block`: parse first fenced ```json block
- `json_only`: parse entire output as JSON
- `markdown_only`:
  - skip structured parsing
  - create **zero** `analysis_extractions` rows
  - pipeline_stage may still advance to `analyzed` on first successful markdown_only run

Empty response handling:
- If LLM returns empty/whitespace-only:
  - treat as `OUTPUT_PARSE_FAILED` (permanent failure)
  - store empty `output.md` for debugging
  - set `analysis_runs.error_message = "LLM returned empty response"`

Partial extraction + validation policy (v1):
- If structured parsing fails entirely → `OUTPUT_PARSE_FAILED` (permanent failure)
- If parsing succeeds:
  - validate field-by-field (best effort)
  - store all valid leaf fields in `analysis_extractions`
  - record validation issues in `analysis_runs.validation_issues_json`
- Determine run success:
  - if any **required** field fails → `OUTPUT_VALIDATION_FAILED` (failed)
  - if only optional fields fail → succeeded with warnings

pipeline_stage advancement to analyzed (explicit + concurrency-safe):
- `pipeline_stage` advances to `analyzed` when the first analysis_run for that paper reaches succeeded.
- Idempotent update: if already `analyzed`, skip (safe under concurrent success).

### 9.7 Cooperative cancellation (required for long-running jobs)
Cooperative cancellation contract:
- `JobQueue.is_cancelled(job_id)` returns true if the job is canceled.
- Handlers for long-running operations (LLM calls, large downloads) poll `is_cancelled()` at safe points (between streaming chunks, between phases).
- If canceled:
  - handler stops work, cleans up temp files best-effort, returns `CANCELED`.
- JobRunner must not overwrite `canceled` status with succeeded/failed.

---

## 10) Search, Filtering, Aggregation

### 10.1 Text search
- `papers_fts` supports title/abstract search.
- Apply project/tag filters via joins.

### 10.2 Semantic search
- LanceDB search over `paper_embeddings`.
- Filters applied in SQLite (via Piccolo ORM); fusion done in application layer.

### 10.2.1 Hybrid fusion (v1) — specified
- Execute text search and semantic search independently.
- Union results by `paper_id`.
- Rank using **Reciprocal Rank Fusion (RRF)**:
  - `RRF_score(paper) = Σ 1/(k + rank_in_list)` for each list containing the paper
  - `k = 60`
- Return top N by RRF_score.
- Implementation should be a pure function (easy to swap later).

### 10.3 “Latest successful run” selection
Because runs are immutable and `force=True` can create multiple runs, filtering on extractions must specify which runs to consult.

Recommended v1 policy:
- Filter/aggregate by `prompt_version_id` and choose the latest successful run per:
  - `(paper_id, prompt_version_id, profile_id, model_name)`
  - or simply `(paper_id, prompt_version_id)` if UI constrains profile/model.

Implementation support:
- Create a view or helper query:
  - `latest_successful_runs(paper_id, prompt_version_id, profile_id, model_name, run_id)` selecting `run_id` with `MAX(created_at)` among succeeded analyze jobs.

### 10.4 Filtering by extracted fields
- Join `analysis_extractions` to `latest_successful_runs` (or a specified scope) to filter.
- Numeric fields use `value_numeric`; booleans use `value_boolean`.

### 10.5 Aggregation queries (v1 meta-analysis primitive)
Examples:
- Count papers by `algorithm_family`
- Average rigor by year
- Distribution of `base_algorithm` values

Implement via SQL on `analysis_extractions`, scoped to `prompt_version_id` and succeeded runs.

### 10.6 Full-text search over extracted narrative fields (prompt-scoped)
- Use `extractions_fts MATCH` against `value_text` and filter by:
  - `prompt_version_id`
  - `field_path`
  - `entity_type/entity_ref` (optional)

---

## 11) Cost Tracking (mechanism specified)
Cost calculation rule for `analysis_runs.cost_usd`:
- If LLM response includes a direct cost field (provider-specific), use it.
- Else if endpoint_profiles has pricing metadata configured:
  - `cost_usd = (tokens_in * input_price_per_1k / 1000) + (tokens_out * output_price_per_1k / 1000)`
- Else `cost_usd = NULL`

Tokens:
- `tokens_in/tokens_out` stored if available; otherwise NULL.

---

## 12) Observability

### 12.1 Error taxonomy (canonical)
- `RATE_LIMITED`, `NETWORK_ERROR`, `TIMEOUT`
- `NO_OPEN_PDF`, `DOWNLOAD_FAILED`
- `CORRUPT_PDF`, `PROTECTED_PDF`
- `CONVERTER_TIMEOUT`, `CONVERTER_OOM`, `EMPTY_OUTPUT`, `CONVERSION_FAILED`
- `EMBEDDING_FAILED`, `DIMENSION_MISMATCH`
- `LLM_ERROR`, `LLM_TIMEOUT`
- `OUTPUT_PARSE_FAILED`, `OUTPUT_VALIDATION_FAILED`

### 12.2 Structured logging
- Log entries include: timestamp, job_id, paper_id (if any), run_id (if any), job.type, status transition.
- Levels: DEBUG (bounded payload), INFO (transitions), WARN (retryable + validation warnings), ERROR (permanent failures).

### 12.3 Metrics
- Jobs by status (queue depth)
- Duration by type (p50/p95)
- Failures by type + error code
- Token usage and cost by prompt_version_id/model_name

---

## 13) Security & Profile Lifecycle
- Endpoint API keys stored in OS keychain:
  - `paper-manager/endpoint/{profile_name}`
- endpoint_profiles referenced by runs are not deletable; retire via `is_active=false`.
- `meta.json` snapshots endpoint settings used so runs remain reproducible.

---

## 14) Ports (Protocols) — Condensed (Restored)

The goal is implementability + testability, not maximal abstraction.

### 14.1 JobQueue
```python
from __future__ import annotations
from typing import Protocol, Any
from datetime import datetime

class Job(Protocol):
    job_id: str
    type: str
    status: str
    paper_id: str | None
    run_id: str | None
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    run_after: datetime | None

class JobQueue(Protocol):
    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str:
        """
        Idempotent enqueue for stage jobs:
        - For download/convert/embed: return existing active job_id if duplicate active job exists.
        - Throw only on unexpected storage errors.
        """

    def claim_next(self, now: datetime) -> Job | None:
        """
        Atomic claim:
        - selects one eligible queued job (run_after <= now, attempts < max_attempts)
        - transitions queued -> running
        - increments attempts
        """

    def mark_succeeded(self, job_id: str, metrics: dict[str, Any] | None = None) -> None: ...
    def mark_retryable(self, job_id: str, error: str, run_after: datetime, metrics: dict[str, Any] | None = None) -> None: ...
    def mark_failed(self, job_id: str, error: str, metrics: dict[str, Any] | None = None) -> None: ...
    def cancel(self, job_id: str) -> None: ...
    def is_cancelled(self, job_id: str) -> bool: ...
```

### 14.2 PaperStore (patching constraints; implemented via Piccolo ORM)
```python
from typing import Protocol, Any

class PaperStore(Protocol):
    # metadata
    def create_paper(self, fields: dict[str, Any]) -> str: ...
    def get(self, paper_id: str) -> dict[str, Any] | None: ...
    def update_metadata(self, paper_id: str, fields: dict[str, Any]) -> None: ...

    # artifacts/provenance
    def set_pdf_fingerprint(self, paper_id: str, pdf_xxh64: str) -> None: ...
    def set_markdown_provenance(
        self,
        paper_id: str,
        md_xxh64: str,
        src_pdf_xxh64: str,
        converter: str,
        converter_version: str,
    ) -> None: ...

    # embedding provenance (SQLite backend is source of truth via Piccolo ORM)
    def set_embedding_state(
        self,
        paper_id: str,
        embedding_model: str,
        embedding_dimension: int,
        text_slice_strategy: str,
        embedded_from_md_xxh64: str,
    ) -> None: ...

    # pipeline stage/health: ONLY job handlers call these
    def advance_pipeline_stage_monotonic(self, paper_id: str, new_stage: str) -> None: ...
    def set_pipeline_health_error(self, paper_id: str, error_code: str, message: str, job_id: str | None) -> None: ...
    def clear_pipeline_health_if_recovered(self, paper_id: str, job_type: str) -> None: ...
```

### 14.3 ExtractionStore
```python
from typing import Protocol

class Extraction(Protocol):
    entity_type: str
    entity_ref: str | None
    field_path: str
    value_text: str | None
    value_numeric: float | None
    value_boolean: int | None

class ExtractionStore(Protocol):
    def upsert_extractions(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        extractions: list[Extraction],
    ) -> None: ...

    def list_by_paper(
        self,
        paper_id: str,
        prompt_version_id: str | None = None,
        successful_only: bool = True,
    ) -> list[Extraction]: ...

    def query(
        self,
        field_path: str,
        *,
        prompt_version_id: str,
        constraints: dict,
    ) -> list[str]:
        """Return matching paper_ids."""
```

### 14.4 BlobStore / VectorIndex / Converter / Embedder / LLMClient / ScholarClient
```python
from typing import Protocol
from pathlib import Path

class BlobStore(Protocol):
    def put_pdf(self, src_path: Path) -> tuple[str, Path]: ...                  # (pdf_xxh64, stored_path)
    def get_pdf_path(self, pdf_xxh64: str) -> Path | None: ...
    def put_markdown(self, paper_id: str, markdown: str) -> tuple[Path, str]: ...  # (path, md_xxh64)
    def get_markdown_path(self, paper_id: str) -> Path | None: ...
    def put_analysis_artifacts(self, run_id: str, output_md: str, output_json: dict | None, meta_json: dict) -> dict[str, Path]: ...

class VectorIndex(Protocol):
    def upsert(self, paper_id: str, embedding: list[float]) -> None: ...
    def query(self, embedding: list[float], limit: int) -> list[tuple[str, float]]: ...

class ConverterResult(Protocol):
    ok: bool
    markdown: str | None
    error_code: str | None
    error_message: str | None

class Converter(Protocol):
    def pdf_to_markdown(self, pdf_path: Path) -> ConverterResult: ...
    def version(self) -> str: ...  # recorded at execution time

class Embedder(Protocol):
    def model_name(self) -> str: ...
    def dimension(self) -> int: ...
    def embed(self, text: str) -> list[float]: ...

class LLMResponse(Protocol):
    text: str
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None

class LLMClient(Protocol):
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None) -> LLMResponse: ...

class ScholarClient(Protocol):
    def search(self, query: str, filters: dict, max_results: int, page_size: int) -> list[dict]: ...
```

---

## 15) Use-Cases (Complete List) — Restored Checklist

### Discovery & Import
- `DiscoverCandidatesUseCase(query, filters, max_results, page_size?)`
- `RejectCandidateUseCase(candidate_id)`
- `ImportCandidateUseCase(candidate_id, project_ids, tag_ids?)`

### Pipeline
- `EnqueueDownloadUseCase(paper_id)`
- `EnqueueConvertUseCase(paper_id)`
- `EnqueueEmbedUseCase(paper_id)`

### Analysis
- `RunAnalysisUseCase(paper_id, prompt_id, version?, profile_id, model_name, force?)`
- `ReanalyzeWithPromptVersionUseCase(scope, prompt_version_id, force?)`
- `AnalyzeProjectUseCase(project_id, prompt_version_id, profile_id, model_name, filters?, force?)`

### Prompts
- `CreatePromptUseCase(name, description, domain?, tags?)`
- `CreatePromptVersionUseCase(prompt_id, body, output_format, extraction_schema_json?)`

### Taxonomy
- `CreateTagUseCase(name, type)`
- `AttachTagToPaperUseCase(paper_id, tag_id, confidence?)`
- `CreateProjectUseCase(name, description)`
- `AttachPaperToProjectUseCase(paper_id, project_id, label?)`

### Admin/Repair
- `RecoverStuckJobsUseCase()`
- `RebuildVectorIndexUseCase(embedder_config?)`

---

## 16) Migration Plan (from current repo)
1. Implement Piccolo ORM models + migrations for SQLite, including `analysis_extractions` and FTS tables (`papers_fts`, `extractions_fts`).
2. Implement blob store with atomic writes and xxh64 fingerprinting.
3. Implement job queue + job runner + handlers (`download/convert/embed/analyze/discover`) with cooperative cancellation.
4. Wrap CLI commands (`discover/import/run-jobs/analyze/query/filter/aggregate`).
5. Build minimal Flet UI:
   - Search/Import
   - Paper Detail (extracted fields + runs)
   - Jobs/Runs monitor
   - Filters + basic aggregations

---

## 17) Future Considerations (explicitly deferred)
- **17.1 Analysis chaining / dependent analyses (v2)**
  - `analysis_runs.depends_on_run_id` (nullable FK)
  - `EnqueueChainedAnalysisUseCase(paper_id, prompt_sequence, profile_id, model)`
- **17.2 Tag suggestion automation (v1.1)** — suggestions only; never auto-apply
- **17.3 Auto-collections (v1.1)** — collections derived from extracted fields
- **17.4 Contradiction surfacing (v2)** — cross-reference “inconsistencies” across corpus
- **17.5 Corpus-level synthesis (v2)** — project-level synthesis from cross-pollination sections
- **17.6 Job retention / pruning (policy TBD)**
  - Keep analyze jobs as long as analysis_runs exist (status derivation depends on jobs).
  - Prune succeeded download/convert/embed jobs older than N days, keep newest per `(paper_id, type)`.
  - Keep failed jobs longer for debugging.
  - `papers.last_error_job_id` is not a FK, so pruning does not break deletes.

---

## Appendix A) `meta.json` schema (explicit JSON schema)

Schema name: `analysis_meta_json_schema_v1`

```json
{
  "type": "object",
  "required": ["run_id", "paper_id", "prompt", "endpoint", "input_provenance", "timing"],
  "properties": {
    "run_id": {"type": "string"},
    "paper_id": {"type": "string"},
    "prompt": {
      "type": "object",
      "required": ["prompt_id", "prompt_version_id", "version", "output_format"],
      "properties": {
        "prompt_id": {"type": "string"},
        "prompt_version_id": {"type": "string"},
        "version": {"type": "integer"},
        "output_format": {"type": "string"},
        "extraction_schema_hash": {"type": ["string", "null"]}
      }
    },
    "endpoint": {
      "type": "object",
      "required": ["profile_name", "base_url", "model_name"],
      "properties": {
        "profile_name": {"type": "string"},
        "base_url": {"type": "string"},
        "model_name": {"type": "string"},
        "parameters": {"type": "object"},
        "pricing": {
          "type": "object",
          "properties": {
            "input_price_per_1k_tokens": {"type": ["number", "null"]},
            "output_price_per_1k_tokens": {"type": ["number", "null"]}
          }
        }
      }
    },
    "input_provenance": {
      "type": "object",
      "required": ["md_fingerprint_xxh64", "md_converter", "md_converter_version"],
      "properties": {
        "md_fingerprint_xxh64": {"type": "string"},
        "pdf_fingerprint_xxh64": {"type": ["string", "null"]},
        "md_converter": {"type": "string"},
        "md_converter_version": {"type": "string"},
        "text_slice_strategy": {"type": ["string", "null"]},
        "embedding_model": {"type": ["string", "null"]},
        "embedding_dimension": {"type": ["integer", "null"]}
      }
    },
    "timing": {
      "type": "object",
      "required": ["started_at", "finished_at", "duration_ms"],
      "properties": {
        "started_at": {"type": "string"},
        "finished_at": {"type": "string"},
        "duration_ms": {"type": "integer"}
      }
    },
    "usage": {
      "type": "object",
      "properties": {
        "tokens_in": {"type": ["integer", "null"]},
        "tokens_out": {"type": ["integer", "null"]},
        "cost_usd": {"type": ["number", "null"]}
      }
    },
    "validation_issues": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "severity", "message"],
        "properties": {
          "path": {"type": "string"},
          "severity": {"type": "string"},
          "message": {"type": "string"},
          "value_preview": {"type": ["string", "null"]}
        }
      }
    }
  }
}
```

Note:
- `validation_issues` appears in both `analysis_runs.validation_issues_json` and `meta.json.validation_issues` intentionally (SQL queries vs artifact inspection).

---

## Appendix B) Extraction flattening example

Structured object:
- evaluation:
  - rigor_rating: 4
  - statistical_tests_used: true
- datasets_used: ["ImageNet", "CIFAR-10"]
- comparisons:
  - {name: "Adam", improvement_claimed: "2.3%"}
  - {name: "SGD", improvement_claimed: "5.1%"}

Flattened extraction rows:
- `evaluation.rigor_rating` → `value_numeric=4`
- `evaluation.statistical_tests_used` → `value_boolean=1`
- `datasets_used[0]` → `value_text="ImageNet"`
- `datasets_used[1]` → `value_text="CIFAR-10"`
- `comparisons[0].name` → `value_text="Adam"`
- `comparisons[0].improvement_claimed` → `value_text="2.3%"`
- `comparisons[1].name` → `value_text="SGD"`
- `comparisons[1].improvement_claimed` → `value_text="5.1%"`

---

## Appendix C) Project structure (restored)

```text
paper-manager/
├── pyproject.toml
├── src/papers/
│   ├── domain/
│   │   ├── models.py              # Pydantic models, enums
│   │   └── policies.py            # Dedup rules, validation policies
│   ├── app/
│   │   ├── use_cases/             # All use-cases
│   │   ├── ports.py               # Protocol definitions (Section 14)
│   │   └── job_runner/
│   │       ├── runner.py          # Claim/dispatch/backoff/cancel
│   │       └── handlers/          # Per-job-type handlers (download/convert/embed/analyze/discover)
│   ├── infra/
│   │   ├── sqlite/                # Piccolo ORM + job queue implementations, migrations
│   │   ├── lancedb/               # Vector index implementation
│   │   ├── blobs_fs/              # Blob store implementation
│   │   ├── converter_docling/
│   │   ├── embedder_st/
│   │   ├── llm_openai_compat/
│   │   └── scholar_s2/
│   ├── ui/                        # Flet thin client
│   ├── cli/                       # typer thin client
│   └── config/                    # settings.toml, defaults
├── data/
│   ├── db/app.sqlite
│   └── blobs/
└── tests/
```
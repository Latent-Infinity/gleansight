# 003. Piccolo on SQLite, forward-only migrations

## Status

Accepted

## Context

The paper evidence pipeline needs a local relational store for papers, jobs, prompts, extractions, and taxonomy. Schema must upgrade existing user databases without a rewrite of persistence.

## Decision

Use Piccolo ORM with a SQLite backend (`src/papers/infra/piccolo/`). Schema changes go through the forward-only `schema_migrations` runner:

- `001_baseline`
- `002_job_integrity_check` (SQLite CHECK matching design job integrity)
- later numbered scripts (`003_nsqd_tables`, …)

V0B migrations established that contract: apply known forward scripts only; never invent reverse migrations; reject unknown future IDs. Job rows are rebuilt with data/index preservation when the CHECK is added.

Atomic candidate import is a dedicated port (`AtomicCandidateImport`) implemented as one Piccolo immediate transaction, not a helper around existing `run_sync()` methods.

## Consequences

- Domain and use-cases depend on ports, not Piccolo types.
- A database created at a previous baseline is upgraded on startup.
- Unknown or out-of-order migration IDs fail closed.

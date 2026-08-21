# Evidence Index (project register)

**Plan Set:** gleansight
**Authority:** `docs/development-plan-open-work.md` v1.3.10
**As of:** 2026-08-21

`Last Result` is CI-derived. `Lifecycle: Pending: Vn` means the path may be missing until phase Vn closes, at which point it becomes `Required`.

| Evidence ID | Facts | Type | Path / Command | Available From | Lifecycle | Oracle & Fixture Deps | Data Version | Environment | Last Result |
|-------------|-------|------|----------------|----------------|-----------|-----------------------|--------------|-------------|-------------|
| EV-01 | SEARCH.HYBRID.FTS_VECTOR_RRF.v1 | test | `uv run pytest tests/facts/test_hybrid_search.py -q --no-cov` | V1 | Required | title+abstract FTS; markdown embed; 0.03252247/0.03226646/0.03200205 | DATA-01a/b/c | hermetic | pass 2026-08-19 |
| EV-02 | DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1 | test | `uv run pytest tests/facts/test_import_taxonomy.py -q --no-cov` | V2 | Required | real Piccolo; in-transaction fault | none | hermetic | pass 2026-08-20 |
| EV-02b | DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1 | test | `uv run pytest tests/facts/test_import_taxonomy_cli.py -q --no-cov` | V2 | Required | CLI ID strings | none | hermetic | pass 2026-08-20 |
| EV-02c | DISCOVERY.IMPORT.IDEMPOTENT_ATTACH.v1 | test | `uv run pytest tests/facts/test_import_idempotent_attach.py -q --no-cov` | V2 | Required | prior import + Piccolo | none | hermetic | pass 2026-08-20 |
| EV-03 | ANALYSIS.PROJECT.APPLY_FILTERS.v1 | test | `uv run pytest tests/facts/test_analyze_project_filters.py -q --no-cov` | V3 | Required | use-case-created data | none | hermetic | pass 2026-08-20 |
| EV-04 | ANALYSIS.RUN.FORCE_NEW.v1 | characterization test | `uv run pytest tests/facts/test_analyze_force.py -q --no-cov` | V3 | Required | existing RunAnalysisUseCase | none | hermetic | pass 2026-08-20 |
| EV-08 | ADAPTER.CONVERT.RESULT_CODES.v1 | test | `uv run pytest tests/facts/test_convert_result_codes.py -q --no-cov` | V6 | Required | empty / exception | none | hermetic | pass 2026-08-20 |
| EV-08b | HANDLER.CONVERT.CORRUPT_PDF.v1 | test | `uv run pytest tests/facts/test_convert_corrupt_pdf.py -q --no-cov` | V6 | Required | invalid PDF header + recovery provenance | none | hermetic | pass 2026-08-20 |
| EV-09 | OBS.LOG.JOB_CONTEXT.v1 | test | `uv run pytest tests/facts/test_job_log_context.py -q --no-cov` | V6 | Required | exact transition log capture | none | hermetic | pass 2026-08-20 |
| EV-10 | CFG.STARTUP.MISSING_DEP.v1 | test | `uv run pytest tests/facts/test_startup_missing_dep.py -q --no-cov` | V6 | Required | standalone fail-fast + bounded CLI startup | none | hermetic | pass 2026-08-20 |
| EV-11 | SCHEMA.JOB.INTEGRITY_CHECK.v1 | test | `uv run pytest tests/facts/test_job_integrity_check.py -q --no-cov` | V0B | Required | SQLite | none | hermetic | pass 2026-08-19 |
| EV-12 | SCHEMA.MIGRATE.FORWARD.v1 | test | `uv run pytest tests/facts/test_schema_forward_migrate.py -q --no-cov` | V0B | Required | previous-baseline DB | none | hermetic | pass 2026-08-19 |
| EV-13 | docs integrity | test | `uv run pytest tests/support/test_docs_cli_commands.py tests/support/test_no_src_todo.py -q --no-cov` | V7 | Required | workflows + src/ | none | hermetic | pass 2026-08-21 |

### NS/QD-inspired (see `docs/development-plan-ns-qd.md` evidence table)

Do not treat smoke fixtures as `calibration`. Smoke E2E (EV-N00) uses an empty snapshot (`evidence=null`), asserts a rejected card, and leaves the production archive empty. N1 also waits on EW-V0.3.

| Evidence ID | Facts | Path / Command | Available From | Lifecycle |
|-------------|-------|----------------|----------------|-----------|
| EV-N00 | NSQD.E2E.SMOKE_LOOP.v1 | `uv run pytest tests/facts/test_nsqd_e2e_smoke.py -q --no-cov` | N1 | Required |
| EV-N01 | NSQD.CORPUS.SNAPSHOT_HASH.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N02 | NSQD.CORPUS.SMOKE_NO_NOVELTY_TERM.v1 | `uv run pytest tests/nsqd/test_domain_policies.py tests/nsqd/test_application.py -q --no-cov` | N1 | Required |
| EV-N03 | NSQD.HARVEST.ENUMERATION.v1 | `uv run pytest tests/facts/test_nsqd_harvest_reject_essay.py -q --no-cov` | N2 | Required |
| EV-N04 | NSQD.GATE.SMOKE_PAIR.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N05 | NSQD.SEP.AUDIT_RECORD.v1 | `uv run pytest tests/nsqd/test_application.py -q --no-cov` | N1 | Required |
| EV-N06 | NSQD.MAP.STATUS_RULES.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N07 | NSQD.ARCHIVE.ELITE_REPLACE.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N08 | NSQD.CARD.SCHEMA.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N09 | NSQD.PROJECT.HUMAN_PARAPHRASE.v1 | `uv run pytest tests/facts/test_nsqd_paper_project.py -q --no-cov` | N2b | Pending: N2b |
| EV-N10 | NSQD.GROUND.CASCADE.v1 | `uv run pytest tests/nsqd/test_domain_policies.py tests/nsqd/test_application.py -q --no-cov` | N1 | Required |
| EV-N11 | NSQD.NOVELTY.METRIC.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N12 | NSQD.JOBS.OWNED.v1 | `uv run pytest tests/facts/test_nsqd_jobs.py -q --no-cov` | N1 | Required |
| EV-N13 | NSQD.SNAPSHOT.PROMOTION.v1 | `uv run pytest tests/facts/test_nsqd_sufficiency.py -q --no-cov` | N6 | Pending: N6 |
| EV-N14 | NSQD.ARCHIVE.RANK_GUARD.v1 | `uv run pytest tests/facts/test_nsqd_rank_guard.py -q --no-cov` | N7 | Pending: N7 |

# Fact Ledger (project register)

**Plan Set:** gleansight
**Authority:** project register. Closeout: `docs/development-plan-open-work.md`. NS-QD: `docs/development-plan-ns-qd.md`.
**As of:** 2026-08-18

Facts are append-only. Lifecycle is not a test result. Evidence results live in `docs/evidence-index.md`.

| Fact ID | Statement (Given / When / Then) | Applies When | Kind | Requirement | Owner | Lifecycle | Evidence |
|---------|--------------------------------|--------------|------|-------------|-------|-----------|----------|
| SEARCH.HYBRID.FTS_VECTOR_RRF.v1 | Given a non-empty query and the three approved paper records, when the user searches papers, then FTS runs on title+abstract, vectors on markdown, and the fused order and one-based RRF scores match the V0A table (A=0.03252247, B=0.03226646, C=0.03200205) | Default paper search | Behavior | LOCAL-AC-HYBRID-SEARCH | product | Active | EV-01 |
| DISCOVERY.IMPORT.ATTACH_TAXONOMY.v1 | Given an unimported candidate and existing project/tag IDs, when import is requested with those IDs, then either the whole import commits or nothing is written | Import from discovery | Behavior | LOCAL-AC-IMPORT-TAXONOMY | product | Proposed | EV-02, EV-02b |
| DISCOVERY.IMPORT.IDEMPOTENT_ATTACH.v1 | Given a candidate already imported to paper P, when import is requested again with project/tag IDs, then P is reused, missing attachments are added, already-present attachments are no-ops, and no second download job is enqueued | Re-import | Behavior | LOCAL-AC-IMPORT-TAXONOMY | product | Proposed | EV-02c |
| ANALYSIS.PROJECT.APPLY_FILTERS.v1 | Given a project and extraction filters, when project analysis is requested, then only members that survive label membership and the filter algebra receive new analysis runs | Analyze-project path | Behavior | LOCAL-AC-ANALYZE-PROJECT-FILTERS | product | Proposed | EV-03 |
| ANALYSIS.RUN.FORCE_NEW.v1 | Given a successful analysis run for the idempotency key, when analysis is requested with force, then a new run and job are created and the prior run is left unchanged | `force=true` | Behavior | LOCAL-AC-ANALYZE-FORCE | product | Proposed | EV-04 |
| SCHEMA.JOB.INTEGRITY_CHECK.v1 | Given a jobs row, when it is inserted, then SQLite rejects it unless it satisfies the design §5.2 job integrity CHECK | Schema after migration 002 | Data Contract | LOCAL-AC-JOB-CHECK | product | Active | EV-11 |
| SCHEMA.MIGRATE.FORWARD.v1 | Given a database created at the previous baseline, when the app starts, then forward-only migrations apply and the job CHECK is present | Existing user DB | Data Contract | LOCAL-AC-MIGRATIONS | product | Active | EV-12 |
| ADAPTER.CONVERT.RESULT_CODES.v1 | Given empty markdown or a converter exception, when `Converter.pdf_to_markdown` returns, then the value is a `ConverterResult` with `ok=False` and `EMPTY_OUTPUT` or `CONVERSION_FAILED` | Converter adapter | Behavior | LOCAL-AC-CONVERT-RESULT | product | Proposed | EV-08 |
| HANDLER.CONVERT.CORRUPT_PDF.v1 | Given a PDF that fails the handler validity check, when convert runs, then the job fails with `CORRUPT_PDF` and a re-download is enqueued | Convert handler | Behavior | LOCAL-AC-CONVERT-CORRUPT | product | Proposed | EV-08b |
| OBS.LOG.JOB_CONTEXT.v1 | Given a job state transition, when the runner logs the event, then the record includes timestamp, job_id, job_type, status_from, status_to, paper_id, and run_id | Job runner | Operational/SLO | LOCAL-NFR-LOGGING | product | Proposed | EV-09 |
| CFG.STARTUP.MISSING_DEP.v1 | Given a required optional dependency is not importable, when the composition root starts, then startup fails with `ConfigurationError` naming the module | Process start | Operational/SLO | LOCAL-NFR-FAILFAST | product | Proposed | EV-10 |
| NSQD.E2E.SMOKE_LOOP.v1 | Given approved requirement-card fixtures and an axiom, when the pipeline runs on an empty smoke_only snapshot, then novelty evidence is null, novelty term is 0, viability is 0, a complete Frontier Card is persisted as rejected, archive insertion is rejected, and the production archive is empty | N1 smoke | Behavior | LOCAL-NSQD-CAL | product | Active | EV-N00 |
| NSQD.CORPUS.SNAPSHOT_HASH.v1 | Given records, when a snapshot is created, then snapshot_id matches ALG-SNAP known vectors (order-invariant; changes with content or schema version) | Any snapshot | Data Contract | LOCAL-NSQD-H | product | Active | EV-N01 |
| NSQD.CORPUS.SMOKE_NO_NOVELTY_TERM.v1 | Given N1’s empty smoke_only snapshot, when the gate runs, then the candidate artifact stores a novelty evidence record with evidence=null and the required measurement stamp, novelty term is 0, and the card is not archive-eligible | Smoke | Behavior | LOCAL-NSQD-H | product | Active | EV-N02 |
| NSQD.GATE.SMOKE_PAIR.v1 | On a smoke snapshot, mechanism-free has mech=0; gamma-flow has mech=5 and nov=0; both viability=0 and archive_eligible=false | Smoke fixtures | Behavior | LOCAL-NSQD-CAL | product | Active | EV-N04 |
| NSQD.SEP.AUDIT_RECORD.v1 | Evaluator loads candidate by candidate_artifact_hash under a new evaluator_run_id; same-run generate+evaluate without persist/reload is rejected | Diverge/value | Architecture Contract | LOCAL-NSQD-SEP | product | Active | EV-N05 |
| NSQD.MAP.STATUS_RULES.v1 | Cell status matches the ALG-STATUS exclusive table at an injected as_of, including listed overlaps | Map | Behavior | LOCAL-NSQD-M | product | Active | EV-N06 |
| NSQD.ARCHIVE.ELITE_REPLACE.v1 | Given non-smoke constructed inputs with viability > 0, elite replacement uses viability then smaller candidate_artifact_hash; rejected cards never insert; replay is order-independent | Archive write | Behavior | LOCAL-NSQD-A | product | Active | EV-N07 |
| NSQD.CARD.SCHEMA.v1 | A card missing any required schema field is rejected independently | Archive | Data Contract | LOCAL-NSQD-C | product | Active | EV-N08 |
| NSQD.GROUND.CASCADE.v1 | Local layers 1–4 run and persist layer records; live and paper hybrid search are not called on the N1 path | Ground | Behavior | LOCAL-NSQD-G | product | Active | EV-N10 |
| NSQD.NOVELTY.METRIC.v1 | Evidence equals mean cosine distance to k-NN paraphrases; covers 0, <k, exact k, ties, and known unit vectors | Novelty | Behavior | LOCAL-NSQD-G | product | Active | EV-N11 |
| NSQD.JOBS.OWNED.v1 | Harvest/diverge/ground/score persist as nsqd_jobs; paper jobs rejects discovery types | Durable work | Architecture Contract | LOCAL-NSQD-E | product | Active | EV-N12 |

### NS/QD-inspired discovery (`docs/development-plan-ns-qd.md` v1.3.3)

See that plan’s ledger for full statements. N1 facts are **Active** with Required evidence. N2/N2b/N6/N7 remain Proposed. No Active fact requires novelty term > 0 on smoke_only, and no Active fact says a smoke card became a production elite.

| Fact ID | First phase | Notes |
|---------|-------------|-------|
| NSQD.E2E.SMOKE_LOOP.v1 | N1 | Empty smoke snapshot; `evidence=null`; rejected card; empty production archive |
| NSQD.CORPUS.SNAPSHOT_HASH.v1 | N1 | |
| NSQD.CORPUS.SMOKE_NO_NOVELTY_TERM.v1 | N1 | |
| NSQD.HARVEST.ENUMERATION.v1 | N2 | |
| NSQD.GATE.SMOKE_PAIR.v1 | N1 | Oracle fields on fixtures |
| NSQD.SEP.AUDIT_RECORD.v1 | N1 | |
| NSQD.MAP.STATUS_RULES.v1 | N1 | |
| NSQD.ARCHIVE.ELITE_REPLACE.v1 | N1 | Non-smoke unit inputs |
| NSQD.CARD.SCHEMA.v1 | N1 | |
| NSQD.PROJECT.HUMAN_PARAPHRASE.v1 | **N2b** | Not N1; needs EW-V0A + DATA-NSQD-04 + EW-V2 |
| NSQD.GROUND.CASCADE.v1 | N1 | |
| NSQD.NOVELTY.METRIC.v1 | N1 | |
| NSQD.JOBS.OWNED.v1 | N1 | |
| NSQD.SNAPSHOT.PROMOTION.v1 | N6 | Blocked on DATA-NSQD-03 for `production_valid` |
| NSQD.ARCHIVE.RANK_GUARD.v1 | N7 | |

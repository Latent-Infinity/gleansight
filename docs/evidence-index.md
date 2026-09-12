# Evidence Index (project register)

**Plan Set:** gleansight
**Authority:** `docs/development-plan-open-work.md` (evidence closeout) and `docs/development-plan-ns-qd.md` v1.6.70 (NS/QD)
**As of:** 2026-09-09

`Last Result` is CI-derived. `Lifecycle: Pending: Vn` means the path may be missing until phase Vn closes, at which point it becomes `Required`.

Current authority clarification (2026-09-11): `docs/reviews/nsqd-operator-activation-2026-09-11-authority-clarification/` (`5b4b50dddca913a2425eb1f965e2dc6f152dd700050379fd65ee8e4e6e9840b8`) is `review_pending` and report-only. It succeeds the technically reviewed remediation overlay without transferring that review. The preserved 2026-08-30 F-PROP-001 `human_approved` field is a `historical_claim_unverified`: repository evidence has no detached trusted approval tuple, so current runtime validation rejects the record, without retroactively endorsing or rejecting whether an actual human decision occurred. The 2026-09-11 C/F/status correction packets and G census remain the current evidence artifacts; historical activation claims are not current authority. Evidence sufficiency, schema admission, packet inclusion, G eligibility, restart, resurrection, operator activation, and runtime authority remain false.

Current release evidence closure (2026-09-12): the independently technically reviewed F implementation binding is `docs/reviews/nsqd-operator-f-readiness-2026-09-12-implementation-binding/` (`e82490162af6f8da4507aef5cfe019869a2caecdaa3cf985a0751e794c8d62fe`), and the independently technically reviewed activation pointer sync is `docs/reviews/nsqd-operator-activation-2026-09-12-pointer-sync/` (`c767f3ced5be85ddd1aa8432106e207e6b0c262593a90a69a910a4518444ebed`). The current unreviewed G successor is `docs/reviews/nsqd-operator-g-readiness-census-2026-09-12-schema-closure/` (`9af4910deb08b980a6a8ee0feda263825cada46703b13d54e00aeb983ea06680`), chained from packet `0649829a742d6433ec757afb5620cfa5f03665372d08196b47259a432bbb3f49`, complete over 354 structured files with 49 source bindings, zero trusted approvals, zero trusted evidence artifacts, and zero qualifying records. Technical review grants no human acceptance, evidence or schema approval, packet inclusion, operator activation, or runtime authority; all authority remains false.

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
| EV-12 | SCHEMA.MIGRATE.FORWARD.v1 | test | `uv run pytest tests/facts/test_schema_forward_migrate.py -q --no-cov` | V0B | Required | previous-baseline DB; NSQD migrations through 010 | none | hermetic | pass 2026-08-22 |
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
| EV-N06 | NSQD.MAP.STATUS_RULES.v1 | `uv run pytest tests/nsqd/test_domain_policies.py tests/nsqd/test_status_table.py tests/nsqd/test_map.py -q --no-cov` | N1 | Required |
| EV-N07 | NSQD.ARCHIVE.ELITE_REPLACE.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N08 | NSQD.CARD.SCHEMA.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N09 | NSQD.PROJECT.HUMAN_PARAPHRASE.v1 | `uv run pytest tests/facts/test_nsqd_paper_project.py -q --no-cov` | N2b | Required |
| EV-N10 | NSQD.GROUND.CASCADE.v1, NSQD.GROUND.LIVE_PRIOR_ART.v1 | `uv run pytest tests/nsqd/test_domain_policies.py tests/nsqd/test_application.py tests/nsqd/test_live_grounding.py -q --no-cov` | N1 | Required |
| EV-N11 | NSQD.NOVELTY.METRIC.v1 | `uv run pytest tests/nsqd/test_domain_policies.py -q --no-cov` | N1 | Required |
| EV-N12 | NSQD.JOBS.OWNED.v1 | `uv run pytest tests/facts/test_nsqd_jobs.py -q --no-cov` | N1 | Required |
| EV-N13 | NSQD.SNAPSHOT.PROMOTION.v1 | `uv run pytest tests/facts/test_nsqd_sufficiency.py tests/nsqd/test_sufficiency.py -q --no-cov` | N6 | Required |
| EV-N14 | NSQD.ARCHIVE.RANK_GUARD.v1 | `uv run pytest tests/facts/test_nsqd_rank_guard.py -q --no-cov` | N7 | Required |
| EV-N15 | NSQD.RESCORE.REPLAY.v1 | `uv run pytest tests/nsqd/test_rescore.py -q --no-cov` | N8 | Required |
| EV-N16 | NSQD.DOMAIN.POLICY_ISOLATION.v1 | `uv run pytest tests/facts/test_nsqd_domain_policy_isolation.py -q --no-cov` | N2a | Required |
| EV-N17 | NSQD.ACQUISITION.FALLBACK.v1 | `uv run pytest tests/facts/test_nsqd_acquisition_fallback.py tests/nsqd/test_acquisition.py tests/nsqd/test_papers_bridge.py tests/nsqd/test_paper_runtime.py -q --no-cov` | N6 | Required |
| EV-N18 | NSQD.SURFACE.UNIFIED.v1 | `uv run pytest tests/cli/test_gleansight.py tests/nsqd/test_cli.py tests/ui/test_discovery_screens.py tests/ui/test_app.py tests/ui/test_ui_main.py -q --no-cov` | N10 | Required |
| EV-N19 | NSQD.NOVELTY.TAU_PACKET.v1 | `uv run pytest tests/nsqd/test_tau_measurement_export.py tests/nsqd/test_tau_review.py tests/nsqd/test_autonomous_tau_review.py tests/nsqd/test_tau_candidate_generation.py tests/nsqd/test_tau_packet_scripts.py tests/nsqd/test_domain_policies.py::test_novelty_threshold_tau_is_active_and_tunable -q --no-cov` | N11 | Required |
| EV-N20 | NSQD.STATUS.CALENDAR_REPORT.v1, NSQD.OPERATOR.ACTIVATION_PLAN.v1 | `uv run pytest tests/nsqd/test_operator_activation_packets.py tests/nsqd/test_operator_activation_authority_clarification.py tests/nsqd/test_operator_approval_boundary.py tests/nsqd/test_operator_authority_surface.py tests/nsqd/test_operator_c.py tests/nsqd/test_operator_c_evidence_packet.py tests/nsqd/test_operator_c_evidence_cycle_2.py tests/nsqd/test_operator_c_evidence_cycle_3.py tests/nsqd/test_operator_c_evidence_cycle_3_review.py tests/nsqd/test_operator_c_followup.py tests/nsqd/test_operator_d_contract.py tests/nsqd/test_operator_d_contract_edges.py tests/nsqd/test_operator_e.py tests/nsqd/test_operator_e_cooccurrence.py tests/nsqd/test_operator_e_report_only_candidates.py tests/nsqd/test_operator_e_broader_prior_art.py tests/nsqd/test_operator_e_runtime.py tests/nsqd/test_operator_f_contract.py tests/nsqd/test_operator_f_validation_target.py tests/nsqd/test_operator_f_pilot.py tests/nsqd/test_operator_f_pilot_inputs.py tests/nsqd/test_operator_f_pilot_result_validation.py tests/nsqd/test_operator_f_readiness.py tests/nsqd/test_operator_g_contract.py tests/nsqd/test_operator_g_census.py tests/nsqd/test_operator_g_census_boundaries.py tests/nsqd/test_operator_g_evidence_trust.py tests/nsqd/test_operator_g_readiness.py tests/nsqd/test_operator_g_readiness_semantics.py tests/nsqd/test_operator_baselines.py tests/nsqd/test_status_window_ablation.py tests/nsqd/test_status_window_receipt_replay.py tests/nsqd/test_status_window_receipt_replay_validation.py tests/nsqd/test_status_window_receipt_replay_projection_identity.py tests/nsqd/test_status_window_receipt_replay_script_boundaries.py tests/nsqd/test_status_window_receipt_replay_portability.py tests/nsqd/test_map.py tests/nsqd/test_cli.py tests/nsqd/test_operator_a.py tests/nsqd/test_operator_b.py -q --no-cov && uv run python scripts/replay_status_window_ablation.py --verify-retained-replay` | Optional packets 1c/5 | Required |
| EV-N21 | NSQD.JEPA.IDEAS_GAPS_REPORT.v1 | `uv run pytest tests/nsqd/test_jepa_ideas_gaps_packet.py tests/nsqd/test_operator_e_broader_prior_art.py -q --no-cov` | JEPA finance report | Required |

The strict historical-receipt check is separate and optional because it requires the original receipt source: `uv run python scripts/replay_status_window_ablation.py --verify-current-receipt`.

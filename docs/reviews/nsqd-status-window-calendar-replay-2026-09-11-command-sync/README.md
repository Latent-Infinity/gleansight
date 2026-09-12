# Status-window calendar replay

**State:** `review_pending`; report-only research artifact; runtime unauthorized

This directory seals a portable replay comparing the current inclusive
730-day status window against a 24-calendar-month UTC clamp replay over
the approved snapshot
`bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5`
/ corpus version `11`.

## Provenance boundary

The timestamps here are real persisted values extracted from the
receipt-bound historical scratch SQLite verified through
`docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/baseline-evidence.json`.
They are **not** proven original 2026-08-29 production-harvest
timestamps because snapshot ids do not bind `harvested_at`.

`sealed_at_utc` records the original packet sealing time, not the
source harvest time, current-as-of replay time, or derived future
sensitivity time.

## Scenarios

- `current_as_of`: observed report-as-of replay at
  `2026-09-02T06:45:00+00:00`; explicit zero delta.
- `boundary_sensitivity`: derived future sensitivity from the real
  receipt-bound `harvested_at`; lifecycle semantics diverge while
  cell-status outputs remain unchanged. This is sensitivity evidence,
  not observed future production state.

## Files

- `extracted-timestamp-rows.json` — receipt-bound rows used by the
  replay.
- `calendar-replay-artifact.json` — portable self-validating replay
  artifact with scenarios and canonical digest.
- `review-summary.json` — file digests and verification notes for human
  review.
- `succession.json` — immutable predecessor identity and non-transferable
  review semantics for this command-only successor.
- `packet-manifest.json` — exact successor artifact hashes and packet digest.

## Verify

```bash
uv run pytest \
  tests/nsqd/test_operator_activation_packets.py \
  tests/nsqd/test_operator_approval_boundary.py \
  tests/nsqd/test_operator_authority_surface.py \
  tests/nsqd/test_operator_c.py \
  tests/nsqd/test_operator_c_evidence_packet.py \
  tests/nsqd/test_operator_c_evidence_cycle_2.py \
  tests/nsqd/test_operator_c_evidence_cycle_3.py \
  tests/nsqd/test_operator_c_evidence_cycle_3_review.py \
  tests/nsqd/test_operator_c_followup.py \
  tests/nsqd/test_operator_d_contract.py \
  tests/nsqd/test_operator_d_contract_edges.py \
  tests/nsqd/test_operator_e.py \
  tests/nsqd/test_operator_e_cooccurrence.py \
  tests/nsqd/test_operator_e_report_only_candidates.py \
  tests/nsqd/test_operator_e_broader_prior_art.py \
  tests/nsqd/test_operator_e_runtime.py \
  tests/nsqd/test_operator_f_contract.py \
  tests/nsqd/test_operator_f_validation_target.py \
  tests/nsqd/test_operator_f_pilot.py \
  tests/nsqd/test_operator_f_pilot_inputs.py \
  tests/nsqd/test_operator_f_pilot_result_validation.py \
  tests/nsqd/test_operator_f_readiness.py \
  tests/nsqd/test_operator_g_contract.py \
  tests/nsqd/test_operator_g_census.py \
  tests/nsqd/test_operator_g_census_boundaries.py \
  tests/nsqd/test_operator_g_evidence_trust.py \
  tests/nsqd/test_operator_g_readiness.py \
  tests/nsqd/test_operator_g_readiness_semantics.py \
  tests/nsqd/test_operator_baselines.py \
  tests/nsqd/test_status_window_ablation.py \
  tests/nsqd/test_status_window_receipt_replay.py \
  tests/nsqd/test_status_window_receipt_replay_validation.py \
  tests/nsqd/test_status_window_receipt_replay_projection_identity.py \
  tests/nsqd/test_status_window_receipt_replay_script_boundaries.py \
  tests/nsqd/test_map.py \
  tests/nsqd/test_cli.py \
  tests/nsqd/test_operator_a.py \
  tests/nsqd/test_operator_b.py \
  -q --no-cov
uv run python scripts/replay_status_window_ablation.py \
  --verify-current-receipt
uv run python scripts/replay_status_window_ablation.py \
  --verify-retained-replay
uv run python scripts/replay_status_window_ablation.py \
  --output-dir docs/reviews/nsqd-status-window-calendar-replay-2026-09-11-command-sync
```

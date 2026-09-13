# Status-window calendar replay

**State:** report-only research artifact; runtime unauthorized

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

## Verify

```bash
uv run pytest \
  tests/nsqd/test_operator_activation_packets.py \
  tests/nsqd/test_operator_c.py \
  tests/nsqd/test_operator_c_evidence_packet.py \
  tests/nsqd/test_operator_e.py \
  tests/nsqd/test_operator_e_cooccurrence.py \
  tests/nsqd/test_operator_e_report_only_candidates.py \
  tests/nsqd/test_operator_e_broader_prior_art.py \
  tests/nsqd/test_operator_baselines.py \
  tests/nsqd/test_status_window_ablation.py \
  tests/nsqd/test_status_window_receipt_replay.py \
  tests/nsqd/test_map.py \
  tests/nsqd/test_cli.py \
  tests/nsqd/test_operator_a.py \
  tests/nsqd/test_operator_b.py -q --no-cov
uv run python scripts/replay_status_window_ablation.py \
  --verify-current-receipt
uv run python scripts/replay_status_window_ablation.py \
  --output-dir docs/reviews/nsqd-status-window-calendar-replay-2026-09-02
```

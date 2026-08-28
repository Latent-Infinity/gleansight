# ALG.NOV threshold τ — packet 2b evidence workflow

**Status:** evidence collection authorized; executable `τ` remains unset.
**Authority:** agent output is proposal-only. Offline human review is the only label approval boundary.

## Required packet

The packet needs at least 120 non-ambiguous, human-approved candidate-neighbor pairs:

| Policy | Near duplicate | Novel |
| --- | ---: | ---: |
| `finance/1` | 30 | 30 |
| `optimization/1` | 30 | 30 |

Ambiguous pairs are retained and reported but do not satisfy these counts. Every pair must come from a `calibration` or `production_valid` snapshot and include the candidate, neighbor, snapshot identity, policy, `k`, and finite non-negative mean cosine distance. Smoke-only, synthetic, LLM-invented, or unapproved corpus rows cannot count.

## Agent proposal loop

`src/nsqd/domain/tau_review.py` owns prompt rendering and validation. For each measured pair:

1. Render `build_tau_label_prompt(pair)` using prompt version `tau-label/1`.
2. Run one writer and one independent reviewer for four refinement rounds using the configured local Ollama chat model.
3. Parse the final structured proposal with `parse_tau_label_proposal`.
4. Keep `review_status=pending`; an agent cannot approve its own label.
5. Export candidate/neighbor text, measurement, proposal, rationale, model, profile, and prompt version for offline review.

The proposed label is one of `near_duplicate`, `novel`, or `ambiguous`. It is an aid to the human reviewer, not evidence.

## Offline human approval

Each reviewed row records `human_review.label`, `reviewer`, UTC `approved_at`, and `approval_revision`. A packet manifest repeats the reviewer metadata and binds the complete JSON packet with `content_sha256 = tau_review_packet_digest(rows)`. Any changed label, rationale, measurement, or metadata invalidates that approval hash.

`evaluate_tau_packet(rows, manifest=manifest, trusted_reviewers=...)` requires an out-of-band trusted reviewer allowlist and rejects model/profile identities as human reviewers. It also rejects agent-only rows, hash mismatch, non-UTC approval, non-finite evidence, duplicate pair ids, and policy/class shortfalls. Before any runtime activation, bind approved packet digests in a trusted local store rather than accepting a caller-supplied manifest alone.

## Threshold rule

Evaluate only `0.15`, `0.30`, `0.45`, and `0.60` with raw-evidence kill semantics (`evidence < τ` zeros the novelty term). A value is admissible only when:

- overall human-labeled novel false-kill rate is at most 5%; and
- each policy’s human-labeled novel false-kill rate is at most 10%.

Choose the highest admissible value. If none is admissible, keep `τ = None`. Balanced accuracy cannot override the false-kill caps. Runtime activation remains a separate human decision after this result.

## Current data blocker

The 2026-08-27 repository inventory found zero persisted NSQD corpus records, snapshots, or candidate artifacts in `data/db/app.sqlite`, and no NSQD corpus LanceDB. DATA-NSQD-03 and DATA-NSQD-04 prove one approved projection per policy but cannot yield 120 distinct balanced pairs. The paper-side vectors and synthetic ALG.K fixtures are not substitutes for policy-bound NSQD evidence.

Acquire and approve enough policy-bound corpus/candidate material, generate snapshot-scoped k-NN measurements, then run the proposal/offline-review workflow. Do not fabricate or duplicate pairs to satisfy the count.

## Verification

```bash
uv run pytest tests/nsqd/test_tau_review.py tests/nsqd/test_domain_policies.py::test_novelty_threshold_tau_is_unset_and_report_only -q --no-cov
```

# ALG.NOV threshold τ — packet 2b evidence workflow

**Status:** evidence collection and staged evaluation complete; packet 2b recommends `τ = 0.45`; human runtime activation as `approved_default_tunable` was authorized on 2026-08-29.
**Target authority:** role-separated autonomous writer/reviewer labels count after four rounds; unresolved disagreement, ambiguity, schema inconsistency, and an audit sample route to a distinct adjudicator. Humans still approve source projections, packet acceptance, and runtime activation, but do not provide the target row labels.

## Required packet

The packet needs at least 120 non-ambiguous, accepted autonomous-agent-labeled candidate-neighbor pairs:

| Policy | Near duplicate | Novel |
| --- | ---: | ---: |
| `finance/1` | 30 | 30 |
| `optimization/1` | 30 | 30 |

Ambiguous pairs are retained and reported but do not satisfy these counts. Every pair must come from a `calibration` or `production_valid` snapshot and include the candidate, neighbor, snapshot identity, policy, `k`, and finite non-negative mean cosine distance. Smoke-only, synthetic, LLM-invented, or unapproved corpus rows cannot count.

## Autonomous agent loop (implemented and executed)

For each measured pair:

1. Run one writer and one independent reviewer for four recorded refinement rounds using the configured local Ollama chat model.
2. Bind every round to role/agent/model/profile/prompt/input/output digests and UTC timestamps.
3. Accept agreement as a pending autonomous label; route disagreement or `ambiguous` outcomes to the distinct configured adjudicator.
4. Retain `ambiguous` rows for audit without counting them toward either class.
5. Bind measurements, all rounds, adjudication, and exact model metadata into the packet digest.

The autonomous label is one of `near_duplicate`, `novel`, or `ambiguous`. Agents may label persisted measurements but cannot approve source projections, packet acceptance, runtime activation, or their own identity allowlists. When the adjudicator provider is `codex_subscription`, `gleansight` invokes the official `codex exec` CLI, relies on Codex-owned ChatGPT subscription OAuth, never reads or copies token files, and records only safe metadata such as requested model, Codex CLI version, reasoning effort, auth mode `chatgpt`, and `identity_source=requested_and_reroute_checked`.

## Current pre-N11.3 compatibility path

Each reviewed row records `human_review.label`, `reviewer`, UTC `approved_at`, and `approval_revision`. A packet manifest repeats the reviewer metadata and binds the complete JSON packet with `content_sha256 = tau_review_packet_digest(rows)`. Any changed label, rationale, measurement, or metadata invalidates that approval hash.

`evaluate_tau_packet(rows, manifest=manifest, trusted_reviewers=...)` requires an out-of-band trusted reviewer allowlist and rejects model/profile identities as human reviewers. It also rejects agent-only rows, hash mismatch, non-UTC approval, non-finite evidence, duplicate pair ids, and policy/class shortfalls. Before any runtime activation, bind approved packet digests in a trusted local store rather than accepting a caller-supplied manifest alone.

This shipped compatibility evaluator does not satisfy the autonomous target packet and its human row labels cannot count toward that packet. N11.3 now adds a separate autonomous boundary and leaves the human evaluator in place only for compatibility checks.

## Threshold rule

Evaluate only `0.15`, `0.30`, `0.45`, and `0.60` with raw-evidence kill semantics (`evidence < τ` zeros the novelty term). A value is admissible only when:

- overall accepted-autonomous-label novel false-kill rate is at most 5%; and
- each policy’s accepted-autonomous-label novel false-kill rate is at most 10%.

Choose the highest admissible value. If none is admissible, keep `τ = None`. Balanced accuracy cannot override the false-kill caps. Runtime activation remains a separate human decision after this result.

## Evaluated result

The trusted balanced packet contains exactly 120 accepted non-ambiguous rows:

| Policy | Near duplicate | Novel |
| --- | ---: | ---: |
| `finance/1` | 30 | 30 |
| `optimization/1` | 30 | 30 |

| `τ` | Admissible | Overall novel false-kill | Finance | Optimization | Near-duplicate false-pass |
| ---: | :---: | ---: | ---: | ---: | ---: |
| 0.15 | yes | 0.00% | 0.00% | 0.00% | 100.00% |
| 0.30 | yes | 0.00% | 0.00% | 0.00% | 100.00% |
| 0.45 | yes | 3.33% | 0.00% | 6.67% | 21.67% |
| 0.60 | no | 83.33% | 66.67% | 100.00% | 0.00% |

The selection rule therefore recommends **`τ = 0.45`**. The packet itself did not mutate runtime state. A later explicit human decision authorized `NOVELTY_THRESHOLD_TAU = 0.45` as `approved_default_tunable`; it is not frozen.

## Measurement inventory (fail-closed)

`qualify_tau_measurement_pair` / `tau_measurement_inventory` / `require_tau_measurement_inventory` accept only `calibration` or `production_valid` measurements with SHA-256 candidate/snapshot identities, a UTC measurement timestamp, exactly five ordered neighbors, recomputable candidate/neighbor text digests, and reviewed-projection digests present in an out-of-band approved allowlist. Each row also carries a `measurement_artifact_digest` created and persisted by grounding. The trusted application boundary is `TauMeasurementEvidenceUseCase`: callers provide only candidate artifact hashes, and the use case loads grounding rows from `NsqdCandidateStore` and derives the trusted-measurement allowlist internally. Raw domain helpers are not an ingestion boundary. Inventory uniqueness is enforced by both pair id and `(domain_policy_id, candidate_artifact_hash)`. Smoke, synthetic, LLM-invented, requirement-card, unapproved, caller-invented, self-consistent-but-unpersisted, or provenance-tampered rows are rejected. Label proposals may start only when each policy has at least 60 qualified measurements (enough for 30 near-duplicate + 30 novel if later labels split). Measurement and labeling workflows do not mutate runtime `τ`.

## Final measurement and label state

As of 2026-08-29, live snapshot `bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5` / corpus version 11 contains six approved `finance/1` sources and five approved `optimization/1` sources. The production `diverge` and `ground` boundaries persisted the original 120 unique candidates plus 60 deterministic semantic-replication reserve candidates. The trusted boundary accepts all 180 measurements—90 per policy—with exactly five ordered approved neighbors per row.

Evidence is stored under `docs/reviews/nsqd-tau-calibration-2026-08-29/`. The original candidate packet SHA-256 is `ac01c344973175e0c3270711403fe5bdb0a80977eb5781717a40cf729ca509f0`; candidate/measurement manifest `e74e6abeb433eda7e8398a274329c1f7dbcd6374c3c4718af1c69650d1239704`; original inventory `2fbb481bedad664a8284da1b7da84d663dda3bdac02eea848a94b0546b233191`; deterministic JSONL `0af46ae4aa2404c29b92af375228bcc2e20b3ad816b9bd5fdce4fe3cb9456bf6`; reserve manifest `6f6c4a3aede9dcc4842550199fea75ef949d789e5ec2c96088377ff58bdc059a`; reserve acquisition `9197ce82ae9f328e0429d34b38d881b243d3990455f4660c901f832877bcb4e5`; balanced selection `3117af36cd550d77ea43afbca1dfd1425e6ab9b72a7165328fed0f4cb6b47afc`; balanced evaluation `584e96d96bf6bf53993d3f5b2840896cca01df3cbf7362484e516905bdde10e5`; and evidence summary `f76a5de36d621ef13682223a2a7ebe4404cc9c3e71840f51e1a081f24a920f73`.

The selected packet binds 960 local Qwen calls and 15 Codex subscription adjudications (13 deterministic audits, one final ambiguity, one final disagreement). Its packet digest is `ad46a6e9838288d2175bf287524af92d5a01d572b081c85899819f7dbd647075`; selected-row digest is `0bac568c30227615d91635cc2dae7b7a6399a6f4a7d40329b113ecdc8cf17f7b`. There are zero selected ambiguous rows. Human review subsequently authorized runtime `τ = 0.45` as `approved_default_tunable`. Operator E, operators C–G, calendar-month semantics, and CLI `--operator` remain unchanged.

Prompt revisions `/2` and `/3` are explicitly allowlisted evidence protocols. Revision `/2` introduced compact inputs and bounded rationales; `/3` additionally constrains `pair_id` in the generation schema after a local model copy error. New calls use `/3`; packet validation rejects unknown or role-mismatched revisions rather than accepting arbitrary version strings.

## Verification

```bash
uv run pytest tests/nsqd/test_tau_measurement_export.py tests/nsqd/test_tau_review.py tests/nsqd/test_domain_policies.py::test_novelty_threshold_tau_is_active_and_tunable -q --no-cov
uv run pytest tests/nsqd/test_autonomous_tau_review.py -q --no-cov
uv run pytest tests/nsqd/test_tau_candidate_generation.py tests/nsqd/test_tau_packet_scripts.py -q --no-cov
```

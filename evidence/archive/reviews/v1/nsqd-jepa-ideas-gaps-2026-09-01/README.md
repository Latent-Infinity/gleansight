# JEPA finance ideas and gaps

**State:** report-only research results; runtime unauthorized
**Cutoff:** `2026-09-01T00:00:00Z`
**Corpus:** one direct financial JEPA paper (`N11-FIN-01`) and four approved adjacent finance papers (`N11-FIN-02` through `N11-FIN-05`)

## Results

The approved corpus supports four useful gaps:

1. Better latent prediction has not been connected reliably to calibrated economic utility.
2. Event-time, regime, and multi-horizon conditioning remain separate from financial JEPA training.
3. Cross-asset, earnings, and dynamically selected exogenous context are not integrated into the approved JEPA objective.
4. Latent fidelity, classification, return forecasting, trading, and denoising use incompatible validation targets.

Three report-only ideas survive the bounded mechanistic and prior-art screen:

1. **Calibrated latent-distribution Fin-JEPA for regime-specific abstention.** Regime and multi-horizon work alone duplicate Fin-JEPA's roadmap; the distinct test is whether calibrated latent uncertainty improves risk-coverage.
2. **Event-conditioned financial JEPA with causal relevance gating.** Reject it if gains disappear under shuffled-event controls or any event data leaks across decision timestamps.
3. **Dual-target Fin-JEPA for raw dynamics and denoised market state.** Bounded manual screening found partial component overlap but no established joint method; reject it unless denoised targets improve held-out economic metrics without degrading raw-latent fidelity.

The packet also identifies `validation_target` as a possible missing archive axis, but five papers are insufficient to establish stability. It is **not** recommended for schema admission.

## Execution accounting

The JEPA structural screen ran as a report-only comparison of three methods:

| Method | Role | Accepted for report |
| --- | --- | ---: |
| `cross_paper_mechanistic_bridge` | three JEPA ideas | 3 |
| `single_paper_future_work` | Fin-JEPA roadmap near-duplicate control | 0 |
| `rarity_only_negative_control` | zero co-occurrence alone as a generation reason | 0 |

Matched-count Operator A and B baselines are now **real Diverge → Ground → Score report-only baseline cards** bound to approved corpus snapshot `bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5` / corpus version `11` with finance/1 filtering to the six approved finance records and grounded with `qwen3-embedding:latest`, immutable manifest digest `64b933495768fbd3b87c20583d379728a07471e0c66733a9df87cd1901b3c44b`, and blob `3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85` on a scratch runtime with no production writes. All six are honestly **rejected** because no human dval assignment exists, so `dval=0` and `viability=0`.

Operator E remains separate: three report-only candidate artifacts were derived from the JEPA ideas, they were not passed to DivergeUseCase, and a broader report-only primary-source prior-art packet now binds those exact artifacts without authorizing E or converting them into candidate_combinations.

A **blinded 9-item human usefulness packet** and separate audit manifest were sealed alongside the artifacts. The absolute scratch paths recorded in `baseline-evidence.json` are historical run metadata, not required locations for ordinary packet validation. Fresh replay verifies logical runtime outputs only. Identity, structure, ordering, ids, hashes, decisions, and all non-floating fields must still match exactly; only finite floating-point numerics may drift within the replay tolerance bound (`1e-3`) observed in the bounded replay study. When both replay mappings are canonical tau-measurement mappings containing every `TAU_MEASUREMENT_ARTIFACT_FIELDS` entry, each side must still carry its own valid `measurement_artifact_digest` computed from its own canonical measurement mapping before that derived field is omitted from cross-side comparison; arbitrary mappings with the same key name still compare exactly. SQLite bytes, Lance tree digests, and historical payload hashes remain exact and are checked only by `--verify-current-receipt`. The packet is **operator-label-blinded**, not guaranteed family-inference-proof, because proposal content is retained for usefulness scoring. The completed operator-label-blinded human usefulness review is now recorded with reviewer label `human-reviewer`, reviewed at `2026-09-02T15:50:20Z`, no abstentions, one duplicate family (`same idea, different targets`), and descriptive raw plus duplicate-collapsed metrics. Candidate artifacts remain immutable and runtime stays disabled. Neither the structural screen nor the new A/B execution bundle authorizes Operator E.

## Interpretation boundary

Only Fin-JEPA is labeled JEPA. The other four papers provide adjacent mechanisms and evaluation evidence. Co-occurrence is measured only within these five approved projections; rarity is not novelty or value. Prior-art search is bounded and cannot prove novelty. A broader thirteen-source primary-source packet narrows overlap conclusions for the three E-report artifacts, but it still does not establish evidence sufficiency or runtime authorization. No result writes corpus facts, enables Operator E/F, changes `enabled_operators`, or requests runtime activation.

## Artifacts

- `source-ledger.json` — digest-bound approved projection and excerpt bindings.
- `results.json` — extracted facts, inferred gaps, proposed ideas, co-occurrence snapshot, and axis hypothesis.
- `prior-art-checks.jsonl` — bounded nearest-prior-art screening for each idea.
- `baseline-evidence.json` — real Operator A/B Diverge → Ground → Score artifacts, runtime receipt, snapshot/model provenance, and historical scratch-runtime metadata.
- `operator-e-report-only-candidates.json` — three report-only Operator E candidate artifacts derived from the JEPA ideas.
- `operator-e-broader-prior-art.json` — bounded broader primary-source prior-art evidence packet for the three report-only Operator E artifacts.
- `blinded-review-packet.json` — reviewer-facing operator-label-blinded 9-item human usefulness packet.
- `blinded-review-audit-manifest.json` — blind-id to A/B/E audit mapping.
- `ablation-results.json` — cross-paper method, real matched-count A/B baseline replay, and rarity-only negative control.
- `review-summary.json` — artifact digests, prior-report review, completed execution-bundle review, and separate broader-packet technical-review state.

## Verify

```bash
uv run pytest tests/nsqd/test_jepa_ideas_gaps_packet.py tests/nsqd/test_operator_e_broader_prior_art.py tests/nsqd/test_operator_baselines.py tests/nsqd/test_operator_e_cooccurrence.py -q --no-cov
uv run python scripts/replay_jepa_operator_baselines.py --scratch-dir "/tmp/nsqd-jepa-baselines-$(python -c 'import uuid; print(uuid.uuid4().hex)')"
uv run python scripts/replay_jepa_operator_baselines.py --scratch-dir "/var/folders/xf/c9939qyj0wx236rc2nrgrdhw0000gn/T/opencode/nsqd-jepa-baselines-fixed" --verify-current-receipt
```

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

## Interpretation boundary

Only Fin-JEPA is labeled JEPA. The other four papers provide adjacent mechanisms and evaluation evidence. Co-occurrence is measured only within these five approved projections; rarity is not novelty or value. Prior-art search is bounded and cannot prove novelty. No result writes corpus facts, enables Operator E/F, changes `enabled_operators`, or requests runtime activation.

## Artifacts

- `source-ledger.json` — digest-bound approved projection and excerpt bindings.
- `results.json` — extracted facts, inferred gaps, proposed ideas, co-occurrence snapshot, and axis hypothesis.
- `prior-art-checks.jsonl` — bounded nearest-prior-art screening for each idea.
- `ablation-results.json` — cross-paper method, single-paper baseline, and rarity-only negative control.
- `review-summary.json` — artifact digests and independent review outcome.

## Verify

```bash
uv run pytest tests/nsqd/test_jepa_ideas_gaps_packet.py -q --no-cov
```

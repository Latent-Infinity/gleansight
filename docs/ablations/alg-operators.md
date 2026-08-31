# Divergence operators packet

**Study:** `ALG.OP`
**Outcome:** Operators A and B are **supported**. B is non-default and enabled only by a composition allowlist; the default composition remains A-only. The divergence CLI may request A/B but cannot authorize either. Operators C–G stay **deferred** and **runtime-disabled**.

## Packet 4 (2026-08-26)

| Id | Name | Activation | Runtime | Wait on |
| --- | --- | --- | --- | --- |
| A | inversion | supported | enabled | — |
| B | archive whitespace | supported | composition-gated | settings `nsqd.enabled_operators`; CLI selection requires target-bound proof |
| C | Swanson ABC | deferred | rejected | two named literatures plus explicit human activation; B composition-gating is not C authorization |
| D | analogical transport | deferred | rejected | source/target `domain_policy_id` after C |
| E | atypical combination | deferred | rejected | separate operator-specific evidence and explicit human activation; executable `τ` alone is insufficient |
| F | missing dimensions | deferred | rejected | axis-policy clarity |
| G | failure resurrection | deferred | rejected | approved failed-experiment corpus; do not invent it |

Command: `uv run pytest tests/nsqd/test_operator_a.py -q --no-cov`

## Operator B supported contract

See `ALG-OP-B`. B targets the full `ALG-SEL` rule without axiom inversion. Before persistence, the candidate descriptor and at least one structured axiom must occupy the selected target; every explicitly bound axiom must match it. Production composition loads the allowlist from settings (`A` or `A,B`); deferred operators are rejected at composition.

Command: `uv run pytest tests/nsqd/test_operator_b.py tests/nsqd/test_operator_a.py -q --no-cov`

## Human validation

- **Validated:** packet 4 keep-disabled outcome accepted 2026-08-26. The `ALG-OP-B` contract was accepted 2026-08-27, followed by human approval for supported, non-default, composition-gated B with controlled durable writes.
- **Validated:** packet 5 CLI scope accepted 2026-08-30: `diverge --operator` may request A/B only. Selection cannot widen the composition allowlist; B requires explicit target and target-bound axiom proof.
- **Evidence target only:** E should be evaluated as experimental, off-by-default, and composition-gated. This is not runtime authorization; executable `τ` remains unrelated to E authorization.
- **Evidence scope:** C starts with `N11-OPT-02 → N11-FIN-04`; D tests `optimization/1 → finance/1` only after C. E evaluates same-policy and explicit cross-policy tracks separately. F permits one report-only candidate axis per packet. G starts a typed human-approved failure-record collection contract; no failure corpus exists yet.
- **Not authorized:** default enablement of B; runtime enablement of C–G.

## Packet 5 activation program (2026-08-30)

| Track | Approved next state | Runtime effect now | Required evidence / dependency |
| --- | --- | --- | --- |
| C | separate evidence packet | none | two named literatures plus explicit human activation; shared status-table semantics with B are not C authorization |
| D | separate evidence packet after C | none | explicit source and target `domain_policy_id`; cross-policy isolation must remain fail-closed |
| E | experimental/config-gated evidence target | none | operational atypical-combination contract, provenance, usefulness/safety comparison, and separate human activation; `τ = 0.45` is not evidence |
| F | separate evidence packet | none | axis-policy contract for proposing a dimension outside the registered archive axes |
| G | separate evidence packet | none | approved failed-experiment corpus with provenance; synthetic or invented failures cannot qualify |
| CLI | A/B divergence selection | A remains default; B remains composition-gated | CLI may narrow to A/B and carry B proof fields; it cannot alter settings or expose C–G |

Dependency order is status semantics → C and E independently → D after C; F and G remain blocked by their own data contracts. CLI exposure does not change that order or authorize any operator.

Each report-only packet uses an explicit baseline and negative control before recommending a method. Current designs compare C bridge pairs and extraction methods, D typed structure mapping against surface similarity, E same/cross-policy tracks and A/B candidates against rarity-only generation, F one candidate axis against current axes and a shuffled axis, and—only after a real corpus exists—G typed failure memory against raw logs and no-memory baselines. The executable packet definitions live in `docs/reviews/nsqd-operator-activation-2026-08-30/`.

### CLI exposure ablation

| Choice | Authorization safety | B usability | Future ambiguity | Decision |
| --- | --- | --- | --- | --- |
| no switch | strongest | unavailable from CLI | low | rejected after B support |
| A only | strong | unavailable | medium; suggests unsupported future surface | rejected |
| A/B selection, composition authoritative | strong; cannot widen allowlist | target-bound proof is expressible | low | **selected** |
| dynamically expose every configured id | depends on future operator contracts | high | high; risks confusing exposure with authorization | deferred |

## Report-only evidence contracts

Every executed deferred-operator packet binds an immutable input snapshot, policy ids, source records, algorithm/prompt identity, UTC generation time, candidate outputs, nearest prior art, known limitations, and `authorization_state=report_only`. Evidence-plan/inventory packets use the same schema but explicitly record `not_run`, empty outputs, absent snapshots where no executable input set exists, and the resulting limitations. Candidate generation, scoring, and human authorization remain separate. Thresholds below are deliberately unset until each packet supplies a measured comparison.

### C — Swanson ABC literature discovery

C takes two named, plausibly noninteracting literatures and produces auditable `A → B` plus `B → C` paths. Each bridge binds normalized concepts, supporting citations, query/corpus snapshot and cutoff, polarity/direction, an explicit `A → C` prior-art search, and a noninteraction check. The evidence packet reports precision/relevance at K, bridge specificity, support counts, time-sliced rediscovery, and leakage or hidden-interaction flags. It never promotes the inferred `A → C` relation to fact.

### D — analogical transport

D follows C but has a different input contract: explicit `source_domain_policy_id` and `target_domain_policy_id`, typed source and target relational graphs, allowed mapping predicates, forbidden attributes, and target-domain constraints. It maps systematic relations rather than surface attributes and emits unapproved candidate inferences. Evidence reports structural/role consistency, target contradiction rate, held-out analogy recovery, human plausibility at K, and a zero-tolerance policy-leak count.

### E — atypical combination

E combines approved, provenance-bound components only. A report row includes component sources, corpus/co-occurrence snapshot, atypicality, nearest prior combinations, and a required mechanistic bridge explaining why the combination is not arbitrary. Low co-occurrence or downstream novelty score alone is insufficient. Evaluation compares bridge-valid usefulness and duplication rates against A/B proposals. `τ = 0.45` may score a grounded artifact later; it is not E evidence or authorization.

### F — missing dimensions

F recommends, but cannot install, a candidate descriptor axis. A row includes the current axis-policy id, measurable axis definition, protocol, stability, residual variation, redundancy with existing axes, association with quality/failure, archive coverage/density ablation, confounds, and dimensionality cost. Human axis admission remains a separate schema/version decision; runtime archives cannot self-modify.

### G — failure resurrection

G requires immutable, human-approved failed-experiment records. Each record distinguishes implementation, measurement, method, hypothesis, regime-bound, and inconclusive failures; binds original conditions and evidence; and names a measurable changed-condition trigger. The packet reports attribution confidence, trigger strength, constraint gain, duplicate-failure avoidance, and corpus limitations. Absence of success is not a failure record, and the system may not invent, approve, or resurrect its own failure.

## Method references

- Swanson, “Fish oil, Raynaud's syndrome, and undiscovered public knowledge” (1986), https://doi.org/10.1353/pbm.1986.0087; Swanson, “Medical literature as a potential source of new knowledge” (1990), https://pmc.ncbi.nlm.nih.gov/articles/PMC225324/.
- Gordon and Lindsay, Arrowsmith literature-based discovery (1997), https://doi.org/10.1016/S0004-3702(97)00008-8.
- Gentner, structure-mapping theory (1983), https://doi.org/10.1207/s15516709cog0702_3; Gick and Holyoak, analogical transfer (1980), https://doi.org/10.1016/0010-0285(80)90013-4.
- Uzzi et al., “Atypical Combinations and Scientific Impact” (2013), https://doi.org/10.1126/science.1240474; Lehman and Stanley, novelty search (2011), https://doi.org/10.1162/EVCO_a_00025.
- Hedayatian and Nikolaidis, AutoQD learned behavior descriptors (2026), https://arxiv.org/abs/2506.05634.
- Wang, failure-aware negative knowledge for automated research (2026), https://arxiv.org/abs/2606.21024.

## Freeze / activation status

- B is **supported**, non-default, and composition-gated.
- C–G remain **deferred**.

# Negative-Space Quality-Diversity (NS-QD) Research Framework

### v1.0

**Status:** frozen for implementation.
**Product home:** **gleansight** is an **NS/QD-inspired** discovery platform (`docs/product-gleansight.md`, `docs/glossary-nsqd.md`). This file is framework WHAT. HOW: `docs/requirements-ns-qd.md`, `docs/algorithm-contract-nsqd.md`, `docs/development-plan-ns-qd.md`.

**Naming:** Do not treat this as canonical Novelty Search or MAP-Elites. The v1 metric is **corpus-relative novelty evidence**.

The existing paper pipeline is in-scope as the **evidence layer** (Stage 0 harvest for `type=paper`), not a separate product.

**Governing heuristic:** *minimum rigor to kill, full rigor to promote.*

**One-line purpose:** produce an *illuminated map of research opportunity space* — sparse cells, missing dimensions, stalled ideas, and newly-enabled regions, each survivor carrying a falsifiable card — **not** a ranked list of "cool ideas."

---

## 0. Diagnosis

> **LLMs are high-recall combinatorial engines with weak frontier valuation and RLHF-suppressed divergence.**

The framework supplies seven capacities the model lacks:

1. A dense **positive corpus** to measure absence against
2. Forced **divergence** off the modal path
3. Mechanized **gap detection**
4. Grounded **novelty verification** (measured, never self-assessed)
5. **Value** discrimination
6. Cheap **falsification**
7. **Archive-based** iterative search

**Positive-corpus axiom.** Negative space is the complement of a well-mapped positive space. Every novelty score is relative to a **versioned corpus snapshot** recorded on the card.

---

## 1. Architecture

```
                             ┌───────────────────── OUTER LOOP ─────────────────────┐
                             │  experiment result → update archive / map / corpus   │
                             ▼                                                      │
  HARVEST ──▶ MAP ──▶ DIVERGE ──▶ GROUND ──▶ VALUE ──▶ ARCHIVE/EVOLVE ──────────────┘
```

Generation and evaluation are **never the same agent in the same pass**.

| Stage | Purpose |
|---|---|
| Harvest | Build the versioned positive corpus |
| Map | Morphospace of what exists |
| Diverge | Non-modal candidates (framework operators A–G; **baseline is A only**) |
| Ground | Prior art vs papers, code, benchmarks |
| Value | Two-tier kill / readiness gate |
| Archive/Evolve | QD archive, illuminate-first |
| Outer loop | Experiment, corpus, and map feedback |

---

## 2. Three structures

- **Corpus** — versioned evidence store (papers, code, benchmarks, patents, industry, internal). Embed **mechanism paraphrases**, not abstracts.
- **Morphospace** — high-dimensional gap-finding grid. Cell statuses: Mature, Active, Sparse, Missing, Code-gap, Benchmark-gap, Future-work-only, Stalled, Invalid, Unknown.
- **QD Archive** — 3–5 axes only. Finance default: `mechanism × prediction-target × horizon` (7 × 8 × 6 = **336 eligible cells**, `ALG-DESC`). Other axes are card metadata.

Finance axis menu (instantiation, not the only domain): prediction target, horizon, data modality, mechanism, model class, optimizer, objective, evaluation, failure mode.

---

## 3. Stage 0 — Harvest

Enumerate (do not synthesize) papers, code, benchmarks, patents, industry writing, automated-ideation SOTA, and internal killed-experiment records.

Multi-provider deep research is **optional** for the initial harvest; citation lists are the product; essays are exhaust. Engine disagreement marks cells `Unknown`, never `Missing`.

**Corpus record:** id, type, claim-or-method (mechanism paraphrase), source, terminology variants, morphospace coordinates, harvest provenance, embedding.

**Sufficiency:** (a) Mature/Active cells have records; (b) recall probe of known works; (c) disagreements resolved or Unknown.

---

## 4–8. Map through Archive

- **Map:** aggregate corpus into cell statuses + load-bearing axioms.
- **Diverge:** operators A inversion, B whitespace, C Swanson ABC, D analogical transport, E atypical combination, F missing dimensions, G failure resurrection. No ranking. **Baseline implementation is Operator A only; B–G are deferred.**
- **Ground:** four layers (exact, synonym, embedding NN, code/benchmark), corpus-first, cost cascade. Stamp corpus version. Finance clean-gap inversion.
- **Value:** Tier-1 multiplicative kill (novelty × mechanism × falsifiability × differential-pred × domain-value). Tier-2 readiness (fixable). Finance inefficiency block required for finance survivors.
- **Archive:** best card per cell; no global rank until 50 elites **or** 20% coverage of the domain-pack eligible universe excluding Invalid (`ALG-COV`). Unknown/uninspected cells remain in the denominator. Outer loop: experiment / corpus re-score / map update.

---

## 9. Frontier Hypothesis Card

Title, conventional core, atypical injection, mechanism, domain inefficiency (finance), components, operator, prior-art, gap class, stall reason, novelty evidence, **corpus snapshot**, differential prediction, cheapest falsifier, baseline, metric, kill criteria, next experiment, Tier-1 scores, Tier-1 kill product, Tier-2 readiness, decision.

Graduation: Frontier Card → (Tier-1 pass + cheap test survives) → Alpha Hypothesis Card.

**Home:** gleansight (this repo). Discovery use-cases live under `src/nsqd/`; evidence/paper pipeline stays `src/papers/`. A later optional plugin is packaging, not the product. The name `liq-ideation` is not used here.

---

## 10. Agents

Harvester, Cartographer, Assumption Miner, Divergence Mutator, ABC Bridge Hunter, Analogist, Negative-Space Hunter, Retrieval Red-Team, Mechanism Arbiter, Experiment Designer, Benchmark Auditor, Archive Curator.

Divergence agents cannot evaluate; evaluation agents cannot generate replacements in the same pass.

---

## 11. Anti-patterns

Novelty theater; self-assessed novelty; mechanism-free transfer; weirdness maximization; benchmark laundering; premature convergence; open-loop generation; clean-gap credulity (finance); thin-corpus novelty; synthesis-as-harvest.

---

## 13. Calibration

The gate must **pass** dealer-convexity / gamma-flow (structural inefficiency, convexity as trust/abstention) and **kill** a mechanism-free “apply X to Y” control.

Implementation binding: that pair is a **requirement-card** smoke/calibration pair, not a corpus. On a `smoke_only` snapshot the novelty term is forced to 0, so both cards have viability 0 and neither becomes a production elite. “Pass” on smoke means gamma-flow is a complete card with `mech > 0` and the control has `mech = 0`. A `calibration` snapshot is required before claiming production calibration (`docs/algorithm-contract-nsqd.md`).

---

## 15. Implementation-readiness (from PRD)

Framework-complete enough to enter requirements. Defaults: archive axes mechanism×target×horizon; 20–30 candidates/cycle into Ground; ≥60% cheap-triage kill; ≤3 live-search escalations; corpus appends per cycle; full re-harvest quarterly.

Deferred to requirements (resolved for this repo in `docs/requirements-ns-qd.md`): embedding model; vector collection design; harvest connectors; card store; score-anchor rubrics; budget calibration.

## References

Kirk et al. 2023; Mouret & Clune 2015; Lehman & Stanley 2011; Boden; Swanson; Gentner 1983; Uzzi et al. 2013.

# Glossary — NS/QD-inspired discovery

gleansight’s discovery layer is **inspired by** Novelty Search (Lehman & Stanley, 2011) and MAP-Elites (Mouret & Clune, 2015). It is **not** a canonical NS or MAP-Elites implementation unless a later revision adds descriptor-space sparseness and local competition.

**Normative owner:** this file owns terminology only. Formulas and policies live in `docs/algorithm-contract-nsqd.md`.

| Term in this product | Meaning here | Not the same as |
|----------------------|--------------|-----------------|
| **NS/QD-inspired** | Preferred product label | Claiming a drop-in NSLC / MAP-Elites solver |
| **Research descriptor** | Discrete coordinates on the morphospace / archive axis menu (mechanism, target, horizon, …) | A continuous **behavior descriptor** in evolutionary robotics (e.g. gait features) |
| **Behavior descriptor** | Canonical QD: a vector that bins an evaluated *behavior*. **Not implemented** in v1 | Research descriptor |
| **Prior-art archive** | Versioned **corpus** of papers/code/benchmarks used to measure absence | The MAP-Elites **quality-diversity archive** of elites |
| **MAP-Elites archive** | Here: grid of Frontier Cards, one elite per research-descriptor cell, with a declared quality comparison | Canonical archive of evaluated behaviors |
| **Corpus-relative novelty evidence** | Distance / absence vs a **named corpus snapshot** (prior art). The v1 metric | Canonical NS novelty (next row) |
| **Canonical NS novelty** | Mean distance to k nearest neighbors in **behavior/descriptor space**, measured against the **current population plus the permanent novelty archive** (Lehman & Stanley, 2011) | Corpus-relative novelty evidence |
| **Domain viability score** | Tier-1 **product** of novelty evidence × mechanism × falsifiability × differential-pred × domain-value (`ALG-VIA`) | NSLC **local competition** and MAP-Elites elite replacement |
| **Local competition** | Canonical NSLC: a neighborhood-relative performance score in niche/behavior space, often the count of nearest neighbors the candidate outperforms (Lehman & Stanley, 2011). **Not implemented** in v1 | Domain viability gate; also not MAP-Elites “replace the occupant if fitter” |
| **Archive elite replacement** | Project rule: keep the higher-viability card in a cell (`ALG-ELITE`) | Local competition |
| **Negative space** | Project term: structured absence vs the positive corpus | A standard QD operator |
| **Frontier Card** | Project term: ideation artifact with corpus stamp and gate scores | A QD individual / genome |
| **Harvest** | Project term: build the positive corpus | A QD evaluation episode |
| **Grounded novelty** | Project term: corpus-relative novelty evidence after the grounding cascade | Self-assessed “this is new” |
| **Target cell** | Cell selected for the next diverge cycle (`ALG-SEL`) | A parent card (an empty target cell has none) |
| **Parent card** | Optional elite already in the target cell; extra context for Operator A | The target cell itself |

**Metric name (normative):** `corpus_relative_novelty_evidence`. Do not name APIs or facts `ns_novelty` or `qd_fitness` unless the canonical definition is implemented.

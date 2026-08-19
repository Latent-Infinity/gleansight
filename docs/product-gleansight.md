# gleansight — Product

**Status:** Direction for review (2026-08-18)
**What:** gleansight is a **local-first NS/QD-inspired discovery platform** (see `docs/glossary-nsqd.md`).
**Maturity:** The **paper evidence pipeline is executable today**. The discovery layer is **planned, not available**.
**Also:** the existing paper pipeline stays, as the **evidence / harvest layer** for scholarly literature.

This document is the product thesis. Framework detail: `docs/prd-ns-qd.md`. Implementation bindings: `docs/requirements-ns-qd.md`. Build order: `docs/development-plan-ns-qd.md` (discovery) and `docs/development-plan-open-work.md` (evidence-layer closeout).

---

## One-line

Illuminate a research opportunity space — sparse cells, missing dimensions, stalled ideas, newly-enabled regions — each survivor a falsifiable card — **and** keep a working corpus of papers (discover, import, convert, extract, search).

Not a ranked list of “cool ideas.” Not a paper manager that happens to have a side plugin.

---

## Two layers, one product

```
                    ┌──────────── gleansight ────────────┐
                    │                                    │
  Discovery         │  Harvest → Map → Diverge → Ground  │
  (NS/QD-inspired)  │  → Value → Archive  (+ outer loop) │
                    │         Frontier Cards             │
                    └──────────────▲─────────────────────┘
                                   │ measures against
                    ┌──────────────┴─────────────────────┐
  Evidence          │  Discover / import / PDF→MD /      │
  (current product) │  embed / extract / hybrid search   │
                    │  projects · tags · jobs            │
                    └────────────────────────────────────┘
```

| Layer | Job | Today |
|-------|-----|--------|
| **Evidence** | Dense, versionable **positive space**: papers (and later code, benchmarks, patents, industry, internal kills) | Implemented as `papers` CLI/UI/pipeline |
| **Discovery** | Structured absence vs the corpus: morphospace, **Operator A in the baseline (B–G later)**, **corpus-relative novelty evidence**, domain-viability gate, MAP-Elites-inspired archive | **Planned, not shipped** |

The paper features are not legacy to sunset. They are how Stage 0 harvests **type=paper**. An imported, converted paper should become a corpus record (mechanism paraphrase + coordinates) when harvest projection runs. Code/benchmark/patent types are additional harvest connectors, not a replacement for papers.

---

## What users do

1. **Build evidence** — discover and import papers, run the pipeline, extract, search (current workflows).
2. **Snapshot a corpus** — enumerated records (from papers + other sources) versioned; novelty is undefined without a version.
3. **Map** — see density and structured absence (cell statuses).
4. **Diverge** — generate candidates without ranking. **Operator A in the baseline; B–G later.**
5. **Ground + value** — prove prior art; multiplicative kill gate; domain packs (finance first for calibration).
6. **Archive** — illuminate cells before any global rank; keep elite cards.

CLI and UI stay **one app** at the **NSQD-N10** target state. Until N10: evidence commands remain `papers …`; N1 adds only `python -m nsqd skeleton`. N10 joins discovery commands (`gleansight harvest|map|diverge|ground|gate|archive`) and grows Map / Archive / Card screens; Search / Paper / Monitor / Query stay.

---

## Domain-general, packs for specificity

gleansight is **not** a finance product. Morphospace axes and the inefficiency block are **domain packs**.

- **Calibration pack:** `finance` (PRD §13 gamma-flow vs mechanism-free).
- **Default product:** configurable domain; axis menu and extra gate terms load from the pack.
- A non-finance domain omits counterparty/capacity fields.

---

## What we are not building (yet)

- A second application or `liq-*` trading stack
- Qdrant beside LanceDB (**HD-NSQD-01 closed:** LanceDB)
- Twelve live agent processes (mandates = use-cases)
- Instant rename of `src/papers` (product name is gleansight; package rename is a later refactor)

---

## Review order

1. This file — product thesis
2. `docs/glossary-nsqd.md` + `docs/algorithm-contract-nsqd.md`
3. `docs/prd-ns-qd.md` — framework WHAT
4. `docs/requirements-ns-qd.md` — bindings
5. `docs/development-plan-ns-qd.md` — build (phases `NSQD-N*`)
6. `docs/development-plan-open-work.md` — how we finish the evidence layer
7. `docs/project-design.md` — evidence-layer architecture (v0.9; still in force for papers)
8. `docs/review-nsqd-action-items.md` — living review / action tracker

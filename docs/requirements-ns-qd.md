# Requirements: gleansight as NS-QD discovery platform

**PRD:** `docs/prd-ns-qd.md` v1.0
**Product:** `docs/product-gleansight.md`
**Normative policies:** `docs/algorithm-contract-nsqd.md` (this file must not redefine them)
**Status:** Implementation bindings
**Date:** 2026-08-18

gleansight **is** the NS/QD-**inspired** discovery platform. Current paper features remain and are the default harvest path for scholarly literature.

**Maturity:** Evidence pipeline **executable**. The discovery baseline provides `python -m nsqd skeleton` and `python -m nsqd harvest`, and the implemented baseline now includes N2a domain-policy isolation, N2b approved-paper projection, persisted pack-scoped map jobs, Operator A driven by a complete validated status table and structured axioms, and pack-scoped grounding with injected paper hybrid/scholar clients and a budget of 3 after local miss. N6 calibration/acquisition orchestration and later archive phases remain pending. Unified `gleansight` CLI and Map/Archive UI are **NSQD-N10**.

**Document roles**

| Document | Owns |
|----------|------|
| `docs/glossary-nsqd.md` | Terminology |
| `docs/algorithm-contract-nsqd.md` | Formulas, states, schemas, version semantics |
| This file | Externally observable obligations, citing contract IDs |
| `docs/development-plan-ns-qd.md` | Sequencing, tests, evidence, delivery status |
| `tests/fixtures/approved/nsqd/` | Approved inputs and expected outcomes |

---

## 1. Product scope

One local-first app with two layers:

| Layer | User job | Code |
|-------|----------|------|
| Evidence | Discover, import, convert, embed, extract, search papers; projects/tags/jobs | `src/papers/` (existing) |
| Discovery | Harvest (all record types) → map → diverge → ground → value → archive | `src/nsqd/` (new), same CLI/UI process |

**Must:**

1. Keep every current evidence workflow working (no regression of paper facts).
2. Project imported/analyzed papers into versioned **corpus records** (`type=paper`) — first in **NSQD-N2b**, after EW-V0A, DATA-NSQD-04, and EW-V2; not in N1.
3. Harvest additional types (code, benchmark, patent, industry, internal) as connectors land.
4. Run NS-QD stages without generate=evaluate in one use-case (`ALG-SEP`).
5. Emit Frontier Cards stamped with `snapshot_id` and `corpus_version` (`ALG-SNAP`).
6. Smoke-test the gate pair (gamma-flow plumbing; mechanism-free killed) against an **empty** `smoke_only` snapshot (`evidence=null`). Full calibration needs a `calibration` snapshot — not a smoke hook (`ALG-STATE`).

**Must not (this increment):** trading/`liq-validation` product, Qdrant, 12-process agents, rewrite of `src/papers`.

Agents in the PRD are **use-cases + CLI/UI commands**. Unified entrypoint `gleansight` is the **N10** target. Until then: `papers` (evidence), `python -m nsqd skeleton` (N1), and `python -m nsqd harvest` (N2).

---

## 2. Defaults

| Topic | Choice | Rationale |
|-------|--------|-----------|
| Product name | gleansight | User direction: evolve this product |
| Evidence package | keep `src/papers/` | Behavior-preserving; rename is a later refactor |
| Discovery package | `src/nsqd/` | New bounded context; not `liq-ideation` |
| Discovery CLI (N1/N2) | `python -m nsqd skeleton`, `python -m nsqd harvest` | Thin vertical slices |
| CLI (N10 target) | `gleansight` + existing `papers` | One product; no break of current scripts |
| UI (N10 target) | One Flet app: evidence screens stay; add Map, Archive, Card | Same desktop; not N1 |
| Vector store | LanceDB: existing paper table **and** a corpus-paraphrase collection | **HD-NSQD-01 closed: LanceDB.** Qdrant is out of scope |
| Embeddings | Existing sentence-transformers embedder for paraphrases in V1 | KISS |
| Card/corpus metadata | Piccolo + `data/blobs/nsqd/` | Rule of Three |
| Paper → corpus (v1) | Approved **human-reviewed** paraphrase + hashes (`ALG-PROJ`) | Abstract is not the paraphrase. Model-assisted drafting requires recorded human approval |
| Harvest (non-paper) | Approved enumerated captures first; optional S2 | No invented citations |
| Domain | Versioned `domain_policy_id` (e.g. `finance/1`, `optimization/1`); no implicit finance default | General platform |
| Generate ≠ evaluate | Persist candidate by hash; evaluator reloads under a new run id (`ALG-SEP`) | Session tokens alone are not sufficient |
| Clock | Injected `as_of` / `Clock` (`ALG-CLOCK`) | Windowed status tests must not use the wall clock |

HD-NSQD-02 is **closed** (product is gleansight, packages as above). HD-NSQD-01 is **closed** (LanceDB).

---

## 3. Functional requirements

### Evidence layer (existing — protect)

- **FR-E1** Discover, import, pipeline, analysis, hybrid search, projects/tags, CLI, UI keep current behavior.
- **FR-E2** Projection uses a **human-approved mechanism paraphrase** (not the abstract). Model-assisted drafting is allowed only when human approval is recorded. Persist explicit `domain_policy_id`, `paraphrase`, `paraphrase_source`, `source_paper_id`, `source_abstract_sha256`, `source_markdown_sha256`, `paraphrase_sha256` over normalized paraphrase bytes, `human_reviewer`, `human_approved_at` (UTC), and `review_status=approved`; the projector assigns/persists `paper-projector/1`. The application computes the normalized reviewed-payload digest and requires it in an injected approved-digest allowlist; caller payloads cannot self-approve, and the payload policy must match the explicit application argument. Canonical `content_hash` stays ALG-SNAP `{type, paraphrase, source}`; `record_id` is policy + source/hash-revision sensitive; the same full identity is idempotent and any approved source/hash revision creates a new record/snapshot. **N2b**, not N1.

### Harvest

- **FR-H1** Ingest enumerated records (type, paraphrase, source, optional coordinates, provenance). Reject essay-only / sourceless rows.
- **FR-H2** Embed the mechanism paraphrase, not the abstract.
- **FR-H3** Each commit increments store-local monotonic `corpus_version` and produces a content-addressed `snapshot_id` (`ALG-SNAP`).
- **FR-H4** Sufficiency report uses the domain expected-cell / recall-probe manifest (`ALG-SUF`), not cell statuses that already imply records.
- **FR-H5** Novelty **term** is 0 unless snapshot state is `calibration` or `production_valid`. N1 `smoke_only` persists a novelty evidence record on the candidate artifact with `evidence=null` plus version stamps (`ALG-NOV`, `ALG-STATE`). Numeric evidence is computed only when neighbors exist.
- **FR-H7** Snapshot id from the canonical JSON preimage (`ALG-SNAP`). Duplicates/retractions per that contract.
- **FR-H8** Sufficiency failure reasons are the closed set in `ALG-SUF` and are all tested.
- **FR-H6** `type=paper` records may originate from FR-E2 (N2b).
- **FR-H9** Bounded sufficiency-driven fallback is observable only for searchable `ALG-SUF` failures: searchable failures may trigger the N6 acquisition loop, integrity failures stop for review, and LLM output cannot set human approval or promote corpus evidence. Lifecycle/evidence remain **EV-N17 / N6** until implemented.

### Map

- **FR-M1** Cell status is an aggregation over corpus records (`ALG-STATUS`).
- **FR-M2** Status ∈ {Mature, Active, Sparse, Missing, Code-gap, Benchmark-gap, Future-work-only, Stalled, Invalid, Unknown}.
- **FR-M3** Load-bearing axioms are structured rows (operator A).
- **FR-M4** Status evaluation takes an injected `as_of` (`ALG-CLOCK`).

### Diverge

- **FR-D1** Baseline requires **Operator A** only. `generating_operator` is recorded as `A`.
- **FR-D1-FUTURE** Operators B–G are future requirements (lifecycle: deferred; not current acceptance criteria). A later revision activates them.
- **FR-D2** No rank/kill/score; does not call the gate.
- **FR-D3** Output is an immutable candidate artifact (hash persisted) plus `generator_run_id`.
- **FR-D4** Evaluator is a separate use-case that reloads by hash (`evaluator_run_id` ≠ `generator_run_id`). Session tokens alone are not sufficient (`ALG-SEP`).
- **FR-D5** When Operator A selects a target, the status table must exactly match the candidate policy universe; the runtime validates any supplied target against `ALG-SEL`, loads elite context from the archive, and rejects conflicting generation semantics at an existing candidate hash.

### Ground

- **FR-G1** Four layers, corpus-first: exact, terminology, embedding k-NN, code/benchmark (`ALG-GROUND`).
- **FR-G2** Live search only after corpus miss (≤3 escalations). N1 must not call live or paper hybrid search.
- **FR-G3** Report includes closest prior art, `GroundingClass`, confidence, `snapshot_id`, `corpus_version`.
- **FR-G4** New prior art creates a **new** snapshot (`ALG-SNAP` change rule). Existing snapshots are immutable.

### Value

- **FR-V1** Tier-1 is the product in `ALG-VIA`; any 0 rejects.
- **FR-V2** Novelty term follows `ALG-NOV` (includes Already done / Renamed → 0).
- **FR-V3** Finance pack: inefficiency-block rubric in `ALG-VIA`.
- **FR-V4** Smoke pair: mechanism-free has `mech=0`. Gamma-flow need not have novelty term > 0 on `smoke_only`. Both produce complete cards that are **not** archive-eligible. A later `calibration` snapshot is required before claiming production calibration.

### Archive and cards

- **FR-A1** One elite card per `mechanism × target × horizon` cell (`ALG-ELITE`).
- **FR-A2** No global rank until the `ALG-COV` guard (`50` elites **or** `20%` of the pack universe excluding Invalid). Unknown/uninspected cells stay in the denominator.
- **FR-A3** Re-score when `card.snapshot_id != current snapshot_id` (later slice).
- **FR-C1** Card schema includes `snapshot_id`, `corpus_version`, and Tier-1 product.
- **FR-C2** Invalid schema cannot be archived.

### Product surfaces

- **FR-U1** Unified `gleansight` CLI — **deferred to NSQD-N10**. Until then: `papers` (evidence), `python -m nsqd skeleton` (N1), and `python -m nsqd harvest` (N2).
- **FR-U2** Map/Archive/Card UI — **deferred to NSQD-N10**.
- **FR-U3** Thin clients only; use-cases own orchestration.

---

## 4. Non-functional

- **NFR-1** Quality gate: `uv run ruff format --check . && uv run ruff check . && uv run ty check && uv run pytest -q`. NS-QD must not weaken this. **EW-V0.11** is the named task that makes the existing Ruff/`ty` failures green; NSQD-N0 does not start until that task is done.
- **NFR-2** No regression of evidence-layer facts once Active.
- **NFR-3** `papers` domain/use-cases and `nsqd` use-cases import no provider SDKs.
- **NFR-4** Real harvest data; PRD calibration cards are requirement fixtures, never corpus records.
- **NFR-5** Local-first: SQLite + LanceDB + filesystem.
- **NFR-6** New `src/nsqd/` code has measured coverage ≥ the repository floor (90% until EW-V0.11 raises `fail_under` to 91.90). N1 cannot close on aggregate repository coverage alone.
- **NFR-7** Stored times are timezone-aware UTC (`ALG-CLOCK`).

---

## 5. Ports and domain services

**Reuse (existing paper ports):** `Embedder`, `LLMClient`, `ScholarClient`, `PaperStore`, paper `VectorIndex`, blob store. NS-QD must not depend on provider SDKs or on broad paper infrastructure except through these ports.

**New discovery ports** (external boundaries only):

| Port | Role |
|------|------|
| `CorpusRecordStore` | Persist/load corpus records |
| `CorpusSnapshotStore` | Commit/load snapshots |
| `CorpusIndex` | Snapshot-scoped k-NN (`ALG-IDX`) |
| `MorphospaceStore` | Cell inspection metadata |
| `NsqdCandidateStore` | Immutable candidate artifacts by hash |
| `FrontierCardStore` | Cards + elite pointer per cell |
| `NsqdJobQueue` | `nsqd_jobs` claim/retry/cancel |
| `Clock` | UTC `now()` |
| `HybridPaperSearch` | N5 search-only access to existing paper hybrid results |
| `LivePaperSearch` | N5 search-only access to scholar results |

**Domain services / functions** (not ports): novelty calculation, viability policy, status policy, elite decision, schema validation, snapshot digest, grounding class selection.

N2b consumes a reviewed projection payload, not a dedicated paper-read port. N5 adds typed search-only hybrid/scholar interfaces for prior-art checks; the stateful NSQD→paper acquisition/orchestration bridge remains deferred to N6.

**Application use cases** (not ports): `ProjectPaperUseCase` (N2b), harvest, map, diverge, ground, score, archive insert. Stage handlers are callable without the CLI.

Port tests assert behavioral contracts (snapshot filter, job exclusivity, clock). They do not freeze unnecessary method/class shapes.

---

## 6. Out of scope (this increment)

- Qdrant (HD-NSQD-01 closed)
- Live multi-engine deep-research APIs (optional later harvest connector)
- `liq-validation` / Alpha-card trading pipeline
- 12-agent runtime
- Renaming `src/papers` in the first slices
- Changing experimental `papers ask` synthesis (not the discovery gate)
- Operators B–G as current acceptance criteria
- Treating smoke snapshots as production-valid novelty or as production elites
- Durable NS-QD work on the paper `jobs` table
- Paper projector / DATA-NSQD-04 in N1
- Persistent nsqd tables before EW-V0B
- Starting NSQD-N0 before EW-V0.11 makes the four-command gate green

---

## 7. Traceability

| ID | Source | Contract | First test / evidence |
|----|--------|----------|------------------------|
| LOCAL-NSQD-H | PRD §3 Harvest | ALG-SNAP, ALG-SUF, ALG-NOV | EV-N01, EV-N02, EV-N03, EV-N13, EV-N16, EV-N17 |
| LOCAL-NSQD-M | PRD §4 Map | ALG-STATUS, ALG-CLOCK, ALG-SEL | EV-N06 |
| LOCAL-NSQD-D | PRD §5 Diverge | ALG-SEP, Operator A only | EV-N05 |
| LOCAL-NSQD-G | PRD §6 Ground | ALG-GROUND, ALG-NOV, ALG-IDX | EV-N10, EV-N11 |
| LOCAL-NSQD-V | PRD §7 Value | ALG-VIA | EV-N04 |
| LOCAL-NSQD-A | PRD §8 Archive | ALG-ELITE, ALG-COV | EV-N07, EV-N14, EV-N16 |
| LOCAL-NSQD-C | PRD §9 Card | ALG-ELITE, card schema | EV-N08 |
| LOCAL-NSQD-CAL | PRD §13 Calibration | ALG-STATE, ALG-VIA | EV-N00, EV-N04 |
| LOCAL-NSQD-SEP | PRD §1 generate ≠ evaluate | ALG-SEP | EV-N05 |
| LOCAL-NSQD-E | product thesis — evidence layer | ALG-PROJ (N2b), ALG-JOB | EV-N09 (N2b), EV-N12, EV-N17 |

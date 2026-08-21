# NS/QD documentation review — action checklist

**Review date:** 2026-08-18
**Status:** Documentation checklist and expensive decisions signed off 2026-08-18. **EW-V0.11, EW-V0.3, and EW-V0B are done.** NSQD-N0 and N1 persist may start. N1 still needs N0 + N0A.2.
**Scope:**

1. `docs/glossary-nsqd.md`
2. `docs/algorithm-contract-nsqd.md`
3. `docs/development-plan-ns-qd.md`
4. `docs/requirements-ns-qd.md`
5. `docs/product-gleansight.md`
6. `tests/fixtures/approved/nsqd/*.yaml` and their manifest

This checklist reviews conceptual correctness, cross-document traceability, implementation feasibility, SOLID/DRY/KISS architecture, and test-first delivery. Mark an item complete only when every acceptance criterion under it is true.

## Resolution log (2026-08-18)

| ID | Disposition | Notes |
|----|-------------|-------|
| PASS-01…08 | Preserved | No change to those decisions |
| REV-P0-01 | **Scope change** | N1 no longer claims a production elite. Smoke card is complete + rejected; elite tests are non-smoke units |
| REV-P0-02 | **Scope change** | Projector + EV-N09 moved to N2b. N1 no longer depends on DATA-NSQD-04. N2b depends on EW-V0A + DATA-NSQD-04 + EW-V2 |
| REV-P0-03 | **Accepted** | N1 is domain → application → adapters → E2E; EV-N00 is last |
| REV-P0-04 | **Accepted** | `ALG-VIA`: novelty evidence is numeric when neighbors exist and `null` on N1’s empty snapshot; the smoke `nov` term is 0. mech/fals/dpred use 0-or-5 presence rubrics; dval is human-assigned with provenance. 1–4 remain reserved for `ALG.VIABILITY` |
| REV-P0-05 | **Accepted** | Exclusive first-match table; Mature before Active; record-level `lifecycle`; injected `as_of` |
| REV-P0-06 | **Accepted** | `ALG-SUF` uses expected-cell / recall-probe manifest; closed failure codes; EV-N13 on N6; DATA-NSQD-03 still blocks `production_valid` |
| REV-P0-07 | **Dependency change** | NSQD-N0 depends on EW-V0.11. This review does not execute V0.11 and does not weaken the gate |
| REV-P1-01…15 | **Accepted** | Ownership, ports, CorpusIndex, jobs, clock, versions, grounding, coverage denom, tie-break, remove obsolete LanceDB gate, fixtures, synthetic units, nsqd coverage, EV-N13/N14, executable ablations |
| REV-P1-08 OR-rule | **Confirmed** | `50 elites OR 20%` stays (illuminate-first). Denominator is pack universe minus Invalid |
| REV-P2-01…08 | **Accepted** | Glossary NS/NSLC, FR-D1 Operator A, human paraphrase default, N10 surfaces, exact snapshot JSON, target cell vs parent card, backup-only rollback |

These were **not** workarounds. Where a claimed N1 behavior was impossible or a required artifact did not exist, **scope moved later** and **hard dependencies were named**. No invented paper, no provisional archive, no ratchet on the quality gate.

## Overall assessment

The revision closes the earlier issues and the P0 logic bugs by changing scope and dependencies. A `smoke_only` snapshot still forces the novelty term to zero and therefore viability to zero; N1’s observable outcome is therefore a rejected card and an empty production archive (elite insertion stays a non-smoke unit). N1 persists an **empty** smoke snapshot with `evidence=null`; synthetic neighbors remain pure unit-test inputs. Paper projection is out of N1 and waits on EW-V0A + DATA-NSQD-04 + EW-V2. NSQD-N0 must wait for EW-V0.11; N1 must additionally wait for EW-V0.3 and EW-V0B.

## Expensive-decision sign-off — accepted

**Product-owner sign-off:** all seven decisions and both implementation-order commitments accepted on 2026-08-18. The technical wording below is now normative for this plan revision.

| # | Decision | Technical recommendation | Human sign-off |
|---:|----------|--------------------------|----------------|
| 1 | N1 smoke produces a rejected card and empty production archive | **Accept.** EV-N00 uses an empty `smoke_only` snapshot, stores a novelty evidence record on the candidate artifact with `evidence=null`, and never creates an elite or provisional archive. | [x] |
| 2 | Projector out of N1; N2b waits on EW-V0A + DATA-NSQD-04 + EW-V2 | **Accept.** Do not invent a paper. | [x] |
| 3 | Viability stubs | **Accept for smoke/N1.** Numeric novelty evidence is computed only when neighbors exist; on N1’s empty snapshot it is `null` and the `nov` term is 0. `mech`/`fals`/`dpred` remain honest 0-or-5 presence checks; `dval` is human-assigned with provenance. No production/calibration claim may rely on these as graded prose-quality scores before `ALG.VIABILITY`. | [x] |
| 4 | Gap statuses preempt Mature/Active | **Accept.** Code-gap wins when papers exist but code does not. Benchmark-gap wins over Mature only when code/paper work claims evaluation but has no benchmark. | [x] |
| 5 | Rank guard: 50 elites OR 20% of `U \ {Invalid}` | **Accept.** Unknown/uninspected cells stay in the denominator. PRD wording was aligned to the 336-cell `finance/1` universe. | [x] |
| 6 | Operator A only in baseline | **Accept.** B–G remain deferred requirements, not hidden N1 obligations. | [x] |
| 7 | LanceDB closed for baseline; independent `nsqd_jobs` | **Accept for baseline.** `CorpusIndex` remains a narrow port and LanceDB a derived, rebuildable index. NS-QD owns its job enum/table; only neutral lease/retry mechanics may later be shared with paper jobs. No Qdrant reconsideration is required in the baseline. | [x] |

### N1 sanity path

```text
DATA-NSQD-01/02 requirement-cards (never corpus records)
  → Operator A + pack axiom → immutable candidate artifact
→ empty smoke_only snapshot → persisted candidate novelty evidence with evidence=null
  → map cell Unknown
  → local grounding layers 1–4; fail if paper hybrid/live search is called
  → nov=0 → viability=0
  → complete rejected Frontier Card
  → archive insertion attempted and rejected
  → production archive empty
  → python -m nsqd skeleton only
```

Synthetic vectors/neighbors are allowed only as deterministic unit-test inputs for novelty/status/archive math. A passing test may evidence algorithm correctness, but the synthetic values are not empirical/domain evidence, approved fixtures, or corpus data, and EV-N00 never persists them.

### TDD and prerequisite confirmation

- [x] N1 order remains Domain → Application → Adapters → EV-N00/thin CLI last.
- [x] Each production increment follows its failing tests and has a refactor checkpoint after green.
- [x] EW-V0.11 is mandatory before NSQD-N0.
- [x] EW-V0.3 and EW-V0B are mandatory before N1 because N1 both activates facts and persists NS-QD state.
- [x] N0A.2 supplies the two approved requirement-card oracles before N1.
- [x] N0A.3/N2b stay blocked until a real approved paper exists.

### Recorded written sign-off

- [x] I accept the seven decisions above.
- [x] I accept EW-V0.11 as the first implementation work; no `src/nsqd/` code starts before it is green. **Closed 2026-08-18:** four-command gate green (536 passed, 1 skipped, 91.91%).
- [x] I accept NSQD-N0 after EW-V0.11, and N1 only after EW-V0.3 + EW-V0B + N0 + N0A.2.

## Confirmed improvements — preserve these

- [x] **PASS-01 — Product terminology is explicitly NS/QD-inspired.**
  - `docs/glossary-nsqd.md` distinguishes project concepts from canonical NS, NSLC, and MAP-Elites.
  - API/fact naming uses `corpus_relative_novelty_evidence` rather than `ns_novelty`.
- [x] **PASS-02 — Product maturity is honest.**
  - `docs/product-gleansight.md`, `docs/requirements-ns-qd.md`, and `README.md` identify the evidence pipeline as executable and discovery as planned.
- [x] **PASS-03 — Snapshot identity includes content.**
  - The contract no longer identifies a snapshot from record IDs alone.
- [x] **PASS-04 — Smoke is not presented as calibration.**
  - `smoke_only` may prove plumbing but cannot activate production novelty facts.
- [x] **PASS-05 — Generate/evaluate separation has an auditable design.**
  - The evaluator reloads an immutable artifact by hash under a different run ID.
- [x] **PASS-06 — Evidence-layer dependencies are named explicitly.**
  - EW-V0.11, EW-V0.3, EW-V0B, EW-V0A, EW-V1, and EW-V2 dependencies and the `NSQD-N*` namespace are clear.
- [x] **PASS-07 — Paper projection does not equate an abstract with a mechanism paraphrase.**
  - The normative projector requires human-approved text in v1; model-assisted drafting requires recorded human review.
- [x] **PASS-08 — Durable NS-QD work has an ownership decision.**
  - Discovery work uses `nsqd_jobs` rather than violating the paper-jobs CHECK constraint.

---

## P0 — Must resolve before implementation

### [x] REV-P0-01 — Make smoke gate and archive semantics logically consistent

**Problem**

- `docs/algorithm-contract-nsqd.md` §3 forces `nov = 0` on `smoke_only`.
- Section 4 defines `viability = nov × mech × fals × dpred × dval`; therefore every smoke card has viability zero.
- Section 5 says viability-zero cards never become archive elites.
- `docs/development-plan-ns-qd.md` NSQD-N1 nevertheless requires one archive elite.

No implementation can satisfy all four rules.

**Resolution**

**Scope change:** N1’s observable outcome is a complete rejected card and an empty production archive. Elite insertion is a non-smoke unit (EV-N07). No second archive was added.

**Acceptance criteria**

- [x] The algorithm contract (`ALG-ELITE`, `ALG-STATE`), N1 observable outcome, EV-N00, EV-N04, EV-N07, and smoke fixture `expected_outcomes` agree: smoke cards are **not** archive-eligible.
- [x] No Active fact can imply a smoke card passed Tier-1 or became a production elite (`NSQD.E2E.SMOKE_LOOP.v1` states rejection; N1.12 forbids those facts).
- [x] A test proves the candidate artifact stores novelty evidence with `evidence=null` and the required measurement stamp, novelty term is zero, viability is zero, and archive insertion is rejected (EV-N00, EV-N02, EV-N04).
- [x] A separate pure unit test is named for empty-cell insertion, higher-quality replacement, tie handling, and rejected-card behavior (EV-N07, non-smoke inputs).

### [x] REV-P0-02 — Keep DATA-NSQD-04 out of N1; defer projector to N2b

**Problem**

The earlier N1 path incorrectly began with an approved paper fixture and claimed `NSQD.PROJECT.HUMAN_PARAPHRASE.v1` while DATA-NSQD-04 was absent. DATA-NSQD-04 must not be invented while the evidence-layer data-acquisition gate EW-V0A remains open.

**Resolution**

**Alternative accepted:** do not invent a paper. Remove projector behavior and EV-N09 from N1. DATA-NSQD-04 was a blocked future data prerequisite during this review and has since been acquired as a real approved paper plus model-assisted, human-approved paraphrase. First projector delivery remains **N2b**; N1 uses DATA-NSQD-01/02 as candidate-requirement-cards only.

**Acceptance criteria**

- [x] DATA-NSQD-04 was not claimed during this review; its later acquisition is recorded separately with integrity and approval metadata.
- [x] Manifest lists 01/02 and the later approved 04 fixture with integrity/approval metadata.
- [x] NSQD-N1 depends on N0A.2 (01/02), not on N0A.3.
- [x] The “else 01 paraphrase only” fallback is removed.
- [x] DATA-NSQD-01 and DATA-NSQD-02 are typed `candidate-requirement-card` and `never_corpus_record = true`.

### [x] REV-P0-03 — Reorder N1 into genuine red-green-refactor increments

**Resolution**

N1.1–N1.3 domain; N1.4–N1.6 application; N1.7–N1.9 adapters; N1.10–N1.11 E2E/CLI; explicit refactor tasks after each green increment.

**Acceptance criteria**

- [x] Every production task names the tests that fail immediately before it and that it alone makes green.
- [x] No “implement E2E” task precedes lower-level contract tests for the same behavior.
- [x] EV-N00 is the final composition test (N1.10/N1.11).
- [x] Each increment ends with the four-command gate green.
- [x] Refactoring checkpoints are explicit (N1.3, N1.6, N1.9).

### [x] REV-P0-04 — Define all viability factor scoring rules

**Resolution**

`ALG-VIA`: numeric novelty evidence is computed when neighbors exist and is `null` for N1’s empty snapshot; the smoke `nov` term is 0. Finance `mech` / `fals` / `dpred` are presence rubrics (0 or 5); `dval` is human-assigned with provenance. Intermediate 1–4 are `ALG.VIABILITY`, not silent invention.

**Acceptance criteria**

- [x] The contract defines deterministic rubrics or declares human-assigned inputs.
- [x] Human-assigned `dval` includes reviewer/provenance and validation (missing → 0).
- [x] Missing/empty fields have a declared factor result (`finance/1`).
- [x] Smoke fixtures contain `expected_outcomes` (not filename branches).
- [x] Unit tests are named for every zero path and representative non-zero boundaries.

### [x] REV-P0-05 — Correct or prove the cell-status precedence table

**Resolution**

`ALG-REC` + `ALG-STATUS` exclusive first-match table; Mature before Active; record-level `lifecycle`; `ALG-CLOCK`.

**Acceptance criteria**

- [x] Predicates are exclusive via first-match plus worked overlap examples.
- [x] Mature is reachable (`P≥5` and `C≥1`, not Code-gap).
- [x] Record-level states used by Stalled are defined separately.
- [x] A table-driven unit test is named for every status and overlap (EV-N06).
- [x] Time-window tests use injected `as_of`.

### [x] REV-P0-06 — Replace the circular sufficiency rule with a measurable policy

**Resolution**

`ALG-SUF` + EV-N13 (N6). DATA-NSQD-03 remains a blocker for honest `production_valid`.

**Acceptance criteria**

- [x] Sufficiency uses an expected-cell / recall-probe manifest.
- [x] Minimum coverage is delegated to versioned domain policy `finance/1`.
- [x] Promotion facts/evidence exist (EV-N13, N6).
- [x] Failure reasons are a closed typed set and are all to be tested.
- [x] DATA-NSQD-03 remains a blocker until the policy can be evaluated honestly.

### [x] REV-P0-07 — Restore the advertised baseline quality gate before N0

**Problem**

At review time `ruff check` (79) and `ty check` (526) fail. Pytest passes.

**Resolution**

**Dependency change:** NSQD-N0.1 depends on EW-V0.11 (`docs/development-plan-open-work.md`). The four-command gate is unchanged. This documentation pass does not execute V0.11. Implementation readiness stays blocked until that closeout task is green.

**Acceptance criteria**

- [x] Failures are assigned to an explicit prerequisite task (EW-V0.11).
- [x] NSQD-N0 does not weaken, bypass, or redefine the repository gate.
- [x] All four commands exit zero from the same clean worktree before NS-QD implementation begins — recorded 2026-08-18: 536 passed, 1 skipped, 91.91%.
- [x] Passing test count and coverage re-recorded after lint/type corrections — 536 passed, 1 skipped, 91.91% combined; `fail_under` is 91.90.

---

## P1 — Architecture and maintainability

### [x] REV-P1-01 — Establish one normative owner for each policy

**Acceptance criteria**

- [x] Duplicated rules now point at `ALG-*` IDs.
- [x] Requirements session-token default removed; `ALG-SEP` persist+reload is the rule.
- [x] Traceability table maps each LOCAL-* id to a contract rule and evidence item.
- [x] Novelty, viability, snapshot state, and archive replacement are owned by the algorithm contract.

### [x] REV-P1-02 — Keep ports at external boundaries; keep policies in domain/application code

**Acceptance criteria**

- [x] Stores, indexes, clocks, external search, model providers, blobs, and job queues are the ports.
- [x] Novelty, viability, status, elite, schema validation are domain functions.
- [x] `PaperToCorpusProjector` is an N2b application use case on a minimal `PaperSource` port.
- [x] NS-QD must not depend on provider SDKs or broad paper infrastructure.
- [x] Port tests are specified as behavioral contracts.

### [x] REV-P1-03 — Define a snapshot-aware `CorpusIndex` contract

**Acceptance criteria**

- [x] `ALG-IDX` is independent from paper `VectorIndex`.
- [x] Query includes snapshot identity and excludes other snapshots.
- [x] Results include record id, distance, deterministic ties.
- [x] Measurements stamp model/version/normalization/metric/contract version.
- [x] Unit tests: deterministic vectors; adapter tests: local LanceDB, no downloads.

### [x] REV-P1-04 — Reuse job policy without coupling NS-QD to paper job types

**Acceptance criteria**

- [x] NS-QD owns `NsqdJobType`, record, table, and queue port (`ALG-JOB`).
- [x] Shared lease/retry extracted only when both contexts actually use it.
- [x] Paper and NS-QD job-type enums remain independent.
- [x] Tests named for claim exclusivity, retries, cancel, terminal states, UTC (EV-N12).
- [x] Stage handlers callable directly; CLI must not duplicate orchestration (N1.5 / N1.11).

### [x] REV-P1-05 — Add a clock seam

**Acceptance criteria**

- [x] `ALG-CLOCK`: status/application logic receives `as_of` / `Clock`.
- [x] Production composition supplies a UTC system clock.
- [x] Tests cover window boundaries with a fixed clock (EV-N06).
- [x] Stored timestamps remain timezone-aware UTC.

### [x] REV-P1-06 — Define snapshot ID, corpus version, and change levels separately

**Acceptance criteria**

- [x] `snapshot_id` is immutable content identity with exact canonical JSON (`ALG-SNAP`).
- [x] `corpus_version` is a monotonic **local** revision, not content identity.
- [x] Minor/major language removed; change rule is `card.snapshot_id != current`.
- [x] Grounding new prior art creates a new snapshot.
- [x] Re-score trigger is that single rule.

### [x] REV-P1-07 — Complete the grounding result contract

**Acceptance criteria**

- [x] `GroundingClass` is a closed enum (`ALG-GROUND`).
- [x] N1 confidence is deterministic from the layer table (not human).
- [x] Every cascade layer records checked / hit / escalate reason.
- [x] N1 fail-fast if paper hybrid or live search is called (EV-N10).
- [x] N5 cannot use paper hybrid search until EW-V1 is Active.

### [x] REV-P1-08 — Fix archive coverage denominator and rank gating

**Acceptance criteria**

- [x] Domain-pack version defines eligible universe (`finance/1`: 336 cells).
- [x] Unknown / uninspected cells stay in the denominator.
- [x] Requirements and contract use the same `U \ {Invalid}` language.
- [x] EV-N14 covers below-threshold and both boundaries (N7).
- [x] Product confirmation recorded: `50 OR 20%` is intentional.

### [x] REV-P1-09 — Use a reproducible archive tie-breaker

**Acceptance criteria**

- [x] Tie-breaker is `candidate_artifact_hash` (`ALG-ELITE`).
- [x] Elite replay is specified as order-independent.
- [x] Unit tests named for replay and equal-viability insertion order (EV-N07).

### [x] REV-P1-10 — Remove the already-decided LanceDB/Qdrant decision task

**Acceptance criteria**

- [x] The obsolete LanceDB/Qdrant decision task was removed and HD-NSQD-01 closed as LanceDB. The current NSQD-N0.4 is the ports/null-adapters implementation task, not that decision gate.

---

## P1 — TDD, fixtures, and coverage

### [x] REV-P1-11 — Define fixture schemas and expected outcomes

**Acceptance criteria**

- [x] Every fixture declares `kind`.
- [x] Candidate-input validation can reach the gate (negative control has empty mechanism fields by design); complete Frontier Card validation stays strict.
- [x] `expected_outcomes` include `snapshot_empty`, `evidence` (`null` on N1), factors, viability, archive eligibility.
- [x] Manifest entries include content hash, reviewer, approval revision, UTC date.
- [x] Tests must load expected outcomes from schema fields (N1.1).

### [x] REV-P1-12 — Clarify synthetic unit inputs versus approved evidence data

**Acceptance criteria**

- [x] Plan header allows synthetic/in-memory values for unit tests; forbids treating them as evidence or approved corpus data.
- [x] Fact/evidence tests use approved fixtures where the claim depends on requirement data.
- [x] Pure math/state-policy tests are specified as fixture-minimal.

### [x] REV-P1-13 — Add NS-QD-specific unit coverage acceptance

**Acceptance criteria**

- [x] New `src/nsqd/` code ≥ 90% measured (`--cov=src/nsqd --cov-fail-under=90`) until EW-V0.11 raises the repo floor.
- [x] Pure domain policies have direct unit tests (N1.1).
- [x] Adapter tests and one E2E complement unit tests.
- [x] Coverage commands stated in the plan (and still 90 in README / `pyproject.toml` until EW-V0.11).
- [x] N1 cannot close solely because aggregate repository coverage passes.

### [x] REV-P1-14 — Add direct evidence for sufficiency and rank guard behavior

**Acceptance criteria**

- [x] EV-N13 / NSQD.SNAPSHOT.PROMOTION.v1 — Pending: N6.
- [x] EV-N14 / NSQD.ARCHIVE.RANK_GUARD.v1 — Active / Required (N7).
- [x] Deferred evidence is clearly Pending with its first available phase.

### [x] REV-P1-15 — Make ablation studies executable

**Acceptance criteria**

- [x] `ALG-ABL` names dataset state, metric, n, threshold, and artifact path.
- [x] Novelty-bin calibration depends on a `calibration` snapshot, not `smoke_only`.
- [x] `ALG.K` uses Spearman ρ ≥ 0.90 vs k=5.
- [x] Axis evaluation has reviewers and a 0–2 rubric.
- [x] Status-threshold evaluation requires ≥ 8/10 agreement on 10 hand-labeled cells.
- [x] `ALG.VIABILITY` is in ablation scope.

---

## P2 — Cross-document cleanup

### [x] REV-P2-01 — Correct the canonical NS novelty glossary entry

- [x] Canonical novelty is k-NN in behavior space against the **current population plus the permanent novelty archive**.
- [x] Corpus-relative project metric remains distinct.

### [x] REV-P2-02 — Correct the local-competition glossary entry

- [x] Local competition is a neighborhood-relative score (often neighbors outperformed).
- [x] Distinguished from elite replacement and the domain viability gate.

### [x] REV-P2-03 — Resolve baseline Operator A versus FR-D1 A–G

- [x] Baseline FR-D1 requires Operator A only.
- [x] B–G are `FR-D1-FUTURE` (deferred), not current acceptance criteria.
- [x] Product language says “Operator A in the baseline; B–G later.”

### [x] REV-P2-04 — Align paper projection defaults with the human-approved v1 contract

- [x] Defaults table: v1 consumes an approved human-reviewed paraphrase.
- [x] Model-assisted drafting is allowed only with recorded human approval.

### [x] REV-P2-05 — Mark unified CLI/UI text as target-state N10

- [x] Product CLI/UI language identifies unified commands/screens as N10.
- [x] N1 promises only `python -m nsqd skeleton`.
- [x] Product Review order numbering is 1–7 (duplicate “5” removed).

### [x] REV-P2-06 — Make the snapshot hash serialization exact

- [x] Canonical JSON object, UTF-8, sorted keys, tight separators, NFC, LF, source normalization.
- [x] Known digest vectors in `ALG-SNAP`.
- [x] Order-invariance and schema-version change vectors recorded.

### [x] REV-P2-07 — Rename “parent cell” where no parent exists

- [x] `ALG-SEL` distinguishes target-cell selection from optional parent-card context.
- [x] Operator A on an empty cell uses pack axioms only.

### [x] REV-P2-08 — Make rollback language match forward-only migrations

- [x] N1 rollback is restore-from-backup taken before persist.
- [x] No implied `DROP` via a non-existent down migration.

---

## Required N1 test matrix

Named in `docs/development-plan-ns-qd.md`. Domain and application increments are in tree on null adapters; Piccolo adapters, CLI, and EV-N00 E2E are not.

### Pure unit tests

- [x] Snapshot digest is order-independent and changes with record content/schema version. (EV-N01 / N1.1)
- [x] Novelty handles zero records, fewer than `k`, exact `k`, ties, and known cosine vectors. (EV-N11)
- [x] Smoke E2E stores a novelty evidence record on the candidate artifact with `evidence=null` and the required measurement stamp, and forces novelty term and viability to zero. Numeric k-NN evidence is a unit test with injected neighbors, never persisted by EV-N00. (EV-N02 / EV-N11)
- [x] Every status rule and overlap boundary is table-tested with a fixed clock. (EV-N06)
- [x] Every viability factor zero rejects; non-zero boundary values use the declared rubric. (EV-N04 / `ALG-VIA`)
- [x] Card schema rejects each missing required field independently. (EV-N08)
- [x] Archive handles empty cell, better/worse/equal candidate, rejected candidate, insertion order, and replay. (EV-N07)
- [x] Grounding classes and cascade escalation are deterministic. (EV-N10 domain part)

### Application tests

- [x] Projector **deferred to N2b** (accepted alternative to P0-02).
- [x] Diverge persists an immutable artifact; Evaluate reloads by hash under a different run ID. (EV-N05)
- [x] N1 local grounding fails the test if live or paper hybrid search is called. (EV-N10)
- [x] Job handlers are separately callable and do not duplicate CLI orchestration. (N1.4 / N1.11)

### Adapter/integration tests

- [x] Piccolo migration creates NS-QD tables only through the EW-V0B runner. (N1.7)
- [x] `nsqd_jobs` cannot write discovery types to paper `jobs`. (EV-N12)
- [x] Null `CorpusIndex` and LanceDB adapter filter by snapshot and return deterministic distances/ties. (`ALG-IDX`)
- [x] One final E2E test composes the approved fixture path and asserts the corrected smoke/archive outcome. (EV-N00)

## Exit criteria for this review

- [x] All P0 documentation and implementation prerequisites are checked; the four-command gate is green.
- [x] Every P1 item is checked.
- [x] P2 documentation corrections are checked.
- [x] The dependency matrix and N1 task order agree with the revised contracts.
- [x] DATA-NSQD-04 is now approved; all paper-projector claims remain removed from N1 and EV-N09 remains pending N2b.
- [x] A plan-only consistency pass finds no requirement simultaneously mandatory and out of scope (FR-D1 vs B–G resolved).
- [x] Pre-existing Ruff/`ty` failures are explicitly assigned to EW-V0.11 and are not required to be fixed by this documentation-review pass. This review does not weaken, bypass, or redefine the four-command gate.

## Reference basis

Canonical terminology findings use:

- Lehman & Stanley (2011), Novelty Search: novelty over behavior-space neighbors from the current population and permanent novelty archive.
- Lehman & Stanley (2011), Novelty Search with Local Competition: local competition compares performance against nearest niche-space neighbors.
- MAP-Elites/QD reference implementations such as QDax and pyribs: an archive cell retains the candidate with the declared better objective/quality.

These references justify terminology corrections only. The project-specific corpus-relative metric and domain viability gate remain valid so long as they are not presented as canonical NS/NSLC behavior.

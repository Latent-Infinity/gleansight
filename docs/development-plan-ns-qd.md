# Development Plan: gleansight NS/QD-inspired discovery

**Guide Version**: 2.0
**Mode**: Vertical-Slice
**Plan Type**: Existing-System Feature
**Planning Horizon**: Rolling-Wave (NSQD-N0, N0A, N1 expanded; N2+ listed)
**Plan Set**: gleansight
**Builds On**: `docs/development-plan-open-work.md` (evidence closeout; **hard deps** below)
**Phase ID prefix**: `NSQD-N*` (never reuse closeout `V0`/`V0B`/`V1`/`V2`)
**Inherited Facts**: all `Active` rows in `docs/fact-ledger.md`
**Supersedes**: `docs/development-plan-ns-qd.md` v1.2.0 wording (same file, revision)
**PRD Trace**: `docs/prd-ns-qd.md` + `docs/requirements-ns-qd.md` + `docs/algorithm-contract-nsqd.md` (`LOCAL-NSQD-*`)
**Real Data Policy**: Approved fixtures only. DATA-NSQD-01/02 are **requirement-card** fixtures (`smoke_only`), never corpus records. Harvest seed and paper-04 still pending.
**Generated Data Authorization**: `None` for evidence claims and approved corpus data. **Synthetic / in-memory values are allowed for pure unit tests** of math and state policy. A passing unit test may evidence algorithm correctness; the synthetic values themselves are not empirical/domain evidence, approved fixtures, or corpus data, and EV-N00 never persists them.
**Provider Policy**: `src/nsqd/` + `src/papers/`. **HD-NSQD-01 closed: LanceDB** corpus collection. Durable NS-QD work in **`nsqd_jobs`**, not paper `jobs`.
**Fact Policy**: Append `NSQD.*`. Smoke snapshots must **not** activate production novelty facts and must **not** produce a production archive elite.
**Data & Provider Readiness**: DATA-NSQD-01/02 committed. DATA-NSQD-03 **missing**. DATA-NSQD-04 **missing** (do not invent). Evidence closeout **EW-V0.11**, **EW-V0.3**, and **EW-V0B** done; **EW-V0A**, **EW-V2**, and **EW-V1** not done.
**Slice Ordering**: Closeout deps first. Domain → application → adapters → final E2E (N1). Then harden stages. Paper projector is **N2b**, not N1.
**Outstanding Blockers**: **EW-V0.11, EW-V0.3, EW-V0B, EW-V0A done.** DATA-NSQD-03; **EW-V2** + DATA-NSQD-04 before N2b; **EW-V1** before N5 paper hybrid search. NSQD-N0 and N1 persist are unblocked. DATA-NSQD-04 still needs a human paraphrase of one V0A paper.

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

NS-QD does not weaken, bypass, or redefine this gate. `pyproject.toml` `fail_under` stays **90** until EW-V0.11 sets **91.90**. New `src/nsqd/` code must also meet ≥90% measured coverage (`uv run pytest tests/nsqd tests/facts/test_nsqd_*.py --cov=src/nsqd --cov-fail-under=90`). N1 cannot close solely because aggregate repository coverage passes.

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-08-18 | Initial plan. |
| 1.1.0 | 2026-08-18 | Product = gleansight platform. |
| 1.2.0 | 2026-08-18 | NS/QD-inspired rename; glossary + algorithm contract; N1 true E2E; cross-plan deps; nsqd_jobs; smoke vs calibration; missing facts; ablations; CLI in N1. |
| 1.3.0 | 2026-08-18 | Review `docs/review-nsqd-action-items.md`: smoke card rejected / empty archive; projector removed from N1; N1 TDD order; viability rubrics; exclusive status table; measurable sufficiency; EW-V0.11 gate prereq; HD-NSQD-01 closed; Operator A only. |
| 1.3.1 | 2026-08-18 | Frame remaining review items as scope/dependency changes, not workarounds: N2b waits on EW-V0A + DATA-NSQD-04 + EW-V2; N0 waits on EW-V0.11; no invented paper or provisional archive. |
| 1.3.2 | 2026-08-18 | Decision-signoff audit: EV-N00 uses an empty snapshot with `evidence=null`; synthetic neighbors stay unit-only; N1 depends on EW-V0.3 fact infrastructure as well as EW-V0B. |
| 1.3.3 | 2026-08-18 | Close leftover contradictions: header blockers name EW-V0.3; N1 smoke oracles say `evidence=null` (not numeric); empty-snapshot digest vector recorded. |
| 1.3.4 | 2026-08-19 | Align data/provider readiness with completed EW-V0.11, EW-V0.3, and EW-V0B prerequisites. |

---

## Cross-plan dependency matrix

Closeout phases (`docs/development-plan-open-work.md`) are prefixed **EW-**.

| Discovery need | Depends on | Why | If skipped |
|----------------|------------|-----|------------|
| Any NSQD-N0 code task | **EW-V0.11** (done 2026-08-18) | Four-command gate must stay green | Do not start N0 from a red tree |
| Any Piccolo `nsqd_*` table | **EW-V0B** (done 2026-08-19) | Shared schema runner; no second ad-hoc `create_table` | — |
| `PaperToCorpusProjector` on imported papers | **EW-V0A** approved real paper fixtures, **EW-V2** atomic import, and DATA-NSQD-04 | Stable paper_id + membership; real approved paper + human paraphrase | Duplicate/orphan corpus rows; invented paper |
| Grounding that calls paper hybrid search | **EW-V1** one-based RRF | Wrong ranks → wrong prior-art neighbors | False grounding |
| Fact surface / approved-path checker | **EW-V0.3** | `tests/facts`, Lifecycle checker | Parallel checker forks |
| UTC timestamps in nsqd | `ALG-CLOCK` from N1; do not copy evidence-layer naive `now()` | Evidence-layer naive `now()` is EW debt | Mixed timestamps |
| Durable harvest/ground/diverge/score | **`nsqd_jobs`** after EW-V0B | Paper `jobs` CHECK allows only discover/download/convert/embed/analyze | Inserts fail or untracked sync work |

**Rule:** N0 (ports, null adapters, glossary tests) may proceed (**EW-V0.11** is done). **N1 persistence and N1 E2E against real Piccolo wait for EW-V0B.** EW-V0.3 fact/evidence infrastructure is in place. N1 does **not** project papers. Live projection waits for N2b (EW-V0A + EW-V2 + DATA-NSQD-04).

---

## Durable work (decision)

**Choice: (2) `nsqd_jobs` owned by discovery.**

Paper `jobs` + EW-V0B CHECK stay paper-only. Harvest, project (N2b), diverge, ground, score, re-score are rows in `nsqd_jobs` with `NsqdJobType` / `NsqdJobRecord` owned by `src/nsqd/`. Do not import paper `JobType`. Shared lease/retry/backoff may be extracted into a **neutral** policy module only when both contexts actually call it. Do not run those stages as untracked synchronous CLI-only work once N1 persists. Stage handlers stay callable without the CLI.

---

## Plan Compliance Matrix

| Invariant | Evidence | Status | Blocked Phases | Resolution |
|-----------|----------|--------|----------------|------------|
| PRD / algorithm contract | glossary + algorithm-contract | Pass | — | — |
| Terminology | NS/QD-inspired; corpus-relative novelty | Pass | — | — |
| Vertical E2E | NSQD-N1 path (rejected smoke card) | Pass | — | — |
| Real data | 01/02 committed; 03/04 pending | Blocked: harvest-from-seed; projector | N2, N2b, N6 | N0A.3 / N0A.4 |
| Four-command gate | EW-V0.11 | Pass (2026-08-18) | — | 536 passed, 1 skipped, 91.91% |
| EW fact surface | EW-V0.3 | Pass (2026-08-18) | — | `tests/support/test_fact_surface.py` |
| EW migrator | EW-V0B | Pass (2026-08-19) | — | `schema_migrations` + jobs CHECK |
| EW approved papers | EW-V0A | Blocked: N2b / N0A.3 | N2b | EW-V0A |
| EW atomic import | EW-V2 | Blocked: N2b live import | N2b | EW-V2 |
| EW RRF | EW-V1 | Blocked: N5 if using paper search | N5 | EW-V1 |
| Operators B–G | explicitly deferred | N/A (deferred) | — | later revision |
| HD-NSQD-01 | LanceDB recorded | Pass | — | closed; no N0.4 |

---

## Fact Ledger (this plan)

| Fact ID | Statement | Applies When | Kind | Req | Evidence |
|---------|-----------|--------------|------|-----|----------|
| NSQD.E2E.SMOKE_LOOP.v1 | Given the approved requirement-card fixtures and an axiom, when the N1 pipeline runs on an **empty** `smoke_only` snapshot, then a novelty evidence row is stored with `evidence=null`, novelty term is 0, viability is 0, one complete Frontier Card is persisted with `card_decision=rejected`, archive insertion is rejected, and the production archive is empty | N1 | Behavior | LOCAL-NSQD-CAL | EV-N00 |
| NSQD.CORPUS.SNAPSHOT_HASH.v1 | Given records, when a snapshot is created, then `snapshot_id` matches `ALG-SNAP` known vectors (order-invariant; changes with content or schema version) | Any snapshot | Data Contract | LOCAL-NSQD-H | EV-N01 |
| NSQD.CORPUS.SMOKE_NO_NOVELTY_TERM.v1 | Given N1’s empty `smoke_only` snapshot, when the gate runs, then a novelty row is stored with `evidence=null`, novelty **term** is 0, and the card is not archive-eligible. Numeric evidence is computed only in unit tests that inject neighbors | Smoke | Behavior | LOCAL-NSQD-H | EV-N02 |
| NSQD.HARVEST.ENUMERATION.v1 | Sourceless / essay-only ingest is rejected | Harvest | Behavior | LOCAL-NSQD-H | EV-N03 |
| NSQD.GATE.SMOKE_PAIR.v1 | On a smoke snapshot, mechanism-free has `mech=0`; gamma-flow has `mech=5` and `nov=0`; both `viability=0` and `archive_eligible=false`. Expected values come from fixture `expected_outcomes`, not filenames | Smoke fixtures | Behavior | LOCAL-NSQD-CAL | EV-N04 |
| NSQD.SEP.AUDIT_RECORD.v1 | Evaluator loads candidate by `candidate_artifact_hash` under a new `evaluator_run_id`; same-run generate+evaluate without persist/reload is rejected | Diverge/value | Architecture Contract | LOCAL-NSQD-SEP | EV-N05 |
| NSQD.MAP.STATUS_RULES.v1 | Cell status matches `ALG-STATUS` exclusive table at an injected `as_of`, including every status and overlap listed there | Map | Behavior | LOCAL-NSQD-M | EV-N06 |
| NSQD.ARCHIVE.ELITE_REPLACE.v1 | Given **non-smoke** constructed inputs with `viability > 0`, elite replacement uses viability then smaller `candidate_artifact_hash`; rejected cards never insert; replay is order-independent | Archive write | Behavior | LOCAL-NSQD-A | EV-N07 |
| NSQD.CARD.SCHEMA.v1 | Card missing any required schema field is rejected independently | Archive | Data Contract | LOCAL-NSQD-C | EV-N08 |
| NSQD.PROJECT.HUMAN_PARAPHRASE.v1 | Projector writes human-approved paraphrase + hashes; abstract is not stored as paraphrase; idempotent on source/content identity | Paper projection **N2b** | Behavior | LOCAL-NSQD-E | EV-N09 |
| NSQD.GROUND.CASCADE.v1 | Local layers 1–4 run and persist `{layer, checked, hit, escalate_reason}`; live and paper hybrid search are not called on the N1 path; version stamped | Ground | Behavior | LOCAL-NSQD-G | EV-N10 |
| NSQD.NOVELTY.METRIC.v1 | Evidence equals mean cosine distance to k-NN paraphrases (`ALG-NOV`); covers 0, `<k`, exact `k`, ties, known unit vectors | Novelty | Behavior | LOCAL-NSQD-G | EV-N11 |
| NSQD.JOBS.OWNED.v1 | Harvest/diverge/ground/score persist as `nsqd_jobs` with `NsqdJobType`; paper `jobs` rejects discovery types | Durable work | Architecture Contract | LOCAL-NSQD-E | EV-N12 |
| NSQD.SNAPSHOT.PROMOTION.v1 | Promotion to `calibration` / `production_valid` follows `ALG-SUF`; every `SufficiencyFailure` code is produced by a test. Honest `production_valid` is blocked until DATA-NSQD-03 | N6 | Behavior | LOCAL-NSQD-H | EV-N13 |
| NSQD.ARCHIVE.RANK_GUARD.v1 | Global rank fails below 50 elites and below 20% of `U \ {Invalid}`; both thresholds and the below-threshold case are tested | N7 | Behavior | LOCAL-NSQD-A | EV-N14 |

**Not activated on smoke:** any “production novelty term > 0” fact; any “smoke card became a production elite” fact. **Deferred (not in baseline):** operators B–G; paper projector (N2b).

---

## Evidence Index

| ID | Facts | Command | Available From | Lifecycle |
|----|-------|---------|----------------|-----------|
| EV-N00 | NSQD.E2E.SMOKE_LOOP.v1 | `uv run pytest tests/facts/test_nsqd_e2e_smoke.py -q` | N1 | Pending: N1 |
| EV-N01 | NSQD.CORPUS.SNAPSHOT_HASH.v1 | `uv run pytest tests/facts/test_nsqd_snapshot_hash.py -q` | N1 | Pending: N1 |
| EV-N02 | NSQD.CORPUS.SMOKE_NO_NOVELTY_TERM.v1 | `uv run pytest tests/facts/test_nsqd_smoke_novelty_term.py -q` | N1 | Pending: N1 |
| EV-N03 | NSQD.HARVEST.ENUMERATION.v1 | `uv run pytest tests/facts/test_nsqd_harvest_reject_essay.py -q` | N2 | Pending: N2 |
| EV-N04 | NSQD.GATE.SMOKE_PAIR.v1 | `uv run pytest tests/facts/test_nsqd_gate_smoke_pair.py -q` | N1 | Pending: N1 |
| EV-N05 | NSQD.SEP.AUDIT_RECORD.v1 | `uv run pytest tests/facts/test_nsqd_eval_audit.py -q` | N1 | Pending: N1 |
| EV-N06 | NSQD.MAP.STATUS_RULES.v1 | `uv run pytest tests/facts/test_nsqd_map_status.py -q` | N1 | Pending: N1 |
| EV-N07 | NSQD.ARCHIVE.ELITE_REPLACE.v1 | `uv run pytest tests/facts/test_nsqd_elite.py -q` | N1 | Pending: N1 |
| EV-N08 | NSQD.CARD.SCHEMA.v1 | `uv run pytest tests/facts/test_nsqd_card_schema.py -q` | N1 | Pending: N1 |
| EV-N09 | NSQD.PROJECT.HUMAN_PARAPHRASE.v1 | `uv run pytest tests/facts/test_nsqd_paper_project.py -q` | N2b | Pending: N2b |
| EV-N10 | NSQD.GROUND.CASCADE.v1 | `uv run pytest tests/facts/test_nsqd_ground_cascade.py -q` | N1 | Pending: N1 |
| EV-N11 | NSQD.NOVELTY.METRIC.v1 | `uv run pytest tests/facts/test_nsqd_novelty_knn.py -q` | N1 | Pending: N1 |
| EV-N12 | NSQD.JOBS.OWNED.v1 | `uv run pytest tests/facts/test_nsqd_jobs.py -q` | N1 | Pending: N1 |
| EV-N13 | NSQD.SNAPSHOT.PROMOTION.v1 | `uv run pytest tests/facts/test_nsqd_sufficiency.py -q` | N6 | Pending: N6 |
| EV-N14 | NSQD.ARCHIVE.RANK_GUARD.v1 | `uv run pytest tests/facts/test_nsqd_rank_guard.py -q` | N7 | Pending: N7 |

Phase close: evidence Required + facts Active (`test_fact_surface.py`).

---

## Real Data Manifest

| Data ID | Status | Kind | Path |
|---------|--------|------|------|
| DATA-NSQD-01 | **Committed** | `candidate-requirement-card` — **not** a corpus record | `tests/fixtures/approved/nsqd/gamma-flow.yaml` |
| DATA-NSQD-02 | **Committed** | `candidate-requirement-card` — **not** a corpus record | `tests/fixtures/approved/nsqd/mechanism-free.yaml` |
| DATA-NSQD-03 | **Pending** | harvest enumeration | `tests/fixtures/approved/nsqd/harvest-seed.toml` |
| DATA-NSQD-04 | **Pending** | approved paper + human paraphrase | `tests/fixtures/approved/nsqd/paper-a.*` |

N1 uses 01+02 as **candidate inputs** only. N1 must reject either file if offered as a corpus record. DATA-NSQD-04 is **not** an N1 prerequisite and must not be invented while EW-V0A is open. If DATA-NSQD-04 remains pending, the projector stays out of N1 and N2b remains blocked.

---

## Provider Boundary Matrix

| Provider | Port | Notes |
|----------|------|--------|
| LanceDB | `CorpusIndex` (`ALG-IDX`) | Snapshot-scoped paraphrase collection; not paper `VectorIndex` |
| Piccolo | nsqd stores + **`nsqd_jobs`** | After EW-V0B |
| Clock | `Clock` | UTC system clock in production |
| Embedder / Scholar / blobs | existing paper ports | No SDK imports in `nsqd` use-cases |
| PaperSource | N2b only | Minimal paper-row read |

---

## Phase NSQD-N0: Foundation

**Role:** Foundation
**Depends On:** **EW-V0.11**
**Facts Introduced:** (none)
**Verification Command:** four-command gate
**Demo:** `test -f docs/algorithm-contract-nsqd.md && test -f docs/glossary-nsqd.md`
**Observable Outcome:** Boundary ports + null adapters; no persistent nsqd tables; no NoveltyMeasurer/ValueGate ports.
**Rollback:** revert the N0 commit. No schema to undo.

### NSQD-N0.1 Re-verify evidence suite

**Type:** Test
**PRD Trace:** NFR-1
**Depends On:** EW-V0.11
**Real Data Dependency:** None
**Provider Boundary:** N/A
**Fact / Evidence (Test tasks):** N/A
**Expected Failure Signature:** `ruff check` or `ty check` non-zero if EW-V0.11 is not done.
**Description:** Four-command gate. Do not ratchet, skip, or redefine it.
**Acceptance Criteria:**
- [x] All four commands exit 0 from a clean worktree
- [x] Passing test count and coverage re-recorded in the phase close note

### NSQD-N0.2 Document deps and jobs choice

**Type:** Document
**PRD Trace:** LOCAL-NSQD-E
**Depends On:** NSQD-N0.1
**Real Data Dependency:** None
**Provider Boundary:** N/A
**Description:** Cite EW-V0.11/V0.3/V0B/V0A/V1/V2, closed HD-NSQD-01, and `nsqd_jobs` in `docs/baseline.md`.
**Acceptance Criteria:**
- [ ] Baseline lists the dependency matrix
- [ ] Coverage N/A

### NSQD-N0.3 Test discovery port shapes

**Type:** Test
**PRD Trace:** LOCAL-NSQD-H, LOCAL-NSQD-C
**Depends On:** NSQD-N0.2
**Real Data Dependency:** None
**Provider Boundary:** nsqd ports
**Expected Failure Signature:** `nsqd.ports` missing `CorpusRecordStore`, `CorpusSnapshotStore`, `CorpusIndex`, `NsqdJobQueue`, `Clock`, card/candidate/morphospace stores.
**Description:** Null-adapter **behavioral** contracts for boundary ports only. Do not introduce ports for novelty, viability, status, elite, or the projector.
**Acceptance Criteria:**
- [ ] `tests/ports/test_nsqd_ports.py` red until N0.5
- [ ] Tests assert snapshot isolation / clock injection / job claim behavior, not frozen class names beyond the Protocol

### NSQD-N0.4 Implement `src/nsqd` ports + null adapters

**Type:** Implement
**PRD Trace:** Technical Enabler
**Makes Green:** N0.3 (`tests/ports/test_nsqd_ports.py`)
**Depends On:** NSQD-N0.3
**Real Data Dependency:** None
**Provider Boundary:** nsqd
**Facts Protected:** all Active
**Description:** Boundary ports + null adapters only. No Piccolo tables until EW-V0B. Domain policies are not implemented here.
**Acceptance Criteria:**
- [ ] N0.3 green; four-command gate green

### NSQD-N0.5 Probe — ablation plan recorded

**Type:** Probe
**PRD Trace:** LOCAL-NSQD-A
**Depends On:** NSQD-N0.4
**Real Data Dependency:** None
**Provider Boundary:** N/A
**Question:** Freeze k, bins, axis triple, viability 1–4?
**Hypothesis:** defaults in the algorithm contract are good enough for smoke.
**Experiment:** do **not** freeze; schedule ALG.* probes after a `calibration` snapshot exists (N6).
**Evidence to collect:** none in N0
**Decision rule:** defaults stay “tunable” until probe artifacts in `ALG-ABL` are filed.
**Max production code allowed:** none
**Disposition:** recorded in algorithm-contract `ALG-ABL`
**Affected slices:** N3+ freeze
**Acceptance Criteria:**
- [ ] `ALG-ABL` remains “not frozen”

**N0 Exit:** ports only; **Stage for review**

---

## Phase NSQD-N0A: Fixtures

**Role:** Data Gate
**Verification:** four-command gate
**Demo:** `ls tests/fixtures/approved/nsqd`
**Observable Outcome:** 01/02 present with expected-outcome fields; 03/04 recorded as pending; N1 not blocked on 04.

### NSQD-N0A.1 Re-verify N0

**Type:** Test
**Depends On:** NSQD-N0.4
**PRD Trace:** Technical Enabler
**Real Data Dependency:** None
**Provider Boundary:** N/A
**Expected Failure Signature:** N/A
**Acceptance Criteria:**
- [ ] Gate exits 0

### NSQD-N0A.2 Confirm committed smoke cards

**Type:** Data Acquisition
**Depends On:** NSQD-N0A.1
**PRD Trace:** LOCAL-NSQD-CAL
**Real Data Dependency:** DATA-NSQD-01, DATA-NSQD-02
**Provider Boundary:** N/A
**Description:** Files already in repo. Confirm manifest, `kind`, `expected_outcomes`, secret scan, content hashes.
**Acceptance Criteria:**
- [ ] Both YAML files match PRD §13 / control and declare `kind: candidate-requirement-card`
- [ ] `expected_outcomes` include snapshot_empty, evidence, nov/mech/fals/dpred/dval/viability/archive_eligible
- [ ] Manifest lists them with reviewer, approval revision, UTC date, `never_corpus_record = true`
- [ ] A loader test fails if either file is offered as a corpus record

### NSQD-N0A.3 Acquire paper-04 (human paraphrase)

**Type:** Data Acquisition
**Depends On:** NSQD-N0A.2, EW-V0A
**PRD Trace:** LOCAL-NSQD-E
**Real Data Dependency:** DATA-NSQD-04
**Provider Boundary:** PaperStore (source)
**Description:** Blocked future data acquisition. After EW-V0A approves real paper fixtures, select one real paper and add its title, abstract, markdown excerpt, **human-written mechanism paraphrase**, and a `paper_id` not lexicographically “first.” **Do not invent.** Not required for N1 or for this documentation-review pass.
**Acceptance Criteria:**
- [ ] Sidecar + markdown under `tests/fixtures/approved/nsqd/` **or** explicitly still pending in the manifest
- [ ] Paraphrase ≠ abstract
- [ ] N2b stays blocked while pending

### NSQD-N0A.4 Harvest seed 03

**Type:** Data Acquisition
**Depends On:** NSQD-N0A.2
**PRD Trace:** LOCAL-NSQD-H
**Real Data Dependency:** DATA-NSQD-03
**Provider Boundary:** N/A
**Description:** Real enumerated citations. Required for N6 `production_valid` and harvest-from-file.
**Acceptance Criteria:**
- [ ] `harvest-seed.toml` or explicitly deferred in manifest

**N0A Exit:** 01/02 approved; 03/04 status recorded; **Stage**

---

## Phase NSQD-N1: Walking skeleton (narrow E2E)

**Role:** Capability
**Depends On:** **EW-V0.11** + **EW-V0.3** + **EW-V0B** + N0 + N0A.2
**Facts Introduced:** NSQD.E2E.SMOKE_LOOP.v1, SNAPSHOT_HASH, SMOKE_NO_NOVELTY_TERM, GATE.SMOKE_PAIR, SEP.AUDIT_RECORD, MAP.STATUS_RULES, ARCHIVE.ELITE_REPLACE, CARD.SCHEMA, GROUND.CASCADE, NOVELTY.METRIC, JOBS.OWNED
**Not in this phase:** NSQD.PROJECT.HUMAN_PARAPHRASE.v1 (N2b), PROMOTION (N6), RANK_GUARD (N7)
**Verification:** four-command gate **and** `uv run pytest tests/nsqd tests/facts/test_nsqd_*.py --cov=src/nsqd --cov-fail-under=90`
**Demo:** `uv run python -m nsqd skeleton --candidate-fixture tests/fixtures/approved/nsqd/gamma-flow.yaml --axiom "predictors assume stationary return signal"`
**Observable Outcome:** One **empty** `smoke_only` snapshot with `evidence=null` → one map cell (Unknown, because smoke) → Operator A candidate persisted → `evaluator_run_id ≠ generator_run_id` → local-only grounding → gate → complete Frontier Card with `card_decision=rejected` → archive insertion rejected → production archive empty. Novelty **term** is 0. Synthetic neighbors are unit-test inputs only.
**Rollback:** restore the SQLite file from the backup taken immediately before the N1 persist step. Forward-only migrations have **no** down migration. Do not `DROP` `nsqd_*` tables as a documented rollback unless a tested operator procedure is added later.

Path (normative):

```
DATA-NSQD-01/02 (candidate-requirement-card, not corpus)
  → nsqd_jobs.diverge (Operator A + axiom; immutable artifact)
  → empty smoke_only snapshot (evidence=null; never 01/02 or synthetic unit inputs as persisted corpus)
  → map one cell (ALG-STATUS; smoke ⇒ Unknown)
  → nsqd_jobs.ground (layers 1–4 local only; fail if live/hybrid called)
  → nsqd_jobs.score (ALG-VIA; novelty term 0; viability 0)
  → Frontier Card (full schema, rejected)
  → archive insert attempted → rejected (ALG-ELITE)
  → production archive empty
```

TDD order is **domain → application → adapters → E2E**. EV-N00 is the **last** composition test.

### NSQD-N1.0 Re-verify + assert EW-V0.3 / EW-V0B

**Type:** Test
**Depends On:** NSQD-N0A.2, EW-V0.11, EW-V0.3, EW-V0B
**PRD Trace:** Technical Enabler
**Real Data Dependency:** None
**Provider Boundary:** Fact surface + Piccolo migrator
**Expected Failure Signature:** `test_fact_surface.py` / Lifecycle checker missing; schema_migrations missing EW 002; or four-command gate red.
**Description:** Gate green, EW-V0.3 fact/evidence infrastructure exists, and schema_migrations includes EW 002 (job CHECK). If either EW dependency is missing, **stop** — do not activate N1 facts or create nsqd tables via `if_not_exists`.
**Acceptance Criteria:**
- [ ] EW-V0.3 fact surface applied
- [ ] EW-V0B applied
- [ ] Four-command gate exits 0

---

### Domain increment

### NSQD-N1.1 Test domain policies

**Type:** Test
**Depends On:** NSQD-N1.0
**PRD Trace:** LOCAL-NSQD-H, M, V, A, C, G, CAL
**Fact / Evidence:** EV-N01, EV-N02, EV-N04 (factor oracles), EV-N06, EV-N07, EV-N08, EV-N11
**Expected Failure Signature:** modules under `nsqd.domain` missing, or known digest / zero-path / status overlap / elite replay assertions fail.
**Real Data Dependency:** DATA-NSQD-01, DATA-NSQD-02 for gate oracles; synthetic vectors allowed for k-NN/status/elite
**Provider Boundary:** none (pure)
**Description:** Table-driven pure unit tests listed in “Required N1 test matrix — Pure unit.” Fixed `as_of`. Elite tests use **non-smoke** constructed viability > 0. Smoke tests assert rejection. Load `expected_outcomes` from fixture schema fields.
**Acceptance Criteria:**
- [ ] All listed domain tests exist and are red
- [ ] Rest of suite green

### NSQD-N1.2 Implement domain policies

**Type:** Implement
**Depends On:** NSQD-N1.1
**Makes Green:** EV-N01, EV-N02, EV-N04 (oracle fields), EV-N06, EV-N07, EV-N08, EV-N11
**PRD Trace:** same as N1.1
**Real Data Dependency:** None
**Provider Boundary:** none
**Facts Protected:** all Active
**Description:** Snapshot digest, novelty, viability rubrics, card validation, elite decision, status policy, grounding class table. No I/O.
**Acceptance Criteria:**
- [ ] Named evidence commands green
- [ ] Four-command gate green

### NSQD-N1.3 Refactor domain

**Type:** Refactor
**Depends On:** NSQD-N1.2
**PRD Trace:** Technical Enabler
**Makes Green:** none (no new behavior)
**Real Data Dependency:** None
**Provider Boundary:** none
**Facts Protected:** N1 domain facts already green
**Description:** Deduplicate tables and helpers. Do not change scores, statuses, or hashes.
**Acceptance Criteria:**
- [ ] Same tests still green
- [ ] Four-command gate green
- [ ] No new public behavior

---

### Application increment

### NSQD-N1.4 Test application use-cases

**Type:** Test
**Depends On:** NSQD-N1.3
**PRD Trace:** LOCAL-NSQD-SEP, G, E
**Fact / Evidence:** EV-N05, EV-N10
**Expected Failure Signature:** evaluator accepts an in-memory object; live or paper hybrid search is invoked; handlers only reachable via CLI.
**Real Data Dependency:** 01, 02
**Provider Boundary:** in-memory fakes of ports
**Description:** Diverge persists artifact; Evaluate reloads by hash; local grounding fail-fast if `ScholarClient` / paper `VectorIndex` is called; handlers callable directly. **No projector tests.**
**Acceptance Criteria:**
- [ ] Application tests red until N1.5

### NSQD-N1.5 Implement application use-cases

**Type:** Implement
**Depends On:** NSQD-N1.4
**Makes Green:** EV-N05, EV-N10
**PRD Trace:** same as N1.4
**Real Data Dependency:** 01, 02
**Provider Boundary:** nsqd ports (fakes ok)
**Facts Protected:** domain facts already green
**Description:** Diverge, Ground (local), Score, Archive-insert-attempt use-cases. Job handlers call those use-cases. CLI is not written here.
**Acceptance Criteria:**
- [ ] EV-N05, EV-N10 green
- [ ] Four-command gate green

### NSQD-N1.6 Refactor application

**Type:** Refactor
**Depends On:** NSQD-N1.5
**PRD Trace:** Technical Enabler
**Makes Green:** none
**Real Data Dependency:** None
**Provider Boundary:** nsqd
**Facts Protected:** EV-N05, EV-N10
**Description:** Share orchestration between handlers and use-cases. No new behavior.
**Acceptance Criteria:**
- [ ] Same tests green; gate green

---

### Adapter increment

### NSQD-N1.7 Test adapters

**Type:** Test
**Depends On:** NSQD-N1.6
**PRD Trace:** LOCAL-NSQD-E, H
**Fact / Evidence:** EV-N12; adapter contracts for `CorpusIndex` and Piccolo stores
**Expected Failure Signature:** nsqd tables created outside the EW-V0B runner; discovery type inserted into paper `jobs`; `CorpusIndex` returns another snapshot’s records or unstable ties.
**Real Data Dependency:** None (deterministic vectors)
**Provider Boundary:** Piccolo, LanceDB local dir, `nsqd_jobs`
**Description:** Migration creates NS-QD tables only through the EW-V0B runner. `nsqd_jobs` claim exclusivity, retries, cancel, terminal states, UTC timestamps. `CorpusIndex` snapshot filter + tie order. No model download.
**Acceptance Criteria:**
- [ ] Adapter tests red until N1.8

### NSQD-N1.8 Implement adapters

**Type:** Implement
**Depends On:** NSQD-N1.7
**Makes Green:** EV-N12; N1.7 adapter tests
**PRD Trace:** same as N1.7
**Real Data Dependency:** None
**Provider Boundary:** Piccolo, LanceDB, `nsqd_jobs`
**Facts Protected:** application facts already green
**Description:** Piccolo stores + `nsqd_jobs` + LanceDB `CorpusIndex`. Own `NsqdJobType`.
**Acceptance Criteria:**
- [ ] EV-N12 green
- [ ] Four-command gate green

### NSQD-N1.9 Refactor adapters

**Type:** Refactor
**Depends On:** NSQD-N1.8
**PRD Trace:** Technical Enabler
**Makes Green:** none
**Real Data Dependency:** None
**Provider Boundary:** Piccolo, LanceDB
**Facts Protected:** EV-N12
**Description:** Deduplicate SQL/index helpers. No new behavior.
**Acceptance Criteria:**
- [ ] Same tests green; gate green

---

### Composition increment

### NSQD-N1.10 Test E2E smoke loop

**Type:** Test
**Depends On:** NSQD-N1.9
**PRD Trace:** LOCAL-NSQD-CAL
**Fact / Evidence:** NSQD.E2E.SMOKE_LOOP.v1 → EV-N00
**Expected Failure Signature:** missing snapshot/cell/candidate/grounding/card; **or** an elite appears in the production archive; **or** novelty term ≠ 0.
**Real Data Dependency:** DATA-NSQD-01, DATA-NSQD-02
**Provider Boundary:** all nsqd ports (real local adapters)
**Description:** **Final** composition test. Asserts the corrected smoke/archive outcome. Does not drive internals that earlier tests already cover.
**Acceptance Criteria:**
- [ ] Red until N1.11
- [ ] Rest of suite green

### NSQD-N1.11 Implement thin CLI orchestration

**Type:** Implement
**Depends On:** NSQD-N1.10
**Makes Green:** EV-N00
**PRD Trace:** LOCAL-NSQD-E
**Real Data Dependency:** DATA-NSQD-01, DATA-NSQD-02
**Provider Boundary:** composition root
**Facts Protected:** all N1 facts already green
**Description:** `python -m nsqd skeleton` wires existing use-cases. No duplicated business logic. FR-U1 unified `gleansight` remains N10.
**Acceptance Criteria:**
- [ ] EV-N00 green
- [ ] Demo command exists and is tested
- [ ] `src/nsqd/` coverage ≥ 90%
- [ ] Four-command gate green

### NSQD-N1.12 Fact sufficiency — smoke vs calibration

**Type:** Fact Sufficiency Review
**Depends On:** NSQD-N1.11
**PRD Trace:** LOCAL-NSQD-CAL
**Real Data Dependency:** 01, 02
**Provider Boundary:** N/A
**Description:** Confirm we did **not** activate a production novelty-term fact or a smoke-elite fact. Gamma-flow/control is smoke, not calibration.
**Acceptance Criteria:**
- [ ] Ledger has no Active fact that requires novelty term > 0 on `smoke_only`
- [ ] Ledger has no Active fact that a smoke card became a production elite

**N1 Exit:** E2E green; smoke_only; empty production archive; **Stage**

---

## Phase NSQD-N2: Harvest validation + later slices

**Role:** Capability
**Depends On:** N1
**Facts Introduced:** NSQD.HARVEST.ENUMERATION.v1
**Demo:** reject essay file
**Tasks:** N2.0 re-verify; N2.1 test essay reject (EV-N03); N2.2 implement. Operators **B–G out of baseline**.

### NSQD-N2b Live paper projection

**Depends On:** N1 **and EW-V0A** **and EW-V2** **and DATA-NSQD-04**
**Facts:** NSQD.PROJECT.HUMAN_PARAPHRASE.v1 → EV-N09
**Acceptance:** Projector over an approved paper fixture (and, when EW-V2 is Active, atomically imported papers); rejects abstract substitution; idempotent on hashes. Requirement-cards 01/02 are rejected as corpus input.

### NSQD-N3 Map harden

**Depends On:** N1
**Acceptance:** Full status table on larger snapshots; `ALG.STATUS` ablation after N6 calibration data.

### NSQD-N4 Operator A harden (B–G still deferred)

**Depends On:** N3
**Acceptance:** Axiom list → Operator A only.

### NSQD-N5 Ground + live budget

**Depends On:** N1 **and EW-V1** if using paper hybrid search
**Acceptance:** EV-N10 on live ≤3; no hybrid until EW-V1 is Active.

### NSQD-N6 Calibration snapshot (not smoke)

**Depends On:** N0A.4 harvest seed + `ALG-SUF`
**Facts:** NSQD.SNAPSHOT.PROMOTION.v1 → EV-N13
**Acceptance:** `calibration` state; every `SufficiencyFailure` tested; then and only then consider a novelty-term>0 fact. `production_valid` stays blocked until DATA-NSQD-03 can be evaluated honestly.

### NSQD-N7 Archive coverage API

**Depends On:** N1
**Facts:** NSQD.ARCHIVE.RANK_GUARD.v1 → EV-N14
**Acceptance:** Rank fails below 50 elites and below 20% of `U \ {Invalid}`; both boundaries tested.

### NSQD-N8 Re-score

**Depends On:** N7
**Acceptance:** `card.snapshot_id != current snapshot_id` → `needs_re_score` → elite replay.

### NSQD-N9 Hardening

**Depends On:** N8
**Acceptance:** Import-boundary; UTC; logs.

### NSQD-N10 Surfaces (FR-U1/U2)

**Depends On:** N9
**Acceptance:** `gleansight` unified CLI; Map/Archive/Card UI. **Until then FR-U1/U2 are deferred.** Only `python -m nsqd skeleton` exists from N1.

---

## Ablations (before freeze)

Execute as probes **after N6** (they need a `calibration` snapshot): `ALG.AXES`, `ALG.K`, `ALG.NOVELTY_BINS`, `ALG.STATUS.THRESHOLDS`, `ALG.VIABILITY` per `ALG-ABL`. File artifacts under `docs/ablations/`. Do not use `smoke_only` for `ALG.NOVELTY_BINS`.

---

## Out of scope (baseline)

- Canonical NS k-NN in behavior space / NSLC local competition
- Operators B–G as required
- Production-valid novelty terms or production elites on smoke snapshots
- Qdrant, `liq-validation`, 12 agents
- Unified `gleansight` CLI / new UI before N10
- Persistent nsqd tables before EW-V0B
- Starting N0 before EW-V0.11
- Invented harvest seeds or invented DATA-NSQD-04
- Paper projector in N1

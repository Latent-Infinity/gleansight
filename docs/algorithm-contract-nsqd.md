# Algorithm contract — NS/QD-inspired discovery

**Status:** v1.1 defaults; **not frozen** until ablation tasks in `docs/development-plan-ns-qd.md` (ALG.* probes) close.
**Normative owner:** this file owns formulas, states, deterministic policies, schemas, and version semantics.
**Related:** terminology in `docs/glossary-nsqd.md`; obligations in `docs/requirements-ns-qd.md`; sequencing in `docs/development-plan-ns-qd.md`.

Implementations must cite the section identifiers below (`ALG-DESC`, `ALG-STATUS`, …). Other documents reference these IDs; they must not redefine them.

---

## ALG-DESC — Research descriptors (archive and map)

**Archive axes (v1 default, finance pack `finance/1`):**

| Axis | ID | Values (closed vocab) |
|------|----|------------------------|
| mechanism | `mechanism` | behavioral, institutional, microstructure, balance-sheet, reflexivity, flow-driven, shock-propagation |
| prediction target | `target` | returns, volatility, drawdown, liquidity, slippage, crowding, signal-decay, regime-transition |
| horizon | `horizon` | tick, intraday, daily, weekly, event-time, regime-time |

Cell id = `mechanism={v}|target={v}|horizon={v}`. Unknown/unlisted value → reject placement (do not coerce).

The finance pack’s **eligible archive-cell universe** is the cartesian product of the three closed vocabs (7 × 8 × 6 = 336 cells). Coverage (ALG-COV) uses the **selected domain policy’s** universe, not an implicit global `finance/1` default. Morphospace may store extra axes (modality, model-class, …) as **metadata**, not archive bins, until `ALG.AXES` says otherwise.

## ALG-POLICY — Versioned subject policies

`domain_policy_id` is required and must be supplied explicitly; there is no implicit default and no fallback from a missing pack field. Verdicts, corpus views, grounding, novelty, cards/elites, and rank coverage are scoped to that id. Archive membership and elite replacement use a policy-scoped archive key while preserving the raw cell id emitted by the selected policy. Key sufficiency/promotion by `(snapshot_id, domain_policy_id)`. Records tagged to one policy cannot satisfy another. `finance/1` is a registered policy, not a missing-value fallback. `optimization/1` is a separate registered policy and does not inherit finance cells, minima, or credit. Its current `optimization/1` use is characterization-only: it does **not** activate a nonzero mechanism rubric, prove sufficiency, or imply production viability.

**Bin boundaries:** v1 values are categorical. Adding a continuous axis requires a new contract revision and an ablation.

---

## ALG-REC — Record-level states (not cell statuses)

Each corpus record has exactly one `lifecycle` at a given `as_of` (UTC):

| `lifecycle` | Predicate |
|-------------|-----------|
| `invalid` | `invalid_reason` set |
| `future_work` | tagged `future_work` and not `invalid` |
| `attempted` | tagged `stalled` or `abandoned` and not `invalid` / `future_work` |
| `current` | `type ∈ {paper, code}`, `harvested_at >= as_of − window`, and not `invalid` / `future_work` / `attempted` |
| `stale` | otherwise (including papers/code older than the window, and all benchmarks that are not invalid/future_work) |

Default `window` = 24 months. `as_of` is injected (ALG-CLOCK). These states are **not** cell statuses.

Counts on a cell, at `as_of`:

- `P`, `C`, `B` — records with `type` paper, code, benchmark (any lifecycle except `invalid`, unless noted)
- `attempted` — records with `lifecycle = attempted`
- `current_paper` / `current_code` — records with `lifecycle = current` and matching type

---

## ALG-STATUS — Cell-status computation (map)

Statuses are a **single** label. A `smoke_only` snapshot always returns `Unknown` before record or cell metadata is evaluated, so smoke maps cannot look production-ready. For every other snapshot state, exception/gap labels preempt density labels and density labels are exclusive of each other. Evaluate **first match** in the table below; later rows assume earlier rows did not match.

`inspected` means the cell appears in the domain-pack expected-cell manifest **or** has an explicit `inspected_at`. `expected` means the cell id is in that manifest.

| Order | Status | Exclusive predicate | Notes |
|------:|--------|---------------------|-------|
| 1 | Invalid | cell `invalid_reason` set **or** ≥1 authoritative `lifecycle=invalid` record | |
| 2 | Unknown | unresolved disagreement flag **or** (`P+C+B = 0` and not `inspected`) | |
| 3 | Future-work-only | `P+C+B ≥ 1` and every non-invalid record is `lifecycle=future_work` | |
| 4 | Stalled | `attempted ≥ 1` and `current_paper = 0` and `current_code = 0` | Uses record-level `current`, not cell Active/Mature |
| 5 | Missing | `inspected` and `expected` and `P+C+B = 0` | |
| 6 | Code-gap | `P ≥ 1` and `C = 0` | Operational gap preempts density |
| 7 | Benchmark-gap | `(P+C) ≥ 1` and `B = 0` and the method claims evaluation | Preempts Mature/Active when a claimed evaluation has no benchmark |
| 8 | Mature | `P ≥ 5` and `C ≥ 1` | Reachable: requires code, so it cannot also be Code-gap |
| 9 | Active | `P+C+B ≥ 3` and ≥1 record with `harvested_at >= as_of − window` | Recent density that is not Mature and not a gap |
| 10 | Sparse | `1 ≤ P+C+B < 3` | Residual populated density |
| 11 | Unknown | `P+C+B ≥ 3`, no record inside the window, `attempted = 0` | Stale populated leftover; do not call it Mature or Active |

Every cell matches exactly one row. Uninspected empty cells are Unknown (row 2). Constants `3`, `5`, `24 months` are ablation-tunable (`ALG.STATUS.THRESHOLDS`).

**Worked overlaps**

| Situation | Winner | Why |
|-----------|--------|-----|
| `P=6`, `C=1`, recent paper, no evaluation claim | Mature | Row 8 before Active |
| `P=6`, `C=1`, recent paper, `B=0`, method claims evaluation | Benchmark-gap | Row 7 before Mature |
| `P=6`, `C=0`, recent papers | Code-gap | Row 6; Mature needs code |
| `P=3`, `C=0`, recent | Code-gap | Gap preempts Active |
| `P=3`, `C=1`, recent, no evaluation claim or `B≥1` | Active | Not Mature (`P<5`), not a gap |
| `P=3`, `C=1`, all records older than the window, `attempted = 0` | Unknown | Row 11 (inspected or not) |
| Attempted kills + no current paper/code | Stalled | Row 4, even if stale papers remain |
| `smoke_only` snapshot, any counts | Unknown | Smoke precondition |

---

## ALG-CLOCK — Time seam

Status, sufficiency, and any windowed rule take an explicit `as_of: datetime` (timezone-aware UTC).

- Production composition supplies a UTC system clock and passes `as_of = clock.now()`.
- Tests inject a fixed `as_of`. No policy may call `datetime.now()` internally.
- Stored timestamps are timezone-aware UTC.

---

## ALG-NOV — Corpus-relative novelty evidence

**Not** canonical NS k-NN sparseness in behavior space (see glossary).

```
evidence(q, snapshot) =
    mean cosine_distance(embed(paraphrase(q)), embed(paraphrase(n)))
    for n in k nearest corpus records in snapshot
```

| Knob | v1 default | Notes |
|------|------------|--------|
| embedding | existing sentence-transformers model | same as evidence layer unless ablation says split |
| distance | `1 - cosine_similarity` | [0, 2] theoretically; expect [0, 1] for unit vectors |
| k | 5 | if `\|snapshot\| < k`, use `\|snapshot\|`; if 0, `evidence` is **undefined** (`null`) |
| tie | smaller `record_id` first | deterministic |
| threshold `τ` | **unset** until ablation | v1 **reports** the number; the gate’s novelty **term** is the discrete map below |

**0–5 novelty term**

| Term | When (first match) |
|------|--------------------|
| 0 | Grounding class ∈ {`already_done`, `renamed`} |
| 0 | Snapshot state ∉ {`calibration`, `production_valid`} (includes `smoke_only`) |
| 0 | `evidence` is `null` (empty snapshot) |
| 1 | evidence < 0.15 |
| 2 | 0.15 ≤ evidence < 0.30 |
| 3 | 0.30 ≤ evidence < 0.45 |
| 4 | 0.45 ≤ evidence < 0.60 |
| 5 | evidence ≥ 0.60 |

On `smoke_only`: persist a novelty evidence record on the candidate artifact and stamp model/metric/contract versions; **novelty term forced to 0**. N1’s snapshot is **empty**, so `evidence` is **`null`** (undefined). Numeric `evidence` is computed only when neighbors exist (unit tests may inject synthetic neighbors; they are not persisted by EV-N00). Smoke **must not** activate a production novelty-term fact and **must not** produce a production archive elite (ALG-ELITE).

---

## ALG-VIA — Domain viability (Tier-1)

```
viability = nov × mech × fals × dpred × dval
```

Each factor ∈ {0,1,2,3,4,5}. Product = 0 ⇒ reject. This is **not** local competition.

### Who assigns each factor

| Factor | Source | Missing / empty result |
|--------|--------|------------------------|
| `nov` | Computed (ALG-NOV) | 0 |
| `mech` | Deterministic finance-pack field rubric below; other packs supply a versioned rubric | 0 |
| `fals` | Deterministic field rubric below | 0 |
| `dpred` | Deterministic field rubric below | 0 |
| `dval` | **Human-assigned** integer 0–5 on the candidate or fixture, with provenance | 0 |

**Provenance required for `dval`:** `assigned_by` (reviewer id), `assigned_at` (UTC), `rubric_id` (e.g. `finance/dval/1`). Absent provenance → `dval = 0`.

v1 does **not** grade prose quality for `mech` / `fals` / `dpred`. Intermediate scores 1–4 for those three are reserved for `ALG.VIABILITY` and must not be invented by implementations.

### Finance pack `finance/1` — `mech`

Required inefficiency-block fields: `mechanism`, `inefficiency`, `counterparty`, `persistence`, `capacity`, `regime_dependence`.

A field is empty when missing, null, or whitespace-only.

| Term | When |
|------|------|
| 0 | any required field empty |
| 5 | all six present |

### All packs — `fals`

| Term | When |
|------|------|
| 0 | `cheapest_falsifier` empty **or** `kill_criteria` empty |
| 5 | both present |

### All packs — `dpred`

| Term | When |
|------|------|
| 0 | `differential_prediction` empty |
| 5 | present |

### All packs — `dval`

Human-assigned 0–5 using rubric `finance/dval/1` (or the active pack’s rubric). Fixture oracles ship the assigned value. Runtime with no assignment → 0.

`finance/dval/1` (for human reviewers; tests read the assigned integer, they do not re-judge prose):

| Score | Meaning |
|------:|---------|
| 0 | No domain claim, or claim is a generic architecture transfer |
| 1 | Domain mentioned, no decision relevant to a pack target |
| 3 | Names a pack target and a decision (trade / abstain / size / hedge) |
| 5 | Names target, decision, and a capacity or regime limit |

Scores 2 and 4 are allowed interpolations by the reviewer.

### Zero paths (must have unit tests)

- `nov = 0` on `smoke_only`, empty snapshot, or grounding `already_done` / `renamed`
- `mech = 0` when any finance required field is empty
- `fals = 0` when falsifier or kill criteria empty
- `dpred = 0` when differential prediction empty
- `dval = 0` when assignment or provenance missing
- any zero ⇒ `viability = 0` ⇒ not archive-eligible

---

## ALG-ELITE — Archive elite replacement (MAP-Elites-inspired)

Applies only to a candidate card that **passed** Tier-1 (`viability > 0`):

1. If cell `c` has no elite → insert `x`.
2. If `viability(x) > viability(elite)` → replace; old elite retained in the card store with `superseded_by`.
3. If equal → keep the elite with the **lexicographically smaller `candidate_artifact_hash`**.
4. Rejected cards (`viability = 0`) never become elite. The insertion attempt is recorded as `rejected` with reason `viability_zero`.

`candidate_artifact_hash` is the SHA-256 of the immutable candidate JSON (ALG-SEP). It is the tie-breaker because it is content-addressed. `card_id` may equal that hash; implementations must not use a random `card_id` for ties.

Replay of the same candidates in any insertion order yields the same elite. Quality comparison is **exactly** `viability`, then `candidate_artifact_hash`.

**Smoke:** every smoke card has `nov = 0` hence `viability = 0`. Archive insertion is attempted and **must be rejected**. The production archive remains empty. There is no provisional archive.

---

## ALG-COV — Coverage and ranking

Let `U` be the domain-pack eligible archive-cell universe (ALG-DESC). `Invalid` cells are removed from the denominator. **Unknown and uninspected cells stay in the denominator.** Leaving cells uninspected cannot raise coverage.

```
coverage = |cells with an elite| / max(1, |U \ {Invalid}|)
```

**Rank guard (intentional OR, illuminate-first):** the global rank API is allowed iff `|elites| ≥ 50` **or** `coverage ≥ 0.20`, whichever first. Otherwise fail with `rank_guard_blocked`. Product confirmation: both legs stay; do not silently drop one.

Dedicated tests: below-threshold rejection; `|elites| = 49` and `coverage < 0.20` blocked; `|elites| = 50` allowed; `coverage = 0.20` with `|elites| < 50` allowed.

---

## ALG-SEL — Target-cell selection (next diverge cycle)

This selects a **target cell**, not a parent card.

v1 default (until ablation):

1. Prefer cells with status ∈ {Missing, Sparse, Code-gap, Benchmark-gap, Stalled} and no elite.
2. Else the cell whose elite has the lowest `viability`.
3. Tie: smaller cell id.

**Operator A input**

- Always: domain-pack axioms registered for the **target cell**.
- If the target cell has an elite, that elite is optional extra context (`parent_card_id`).
- If the target cell is empty, there is **no parent card**. Operator A still runs on the pack axioms alone.

Do not call the empty-cell case “parent cell.”

---

## ALG-SNAP — Snapshot identity, corpus version, and change

### Content hash of a record

Preimage is UTF-8 JSON with `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`:

```json
{"paraphrase":"<NFC, newlines = LF>","source":"<normalized>","type":"<type>"}
```

`content_hash = hex(SHA-256(preimage))` (64 lowercase hex chars).

**Source normalization**

1. Unicode NFC.
2. Strip leading/trailing whitespace; collapse internal newlines to LF.
3. If the value is a DOI (starts with `10.` or `doi:` or a `doi.org` URL): lowercase, strip `doi:` / `https://doi.org/` / `http://doi.org/` prefix, strip a single trailing `/`. Prefix the result with `doi:`.
4. Else if it is an `http://` or `https://` URL: lowercase scheme and host, drop fragment, strip a single trailing `/`.
5. Else: NFC string as in (1)–(2).

Empty `source` or empty `paraphrase` is rejected at harvest (not hashed).

**Known vector**

| Field | Value |
|-------|--------|
| type | `paper` |
| paraphrase | `Condition allocation trust on dealer-hedging convexity regime.` |
| source | `doi:10.0000/example` |
| preimage | `{"paraphrase":"Condition allocation trust on dealer-hedging convexity regime.","source":"doi:10.0000/example","type":"paper"}` |
| content_hash | `3036b024a7a63dc6116f42e11a04d2b29ae382abfffc878dcdff890c73e15ced` |

### Snapshot id

Preimage is UTF-8 JSON with the same canonicalization:

```json
{"records":[{"content_hash":"<hex>","record_id":"<id>"},...],"schema_version":<int>}
```

`records` is sorted by `record_id` ascending (Unicode code point). Duplicate `record_id` is illegal.

`snapshot_id = hex(SHA-256(preimage))`.

**Known vector** (`schema_version = 1`, records `rec-a` with the content hash above and `rec-b` with 64 zero hex digits):

| Insertion order | snapshot_id |
|-----------------|-------------|
| either order | `00b5ac629b90943fd9cc61b7361f8941d2dd1e7e8b0367ffb9c0c65fe2f8a9b4` |
| same records, `schema_version = 2` | `d08d2cbf7ea0ccb830af4d9ab21ae2eb816f6bdf23209f8f976e3990159209db` |
| empty snapshot (`records=[]`, `schema_version=1`) | `16bf24d404b6914dd084140cfc2ff9adc145ed6a3db2fe852f20b47f5bab0d6c` |

`snapshot_id` is immutable content identity. Two stores with the same records share the same `snapshot_id`.

### `corpus_version`

Monotonic integer **local to a store instance**. It increments when that store commits a new snapshot. It is **not** content identity. Cards stamp both `snapshot_id` and `corpus_version`. Do not call either a “minor” or “major” bump.

### Change rule (replaces minor/major)

- Grounding that appends prior art **creates a new snapshot** (new `snapshot_id`, `corpus_version += 1`). Existing snapshots are never mutated.
- A card needs re-score iff `card.snapshot_id != current_snapshot_id`.
- Re-score recomputes evidence, viability, and elite replacement against the new snapshot.

---

## ALG-STATE — Snapshot states

| State | Meaning | Novelty term | Archive elite |
|-------|---------|--------------|---------------|
| `smoke_only` | Plumbing. N1 uses an **empty** snapshot (`evidence=null`) | Forced 0 | Never |
| `calibration` | Human-approved fixtures + recall probe listed in the domain manifest | ALG-NOV bins apply | Allowed if `viability > 0` |
| `production_valid` | Sufficiency policy (ALG-SUF) passed | ALG-NOV bins apply | Allowed if `viability > 0` |

---

## ALG-SUF — Sufficiency and promotion

Sufficiency is **not** “an Active/Mature cell has records” (those statuses already imply records).

A versioned domain policy (`finance/1`, later packs) declares:

- `expected_cells`: cell ids that must be inspectable
- `recall_probe`: `{probe_id, source, expected_record_type}` items that must be present
- `required_record_types`: minimum counts by type (may be zero until the harvest seed exists)
- `min_records`: integer floor (may be 0 for `calibration` if the probe is complete)

**Closed failure reasons** (`SufficiencyFailure`):

| Code | When |
|------|------|
| `expected_cell_empty` | An `expected_cells` entry has `P+C+B = 0` |
| `recall_probe_missing` | A recall-probe item has no matching record |
| `disagreement_unresolved` | Engine disagreement not marked Unknown |
| `record_metadata_missing` | Any record lacks `type`, non-empty `paraphrase`, `source`, or `content_hash` |
| `duplicate_source_conflict` | Same normalized source, conflicting paraphrase, unresolved |
| `retracted_unmarked` | Retracted source included without `retracted=true` |
| `domain_minima_unmet` | Pack `min_records` / `required_record_types` not met |
| `manifest_missing` | No domain policy / harvest-seed manifest is approved |

`production_valid` requires zero failures. `calibration` requires the recall probe and approved fixtures; it may leave `expected_cell_empty` / `domain_minima_unmet` pending until DATA-NSQD-03 exists. **DATA-NSQD-03 remains a blocker** for an honest `production_valid` decision and for harvest-from-seed.

Duplicates with identical paraphrase: keep one, point aliases. Retractions: exclude from k-NN unless `include_retracted`.

---

## ALG-SEP — Generate / evaluate audit record

Not a session token alone. Persist:

```
generator_run_id
candidate_artifact_hash   # SHA-256 of immutable candidate JSON (canonical UTF-8 JSON as ALG-SNAP)
evaluator_run_id          # different id; separate use-case invocation
model_profile_id
prompt_or_policy_version
snapshot_id
corpus_version
calibration_version
evaluation_result         # viability + terms + grounding class
```

The evaluator **loads the artifact by hash**; it does not accept a live object from Diverge in-process without that persist+reload path.

---

## ALG-PROJ — Paper → corpus paraphrase

v1 projector (**human-approved only**). Model-assisted drafting is allowed when the fixture records human approval. **Not part of NSQD-N1.** First delivery is NSQD-N2b, after EW-V0A approves real paper fixtures, DATA-NSQD-04 exists (real paper + approved mechanism paraphrase), and EW-V2 is available for live imports.

- Input: approved fixture or reviewed projection payload: `domain_policy_id`, `paraphrase`, `paraphrase_source`, `source_paper_id`, `source_abstract_sha256`, `source_markdown_sha256`, `paraphrase_sha256` computed from normalized paraphrase bytes, `human_reviewer`, `human_approved_at` (UTC), and `review_status=approved`
- The application computes a canonical digest of the normalized reviewed payload and requires it in an injected human-approved digest allowlist. A job payload cannot approve itself by supplying a status or digest, and its explicit `domain_policy_id` must match the policy bound into the approved payload. N6 owns replacement of the fixture/config allowlist with durable live approval state.
- The executable fixture-backed path is `python -m nsqd project`: it verifies the projection file's byte hash and approval metadata against an operator-selected approved manifest before injecting the contract-field digest. The manifest path and trusted digest are not copied into the job payload.
- **Not** “use the abstract as the paraphrase”
- Persist the approved payload's `paraphrase_source`, `review_status = approved`, human-review metadata, hashes, and projector-assigned version `paper-projector/1`
- Canonical `content_hash` stays the ALG-SNAP hash of `{type, paraphrase, source}`. `record_id` is policy + source/hash-revision sensitive. The same full identity is idempotent; any source/hash revision creates a new record and therefore a new snapshot.
- There is no fallback from `paper_id` to `source_paper_id`; projector identity is driven by the reviewed payload fields above.

Unapproved model output (`review_status = pending`) is not accepted by v1.

Requirement-card fixtures (DATA-NSQD-01/02) are **not** corpus records and **must not** be accepted by the projector.

---

## ALG-GROUND — Grounding cascade

Closed `GroundingClass`: `already_done` | `renamed` | `related_partial` | `orthogonal` | `clean_gap` | `unevaluated`.

| Layer | Check | On hit | Else escalate because |
|------:|-------|--------|------------------------|
| 1 | Exact normalized `source` / DOI / title in snapshot | `already_done`, confidence `1.00` | no exact identity |
| 2 | Terminology variants (harvest `terminology` + disagreement flags) | `renamed`, confidence `0.80` | no variant hit |
| 3 | Embedding k-NN (ALG-NOV) | `related_partial` if evidence < 0.15, confidence `0.60`; else `orthogonal`, confidence `0.50` | snapshot empty (`evidence` null) or layer inconclusive |
| 4 | Code/benchmark records in snapshot | `already_done`, confidence `0.90` | no code/benchmark neighbor |

If layers 1–4 miss: `unevaluated`, confidence `0.00`. Live search only after that, **≤3** calls per candidate. N1 and `smoke_only` are local-only: live search and paper hybrid search are **not called**; a test fails if they are.

On N5 calibration/production-valid escalation, paper hybrid runs before scholar. A hybrid hit requires a non-empty `paper_id` and finite positive numeric `score`; a scholar hit requires a non-empty `source_paper_id` and `title`. Malformed results are misses. The first valid normalized result is `closest_prior_art` and yields `related_partial`, confidence `0.40`; it is evidence only and never writes a corpus record or claims `already_done`. Persist call source, hit status, and `query_sha256`, never raw candidate query text.

Every layer persists `{layer, checked, hit, escalate_reason}`. Stamp `snapshot_id` and its matching `corpus_version`; mismatches are rejected. The report includes `closest_prior_art` (or null), `GroundingClass`, confidence, snapshot identity, and bounded call metadata.

Confidence in N1 is **deterministic from the table**, not human-assigned. A later slice may attach a human override with provenance.

---

## ALG-IDX — `CorpusIndex` contract

Independent from the paper `VectorIndex` (which is keyed by `paper_id` and has no snapshot filter). `CorpusIndex` is a **derived, rebuildable index**, not the source of truth: canonical corpus records and snapshot membership live in the metadata store. Domain/application code depends only on this port and must not import LanceDB types.

**Query input:** `snapshot_id`, query vector, `k`, contract version.
**Must exclude** records not in that snapshot.

**Each hit:** `record_id`, `distance`, `rank` (1-based). Order: distance ascending, then `record_id` ascending.

**Measurement stamp** (required on every persisted novelty evidence record): embedding model id, embedding model version, normalization policy (`l2` or `none`), distance metric (`cosine_distance`), `algorithm_contract_version`.

Unit tests use deterministic hand-built vectors. Adapter tests use a local LanceDB directory and do not download models.

---

## ALG-JOB — Discovery jobs

NS-QD owns `NsqdJobType`, table `nsqd_jobs`, and its queue port. Types: `harvest | project | map | diverge | ground | score | rescore`.

Paper `JobType` / `jobs` remain closed: `discover | download | convert | embed | analyze`. Discovery types must not be inserted there.

Shared lease/retry/backoff/state-transition logic may be extracted into a **neutral** policy module only when both contexts actually call it. N1 must not import paper job types.

---

## ALG-ABL — Ablations before freeze

| Study | Dataset state | Metric | n | Threshold | Artifact |
|-------|---------------|--------|---|-----------|----------|
| `ALG.AXES` | `calibration` snapshot + 2 reviewers | each proposed triple scored 0–2 on {illuminable, not empty, not >10k cells}; keep if mean ≥ 4/6 | 3 triples | mean ≥ 4 | `docs/ablations/alg-axes.md` |
| `ALG.K` | `calibration` snapshot | Spearman rank correlation of calibration-item novelty ranks vs k=5 baseline | k ∈ {3,5,10}, same items | ρ ≥ 0.90 vs k=5 | `docs/ablations/alg-k.md` |
| `ALG.NOVELTY_BINS` | **`calibration` only** (not `smoke_only`) | gamma-flow `nov ≥ 1`; mechanism-free still `mech = 0` | the approved pair | both hold | `docs/ablations/alg-novelty-bins.md` |
| `ALG.STATUS.THRESHOLDS` | 10 hand-labeled cells + fixed `as_of` | exact status agreement | Sparse cut ∈ {2,3,5} | ≥ 8/10 | `docs/ablations/alg-status.md` |
| `ALG.VIABILITY` | same calibration pair + 5 extra labeled cards | reviewer agreement on 1–4 intermediates if introduced | 2 reviewers | Cohen’s κ ≥ 0.6 or keep 0/5 presence stubs | `docs/ablations/alg-viability.md` |

Do not treat numeric defaults as frozen until the matching artifact exists.

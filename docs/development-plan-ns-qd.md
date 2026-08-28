# Development Plan: gleansight NS/QD-inspired discovery

**Guide Version**: 2.0
**Mode**: Vertical-Slice
**Plan Type**: Existing-System Feature
**Planning Horizon**: Rolling-Wave (NSQD-N0, N0A, N1 expanded; N2+ listed)
**Plan Set**: gleansight
**Builds On**: `docs/development-plan-open-work.md` (evidence closeout; **hard deps** below)
**Phase ID prefix**: `NSQD-N*` (never reuse closeout `V0`/`V0B`/`V1`/`V2`)
**Inherited Facts**: all `Active` rows in `docs/fact-ledger.md`
**Supersedes**: `docs/development-plan-ns-qd.md` v1.6.21 wording (same file, revision)
**PRD Trace**: `docs/prd-ns-qd.md` + `docs/requirements-ns-qd.md` + `docs/algorithm-contract-nsqd.md` (`LOCAL-NSQD-*`)
**Domain Policy**: Sufficiency, descriptors, viability rubrics, corpus views, and promotion verdicts are versioned by `domain_policy_id`. Verdicts are keyed by `(snapshot_id, domain_policy_id)`; one subject cannot satisfy or unlock another.
**Real Data Policy**: Approved fixtures only. DATA-NSQD-01/02 are **requirement-card** fixtures (`smoke_only`), never corpus records. DATA-NSQD-04 is approved optimization evidence and receives no `finance/1` sufficiency credit. DATA-NSQD-03 is approved finance evidence bound to its primary-source excerpt and reviewed projection.
**Generated Data Authorization**: `None` for evidence claims and approved corpus data. **Synthetic / in-memory values are allowed for pure unit tests** of math and state policy. A passing unit test may evidence algorithm correctness; the synthetic values themselves are not empirical/domain evidence, approved fixtures, or corpus data, and EV-N00 never persists them.
**Provider Policy**: `src/nsqd/` orchestrates through existing `src/papers/` application ports. Paper discovery/import/download/convert/embed/analyze remains paper-owned; durable NS-QD coordination remains in **`nsqd_jobs`**, not paper `jobs`.
**Fact Policy**: Append `NSQD.*`. Smoke snapshots must **not** activate production novelty facts and must **not** produce a production archive elite. LLM selection or analysis must never self-approve corpus evidence or a promoted state.
**Data & Provider Readiness**: DATA-NSQD-01/02/03/04 committed. DATA-NSQD-03 is approved and its `finance/1 production_valid` path is verified with zero `ALG-SUF` failures. Evidence closeout **EW-V0.11**, **EW-V0.3**, **EW-V0B**, **EW-V0A**, **EW-V1**, and **EW-V2** done.
**Slice Ordering**: Preserve completed N1–N10 including N6 default paper-runtime composition. Harvest and projection upsert snapshot-scoped paraphrase vectors. Acquisition drafts and shortlists use the configured Ollama chat model and cannot self-approve. `papers analyze` / `analyze-project` omit `--model-name` to `settings.llm.default_model` (`qwen3.6:35b-a3b-q4_K_M`). Calibration ablation probes are human-validated and remain not frozen. DATA-NSQD-03 is approved and the honest `finance/1 production_valid` path is complete.
**Outstanding Blockers**: None for Operator A or supported, non-default Operator B work. B is composition-gated via `settings.nsqd.enabled_operators` (default `A` only); the CLI has no `--operator` switch. `τ` stays unset while packet 2b collects 120 policy-balanced, offline human-approved labels. The current repository lacks enough approved NSQD candidate-neighbor pairs. Calendar-month subtraction is rejected for v1 and is not a reopen trigger.
**N8 Status**: Re-score is done for the historical finance-calibrated baseline; later N2a/N2b completion now makes snapshot, corpus, archive, and rank inputs explicitly policy-aware without weakening EV-N15.

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest -q
```

NS-QD does not weaken, bypass, or redefine this gate. `pyproject.toml` `fail_under` is **91.90**. New `src/nsqd/` code must also meet ≥90% measured coverage (`uv run pytest tests/nsqd tests/ports/test_nsqd_ports.py tests/facts --cov-reset --cov=src/nsqd --cov-fail-under=90`). N1 cannot close solely because aggregate repository coverage passes.

---

## Changelog

| Version | Date | Change |
| --- | --- | --- |
| 1.0.0 | 2026-08-18 | Initial plan. |
| 1.1.0 | 2026-08-18 | Product = gleansight platform. |
| 1.2.0 | 2026-08-18 | NS/QD-inspired rename; glossary + algorithm contract; N1 true E2E; cross-plan deps; nsqd_jobs; smoke vs calibration; missing facts; ablations; CLI in N1. |
| 1.3.0 | 2026-08-18 | Review `docs/review-nsqd-action-items.md`: smoke card rejected / empty archive; projector removed from N1; N1 TDD order; viability rubrics; exclusive status table; measurable sufficiency; EW-V0.11 gate prereq; HD-NSQD-01 closed; Operator A only. |
| 1.3.1 | 2026-08-18 | Frame remaining review items as scope/dependency changes, not workarounds: N2b waits on EW-V0A + DATA-NSQD-04 + EW-V2; N0 waits on EW-V0.11; no invented paper or provisional archive. |
| 1.3.2 | 2026-08-18 | Decision-signoff audit: EV-N00 uses an empty snapshot with `evidence=null`; synthetic neighbors stay unit-only; N1 depends on EW-V0.3 fact infrastructure as well as EW-V0B. |
| 1.3.3 | 2026-08-18 | Close leftover contradictions: header blockers name EW-V0.3; N1 smoke oracles say `evidence=null` (not numeric); empty-snapshot digest vector recorded. |
| 1.3.4 | 2026-08-19 | Align data/provider readiness with completed EW-V0.11, EW-V0.3, and EW-V0B prerequisites. |
| 1.3.5 | 2026-08-19 | N0 ports + null adapters. Domain policies started (snapshot digest, novelty, viability, status, elite, card, grounding). |
| 1.3.6 | 2026-08-19 | N0A 01/02 confirmed; N1 domain table tests + policies; N1 application use-cases and handlers on null adapters. Adapters/CLI/E2E not started. |
| 1.3.7 | 2026-08-20 | Correct focused evidence and NSQD coverage commands; distinguish completed EW-V0A from pending DATA-NSQD-04; keep N1 adapters and E2E pending. |
| 1.3.8 | 2026-08-20 | N1 adapters: forward migration `003_nsqd_tables`, Piccolo stores, `nsqd_jobs`, LanceDB `CorpusIndex`. E2E/CLI still pending. |
| 1.3.9 | 2026-08-20 | N1 composition: smoke E2E + `python -m nsqd skeleton`. N1 facts Active. |
| 1.3.10 | 2026-08-20 | N2 harvest: essay-only and sourceless ingest rejected; synthetic ALG-SNAP hash vector accepted. DATA-NSQD-03 still pending. |
| 1.3.11 | 2026-08-20 | N2 review: TOML parsing, specific job claims, terminal failures, metadata retention, UTC lifecycle, and versioned snapshot commits. Clarify that the hash vector is synthetic test evidence, not approved corpus data. |
| 1.3.12 | 2026-08-20 | N2 hardening: atomic harvest commits, immutable record metadata, bounded input/schema validation, queue-port parity, and authoritative skeleton version stamps. |
| 1.3.13 | 2026-08-20 | Reconcile completed N1 E2E and persistence status after EW-V2 closeout. |
| 1.3.14 | 2026-08-21 | Historical N7 close wording at that revision: global rank fails unless 50 elites or 20% coverage of U excluding Invalid. N2b was still blocked on DATA-NSQD-04 before later acquisition and implementation. |
| 1.3.15 | 2026-08-21 | N8 re-score: stale card snapshot_id triggers ground+score+elite replay; rejected elites are cleared. |
| 1.3.16 | 2026-08-21 | Historical post-acquisition note at that revision: DATA-NSQD-04 was acquired from DATA-01c with a model-assisted, human-approved paraphrase and integrity metadata while N2b implementation and EV-N09 were still pending before later N2b closeout. |
| 1.4.0 | 2026-08-21 | Generalize NSQD to versioned subject policies; add pack isolation before projection/calibration; make DATA-NSQD-03 an output of a bounded insufficiency-driven search → LLM shortlist → paper pipeline → human approval loop; keep ALG-SUF separate from ALG-COV. |
| 1.4.1 | 2026-08-21 | N2a: explicit domain_policy_id, finance/optimization isolation, pack-scoped rank universe, policy verdict keys. |
| 1.4.2 | 2026-08-21 | N2b: project human-approved paraphrases into optimization/1; reject abstract substitution and finance credit for DATA-NSQD-04. |
| 1.4.3 | 2026-08-21 | Reconcile docs with completed N2a/N2b hardening and explicitly deferred N6 sufficiency/acquisition orchestration. |
| 1.4.4 | 2026-08-22 | Pack-scoped ALG-STATUS tables over finance/optimization universes on larger snapshots; `ALG.STATUS` ablation still deferred until N6 calibration. |
| 1.4.5 | 2026-08-22 | Operator A only: structured axiom list, ALG-SEL target-cell selection, no parent card on empty cells; B–G remain deferred. |
| 1.4.6 | 2026-08-22 | Persist map as an `nsqd_jobs` stage; validate pack-scoped status inputs; derive Operator A target, axiom-cell, and elite context from trusted runtime state; atomically reject immutable generation conflicts. |
| 1.4.7 | 2026-08-22 | Live grounding after local miss, ≤3 calls, pack-scoped corpus view; hybrid allowed because EW-V1 is Active; no acquisition side effects. |
| 1.4.8 | 2026-08-22 | Pack-aware ALG-SUF promotion plus a fail-closed acquisition-staging foundation; full approval/projection/recheck fallback remains pending. |
| 1.4.9 | 2026-08-22 | Harden discovery import-boundary, injected UTC job timestamps, and runner job-transition logs. |
| 1.5.0 | 2026-08-22 | Complete bounded acquisition fallback: human approval, N2b projection, snapshot recheck, persisted `acquire` jobs, and two-recheck stops. |
| 1.6.0 | 2026-08-22 | Unified `gleansight` CLI and Map/Archive/Card screens. |
| 1.6.1 | 2026-08-22 | Correct EV-N17 to Pending: injected orchestration and reserved acquire persistence exist, but the production paper bridge and durable approval bootstrap do not. |
| 1.6.2 | 2026-08-22 | Injection-ready paper acquisition adapter, durable approved-digest bootstrap, and immutable unapproved-projection quarantine migration. |
| 1.6.3 | 2026-08-22 | Correct production boundary: default CLI/UI composition still lacks paper runtime and analysis-metadata bootstrap. |
| 1.6.4 | 2026-08-23 | Default acquire/UI composition wires the paper runtime, paper workers, and analysis-metadata bootstrap. |
| 1.6.5 | 2026-08-23 | ALG.K math probe on a constructed calibration snapshot; k=5 stays tunable; DATA-NSQD-03 still uninvented. |
| 1.6.6 | 2026-08-23 | ALG.K is a synthetic math probe; the other ablation labels/scores are LLM-produced and human-validated. Remaining probes filed; defaults not frozen. |
| 1.6.7 | 2026-08-24 | Approve DATA-NSQD-03 from Gamma Fragility; bind source/paraphrase/coordinates; activate non-empty finance/1 policy; verify production_valid with zero ALG-SUF failures. |
| 1.6.8 | 2026-08-24 | Harvest/project upsert snapshot-scoped paraphrase vectors; ground embeds candidate paraphrases; gamma-flow novelty is defined against DATA-NSQD-03 on production_valid. Four-command gate: 1084 passed, 1 skipped, 92.41%; dedicated NSQD: 494 passed, 93.68%. |
| 1.6.9 | 2026-08-24 | Default chat is Ollama `qwen3.6:35b-a3b-q4_K_M` with thinking off. Embeddings standardize on `qwen3-embedding:latest` (4096-d) until a later Qwen embedding family ships. Four-command gate: 1089 passed, 1 skipped, 92.34%; dedicated NSQD: 494 passed, 93.68%. |
| 1.6.10 | 2026-08-24 | Acquisition drafts call the configured chat model; review_status stays pending. Four-command gate: 1112 passed, 1 skipped, 92.38%; dedicated NSQD: 511 passed, 93.75%. |
| 1.6.11 | 2026-08-24 | Acquisition shortlist ranks discovered ids through the chat model; unknown ids are dropped; review_status stays pending. Four-command gate: 1116 passed, 1 skipped, 92.31%; dedicated NSQD: 516 passed, 93.71%. |
| 1.6.12 | 2026-08-24 | `analyze` / `analyze-project` default `--model-name` to configured `llm.default_model` (`qwen3.6:35b-a3b-q4_K_M`); explicit flag still overrides. Four-command gate: 1119 passed, 1 skipped, 92.38%; dedicated NSQD: 517 passed, 93.71%. |
| 1.6.13 | 2026-08-24 | Acquisition-budget math probe on constructed searchable-failure worlds; keep 3 / 25 / 3 / 2; not frozen. Four-command gate: 1145 passed, 1 skipped, 92.35%; dedicated NSQD: 531 passed, 93.47%. |
| 1.6.14 | 2026-08-25 | `papers rebuild-fts` rebuilds title/abstract search from `papers`; harvest/projection/runner fail-closed paths covered. Four-command gate: 1155 passed, 1 skipped, 92.74%; dedicated NSQD: 538 passed, 94.11%. |
| 1.6.15 | 2026-08-25 | Status recency window v1 is 730 days, overridable with `--window-days`; 12/36 day-length probe filed and not frozen. Four-command gate: 1162 passed, 1 skipped, 92.77%; dedicated NSQD: 545 passed, 94.32%. |
| 1.6.16 | 2026-08-25 | Novelty `τ` is unset/report-only; score stamps `tau: null`; low evidence stays term 1. Four-command gate: 1163 passed, 1 skipped, 92.76%; dedicated NSQD: 547 passed, 94.30%. |
| 1.6.17 | 2026-08-26 | Packet 3: ALG families stay `approved_default_tunable`; no freeze. Four-command gate: 1165 passed, 1 skipped, 92.77%; dedicated NSQD: 549 passed, 94.32%. |
| 1.6.18 | 2026-08-26 | Packet 4: Operators B–G stay deferred; ALG-OP-B archive-whitespace contract drafted, not activated. Four-command gate: 1166 passed, 1 skipped, 92.79%; dedicated NSQD: 550 passed, 94.35%. |
| 1.6.19 | 2026-08-27 | Human decisions: retain 730-day fixed-window semantics, defer executable `τ` packet 2b, and accept ALG-OP-B as archive whitespace over the full `ALG-SEL` preferred set without activation. Four-command gate: 1166 passed, 1 skipped, 92.80%. |
| 1.6.20 | 2026-08-27 | Operator B archive-whitespace domain policy and tests; diverge still rejects `operator=B`. Four-command gate: 1171 passed, 1 skipped, 92.81%; dedicated NSQD: 555 passed, 94.38%. |
| 1.6.21 | 2026-08-27 | Operator B becomes supported, non-default, and composition-gated with controlled persistence and provenance. Packet 2b gains pending-only agent proposals, trusted offline human review, and constrained 120-pair evaluation; executable `τ` remains unset. Calendar-month semantics remain rejected for v1. Four-command gate: 1188 passed, 1 skipped, 92.55%. |
| 1.6.22 | 2026-08-27 | Composition allowlist is settings-backed (`nsqd.enabled_operators`, default A only, optional A+B) and rejects deferred or malformed operator sets; CLI still has no `--operator` switch. Four-command gate: 1198 passed, 1 skipped, 92.58%; dedicated NSQD: 576 passed, 93.80%. |

---

## Cross-plan dependency matrix

Closeout phases (`docs/development-plan-open-work.md`) are prefixed **EW-**.

| Discovery need | Depends on | Why | If skipped |
|----------------|------------|-----|------------|
| Any NSQD-N0 code task | **EW-V0.11** (done 2026-08-18) | Four-command gate must stay green | Do not start N0 from a red tree |
| Any Piccolo `nsqd_*` table | **EW-V0B** (done 2026-08-19) | Shared schema runner; no second ad-hoc `create_table` | — |
| `ProjectPaperUseCase` on reviewed payloads | **EW-V0A** approved real paper fixtures, **EW-V2** atomic import, and DATA-NSQD-04 | Reviewed payload baseline and default CLI/UI paper-runtime composition are implemented; NSQD trust state stays in the canonical NSQD database | Duplicate/orphan corpus rows; invented paper |
| Grounding that calls paper hybrid search | **EW-V1** one-based RRF (done 2026-08-19) | Wrong ranks → wrong prior-art neighbors | False grounding |
| Fact surface / approved-path checker | **EW-V0.3** | `tests/facts`, Lifecycle checker | Parallel checker forks |
| UTC timestamps in nsqd | `ALG-CLOCK` from N1; do not copy evidence-layer naive `now()` | Evidence-layer naive `now()` is EW debt | Mixed timestamps |
| Durable harvest/ground/diverge/score | **`nsqd_jobs`** after EW-V0B | Paper `jobs` CHECK allows only discover/download/convert/embed/analyze | Inserts fail or untracked sync work |

**Rule:** N0 ports and N1 domain/application, persistence, and E2E against real Piccolo are in tree; the completed adapter prerequisite was EW-V0B. EW-V0.3 fact/evidence infrastructure is in place. N1 does **not** project papers. N2b prerequisites are satisfied, and its reviewed-payload baseline is implemented; the typed NSQD→paper adapter and default CLI/UI composition are implemented while lightweight composition remains fail-closed.

---

## Durable work (decision)

**Choice: (2) `nsqd_jobs` owned by discovery.**

Paper `jobs` + EW-V0B CHECK stay paper-only. Harvest, project (N2b), map, diverge, ground, score, and re-score are rows in `nsqd_jobs` with `NsqdJobType` owned by `src/nsqd/`. Do not import paper `JobType`. Shared lease/retry/backoff may be extracted into a **neutral** policy module only when both contexts actually call it. Do not run those stages as untracked synchronous CLI-only work once N1 persists. Stage handlers stay callable without the CLI.

---

## Plan Compliance Matrix

| Invariant | Evidence | Status | Blocked Phases | Resolution |
| --- | --- | --- | --- | --- |
| PRD / algorithm contract | glossary + algorithm-contract | Pass | — | — |
| Terminology | NS/QD-inspired; corpus-relative novelty | Pass | — | — |
| Vertical E2E | NSQD-N1 path (rejected smoke card) | Pass (implemented) | — | EV-N00 green; N1 closed |
| Real data | 01/02/03/04 committed | Pass: `finance/1 production_valid` verified | — | DATA-NSQD-03 is human-approved and bound to primary-source evidence |
| Four-command gate | EW-V0.11 | Pass (2026-08-18) | — | 536 passed, 1 skipped, 91.91% |
| EW fact surface | EW-V0.3 | Pass (2026-08-18) | — | `tests/support/test_fact_surface.py` |
| EW migrator | EW-V0B | Pass (2026-08-19) | — | `schema_migrations` + jobs CHECK |
| EW approved papers | EW-V0A | Pass (2026-08-19) | — | DATA-01a/b/c approved; DATA-NSQD-04 approved separately |
| EW atomic import | EW-V2 | Pass | — | done 2026-08-20 |
| EW RRF | EW-V1 | Pass | — | done 2026-08-19 |
| Operator B | supported, non-default, config-gated | Pass | — | settings authorize A+B; internal job/use-case selects B |
| Operators C–G | explicitly deferred | N/A (deferred) | — | later revision |
| HD-NSQD-01 | LanceDB recorded | Pass | — | closed; no N0.4 |
| Domain-policy isolation | EV-N16 | Pass | — | Explicit policy id; pack-scoped corpus views/verdicts; no implicit `finance/1` |
| Insufficiency acquisition fallback | EV-N17 | Pass | — | Default acquire/UI composition wires the paper runtime, workers, and analysis-metadata bootstrap; approved DATA-NSQD-03 is committed and verified |

---

## Fact Ledger (this plan)

| Fact ID | Statement | Applies When | Kind | Req | Evidence |
| --- | --- | --- | --- | --- | --- |
| NSQD.E2E.SMOKE_LOOP.v1 | Given the approved requirement-card fixtures and an axiom, when the N1 pipeline runs on an **empty** `smoke_only` snapshot, then the candidate artifact stores a novelty evidence record with `evidence=null` and the required measurement stamp, novelty term is 0, viability is 0, one complete Frontier Card is persisted with `card_decision=rejected`, archive insertion is rejected, and the production archive is empty | N1 | Behavior | LOCAL-NSQD-CAL | EV-N00 |
| NSQD.CORPUS.SNAPSHOT_HASH.v1 | Given records, when a snapshot is created, then `snapshot_id` matches `ALG-SNAP` known vectors (order-invariant; changes with content or schema version) | Any snapshot | Data Contract | LOCAL-NSQD-H | EV-N01 |
| NSQD.CORPUS.SMOKE_NO_NOVELTY_TERM.v1 | Given N1’s empty `smoke_only` snapshot, when the gate runs, then the candidate artifact stores a novelty evidence record with `evidence=null` and the required measurement stamp, novelty **term** is 0, and the card is not archive-eligible. Numeric evidence is computed only in unit tests that inject neighbors | Smoke | Behavior | LOCAL-NSQD-H | EV-N02 |
| NSQD.HARVEST.ENUMERATION.v1 | Sourceless / essay-only ingest is rejected | Harvest | Behavior | LOCAL-NSQD-H | EV-N03 |
| NSQD.GATE.SMOKE_PAIR.v1 | On a smoke snapshot, mechanism-free has `mech=0`; gamma-flow has `mech=5` and `nov=0`; both `viability=0` and `archive_eligible=false`. Expected values come from fixture `expected_outcomes`, not filenames | Smoke fixtures | Behavior | LOCAL-NSQD-CAL | EV-N04 |
| NSQD.SEP.AUDIT_RECORD.v1 | Evaluator loads candidate by `candidate_artifact_hash` under a new `evaluator_run_id`; same-run generate+evaluate without persist/reload is rejected | Diverge/value | Architecture Contract | LOCAL-NSQD-SEP | EV-N05 |
| NSQD.MAP.STATUS_RULES.v1 | Cell status matches `ALG-STATUS` exclusive table at an injected `as_of`, including every status and overlap listed there | Map | Behavior | LOCAL-NSQD-M | EV-N06 |
| NSQD.ARCHIVE.ELITE_REPLACE.v1 | Given **non-smoke** constructed inputs with `viability > 0`, elite replacement uses viability then smaller `candidate_artifact_hash`; rejected cards never insert; replay is order-independent | Archive write | Behavior | LOCAL-NSQD-A | EV-N07 |
| NSQD.CARD.SCHEMA.v1 | Card missing any required schema field is rejected independently | Archive | Data Contract | LOCAL-NSQD-C | EV-N08 |
| NSQD.PROJECT.HUMAN_PARAPHRASE.v1 | Projector writes human-approved paraphrase + hashes; abstract is not stored as paraphrase; idempotent on source/content identity | Paper projection **N2b** | Behavior | LOCAL-NSQD-E | EV-N09 |
| NSQD.GROUND.CASCADE.v1 | Local layers 1–4 run and persist `{layer, checked, hit, escalate_reason}`; live and paper hybrid search are not called on the N1 path; version stamped | Ground | Behavior | LOCAL-NSQD-G | EV-N10 |
| NSQD.GROUND.LIVE_PRIOR_ART.v1 | After a pack-scoped local miss on calibration/production-valid, at most 3 calls use typed hybrid/scholar search-only interfaces; only backend-contract hits become normalized closest-prior-art evidence with hashed query metadata; no corpus writes | N5 ground escalation | Behavior | LOCAL-NSQD-G | EV-N10 |
| NSQD.NOVELTY.METRIC.v1 | Evidence equals mean cosine distance to k-NN paraphrases (`ALG-NOV`); covers 0, `<k`, exact `k`, ties, known unit vectors | Novelty | Behavior | LOCAL-NSQD-G | EV-N11 |
| NSQD.JOBS.OWNED.v1 | Harvest/project/map/diverge/ground/score/rescore and reserved acquire work persist as `nsqd_jobs` with `NsqdJobType`; paper `jobs` rejects discovery types | Durable work | Architecture Contract | LOCAL-NSQD-E | EV-N12 |
| NSQD.SNAPSHOT.PROMOTION.v1 | Promotion to `calibration` / `production_valid` is evaluated independently by `(snapshot_id, domain_policy_id)` under `ALG-SUF`; every `SufficiencyFailure` code is tested. Honest `finance/1 production_valid` requires approved DATA-NSQD-03 and now passes with zero failures | N6 | Behavior | LOCAL-NSQD-H | EV-N13 |
| NSQD.ARCHIVE.RANK_GUARD.v1 | Global rank fails below 50 elites and below 20% of `U \\ {Invalid}`; both thresholds and the below-threshold case are tested | N7 | Behavior | LOCAL-NSQD-A | EV-N14 |
| NSQD.RESCORE.REPLAY.v1 | Stale cards re-ground and re-score against the current snapshot; current-card retries skip those operations but reconcile archive state; rejected current elites are removed | N8 | Behavior | LOCAL-NSQD-A | EV-N15 |
| NSQD.DOMAIN.POLICY_ISOLATION.v1 | Registered descriptor axes/universe and dval compatibility resolve by explicit `domain_policy_id`; grounding, corpus filtering, cards/elites/rank are policy-scoped; verdict identity is reserved/validated by `(snapshot_id, domain_policy_id)` schema; records from one policy cannot satisfy, ground, rank, or archive under another | N2a | Architecture Contract | LOCAL-NSQD-H, LOCAL-NSQD-A | EV-N16 |
| NSQD.ACQUISITION.FALLBACK.v1 | Searchable `ALG-SUF` failures run a bounded discover → shortlist → stage → analyze → pending draft → human approval → projection → recheck loop; integrity failures do not search; drafts cannot approve; default acquire/UI composition wires the paper runtime | N6 | Behavior | LOCAL-NSQD-H, LOCAL-NSQD-E | EV-N17 |
| NSQD.SURFACE.UNIFIED.v1 | `gleansight` exposes harvest, map, diverge, ground, gate, and archive without breaking `papers`; the desktop app keeps evidence screens and adds Map, Archive, and Card | N10 | Behavior | LOCAL-NSQD-U | EV-N18 |

**Not activated on smoke:** any “production novelty term > 0” fact; any “smoke card became a production elite” fact. **Non-default:** Operator B requires configuration authorization plus internal job/use-case selection. **Deferred:** operators C–G.

---

## Evidence Index

| ID | Facts | Command | Available From | Lifecycle |
| --- | --- | --- | --- | --- |
| EV-N00 | NSQD.E2E.SMOKE_LOOP.v1 | `uv run pytest tests/facts/test_nsqd_e2e_smoke.py -q --no-cov` | N1 | Required |
| EV-N01 | NSQD.CORPUS.SNAPSHOT_HASH.v1 | `uv run pytest tests/nsqd/test_domain_policies.py::test_snapshot_digest_known_vectors_and_order_invariance -q --no-cov` | N1 | Required |
| EV-N02 | NSQD.CORPUS.SMOKE_NO_NOVELTY_TERM.v1 | `uv run pytest tests/nsqd/test_domain_policies.py::test_smoke_forces_novelty_and_viability_zero tests/nsqd/test_application.py::test_score_and_archive_reject_smoke_fixtures -q --no-cov` | N1 | Required |
| EV-N03 | NSQD.HARVEST.ENUMERATION.v1 | `uv run pytest tests/facts/test_nsqd_harvest_reject_essay.py -q --no-cov` | N2 | Required |
| EV-N04 | NSQD.GATE.SMOKE_PAIR.v1 | `uv run pytest tests/nsqd/test_domain_policies.py::test_fixture_expected_outcomes_match_gate_oracles -q --no-cov` | N1 | Required |
| EV-N05 | NSQD.SEP.AUDIT_RECORD.v1 | `uv run pytest tests/nsqd/test_application.py::test_diverge_persists_artifact_and_evaluate_reloads_by_hash -q --no-cov` | N1 | Required |
| EV-N06 | NSQD.MAP.STATUS_RULES.v1 | `uv run pytest tests/nsqd/test_domain_policies.py::test_status_table_and_overlaps tests/nsqd/test_status_table.py tests/nsqd/test_map.py -q --no-cov` | N1 | Required |
| EV-N07 | NSQD.ARCHIVE.ELITE_REPLACE.v1 | `uv run pytest tests/nsqd/test_domain_policies.py::test_elite_replacement_and_hash_tie_and_rejection tests/nsqd/test_domain_policies.py::test_elite_replay_is_order_independent -q --no-cov` | N1 | Required |
| EV-N08 | NSQD.CARD.SCHEMA.v1 | `uv run pytest tests/nsqd/test_domain_policies.py::test_card_schema_rejects_each_required_field -q --no-cov` | N1 | Required |
| EV-N09 | NSQD.PROJECT.HUMAN_PARAPHRASE.v1 | `uv run pytest tests/facts/test_nsqd_paper_project.py -q --no-cov` | N2b | Required |
| EV-N10 | NSQD.GROUND.CASCADE.v1, NSQD.GROUND.LIVE_PRIOR_ART.v1 | `uv run pytest tests/nsqd/test_domain_policies.py::test_grounding_classes_are_deterministic tests/nsqd/test_application.py::test_local_grounding_empty_snapshot_is_unevaluated_and_ignores_live_search tests/nsqd/test_live_grounding.py -q --no-cov` | N1 | Required |
| EV-N11 | NSQD.NOVELTY.METRIC.v1 | `uv run pytest tests/nsqd/test_domain_policies.py::test_novelty_evidence_mean_and_k_sizes tests/nsqd/test_domain_policies.py::test_novelty_term_bins -q --no-cov` | N1 | Required |
| EV-N12 | NSQD.JOBS.OWNED.v1 | `uv run pytest tests/facts/test_nsqd_jobs.py -q --no-cov` | N1 | Required |
| EV-N13 | NSQD.SNAPSHOT.PROMOTION.v1 | `uv run pytest tests/facts/test_nsqd_sufficiency.py tests/nsqd/test_sufficiency.py -q --no-cov` | N6 | Required |
| EV-N14 | NSQD.ARCHIVE.RANK_GUARD.v1 | `uv run pytest tests/facts/test_nsqd_rank_guard.py -q --no-cov` | N7 | Required |
| EV-N15 | NSQD.RESCORE.REPLAY.v1 | `uv run pytest tests/nsqd/test_rescore.py -q --no-cov` | N8 | Required |
| EV-N16 | NSQD.DOMAIN.POLICY_ISOLATION.v1 | `uv run pytest tests/facts/test_nsqd_domain_policy_isolation.py -q --no-cov` | N2a | Required |
| EV-N17 | NSQD.ACQUISITION.FALLBACK.v1 | `uv run pytest tests/facts/test_nsqd_acquisition_fallback.py tests/nsqd/test_acquisition.py tests/nsqd/test_papers_bridge.py tests/nsqd/test_paper_runtime.py -q --no-cov` | N6 | Required |
| EV-N18 | NSQD.SURFACE.UNIFIED.v1 | `uv run pytest tests/cli/test_gleansight.py tests/nsqd/test_cli.py tests/ui/test_discovery_screens.py tests/ui/test_app.py tests/ui/test_ui_main.py -q --no-cov` | N10 | Required |

Phase close: evidence Required + facts Active (`test_fact_surface.py`).

---

## Real Data Manifest

| Data ID | Status | Kind | Path |
| --- | --- | --- | --- |
| DATA-NSQD-01 | **Committed** | `candidate-requirement-card` — **not** a corpus record | `tests/fixtures/approved/nsqd/gamma-flow.yaml` |
| DATA-NSQD-02 | **Committed** | `candidate-requirement-card` — **not** a corpus record | `tests/fixtures/approved/nsqd/mechanism-free.yaml` |
| DATA-NSQD-03 | **Committed** | approved finance paper + model-assisted, four-round-reviewed, human-approved mechanism paraphrase | `tests/fixtures/approved/nsqd/gamma-fragility.*` |
| DATA-NSQD-04 | **Committed** | approved optimization paper + model-assisted, human-approved mechanism paraphrase; zero `finance/1` credit | `tests/fixtures/approved/nsqd/paper-a.*` |

N1 uses 01+02 as **candidate inputs** only and rejects either as corpus data. DATA-NSQD-04 is approved optimization evidence, is not an N1 prerequisite, and receives no `finance/1` expected-cell, minima, recall, calibration, or production credit. DATA-NSQD-03 is approved finance evidence; its DOI source, excerpt bytes, paraphrase, coordinates, and reviewed digest are bound by the fixture manifests.

---

## Provider Boundary Matrix

| Provider | Port | Notes |
|----------|------|--------|
| LanceDB | `CorpusIndex` (`ALG-IDX`) | Snapshot-scoped paraphrase collection; not paper `VectorIndex` |
| Piccolo | nsqd stores + **`nsqd_jobs`** | After EW-V0B |
| Clock | `Clock` | UTC system clock in production |
| Embedder / Scholar / blobs | existing paper ports | No SDK imports in `nsqd` use-cases |
| Reviewed projection payload | N2b input | Approved reviewed payload verification and the typed NSQD→paper live acquisition bridge are in place; live projection remains manifest/hash/digest gated |

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
- [x] Baseline lists the dependency matrix
- [x] Coverage N/A

### NSQD-N0.3 Test discovery port shapes

**Type:** Test
**PRD Trace:** LOCAL-NSQD-H, LOCAL-NSQD-C
**Depends On:** NSQD-N0.2
**Real Data Dependency:** None
**Provider Boundary:** nsqd ports
**Expected Failure Signature:** `nsqd.ports` missing `CorpusRecordStore`, `CorpusSnapshotStore`, `CorpusIndex`, `NsqdJobQueue`, `Clock`, card/candidate/morphospace stores.
**Description:** Null-adapter **behavioral** contracts for boundary ports only. Do not introduce ports for novelty, viability, status, elite, or the projector.
**Acceptance Criteria:**
- [x] `tests/ports/test_nsqd_ports.py` red until N0.5
- [x] Tests assert snapshot isolation / clock injection / job claim behavior, not frozen class names beyond the Protocol

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
- [x] N0.3 green; four-command gate green

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
- [x] `ALG-ABL` remains “not frozen”

**N0 Exit:** ports only; **Stage for review**

**Close note (2026-08-19):** `src/nsqd/ports.py` + in-memory `null_adapters.py`. Behavioral tests cover clock injection, snapshot-filtered k-NN with record_id ties, and exclusive job claim. No Piccolo `nsqd_*` tables.

---

## Phase NSQD-N0A: Fixtures

**Role:** Data Gate
**Verification:** four-command gate
**Demo:** `ls tests/fixtures/approved/nsqd`
**Observable Outcome:** 01/02 present with expected-outcome fields; 03/04 approved with bound provenance; N1 fixture prerequisites complete.

### NSQD-N0A.1 Re-verify N0

**Type:** Test
**Depends On:** NSQD-N0.4
**PRD Trace:** Technical Enabler
**Real Data Dependency:** None
**Provider Boundary:** N/A
**Expected Failure Signature:** N/A
**Acceptance Criteria:**
- [x] Gate exits 0

### NSQD-N0A.2 Confirm committed smoke cards

**Type:** Data Acquisition
**Depends On:** NSQD-N0A.1
**PRD Trace:** LOCAL-NSQD-CAL
**Real Data Dependency:** DATA-NSQD-01, DATA-NSQD-02
**Provider Boundary:** N/A
**Description:** Files already in repo. Confirm manifest, `kind`, `expected_outcomes`, secret scan, content hashes.
**Acceptance Criteria:**
- [x] Both YAML files match PRD §13 / control and declare `kind: candidate-requirement-card`
- [x] `expected_outcomes` include snapshot_empty, evidence, nov/mech/fals/dpred/dval/viability/archive_eligible
- [x] Manifest lists them with reviewer, approval revision, UTC date, `never_corpus_record = true`
- [x] A loader test fails if either file is offered as a corpus record

### NSQD-N0A.3 Acquire paper-04 (human-approved paraphrase)

**Type:** Data Acquisition
**Depends On:** NSQD-N0A.2, EW-V0A
**PRD Trace:** LOCAL-NSQD-E
**Real Data Dependency:** DATA-NSQD-04
**Provider Boundary:** PaperStore (source)
**Description:** Completed data acquisition. DATA-01c (`paper-20`) supplies the real title, abstract identity, and markdown excerpt. The mechanism paraphrase was model-assisted through four writer/reviewer rounds and approved by product; it is not the abstract. Not required for N1.
**Acceptance Criteria:**
- [x] Sidecar + markdown under `tests/fixtures/approved/nsqd/`
- [x] Paraphrase ≠ abstract; maximum contiguous source overlap is 7 tokens against an 8-token limit
- [x] Historical at N0A.3 close: DATA-NSQD-04 no longer blocked N2b data readiness; N2b later closed EV-N09 with the reviewed-payload projector baseline.

### NSQD-N0A.4 Harvest seed 03

**Type:** Data Acquisition
**Depends On:** NSQD-N0A.2
**PRD Trace:** LOCAL-NSQD-H
**Real Data Dependency:** DATA-NSQD-03
**Provider Boundary:** existing paper discovery/import/pipeline ports through N6
**Description:** Approved `finance/1` evidence. DATA-NSQD-03 was created from an explicit primary-source import, passed four writer/reviewer rounds, and received human approval. Its trusted projection is required for an honest `finance/1 production_valid` verdict.
**Acceptance Criteria:**

- [x] Approved `gamma-fragility.yaml` projection and bound source excerpt recorded in the manifest

**N0A Exit:** 01/02 approved as requirement cards; 03/04 approved as corpus evidence; **Stage**

**Close note (2026-08-19):** `tests/nsqd/test_smoke_fixtures.py` binds DATA-NSQD-01/02 hashes, `kind`, `never_corpus_record`, and `expected_outcomes`. Requirement cards are rejected as corpus input. At this close, DATA-NSQD-03 was pending; DATA-NSQD-04 was acquired and approved later under N0A.3. DATA-NSQD-03 was subsequently approved on 2026-08-24 as recorded below.

**Update note (2026-08-24):** DATA-NSQD-03 is approved from *Gamma Fragility* (DOI `10.2139/ssrn.3725454`). The source excerpt, abstract, projection, coordinates, reviewer metadata, and policy values are hash-bound; the projected snapshot reaches `finance/1 production_valid` with zero `ALG-SUF` failures. Final gate: 1081 passed, 1 skipped, 92.35% coverage; format, lint, and type checks passed.

---

## Phase NSQD-N1: Walking skeleton (narrow E2E)

**Role:** Capability
**Depends On:** **EW-V0.11** + **EW-V0.3** + **EW-V0B** + N0 + N0A.2
**Facts Introduced:** NSQD.E2E.SMOKE_LOOP.v1, SNAPSHOT_HASH, SMOKE_NO_NOVELTY_TERM, GATE.SMOKE_PAIR, SEP.AUDIT_RECORD, MAP.STATUS_RULES, ARCHIVE.ELITE_REPLACE, CARD.SCHEMA, GROUND.CASCADE, NOVELTY.METRIC, JOBS.OWNED
**Not in this phase:** NSQD.PROJECT.HUMAN_PARAPHRASE.v1 (N2b), PROMOTION (N6), RANK_GUARD (N7)
**Verification:** four-command gate **and** `uv run pytest tests/nsqd tests/ports/test_nsqd_ports.py tests/facts --cov-reset --cov=src/nsqd --cov-fail-under=90`
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
- [x] EW-V0.3 fact surface applied
- [x] EW-V0B applied
- [x] Four-command gate exits 0

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
- [x] All listed domain tests exist and are red
- [x] Rest of suite green

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
- [x] Named evidence commands green
- [x] Four-command gate green

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
- [x] Same tests still green
- [x] Four-command gate green
- [x] No new public behavior

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
- [x] Application tests red until N1.5

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
- [x] EV-N05, EV-N10 green
- [x] Four-command gate green

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
- [x] Same tests green; gate green

**Application increment close note (2026-08-19):** `src/nsqd/app/use_cases.py` + `handlers.py` on null adapters. Diverge persists a canonical artifact; score reloads by hash and rejects a live candidate / same run id; local ground does not call live or paper search; smoke fixtures score to `viability=0` and archive insert is rejected. Frontier cards are stored; production elite is not set. No Piccolo `nsqd_*` tables. NSQD facts stay Proposed until the E2E close.

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
- [x] Adapter tests red until N1.8

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
- [x] EV-N12 green
- [x] Four-command gate green

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
- [x] Same tests green; gate green

**Adapter increment close note (2026-08-20):** `003_nsqd_tables` is applied only by the shared forward runner. `src/nsqd/infra/piccolo` stores persist records, snapshots, candidates, cards, elites, morphospace, and `nsqd_jobs`. Paper `jobs` still rejects discovery types. `LanceDBCorpusIndex` is snapshot-scoped with record_id ties; no model download. NSQD facts stay Proposed until EV-N00.

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
- [x] Red until N1.11
- [x] Rest of suite green

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
- [x] EV-N00 green
- [x] Demo command exists and is tested
- [x] `src/nsqd/` coverage ≥ 90%
- [x] Four-command gate green

### NSQD-N1.12 Fact sufficiency — smoke vs calibration

**Type:** Fact Sufficiency Review
**Depends On:** NSQD-N1.11
**PRD Trace:** LOCAL-NSQD-CAL
**Real Data Dependency:** 01, 02
**Provider Boundary:** N/A
**Description:** Confirm we did **not** activate a production novelty-term fact or a smoke-elite fact. Gamma-flow/control is smoke, not calibration.
**Acceptance Criteria:**
- [x] Ledger has no Active fact that requires novelty term > 0 on `smoke_only`
- [x] Ledger has no Active fact that a smoke card became a production elite

**N1 Exit:** E2E green; smoke_only; empty production archive; **Stage**

**Close note (2026-08-20):** `python -m nsqd skeleton` runs diverge → empty smoke snapshot → ground → score on Piccolo + LanceDB adapters. Gamma-flow and mechanism-free both reject (`nov=0`, `viability=0`); production archive stays empty. EV-N00–EV-N12 (except N03/N09) are Required; corresponding N1 facts are Active. No production-novelty or smoke-elite fact was activated.

---

## Phase NSQD-N2: Harvest validation + later slices

**Role:** Capability
**Depends On:** N1
**Facts Introduced:** NSQD.HARVEST.ENUMERATION.v1
**Demo:** `uv run python -m nsqd harvest --file <essay.md>`
**Tasks:** N2.0 re-verify; N2.1 test essay reject (EV-N03); N2.2 implement. Operators **B–G out of baseline**.

- [x] N2.0 four-command gate green on N1
- [x] N2.1 `tests/facts/test_nsqd_harvest_reject_essay.py` red until N2.2
- [x] N2.2 essay-only / sourceless / requirement-card ingest rejected; synthetic known-hash-vector record accepted; successful harvest commits a content-addressed snapshot and store-local corpus version

**Close note (2026-08-20):** `HarvestUseCase` + `python -m nsqd harvest`. Markdown essays, sourceless rows, and DATA-NSQD-01/02 requirement cards are rejected and write no corpus rows. The accepted ALG-SNAP record is a synthetic known hash vector used only in tests; it is not DATA-NSQD-03 approved corpus data. Successful enumerated harvests atomically preserve immutable approved metadata and commit immutable snapshot/version stamps; omitted metadata is retained and conflicting metadata is rejected. DATA-NSQD-03 harvest seed is still not invented. Final four-command gate: 733 passed, 1 skipped, 92.75% repository coverage; dedicated NSQD command: 170 passed, 95.05% coverage.

### NSQD-N2a Domain-policy isolation

**Role:** Architecture boundary
**Depends On:** N2 plus the approved domain-general decision recorded in plan v1.4.0
**Facts:** NSQD.DOMAIN.POLICY_ISOLATION.v1 → EV-N16
**Purpose:** Replace the finance-calibrated implicit global model with explicit, versioned subject policies before live projection or calibration.

**TDD order:** contract/schema → pure policy tests → application tests → persistence/index tests → cross-pack E2E.

**Acceptance:**
- Add a versioned domain-policy contract owning registered descriptor axes/vocabulary, cell universe, and viability/dval rubric compatibility.
- Require explicit `domain_policy_id`; remove the missing-value fallback to `finance/1`.
- Scope corpus filtering, grounding, cards, elites, and rank coverage to that policy.
- Reserve and validate verdict identity/schema by `(snapshot_id, domain_policy_id)` without claiming the N6 verdict store/use case yet.
- Prevent cell-id collisions and cross-pack evidence leakage. Optimization records cannot satisfy or influence `finance/1`, and finance records cannot satisfy or influence `optimization/1`.
- Inject the policy universe into N7 instead of calling `finance_pack_universe()` directly; preserve the existing 50-elite/20% ALG-COV thresholds and EV-N14 behavior.
- Preserve `finance/1` as a versioned policy, not a default. `optimization/1` remains characterization-only here with zero sufficiency credit; expected cells, minima, recall probes, acquisition query templates, and actual promotion verdict behavior remain N6 work.
- [x] Cover pack mismatch, missing policy, incompatible dval rubric, same-snapshot independent verdicts, corpus filtering, and rank-denominator isolation in EV-N16.
- [x] Update `docs/algorithm-contract-nsqd.md`, requirements, central fact/evidence indexes, migrations, and approved fixtures in the implementation slice; no Active fact until the full gate passes.

**Close note (2026-08-21):** Registered `finance/1` and `optimization/1` policies. Scoring and grounding require a strict explicit `domain_policy_id`; there is no `domain_pack` fallback. Grounding, corpus filtering, cards, elites, and rank universes are scoped to the selected policy, including vector-neighbor selection before top-k truncation. Verdict identity is `(snapshot_id, domain_policy_id)`, migration `005_nsqd_policy_verdicts` reserves and validates that schema while N6 still owns the verdict store/use-case behavior, and migration `006_nsqd_legacy_finance_policy_backfill` atomically backfills legacy finance-only NSQD rows to explicit `finance/1` policy identity. DATA-NSQD-04 is not treated as finance credit. `optimization/1` remains characterization-only here with zero sufficiency credit; the close does not presume its current papers are sufficient, viable, or production-ready. Four-command gate: 865 passed, 1 skipped, 92.17% repository coverage.

### NSQD-N2b Live paper projection

**Depends On:** N1 **and N2a** **and EW-V0A** **and EW-V2** **and DATA-NSQD-04**
**Facts:** NSQD.PROJECT.HUMAN_PARAPHRASE.v1 → EV-N09
**Acceptance:** Projector requires an explicit `domain_policy_id`, rejects abstract substitution and requirement cards, and is idempotent on policy + source/hash-revision identity. Model-assisted paraphrases remain drafts until human approval; importing or analyzing a paper does not make it an NSQD corpus record. Acceptance includes validated `paraphrase_source`, `source_paper_id`, `source_abstract_sha256`, `source_markdown_sha256`, `paraphrase_sha256` over normalized paraphrase bytes, `human_reviewer`, `human_approved_at` UTC, `review_status=approved`, policy/revision-sensitive record identity, canonical ALG-SNAP content hashing, and DATA-NSQD-04 receiving optimization-only credit. The application computes the canonical normalized payload digest and requires it in an injected human-approved allowlist; a job cannot self-approve, and the approved payload's policy must match the explicit application argument.
**Current state:** Projector implemented; EV-N09 Required. DATA-NSQD-04 projects only into `optimization/1`.

- [x] Explicit `domain_policy_id`
- [x] Reject abstract substitution and requirement cards
- [x] Unapproved drafts rejected
- [x] Idempotent on source/content/policy identity
- [x] DATA-NSQD-04 cannot credit `finance/1`

**Close note (2026-08-21):** `ProjectPaperUseCase` writes human-approved paraphrases with projector-assigned `paper-projector/1`. Projection validates `paraphrase_source`, `source_paper_id`, `source_abstract_sha256`, `source_markdown_sha256`, `paraphrase_sha256` over normalized paraphrase bytes, `human_reviewer`, `human_approved_at` UTC, and `review_status=approved`; it then computes the normalized reviewed-payload digest, checks the injected approval allowlist, and binds the embedded policy to the explicit application argument before writing a policy/revision-sensitive record id and canonical ALG-SNAP content hash. `python -m nsqd project` verifies fixture bytes and approval metadata against the selected approved manifest before injecting that allowlist and dispatching the persisted project job. The same full identity is idempotent; an approved source/hash revision creates a distinct record and snapshot. Importing or analyzing a paper does not create corpus rows. DATA-NSQD-04 remains optimization-only credit and does not satisfy `finance/1`. DATA-NSQD-03 was not invented. Four-command gate: 865 passed, 1 skipped, 92.17% repository coverage.

### NSQD-N3 Map harden

**Depends On:** N2a
**Facts:** NSQD.MAP.STATUS_RULES.v1 → EV-N06
**Acceptance:** Full pack-scoped status table on larger snapshots; `ALG.STATUS` ablation only after N6 produces a calibration snapshot for the policy under test.

- [x] Finance universe table has 336 cells; optimization has 8
- [x] Records from one policy cannot change another policy's statuses
- [x] Unlisted coordinates do not coerce into a cell
- [x] Smoke snapshots force every cell to Unknown
- [x] `ALG.STATUS` ablation deferred until N6 calibration

**Close note (2026-08-22):** `status_table` and `MapSnapshotUseCase` emit a complete ALG-STATUS table for an explicit `domain_policy_id`. Finance covers the 336-cell universe and optimization covers the 8-cell universe. Records are filtered by policy before placement; unlisted coordinates are left unplaced. Snapshot states and expected/inspected/disagreement/invalid-reason cell metadata are validated against the selected policy, while every `smoke_only` cell remains Unknown as required. Expected cells come from the policy (or an injected override); morphospace inspection is keyed by `archive_cell_key`. `map` now runs through its callable handler and persisted `nsqd_jobs` dispatch path, including the executable smoke skeleton; migration `007_nsqd_map_job_type` upgrades existing databases and rolls back atomically on copy failure. Rank can consume the table without callers inventing per-cell statuses. No `ALG.STATUS` ablation was run; DATA-NSQD-03 was not invented. Four-command gate: 932 passed, 1 skipped, 92.39% repository coverage; dedicated NSQD command: 356 passed, 94.59% coverage.

### NSQD-N4 Operator A harden (B–G still deferred)

**Depends On:** N3
**Acceptance:** Axiom list → Operator A only.

- [x] Structured axiom rows (FR-M3); empty/blank lists rejected
- [x] `generating_operator` / artifact operator is `A`; B–G rejected
- [x] ALG-SEL target-cell selection from the pack-scoped status table
- [x] Empty target cell has no parent card; parent must be the cell elite when present
- [x] Operators B–G remain deferred

**Close note (2026-08-22):** Diverge accepts a structured axiom list and always records operator `A`. Deferred operators B–G are rejected. A supplied status table must exactly cover the candidate's registered policy universe. ALG-SEL prefers Missing/Sparse/Code-gap/Benchmark-gap/Stalled cells with no elite, then the lowest-viability stored elite, then the smaller cell id (including an all-Unknown table); a caller-supplied target must agree with that result, and any structured axiom `cell_id` must be in-policy and match it. Parent context is validated against the actual elite loaded from the archive, and empty targets cannot carry a parent. Initial candidate persistence is atomic: repeating the same semantic generation, including the legacy single-axiom Operator A shape, is idempotent, while different axioms, operator context, parent, target, or generator run at the same candidate hash raise an immutable-artifact conflict instead of overwriting, including competing inserts. Single-string `axiom` payloads remain valid as a one-row list so the smoke skeleton is unchanged. No `ALG.STATUS` ablation was run; DATA-NSQD-03 was not invented. Four-command gate: 932 passed, 1 skipped, 92.39% repository coverage; dedicated NSQD command: 356 passed, 94.59% coverage.

### NSQD-N5 Ground + live budget

**Depends On:** N2a **and EW-V1** if using paper hybrid search
**Facts:** NSQD.GROUND.LIVE_PRIOR_ART.v1 → EV-N10
**Acceptance:** EV-N10 on live ≤3; no hybrid until EW-V1 is Active. Grounding searches only the candidate's explicit domain-policy corpus view. N5 grounding escalation is distinct from the N6 acquisition fallback.

- [x] Local layers 1–4 remain pack-scoped and still skip live/hybrid on `smoke_only`
- [x] After a local miss on `calibration` / `production_valid`, escalate with a hard budget of 3 live calls
- [x] Paper hybrid is allowed (EW-V1 Active) and is tried before scholar live search
- [x] Live hits are prior-art evidence (`related_partial`), not corpus ingest and not `already_done`
- [x] Distinct from N6 acquisition fallback: no harvest/projection side effects
- [x] Hybrid and scholar search-only interfaces are explicit typed composition inputs; the persisted ground/rescore handlers propagate them and snapshot state
- [x] Only backend-contract hits become normalized `closest_prior_art`; persisted call metadata hashes queries instead of storing candidate text

**Close note (2026-08-22):** `GroundUseCase` keeps layers 1–4 on the candidate's explicit `domain_policy_id` corpus view. `smoke_only` never calls hybrid or live search even when those clients are wired. On `calibration` and `production_valid`, a local `unevaluated` result may escalate through the explicitly injected paper hybrid client and then the scholar client, stopping at the first hit or at `LIVE_SEARCH_BUDGET=3`. `build_container` accepts both typed search-only dependencies, and persisted ground/re-score handlers propagate them and the validated snapshot state; no standalone ground CLI is claimed before N10. Grounding rejects snapshot/corpus-version mismatches, accepts only backend-contract hit shapes, reports normalized `closest_prior_art` for local or external evidence, and persists SHA-256 query fingerprints rather than raw candidate queries. Live hits do not write corpus records and do not classify as `already_done`, so they cannot zero novelty or stand in for N6 acquisition. EW-V1 is Active, so hybrid is in the escalation path when injected. DATA-NSQD-03 was not invented. Four-command gate: 944 passed, 1 skipped, 92.38% repository coverage; dedicated NSQD command: 368 passed, 94.41% coverage.

### NSQD-N6 Calibration snapshot (not smoke)

**Depends On:** N2a + N2b + N5 + `ALG-SUF`; approved DATA-NSQD-03 closes the finance production-valid data dependency
**Facts:** NSQD.SNAPSHOT.PROMOTION.v1 → EV-N13; NSQD.ACQUISITION.FALLBACK.v1 → EV-N17
**Purpose:** Evaluate sufficiency independently for each `(snapshot_id, domain_policy_id)`, acquire searchable gaps through existing paper capabilities, and recheck without conflating ALG-SUF with ALG-COV.

**Missing prerequisites:** None for the `finance/1 production_valid` evidence path.

- [x] Table-driven tests for every closed `SufficiencyFailure`
- [x] Independent optimization/finance verdicts and cross-pack leakage
- [x] Pack-aware sufficiency evaluator and persisted `(snapshot_id, domain_policy_id)` verdict
- [x] Searchable versus integrity routing; LLM cannot approve; staging cycles reserve before provider side effects and fail closed for manual recovery
- [x] Exercise human approval through N2b projection, a new snapshot, and ALG-SUF recheck through an injected bridge
- [x] Persist reserved handler/runner dispatch and retry-safe cycle progress
- [x] Bound injected rechecks with budget-exhaustion and no-approved-snapshot-delta stops
- [x] Implement an injection-ready paper bridge plus durable policy/digest approval bootstrap
- [x] Compose the default production paper runtime with settings, workers, and analysis-metadata bootstrap
- [x] Rank guard does not trigger acquisition
- [x] `finance/1 production_valid` blocked without DATA-NSQD-03 and passes with the approved fixture

**TDD sequence:**
1. Add red table-driven tests for every closed `SufficiencyFailure`, independent optimization/finance verdicts, and cross-pack leakage.
2. Implement the pure pack-aware sufficiency evaluator and persisted verdict; `production_valid` requires zero failures on approved corpus records.
3. Add red orchestration tests for searchable versus non-searchable failures, bounded retries, idempotency, no-delta stops, and human rejection.
4. Implement the fallback at the N5/N6 application boundary. Do not put side effects in pure domain policy or trigger acquisition from `RankGuardBlocked`.
5. Run calibration with faked providers, then project the separately human-approved DATA-NSQD-03 and verify production sufficiency.

**Failure routing:**
- Search for `expected_cell_empty`, `recall_probe_missing`, and `domain_minima_unmet`; render deterministic queries from the policy manifest, missing cell/probe, and record type before any LLM ranking.
- Stop for manual resolution on `manifest_missing`, `record_metadata_missing`, `duplicate_source_conflict`, `retracted_unmarked`, and `disagreement_unresolved`.

**Acquisition trust path:**
Target path: `ALG-SUF failure → deterministic query plan → existing paper discovery → bounded shortlist → automatic import into the paper pipeline → existing download/convert/embed jobs → explicit analyze enqueue → draft projection/paraphrase → human approval → N2b projection → new snapshot → ALG-SUF recheck`.
Imported papers and LLM output are operational staging data, not approved NSQD corpus evidence. The LLM may rank and draft, but cannot set human approval, activate a fact, or promote a snapshot.

**Bounds and idempotency:** Persist an acquisition-cycle identity from `(snapshot_id, domain_policy_id, failure_signature, rendered_query, filters)`. Reuse paper deduplication and job retries. Current compatibility defaults are three query batches per search pass, 25 candidates per discover call, three staged imports per search pass, and stop after two approved rechecks if insufficiency persists. Human review approved those defaults as tunable in `ALG.ACQUISITION_BUDGET`; they are **not frozen** or claimed optimal. Stop on sufficiency, budget exhaustion, no new candidates, human decline, or no change to the approved snapshot/failure set.

**Acceptance:**
- `optimization/1` and `finance/1` can hold different verdicts over the same physical snapshot; scoring, grounding, archive coverage, and novelty use the candidate's own policy view.
- Existing optimization papers count only after an approved `optimization/1` manifest/rubric/probe defines their eligibility; the plan does not presume they pass.
- With an explicitly injected bridge and approved policy manifest, missing finance evidence exercises the bounded seam; approved DATA-NSQD-03 now closes the production-valid loop.
- `calibration` requires an approved recall probe and fixtures; allowed calibration failures remain explicit.
- `finance/1 production_valid` requires approved DATA-NSQD-03, approved nonzero minima, expected-cell coverage, satisfied recall probes, and zero `ALG-SUF` failures.
- ALG-COV remains a separate N7 rank permission and never triggers acquisition.

**Close note (2026-08-23):** Default `gleansight acquire` / `run-paper-jobs` and the desktop app compose the paper runtime from papers settings: analysis prompt/profile metadata is bootstrapped, `PapersAcquisitionBridge` is wired, NSQD state stays in the canonical NSQD database while paper stores remain in the papers database, and the papers job runner owns download/convert/embed/analyze workers. Lightweight `build_container` remains fail-closed without an injected bridge so harvest/map tests stay hermetic. Rank coverage does not acquire, and DATA-NSQD-03 was not invented. Verification passed without exclusions: format, lint, and type checks passed; the full repository gate passed 1067 tests with 1 skipped and 92.31% coverage. The dedicated NSQD command passed 477 tests with 93.60% coverage.

### NSQD-N7 Archive coverage API

**Depends On:** N1
**Facts:** NSQD.ARCHIVE.RANK_GUARD.v1 → EV-N14
**Acceptance:** Rank fails below 50 elites and below 20% of `U \ {Invalid}`; both boundaries tested.

- [x] Below-threshold rejection (`rank_guard_blocked`)
- [x] `|elites| = 49` and coverage < 0.20 blocked
- [x] `|elites| = 50` allowed
- [x] coverage = 0.20 with `|elites| < 50` allowed
- [x] Unknown/uninspected cells remain in the denominator
- [x] Invalid elite cells are excluded from the numerator
- [x] An all-Invalid universe remains below both thresholds

**Close note (2026-08-21):** `RankArchiveUseCase` implements ALG-COV for the original finance-calibrated baseline: allow iff elite count ≥ 50 or coverage ≥ 0.20 of the `finance/1` universe minus Invalid. The use case derives Invalid cells from its injected authoritative status table; callers cannot submit denominator exclusions per rank request. Unknown/uninspected cells stay in the denominator, while Invalid cells are excluded from numerator and denominator. This note records the historical N7 close before later N2a/N2b completion; the current implementation now injects the selected policy universe and keeps projection separate from rank coverage. Four-command gate: 787 passed, 1 skipped, 92.88% repository coverage.

### NSQD-N8 Re-score

**Depends On:** N7
**Facts:** NSQD.RESCORE.REPLAY.v1 → EV-N15
**Acceptance:** `card.snapshot_id != current snapshot_id` → `needs_re_score` → elite replay.

- [x] Equal snapshot ids skip ground/score
- [x] Current-snapshot retries reconcile archive state without rerunning ground/score
- [x] Stale snapshot re-grounds, re-scores, and stamps the current snapshot
- [x] Elite replay: a rescored elite with viability 0 is cleared
- [x] `handle_rescore` on `nsqd_jobs` type `rescore`
- [x] Skeleton runner dispatches claimed `rescore` jobs through `handle_rescore`
- [x] Handler validates persisted corpus version and owns baseline `smoke_only` state plus evaluator provenance; N6 will own promoted snapshot state

**Close note (2026-08-21):** `needs_re_score` is `card.snapshot_id != current_snapshot_id`. Stale cards re-ground and re-score against the current snapshot; current-card retries skip those operations but still reconcile archive state. Archive replay and its returned elite are idempotent, and a current elite that scores viability 0 is removed. Claimed `rescore` jobs dispatch through the skeleton runner; the handler rejects corpus-version mismatch and derives baseline state/provenance instead of trusting those payload fields. This note records the historical N8 close before later DATA-NSQD-04 acquisition and N2a/N2b completion. Four-command gate: 794 passed, 1 skipped, 92.91% repository coverage; dedicated NSQD coverage 95.25%.

### NSQD-N9 Hardening

**Depends On:** N8
**Acceptance:** Import-boundary; UTC; logs.

- [x] `nsqd` domain/application cannot import `nsqd.infra` or `papers.infra`
- [x] Domain policies do not call `datetime.now()`
- [x] Job timestamps come from an injected UTC clock
- [x] Runner logs job transitions with UTC timestamp, job_id, job_type, status_from, status_to

**Close note (2026-08-22):** Import-boundary scanning treats `nsqd.infra` as forbidden from `src/nsqd/domain` and `src/nsqd/app`. Domain modules have no `datetime.now()` calls. `PiccoloNsqdJobQueue` and `build_container` persist job created/updated times from the injected UTC clock. `run_job` logs `job_event` records on queued→running and running→succeeded/failed with that clock. DATA-NSQD-03 was not invented. Four-command gate: 973 passed, 1 skipped, 92.30% repository coverage; dedicated NSQD coverage 94.11%.

### NSQD-N10 Surfaces (FR-U1/U2)

**Depends On:** N6 promotion + N9; production acquisition completion is independent remaining work
**Facts:** NSQD.SURFACE.UNIFIED.v1 → EV-N18
**Acceptance:** `gleansight` unified CLI; Map/Archive/Card UI.

- [x] `gleansight` entrypoint lists harvest, map, diverge, ground, gate, archive
- [x] Existing `papers` CLI remains
- [x] Thin commands call existing use-cases / `nsqd_jobs` dispatch
- [x] Flet app keeps Search/Paper/Monitor/Query/Synthesis and adds Map, Archive, Card

**Close note (2026-08-22):** `gleansight` is the product CLI and reuses the discovery Typer app (`python -m nsqd` still works). Map/diverge/ground/gate/archive are thin wrappers over persisted jobs and rank evaluation. The desktop app adds Map, Archive, and Card screens beside the evidence screens. DATA-NSQD-03 was not invented. Four-command gate: 1021 passed, 1 skipped, 91.91% repository coverage; dedicated NSQD command: 434 passed, 92.99% coverage.

---

## Ablations (before freeze)

Execute as probes **after N6** (they need a `calibration` snapshot): `ALG.AXES`, `ALG.K`, `ALG.NOVELTY_BINS`, `ALG.STATUS.THRESHOLDS`, `ALG.STATUS.WINDOW`, `ALG.VIABILITY`, and `ALG.ACQUISITION_BUDGET` per `ALG-ABL`. File artifacts under `docs/ablations/`. Do not use `smoke_only` for `ALG.NOVELTY_BINS`. ALG.K and ALG.ACQUISITION_BUDGET are synthetic math/state probes. Scores for the five other ablations are LLM-produced; humans validate their prompts and results. Independent human labeling panels are not required.

| Study | Artifact validated | Current decision | Freeze approved |
| --- | --- | --- | --- |
| `ALG.AXES` | yes, 2026-08-24 | keep finance v1 mechanism × target × horizon | no; tunable |
| `ALG.K` | yes, 2026-08-24 | keep k=5 | no; tunable pending production calibration repeat |
| `ALG.NOVELTY_BINS` | yes, 2026-08-24 | keep 0.15 / 0.30 / 0.45 / 0.60 edges | no; tunable |
| `ALG.NOV.TAU` | yes, 2026-08-25 (2a) | unset / report-only | n/a; 2b not authorized |
| `ALG.STATUS.THRESHOLDS` | yes, 2026-08-24 | keep density cut 3 | no; tunable |
| `ALG.STATUS.WINDOW` | yes, 2026-08-25 (1a) | 730-day v1 “24 months”; `--window-days` override | no; tunable; 12/36 table filed |
| `ALG.VIABILITY` | yes, 2026-08-24 | keep 0/5 presence stubs | no; tunable |
| `ALG.ACQUISITION_BUDGET` | yes, 2026-08-25 | keep 3 batches/pass / 25 candidates/call / 3 imports/pass / 2 approved rechecks as compatibility defaults | no; `approved_default_tunable` |
| `ALG.FREEZE` | yes, 2026-08-26 (packet 3) | keep all numeric/default families tunable; `τ` unset | **no** |

- [x] `ALG.K` math probe: Spearman ρ of leave-one-out novelty ranks at k ∈ {3,5,10} vs k=5 on a constructed `calibration` snapshot (`docs/ablations/alg-k.md`). k=3 meets ρ ≥ 0.90; k=10 does not. Production k remains 5 and is **not frozen**. Synthetic unit vectors only; not DATA-NSQD-03.
- [x] `ALG.AXES` LLM probe: keep finance v1 mechanism × target × horizon; reject oversized and non-illuminable triples (`docs/ablations/alg-axes.md`)
- [x] `ALG.NOVELTY_BINS` on constructed calibration: gamma-flow `nov ≥ 1`; mechanism-free `mech = 0`; smoke still forces `nov = 0` (`docs/ablations/alg-novelty-bins.md`)
- [x] `ALG.NOV.TAU` packet 2a: unset/report-only; score stamps `tau: null`; evidence 0.0 stays term 1 (`docs/ablations/alg-novelty-tau.md`)
- [x] `ALG.STATUS.THRESHOLDS` LLM-labeled 10 cells: density cut 3 wins 10/10 vs 2 (9/10) and 5 (8/10); keep 3 (`docs/ablations/alg-status.md`)
- [x] `ALG.STATUS.WINDOW` packet 1a: 730-day default, `--window-days` override; 12/36 day lengths filed (`docs/ablations/alg-status-window.md`)
- [x] `ALG.VIABILITY` keeps 0/5 presence stubs; no 1–4 intermediates (`docs/ablations/alg-viability.md`)
- [x] `ALG.ACQUISITION_BUDGET` math probe: dense first-page useful-at-rank-2 has smallest winner (1, 2, 5); page-2 winners require one candidate per discover call and spare import capacity (`docs/ablations/alg-acquisition-budget.md`). Current 3 / 25 / 3 / 2 is an approved tunable compatibility default and an explicit page-2 counterexample, not an optimum or freeze.
- [x] `ALG.FREEZE` packet 3: freeze-now vs keep-tunable; all families `approved_default_tunable` except `τ` unset (`docs/ablations/alg-freeze.md`)

**Close note (2026-08-24):** Human validation is complete for the ALG.K math artifact and the four recorded LLM prompts/results. The review keeps the current defaults without freezing them: axes remain the finance v1 triple, k remains 5, novelty edges remain 0.15 / 0.30 / 0.45 / 0.60, the density cut remains 3, and viability remains 0/5 presence stubs. At this close, the 24-month status window had not yet been reviewed; packet 1a accepted the 730-day overridable default on 2026-08-25 without freezing it. Novelty threshold `τ` remains unset, and no second labeling panel is required. Final four-command gate evidence for the completed close is 1131 passed, 1 skipped, 92.28% coverage; format, lint, and type checks passed.

**Follow-up note (2026-08-25):** Human review approved ALG.ACQUISITION_BUDGET as `approved_default_tunable`: keep 3 batches per search pass / 25 candidates per discover call / 3 imports per search pass / 2 approved rechecks as compatibility defaults. The synthetic probe explicitly records that 3/3/25 loses its page-2 world, so this is not an optimum or freeze. Production-log or paging-contract evidence reopens the decision.

### Remaining optional decision packets

Keep calibration, freeze, and operator activation as separate approvals. Each packet uses one writer and one independent reviewer for four refinement rounds, then asks the human to choose one explicit outcome: `approved_default_tunable`, `frozen`, `deferred`, `unset`, or `rejected`. No packet implies approval of an adjacent knob or operator.

Review in dependency order:

1. **Status recency window:** packet 1a accepted — v1 “24 months” is **730 days**, overridable with `window_days`. 12/36 (365/1095 day) sensitivity is filed and not frozen. Human review retained fixed-day UTC semantics and rejected calendar-month subtraction for v1 on 2026-08-27; reopening requires a separately approved, versioned semantics packet.
2. **Novelty threshold `τ`:** packet 2a accepted — **unset / report-only**. Packet 2b evidence collection is authorized for 120 balanced pairs using agent proposals plus offline human approval. The current approved data cannot populate that packet. Threshold selection is highest admissible bin edge under 5% overall / 10% per-policy novel false-kill caps; runtime `τ` remains unset (`docs/ablations/alg-novelty-tau-2b.md`).
3. **Existing ALG freezes:** packet 3 accepted — every numeric/default family is `approved_default_tunable`; `τ` stays `unset`. No family is frozen. Reopen freeze only after a production-valid or human-accepted calibration repeat for that family (`docs/ablations/alg-freeze.md`).
4. **Operators B–G:** B is **supported**, non-default, and composition-gated. The default settings allowlist is `A`; a config override may add `B`. The CLI remains without `--operator`. An allowlisted composition may persist `operator=B`, with scored cards preserving `generating_operator=B`. C–G remain deferred. E waits on executable `τ` if it uses novelty; F on axis-policy clarity; G on approved failure data (`docs/ablations/alg-operators.md`).

Every packet ends with explicit sign-off on scope, current default/state, `approved_default_tunable` versus `frozen`, evidence sufficiency, reopen trigger, and exact downstream authorization. Operator packets additionally choose deferred, experimental/off-by-default, or supported; they never relax policy isolation, ALG-SEP, production-valid gates, rank coverage, or no-self-approval.

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

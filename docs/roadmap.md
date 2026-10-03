# Gleansight capability roadmap

Reviewed: 2026-10-02 against commit `016f24540135add841dde453a14ccf1b18731175`.

R01–R12 have been implemented. R10 delivered the feasibility audit and defers exact
Fin-JEPA replication; R11 delivered development diagnostics and an unexecuted walk-forward
preregistration. See the [workflow guide](workflows/roadmap-capabilities.md) for the shipped
capabilities. The baseline and proposals below describe the reviewed starting point.

This roadmap records the additions proposed from that baseline. The original priorities assumed a local-first research workspace used by a researcher and AI agents, favoring trustworthy, reusable outputs before new deployment infrastructure. The sequencing below records dependencies rather than delivery dates.

## Reviewed baseline

Gleansight already supports discovery/import, PDF conversion, embeddings and hybrid search, prompt-versioned analysis and extraction, projects/tags, persisted job controls, corpus synthesis, project ideation, and selected-idea planning. Its shared Python/JSON CLI registry exposes 95 operations and an installed agent skill. Adding basic CRUD, JSON output, job retries/cancellation, or another generic dispatcher would duplicate shipped work. See the [API surface audit](api-surface-audit.md) and [agent API guide](agent-api.md).

The [NSQD baseline is closed](nsqd-plan-closeout.md): A is enabled by default, B is supported within its gates, and E is experimental and requires explicit configuration. C/D/F/G remain deferred. The [open-work closeout](development-plan-open-work.md) deliberately leaves corpus synthesis experimental. Superseded development-plan checkboxes are not proof that a capability is absent.

The financial research workflow already produces verified, hash-bound YieldJEPA runs and diagnostic bundles. It is a Treasury-based prototype, not a demonstrated Fin-JEPA paper replication. Keep that distinction when choosing research extensions. See [the prototype workflow](workflows/financial-jepa.md) and [diagnostic limitations](workflows/financial-jepa-diagnostics.md).

## Recommended sequence

| ID | Addition | Current coverage | Priority / dependency |
| --- | --- | --- | --- |
| R01 | Citation-ready and provenance-aware exports | CSV metadata export exists; bibliography formats and extraction provenance export are missing | Next product increment |
| R02 | Grounded, project-scoped synthesis | Backend scope and paper-level sources exist; UI scope and passage-level grounding are incomplete | Next; needed before calling synthesis production-ready |
| R03 | Analysis output inspection and run comparison | Run metadata, outputs, extraction values, tokens and costs are stored; comparison is missing | Next; supports reliable prompt revisions |
| R04 | Verified workspace backup and restore | Data and artifact stores exist; no unified product workflow | Next; protect accumulated research |
| R05 | Saved discovery and persistent screening | Source-ID deduplication and rejection exist; saved searches and review history are missing | After R01; scheduling depends on R07 |
| R06 | Human review desk for ideas and plans | Evidence/critique bundles and selected-idea planning exist; durable researcher decisions and an attributed review handoff are missing | After R02/R03 establish review patterns |
| R07 | Managed background execution and resource controls | Persisted queue, bounded execution, recovery and cancellation exist; unattended orchestration is incomplete | Before scheduled discovery or concurrent agent execution |
| R08 | Acquisition planning across deficits and source contribution reports | NSQD acquisition and rechecks exist; planning starts from one deficit and reports aggregate changes | After a bounded acquisition pilot |
| R09 | Local MCP adapter over the existing registry | Python/JSON CLI available; MCP transport is missing | When a target agent client needs it; preserve one registry |
| R10 | Fin-JEPA baseline feasibility audit | Investigation plan exists; prerequisite audit is explicitly not started | Immediate research prerequisite, independent of product work |
| R11 | Capacity-matched and walk-forward diagnostics | Current diagnostics use a fixed development split and unmatched input dimensions | Capacity matching first; new evaluation protocol before walk-forward work |
| R12 | Verified experiment catalog and cross-run comparison | Individual run manifests and validation exist; shared comparison surface is missing | When at least two compatible controlled runs exist |

Recommended first delivery: R01, starting with selected-paper/project bibliography export and an export manifest. It adds useful interoperability without a model call or new server. Then prioritize R03 and R02 to make generated findings reviewable. R04 can proceed independently. If financial research is the immediate objective, begin R10 in parallel rather than treating the current prototype as a replication baseline.

## Next product increments

### R01 — Citation-ready and provenance-aware exports

**Why:** A research result should move into a reference manager, literature table, or report without manual copying or losing its origin.

**Evidence:** [Query export](../src/papers/ui/screens/query.py#L488) writes search-hit CSV fields rather than citation records; [paper and external-ID tables](../src/papers/infra/piccolo/tables.py#L30) already retain metadata and identifiers. Existing [ideation evidence contracts](../src/papers/domain/ideation.py#L58) provide a pattern for exact excerpt provenance. BibTeX, RIS and CSL JSON are established metadata interchange choices documented by [Crossref](https://www.crossref.org/documentation/retrieve-metadata/content-negotiation/).

**Scope:** Export selected papers or a project as BibTeX/RIS, retain CSV, and add an extraction export with run/prompt identities. Add metadata enrichment only when required fields are missing, with an explicit provider call and source record.

**Done when:**

- Bibliography exports preserve available authors, title, year, venue, DOI and stable paper identity; missing fields are reported rather than invented. Unicode and escaping survive import into a reference manager.
- Extraction rows include field/value, paper ID, analysis-run ID, prompt-version ID, and a source locator when available; absent source locators are explicit.
- A manifest records selection and source/run identities, so later reanalysis cannot silently change a previous export. The same export is available through CLI/API and the desktop selection workflow.

**Tradeoff:** Citation formatting and extraction provenance are different concerns. Ship bibliography export first rather than making it wait for complete passage annotation.

### R02 — Grounded, project-scoped synthesis

**Why:** Researchers need to inspect supporting passages and recognize unsupported answers before relying on corpus Q&A.

**Evidence:** The [synthesis use case](../src/papers/app/use_cases/synthesis.py#L43) supports project filtering and returns paper-level sources. The [desktop synthesis screen](../src/papers/ui/screens/synthesis.py#L67) calls it without a project scope and renders source titles as text. The current closeout explicitly retains experimental status.

**Scope:** Expose project scope in the UI; make sources navigable; attach exact retrieved passages to generated claims; represent insufficient/conflicting evidence explicitly. Reuse existing evidence IDs and digest validation where applicable.

**Done when:**

- A project-scoped question cannot use papers outside that project, and each source opens the paper and supporting passage.
- Source references bind to a specific Markdown artifact and section/offset or page locator; changed artifacts make stale references visible.
- Offline evaluation includes unsupported questions, conflicting papers, incorrect citations and empty projects. A supported-looking answer with invalid references fails validation; docs change experimental status only after the agreed grounding criteria pass.

**Tradeoff:** Retrieving a paper is not evidence for every claim in an answer. Locator quality must be proven before describing citations as claim-level support.

### R03 — Analysis output inspection and run comparison

**Why:** Prompt revisions and model changes should be reviewed before their extracted values drive filters or aggregates.

**Evidence:** [Paper detail](../src/papers/ui/screens/paper.py#L301) presents run metadata. The [analysis store](../src/papers/infra/piccolo/stores.py#L1354) persists output paths and validation details, and [project analysis](../src/papers/app/use_cases/analysis.py#L65) already targets prompt versions.

**Scope:** Open successful/failed analysis outputs from paper detail; compare two runs and their extracted fields; inspect validation failures, model, prompt version, tokens and recorded cost. Extend comparison to a selected project cohort after the per-paper view works.

**Done when:**

- Two runs can be compared with output and extraction diffs, source paper/run/prompt identities, statuses and validation errors visible.
- A changed extraction schema is called out; absent values are distinct from changed values. Prior runs remain immutable.
- A saved evaluation cohort can compare a prompt revision against the existing baseline without overwriting accepted outputs. Cost is labeled unknown when pricing or provider usage is unavailable.

**Tradeoff:** A text diff is useful inspection, not a quality score. Automated quality rankings require declared evaluation criteria and reviewer labels.

### R04 — Verified workspace backup and restore

**Why:** The corpus, accepted reviews and provenance are accumulated work that should survive migration or disk loss.

**Evidence:** [Composition](../src/papers/app/composition_root.py) and [API runtime](../src/gleansight/api/runtime.py) span paper SQLite, NSQD SQLite, artifact blobs and vector indexes. The current API catalog has no coordinated backup/restore workflow.

**Scope:** Create a consistent workspace export with a manifest, then verify and restore into a new workspace. Separate authoritative records/artifacts from rebuildable indexes.

**Done when:**

- Export records schema versions and hashes of required records/artifacts; a database and its referenced blobs cannot be captured at inconsistent points in an active pipeline.
- Restore into an empty destination preserves paper IDs, project membership, runs, review/projection identities and approved-digest history; public reads agree with the source workspace. Indexes can be restored or explicitly rebuilt.
- Corruption and missing artifacts are detected before using the restored workspace. Credentials, environment files and provider caches are excluded by default; an existing workspace is never silently overwritten.

**Tradeoff:** Copying SQLite alone is not a corpus backup. Decide which indexes are cheaper to rebuild than archive, and retain the distinction between archived evidence and generated reports.

## Follow-on workflow capabilities

### R05 — Saved discovery and persistent screening

**Why:** Repeating a literature search should reveal new papers without losing prior inclusion/exclusion decisions.

**Evidence:** [Discovery](../src/papers/app/use_cases/discovery.py#L100) reuses candidates by source ID; [search UI](../src/papers/ui/screens/search.py#L535) keeps current results in screen state. Rejection exists, but a saved-query and attributed screening-history workflow does not.

**Scope:** Save query/filter/provider settings to a project; rerun on demand; present a delta; record include/exclude/maybe, reviewer and rationale. Add scheduling only after R07.

**Done when:** Saved searches and decisions survive restart; reruns identify previously seen candidates; repeated imports retain existing idempotency; selected inclusions use existing atomic project/tag attachment. History distinguishes a query rerun, metadata change and deliberate reviewer revision.

**Tradeoff:** Different providers may identify the same paper differently. Define canonical DOI/source-ID reconciliation without discarding source-specific provenance.

### R06 — Human review desk for ideas and plans

**Why:** Generated ideas need durable keep/revise/reject decisions and an explicit research handoff.

**Evidence:** [Ideation](../src/papers/app/use_cases/ideation.py#L55) already emits evidence and critiques; [bundle declarations](../src/papers/domain/ideation_artifacts.py#L35) do not claim human approval. The [workflow](workflows/ideation.md) treats idea selection as an operator action, not recorded endorsement.

**Scope:** Browse a project bundle in the desktop, inspect evidence and critique, record a researcher decision, then select an idea for the existing plan workflow. Expose those decisions through CLI/API as well.

**Done when:** A verdict and rationale bind to the exact bundle/idea hash; revisions create new immutable review records; planning links to the selected idea and review; a reviewer can distinguish generated, reviewed and selected artifacts after restart. A review never grants NSQD operator activation or changes evidence verification automatically.

**Tradeoff:** Keep acceptance of an idea separate from approval of a projection, experiment execution, or runtime operator activation.

### R07 — Managed background execution and resource controls

**Why:** Long imports and project analyses should continue predictably without an agent holding a synchronous call open.

**Evidence:** The [runner](../src/papers/app/job_runner/runner.py) executes `run_next` synchronously; the [public job adapter](../src/gleansight/api/papers/jobs.py) already exposes enqueue, bounded execution, recovery and cancellation. This proposal extends those facilities rather than replacing the queue.

**Scope:** Add an explicit supervised local worker with persisted progress, pause intake, bounded concurrency and cycle/job/time/token limits. Preserve existing cancellation semantics and distinguish pausing new work from checkpoint-resuming an in-flight provider call.

**Done when:** Restart and stale-worker recovery do not duplicate committed work; progress can be polled through the API; limits stop further work at documented boundaries; cancellation is truthful about work already completed. Two clients using different workspaces cannot cross-bind paper tables or consume each other's jobs. Concurrent claims and workspace isolation are tested before enabling parallel execution.

**Tradeoff:** Local SQLite/Piccolo bindings and provider limits make unrestricted concurrency a poor default. Start with one managed worker and add parallelism only after isolation is demonstrated; do not invent dollar precision when cost data is absent.

### R08 — Acquisition portfolios and source contribution reports

**Why:** A reviewer should see all actionable evidence gaps and which approved sources corresponded to measured progress.

**Evidence:** [Acquisition planning](../src/nsqd/app/use_cases.py#L2113) starts with the first searchable deficit and one query. [Projection/recheck](../src/nsqd/app/use_cases.py#L2268) processes approved inputs and returns aggregate sufficiency changes.

**Scope:** Plan a deterministic, capped portfolio of deficits, deduplicate overlapping retrievals, and emit a projection-by-projection contribution report.

**Done when:** Each query/shortlist/source binds to a target cell/probe/type deficit; global and per-deficit caps are enforced; a digest-bound report shows observed before/after deficits for every projection, including duplicate/no-change inputs. Offline replay verifies the report. Existing manifest verification, manual-review routing and promotion guards remain authoritative.

**Tradeoff:** Observed sufficiency changes are not causal importance scores. Broader acquisition should reduce repeated cycles without increasing unbounded review burden or creating approval authority.

### R09 — Local MCP adapter

**Why:** An agent client that supports MCP could discover and invoke Gleansight tools without shell command construction.

**Evidence:** The [operation registry](../src/gleansight/api/catalog.py) already has request schemas, effects and approval metadata, but no MCP transport. MCP defines [schema-described tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) and a [local stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports).

**Scope:** Add a thin local adapter over that registry, with configurable namespaces/tool subsets and compatibility tested against a chosen agent client. Keep business logic in the existing handlers; use queue operations for long work when R07 is available.

**Done when:** Tool discovery and results agree with the Python/CLI contracts; structured validation/errors and resource identities survive transport; stdout contains protocol messages only; approval operations remain unavailable without explicit human authorization. Transport hints describe behavior but never authorize it. Pin and test a client-compatible protocol revision.

**Tradeoff:** MCP improves integration, not research quality. Validate a real client need before maintaining a second transport; a hosted HTTP service is a separate decision.

## Research capability track

### R10 — Fin-JEPA baseline feasibility audit

**Why:** Proposed paper-derived experiments currently lack an established comparable baseline.

**Evidence:** The [investigation plan](../scripts/_jepa_investigation_plan.py#L61) marks its prerequisite audit `not_started` and records unresolved dataset, feature, split, optimizer, license, code/checkpoint and resource details. [Direction proposals](../scripts/_jepa_investigation_directions.py#L37) keep their experiment steps blocked on that baseline.

**Scope:** Produce a versioned feasibility/protocol record classifying every prerequisite as reported, proposed, unknown or verified, with sources and explicit substitutions.

**Done when:** Required access/licensing, timestamp alignment, leakage-safe splits and compute requirements are recorded; a permissible baseline passes a smoke check before a reduced study; substitutions are visible in reports. Paper-equivalent metrics are not claimed unless equivalence is established. If required evidence/access remains unavailable, the audit records a concrete deferral instead of treating the Treasury prototype as replication.

**Tradeoff:** An honest audit may conclude that exact replication is currently infeasible. That is useful prioritization evidence, not permission to manufacture a baseline.

### R11 — Capacity-matched and walk-forward diagnostics

**Why:** Current development diagnostics cannot distinguish representation benefit from differences in input/readout capacity or regime sensitivity.

**Evidence:** The [diagnostic guide](workflows/financial-jepa-diagnostics.md) explicitly notes a 240-input raw baseline versus 16-dimensional neural probes, one training/selection split, and no held-out estimate. The [probe implementation](../src/research/financial_jepa/diagnostic_probes.py#L45) and [split guard](../src/research/financial_jepa/diagnostic_guard.py#L58) enforce the current bounded protocol.

**Scope:** First add predeclared capacity/input-budget comparisons for the existing YieldJEPA prototype. Later introduce a separate versioned walk-forward protocol with fold-local preprocessing and an untouched evaluation segment. Fin-JEPA paper-derived branches additionally require R10; improving the existing prototype does not imply paper replication.

**Done when:** Comparisons share dates, targets, seeds and train-only preprocessing; matched-capacity assumptions are stated and checked. Fold membership, selection and artifact identities are hash-bound; paired and aggregate reports include variation and failures. Existing development metrics are not relabeled as held-out results, and old guards are not silently relaxed to consume a reserved evaluation period.

**Tradeoff:** More folds and fits cost more, and chronological folds are not independent samples. Predeclare interpretation; do not present these diagnostics as significance, profitability or a model-winner claim.

### R12 — Verified experiment catalog and cross-run comparison

**Why:** Researchers and agents should compare controlled runs without hand-copying metrics or confusing datasets, protocols and code versions.

**Evidence:** [YieldJEPA](workflows/financial-jepa.md) and [diagnostic workflows](workflows/financial-jepa-diagnostics.md) already produce validated hash-bound bundles. Their scripts are research surfaces distinct from the current product operation registry; a shared verified run catalog/comparison interface is absent.

**Scope:** Index explicitly selected research bundles and expose read-only verification/list/compare through the CLI/API. Add execution handoffs only after protocol and resource prerequisites are satisfied.

**Done when:** Bundles are verified before indexing or comparison; incompatible source/split/protocol identities are refused or explicitly shown as incomparable; reports preserve paired dates/seeds, metric definitions and code/artifact identity. Comparison creates a separate report without rewriting source bundles. A smoke result, a development diagnostic and a validated evaluation remain distinguishable.

**Tradeoff:** Start when compatible controlled runs exist. A comparison screen cannot compensate for an invalid experiment protocol, and must not declare a winner by default.

## Deliberately deferred

| Capability | Prerequisite before scheduling implementation |
| --- | --- |
| Operator C activation | Resolve the unsupported typed bridge and required independent evidence; obtain the specific human activation decision |
| Operator D activation | Satisfy C and the analogy/evidence contract, then its own activation decision |
| Operator F activation | Required held-out, stability, threshold and evidence-sufficiency checks, followed by explicit activation authority |
| Operator G activation | Qualifying approved failure records and the frozen contract/census checks, followed by explicit activation authority |
| Event-conditioned or dual-target Fin-JEPA experiments | R10 plus direction-specific timestamped data/licensing/alignment or reproduced denoising baseline |
| Hosted HTTP API, team collaboration or multiuser deployment | Demonstrated demand plus a separate resource-isolation, authentication, secret-management and deployment design |

These are prerequisites, not requests to change current operator allowlists or promote experimental evidence. See the [NSQD algorithm contract](algorithm-contract-nsqd.md) and [baseline closeout](nsqd-plan-closeout.md). A/B support, configured E execution, existing verified projection/Tau workflows, and approved-digest checks are already shipped.

## Completion standard for each selected increment

Each selected item should receive a bounded implementation plan and observable acceptance scenarios. New supported workflows should share CLI/API handlers, appear in catalog discovery, and be documented in the agent skill; user-facing workflows should have a usable desktop path where relevant. Verify ordinary use, malformed/empty/stale inputs, restart/idempotency behavior where applicable, and one adjacent regression. Retain generated reports under `output/<workflow>/<UTC-run-id>/`; archived evidence and prior review/run identities remain immutable. Use the existing repository verification gate before calling an increment complete.

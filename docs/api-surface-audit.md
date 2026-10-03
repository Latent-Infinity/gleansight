# Gleansight API surface audit

The public registry exposes 95 operations: 60 paper operations, 34 NSQD operations, and one capability operation. Each operation has one typed request schema and handler shared by `GleansightAPI.call` and `gleansight api call`. `gleansight papers` also exposes the existing human-oriented paper commands alongside the existing NSQD commands. This audit covers existing product workflows, including UI-only actions and application use cases that previously lacked CLI access.

| Existing workflow or gap | Public operation coverage |
| --- | --- |
| Discover and page scholar results; inspect/import/reject candidates | `papers.candidates.discover`, `list`, `get`, `import`, `reject` |
| Inspect papers and Markdown; delete/reset stage | `papers.papers.list`, `get`, `get-markdown`, `delete`, `reset-stage` |
| Download, convert, embed, analyze one paper/project, reanalyze | `papers.pipeline.download`, `convert`, `embed`, `analyze`, `analyze-project`, `reanalyze` |
| Typed enqueue, persisted progress, recovery, retries, individual/bulk job controls | `papers.jobs.enqueue`, `list`, `get`, `status`, `recover`, `retry`, `run-next`, `run-bounded`, `cancel`, `bulk-cancel`, `delete`, `bulk-delete` |
| Inspect analysis runs and extracted values | `papers.runs.list`, `get`, `extractions` |
| Create and version prompts; inspect exact versions | `papers.prompts.create`, `create-version`, `list`, `get`, `get-version`, `versions` |
| Create projects/tags, attach papers, inspect both membership directions | `papers.projects.*`, `papers.tags.*` |
| Search, filter, count, aggregate; corpus synthesis and evidence-grounded plans | `papers.query.search`, `filter`, `count`, `average`; `papers.synthesis.ask`; `papers.research.ideate-project`, `plan-idea` |
| Existing configured analysis profiles and vector/FTS rebuilds | `papers.profiles.list`, `get`; `papers.indexes.rebuild-vector`, `rebuild-fts` |
| Skeleton and corpus ingestion with verified projection manifests | `nsqd.skeleton.run`; `nsqd.corpus.harvest`, `project` |
| Full snapshot map, configured divergence, grounding, gate, rescore, archive rank | `nsqd.snapshots.map`; `nsqd.candidates.diverge`, `ground`; `nsqd.cards.gate`, `rescore`; `nsqd.archive.rank` |
| Real paper acquisition bridge and bounded paper execution | `nsqd.corpus.acquire`; `papers.jobs.run-bounded` replaces the separate `run-paper-jobs` workflow |
| Tau export/inventory, autonomous review, verified packet evaluation | `nsqd.tau.export`, `inventory`, `review`, `evaluate` |
| Persisted records, snapshots/members, candidate artifacts, cards/elites, verdicts, cycles, and NSQD jobs | Corresponding `nsqd.*.list`/`get`, `nsqd.snapshots.members`, `nsqd.elites.list`, `nsqd.jobs.status`, `cancel` |
| Explicit digest approval and approval inspection | `nsqd.digests.approve`, `list` |
| Inspect resolved resources, enabled operators, and provider metadata | `system.capabilities` |

Operation discovery includes effects and approval metadata; `describe` supplies the precise full schema. Compact catalog discovery avoids repeating every schema. List requests use bounded limits and stable offset ordering. Metadata does not initialize application resources; paper CRUD uses database-only adapters. Existing use cases retain pipeline prerequisites, enqueue idempotency, provenance validation, and configured operator allowlists. Decimal costs, dates, and paths are normalized to JSON; failures have versioned structured envelopes without configuration secrets. CLI input is bounded to 1 MiB and supports files/stdin.

The local API has Python and JSON CLI transports. Live discovery, downloading, embedding, and model execution still need their existing providers. Runtime credential administration and new HTTP/MCP servers are outside the existing product surface. Internal provenance mutators are deliberately not public operations. C, D, F, and G remain deferred under the existing operator contract; this interface does not authorize their activation. E executes only when explicitly configured. Projection inputs still require verified manifests, and digest approval remains an explicit human-authorized operation. Generated reports use `output/<workflow>/<UTC>/`; archived evidence is immutable.

The agent skill is versioned under [skills/gleansight](../skills/gleansight/SKILL.md). Its conditional paper and NSQD references enumerate the workflow operations and instruct agents to discover schemas, reuse returned identifiers, poll persisted job state, and respect approval boundaries. See [agent-api.md](agent-api.md) for the callable contract and examples.

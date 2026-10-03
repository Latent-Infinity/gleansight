# Research workflow additions

Use `uv run gleansight api describe OPERATION` before constructing a request. The installed
schema defines nested fields, identifiers and bounds. Each call returns one success/error
envelope; retain returned identifiers and artifact paths for the next step.

| Workflow | Public operations and desktop handoff |
| --- | --- |
| Export selected papers or a project | `papers.exports.create` accepts `paper_ids` or `project_id` and `format` (`bibtex`, `ris`, `csv`, `extractions`); `papers.exports.verify` verifies the returned manifest. Query-screen controls export the current selection. |
| Review analysis changes | `papers.analysis.inspect` reads a run; `.compare` compares baseline/revised IDs. `papers.analysis.cohorts.save/get/list/compare` retain explicit immutable selections. Paper detail shows outputs, extraction/schema changes and saved cohorts. Unknown cost remains unknown. |
| Inspect synthesis evidence | `papers.synthesis.ask` returns grounded claims and exact source passages; use `papers.synthesis.verify-source` on its source record before relying on it. The synthesis screen links readable passages and signals stale sources. Citation integrity does not establish semantic truth. |
| Back up a workspace | `workspaces.backup` snapshots authoritative databases and referenced artifacts; `.verify` checks the backup; `.restore` requires `backup_path` and an empty new `destination`, plus the existing explicit approval path. Active work refuses backup. Idle queued work is retained. Secrets are excluded and search indexes require rebuilding. |
| Save and screen discovery | `papers.screening.save/list/get/rerun/review/import/schedule` retain project queries, source identity/provenance, deltas and attributed decision revisions. Search-screen controls provide the same handoff. Imports retain memberships and queue the normal pipeline. Scheduled runs use the ordinary job queue. |
| Review generated research ideas | `papers.reviews.bundles/inspect/record/list/plan` bind researcher decisions to exact bundle/idea hashes. Record `keep`, `revise` or `reject` with reviewer/rationale and the inspected binding. Planning requires a current kept review and selection note. Ideation-screen controls retain these decisions after restart. Reviews grant no NSQD approval. |
| Run bounded background work | `papers.workers.start/status/list/pause/resume/stop` manage a local process and persistent progress. A workspace permits one managed executor. Manual execution refuses while its reservation is active. Pause/stop and resource limits stop intake at job boundaries; active provider calls finish before the checkpoint. |
| Attribute acquisition contributions | `nsqd.portfolios.plan/stage/project/replay` create capped deficit plans, stage normal acquisition, project existing approved inputs, and replay contribution reports offline. Preserve the returned plan/report paths. Source duplicates and no-change projections remain visible; changes are observed contributions, not causal estimates. |
| Verify and compare controlled research runs | `research.runs.verify/index/list/compare` verify explicitly selected owned bundles under `output/`, retain immutable catalog identities and create separate compatibility/paired-metric reports. Every read reverifies source bytes. Install the optional research group for these calls; metadata discovery remains core-only. |

For example:

```sh
uv run gleansight api call papers.exports.create \
  --input-json '{"project_id":"PROJECT_ID","format":"bibtex"}'
uv run gleansight api call papers.analysis.compare \
  --input-json '{"baseline_run_id":"BASELINE_ID","revised_run_id":"REVISED_ID"}'
uv run gleansight api call workspaces.backup
uv run gleansight api call papers.workers.start \
  --input-json '{"limits":{"max_jobs":10,"max_cycles":100,"max_seconds":60}}'
```

Worker defaults are concurrency 1, 100 jobs, 1000 intake cycles and 300 seconds, with no token
cap. An explicit token cap refuses jobs whose intake cost cannot be bounded. Inspect status
for active job, elapsed progress, stop reason and unknown token usage. Interrupted jobs require
an explicit retry; terminal jobs are not replayed during recovery.

Backup verification does not authorize restore over an existing workspace. Restore preserves
authority records and rebuild instructions while rebasing operational file references; use
the returned configuration/resource paths when opening it.

The [local MCP guide](local-mcp.md) describes stdio client configuration. The
[Fin-JEPA feasibility audit](../research/fin-jepa-feasibility.md) records the exact-replication
deferral and gates for a distinct substitute protocol. Financial prototype diagnostics remain
separate from claims of replication, held-out performance or profitability.

The [capacity diagnostic guide](financial-jepa-capacity.md) describes matched Treasury
input/readout comparisons and a separate versioned walk-forward preregistration. Its command
uses only the verified development cache; it does not execute the reserved evaluation period.

New evaluation cohorts use version2 content fingerprints and remain verifiable after workspace
backup/restore. Legacy cohorts continue to reopen in their original workspace. Before backing
up a workspace containing legacy cohorts, save each selection as a new cohort in the original
workspace; this creates a version2 record without altering the old record. A relocated legacy
cohort cannot be verified from its path-bound fingerprint and reports an actionable
re-save-before-backup error.

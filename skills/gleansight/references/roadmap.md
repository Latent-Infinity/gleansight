# Added workflow surfaces

Discover the installed registry and inspect each operation schema before building inputs.
The [workflow guide](../../../docs/workflows/roadmap-capabilities.md) describes desktop and
CLI handoffs; [local MCP](../../../docs/workflows/local-mcp.md) uses the identical registry.

| Goal | Operation group |
| --- | --- |
| Bibliography/extraction export and verification | `papers.exports.create`, `papers.exports.verify` |
| Stored analysis inspection/comparison and immutable cohorts | `papers.analysis.inspect`, `.compare`, `.cohorts.save/get/list/compare` |
| Verify grounded synthesis sources | `papers.synthesis.ask`, `papers.synthesis.verify-source` |
| Saved discovery, screening, import and bounded scheduling | `papers.screening.save/list/get/rerun/review/import/schedule` |
| Attributed idea review and selected planning | `papers.reviews.bundles/inspect/record/list/plan` |
| Managed job execution and progress/control | `papers.workers.start/status/list/pause/resume/stop` |
| Authoritative backup, verification and fresh restore | `workspaces.backup/verify/restore` |
| Capped deficit acquisition and observed contribution replay | `nsqd.portfolios.plan/stage/project/replay` |
| Explicit research bundle verification, catalog and compatible comparison | `research.runs.verify/index/list/compare` |

Use returned resource identifiers and paths. An immutable review is not a projection approval.
Newly saved analysis cohorts have portable content fingerprints. Re-save a legacy cohort's
selection in its original workspace before backup; its original record remains immutable and
its path-bound fingerprint cannot verify a relocated copy.
Worker limits apply at job intake/checkpoints, not preemptive cancellation of provider calls.
Restore requires the explicit existing approval path and an empty new destination. Approval
manifests remain authoritative for portfolio projection; reports cannot manufacture approval.

Fin-JEPA exact replication is deferred in the
[versioned audit](../../../docs/research/fin-jepa-feasibility-v1.json). The Treasury prototype
does not satisfy that baseline, and diagnostic comparisons do not declare a winner.

Research runs must be explicitly selected owned bundles under the workspace's `output/`.
See the [catalog workflow](../../../docs/workflows/research-catalog.md) for verification,
indexing, comparison and portable backup commands.
Install the optional research group for verification (`uv sync --group research`); ordinary
registry discovery works without it. Catalog reads reverify source artifacts, comparisons
write separate reports, and incompatibilities remain explicit. The
[capacity diagnostic guide](../../../docs/workflows/financial-jepa-capacity.md) documents
matched development comparisons and a separate unexecuted walk-forward preregistration;
reserved evaluation is not consumed by that command.

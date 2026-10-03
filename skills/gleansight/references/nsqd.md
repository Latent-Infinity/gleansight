# NSQD discovery operations

Inspect the live JSON schema with `gleansight api describe NAME` before each call. NSQD uses persisted snapshots, candidates, cards, verdicts, and jobs; use IDs returned by operations. The approved review archive at `archive/reviews/v1` is immutable.

| Goal | Operations |
| --- | --- |
| Smoke and corpus intake | `nsqd.skeleton.run`, `nsqd.corpus.harvest`, `nsqd.corpus.project` |
| Map and generate | `nsqd.snapshots.map`, `nsqd.candidates.diverge`, `nsqd.candidates.ground` |
| Evaluate and archive | `nsqd.cards.gate`, `nsqd.cards.rescore`, `nsqd.archive.rank`, `nsqd.elites.list`, `nsqd.verdicts.get`, `nsqd.verdicts.list` |
| Acquisition and digest review | `nsqd.corpus.acquire`, `nsqd.digests.list`, `nsqd.digests.approve` |
| Tau measurement and review | `nsqd.tau.inventory`, `nsqd.tau.export`, `nsqd.tau.review`, `nsqd.tau.evaluate` |
| Inspect persisted resources | `nsqd.records.list`, `nsqd.records.get`, `nsqd.snapshots.list`, `nsqd.snapshots.get`, `nsqd.snapshots.members`, `nsqd.candidates.list`, `nsqd.candidates.get`, `nsqd.cards.list`, `nsqd.cards.get`, `nsqd.cycles.list`, `nsqd.cycles.get`, `nsqd.jobs.list`, `nsqd.jobs.get`, `nsqd.jobs.status`, `nsqd.jobs.cancel` |

Listing is bounded by the schema's pagination fields.

For a reviewed projection, pass both `projection` and `manifest` to `nsqd.corpus.project`. The runtime verifies the approved manifest row and file bytes; the projection never self-approves. `nsqd.digests.approve` is a distinct human approval action. Call it only after a human authorizes the specific digest and set the API's explicit approval opt-in for that call. `nsqd.corpus.acquire` accepts `human_decision` and an optional paired `approved_projections`/`approval_manifest`; a decision does not approve a digest.

The API supports A, B, and explicitly configured E; `system.capabilities` reports the actual enabled allowlist, which defaults to A. B requires `target_cell_id` and `axiom_cell_id`. C, D, F, and G remain deferred. Use `nsqd.candidates.diverge` schema and configured operators rather than inventing requests for deferred operators. Grounding, rescoring, and acquisition may use external providers. `nsqd.tau.review` requires its configured review provider; inventory and export read persisted measurements. Choose snapshot state, policy, and corpus version from actual persisted artifacts.

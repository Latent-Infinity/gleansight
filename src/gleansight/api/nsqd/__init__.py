"""Discoverable NSQD workflow and operational read API."""

from gleansight.api.models import EmptyRequest
from gleansight.api.nsqd import acquisition, reads, requests, tau, workflows
from gleansight.api.operation import Operation, RegisteredOperation


def operations() -> tuple[RegisteredOperation, ...]:
    result: list[RegisteredOperation] = [
        Operation(
            "nsqd.skeleton.run",
            "Run the bounded smoke workflow.",
            requests.SkeletonRequest,
            workflows.skeleton,
            ("write",),
        ),
        Operation(
            "nsqd.corpus.harvest",
            "Validate and harvest corpus records.",
            requests.HarvestRequest,
            workflows.harvest,
            ("write", "external"),
        ),
        Operation(
            "nsqd.corpus.project",
            "Import a manifest-verified reviewed projection.",
            requests.ProjectRequest,
            workflows.project,
            ("write", "external"),
        ),
        Operation(
            "nsqd.snapshots.map",
            "Map every cell status for a snapshot and policy.",
            requests.MapRequest,
            workflows.map_snapshot,
            ("write",),
        ),
        Operation(
            "nsqd.candidates.diverge",
            "Generate a candidate using a configured operator.",
            requests.DivergeRequest,
            workflows.diverge,
            ("write",),
        ),
        Operation(
            "nsqd.candidates.ground",
            "Ground a candidate against a corpus snapshot.",
            requests.GroundRequest,
            workflows.ground,
            ("write", "external"),
        ),
        Operation(
            "nsqd.cards.gate",
            "Evaluate viability and archive eligibility.",
            requests.GateRequest,
            workflows.gate,
            ("write",),
        ),
        Operation(
            "nsqd.cards.rescore",
            "Rescore a card against current corpus metadata.",
            requests.RescoreRequest,
            workflows.rescore,
            ("write", "external"),
        ),
        Operation(
            "nsqd.archive.rank",
            "Return full policy elites and guarded archive ranking.",
            requests.MapRequest,
            workflows.rank,
            ("write",),
        ),
        Operation(
            "nsqd.corpus.acquire",
            "Acquire papers with the configured paper bridge and verified projections.",
            requests.AcquireRequest,
            acquisition.acquire,
            ("write", "external"),
        ),
        Operation(
            "nsqd.digests.approve",
            "Explicitly approve a reviewed projection digest.",
            requests.DigestRequest,
            acquisition.approve_digest,
            ("write", "approval"),
        ),
        Operation(
            "nsqd.digests.list",
            "List approved projection digests.",
            EmptyRequest,
            acquisition.approved_digests,
        ),
        Operation(
            "nsqd.tau.export",
            "Export persisted provenance-checked Tau measurements as JSONL.",
            requests.TauRequest,
            tau.export,
        ),
        Operation(
            "nsqd.tau.inventory",
            "Inspect Tau measurement sufficiency.",
            requests.TauRequest,
            tau.inventory,
        ),
        Operation(
            "nsqd.tau.review",
            "Run configured autonomous Tau review and write its report.",
            requests.TauRequest,
            tau.review,
            ("write", "external"),
        ),
        Operation(
            "nsqd.tau.evaluate",
            "Verify and evaluate autonomous review packets.",
            requests.TauEvaluateRequest,
            tau.evaluate,
            ("write",),
        ),
        Operation(
            "nsqd.snapshots.members",
            "Return snapshot member record identifiers.",
            requests.GetRequest,
            reads.snapshot_members,
        ),
        Operation(
            "nsqd.verdicts.get",
            "Read the verdict for a snapshot and domain policy.",
            requests.VerdictRequest,
            reads.verdict,
        ),
        Operation(
            "nsqd.elites.list",
            "List full archived elite cards.",
            requests.PageRequest,
            reads.elites,
        ),
        Operation(
            "nsqd.jobs.cancel",
            "Cancel a queued or running NSQD job.",
            requests.GetRequest,
            reads.cancel_job,
            ("write",),
        ),
    ]
    for resource, table, key in (
        ("records", "nsqd_corpus_records", "record_id"),
        ("snapshots", "nsqd_corpus_snapshots", "snapshot_id"),
        ("candidates", "nsqd_candidates", "artifact_hash"),
        ("cards", "nsqd_frontier_cards", "card_id"),
        ("cycles", "nsqd_acquisition_cycles", "cycle_id"),
        ("jobs", "nsqd_jobs", "job_id"),
    ):
        adapter = reads.ReadResource(table, key)
        result.extend(
            (
                Operation(
                    f"nsqd.{resource}.list",
                    f"List {resource} with bounded pagination.",
                    requests.PageRequest,
                    adapter.list,
                ),
                Operation(
                    f"nsqd.{resource}.get",
                    f"Get a {resource} record by identifier.",
                    requests.GetRequest,
                    adapter.get,
                ),
            )
        )
    result.append(
        Operation(
            "nsqd.verdicts.list",
            "List policy verdicts with bounded pagination.",
            requests.PageRequest,
            reads.ReadResource("nsqd_policy_verdicts", "snapshot_id, domain_policy_id").list,
        )
    )
    result.append(
        Operation(
            "nsqd.jobs.status",
            "Get a persisted NSQD job status and metadata.",
            requests.GetRequest,
            reads.ReadResource("nsqd_jobs", "job_id").get,
        )
    )
    return tuple(result)

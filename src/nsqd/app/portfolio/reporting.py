from __future__ import annotations

from dataclasses import replace

import yaml
from pydantic import JsonValue, TypeAdapter

from nsqd.app.handlers import NsqdHandlerContext
from nsqd.app.portfolio.inputs import verified_input
from nsqd.app.portfolio.validation import validate_staged
from nsqd.app.use_cases import ProjectPaperUseCase, PromoteSnapshotUseCase
from nsqd.domain.acquisition import acquisition_route
from nsqd.domain.acquisition_portfolio import (
    PortfolioError,
    StagedPortfolio,
    SufficiencyObservation,
    Target,
)
from nsqd.domain.contribution import (
    ContributionReport,
    FrozenProjectionInput,
    ProjectionContribution,
)
from nsqd.domain.policy import get_policy
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.null_adapters import FixedClock


def observe(
    ctx: NsqdHandlerContext, snapshot_id: str, policy_id: str, target: Target
) -> SufficiencyObservation:
    if ctx.verdicts is None:
        raise PortfolioError("NSQD verdict persistence is not configured")
    result = PromoteSnapshotUseCase(
        snapshots=ctx.snapshots,
        records=ctx.records,
        verdicts=ctx.verdicts,
        clock=ctx.clock,
        policies=ctx.policies,
        approved_harvest_seed_digests=ctx.approved_projection_digests,
    ).run(snapshot_id=snapshot_id, domain_policy_id=policy_id, target=target)
    return SufficiencyObservation.model_validate(
        {
            "target": target,
            "snapshot_id": snapshot_id,
            "domain_policy_id": policy_id,
            **{
                key: result[key]
                for key in (
                    "state",
                    "failures",
                    "search_context",
                )
            },
        }
    )


def project_inputs(
    ctx: NsqdHandlerContext, staged: StagedPortfolio, inputs: tuple[FrozenProjectionInput, ...]
) -> ContributionReport:
    validate_staged(staged)
    if not inputs or len(inputs) > 200:
        raise PortfolioError("A contribution report requires 1 to 200 projection inputs")
    clock = FixedClock(ctx.clock.now())
    ctx = replace(ctx, clock=clock)
    baseline = staged.plan.before
    initial_snapshot = ctx.snapshots.get(baseline.snapshot_id)
    if initial_snapshot is None:
        raise PortfolioError("Portfolio snapshot no longer exists")
    records: list[dict[str, JsonValue]] = []
    for record_id in ctx.records.list_ids():
        records.append(
            TypeAdapter(dict[str, JsonValue]).validate_python(ctx.records.get(record_id))
        )
    entries: list[ProjectionContribution] = []
    snapshot = baseline.snapshot_id
    source_bindings = {source.source_paper_id: source.target_ids for source in staged.sources}
    for ordinal, value in enumerate(inputs):
        before = observe(ctx, snapshot, baseline.domain_policy_id, baseline.target)
        source_id, digest, record_id, refusal = None, None, None, None
        targets: tuple[str, ...] = ()
        created = False
        try:
            projection = verified_input(value)
            source_id = TypeAdapter(str).validate_python(projection.get("source_paper_id"))
            if source_id not in source_bindings:
                raise PortfolioError("Approved projection is not a staged portfolio source")
            targets = source_bindings[source_id]
            digest = canonical_reviewed_projection_digest(projection)
            if acquisition_route(list(before.failures)) == "manual":
                raise PortfolioError("Manual integrity review is required before projection")
            result = ProjectPaperUseCase(
                harvest=ctx.harvest,
                records=ctx.records,
                snapshots=ctx.snapshots,
                clock=clock,
                approved_projection_digests=ctx.approved_projection_digests | {digest},
                index=ctx.index,
                embedder=ctx.embedder,
            ).run(domain_policy_id=baseline.domain_policy_id, projection=projection)
            snapshot = TypeAdapter(str).validate_python(result["snapshot_id"])
            created = TypeAdapter(bool).validate_python(result["created"])
            record_id = TypeAdapter(str).validate_python(result["record_id"])
        except (ValueError, OSError, yaml.YAMLError) as exc:
            refusal = str(exc)
        after = observe(ctx, snapshot, baseline.domain_policy_id, baseline.target)
        entries.append(
            ProjectionContribution(
                ordinal=ordinal,
                input=value,
                source_paper_id=source_id,
                target_ids=targets,
                reviewed_projection_digest=digest,
                outcome="refused" if refusal is not None else "applied",
                created=created,
                record_id=record_id,
                before=before,
                after=after,
                refusal=refusal,
            )
        )
    policy = ctx.policies.get(baseline.domain_policy_id) if ctx.policies is not None else None
    policy = policy or get_policy(baseline.domain_policy_id)
    policy = replace(policy, required_record_types=dict(policy.required_record_types))
    return ContributionReport(
        staged=staged,
        as_of=clock.now(),
        policy=policy,
        policy_manifest_available=ctx.policies is not None
        and baseline.domain_policy_id in ctx.policies,
        approved_harvest_seed_digests=ctx.approved_projection_digests,
        initial_records=tuple(records),
        initial_snapshot_members=tuple(ctx.snapshots.record_ids(baseline.snapshot_id)),
        initial_snapshot_schema_version=TypeAdapter(int).validate_python(
            initial_snapshot["schema_version"]
        ),
        entries=tuple(entries),
    )

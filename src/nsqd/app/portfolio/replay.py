from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from nsqd.app.portfolio.reporting import project_inputs
from nsqd.composition import build_container
from nsqd.domain.acquisition_portfolio import PortfolioError
from nsqd.domain.contribution import ContributionReport, ReplayResult
from nsqd.null_adapters import FixedClock, HashParaphraseEmbedder


def replay_report(report: ContributionReport) -> ReplayResult:
    """Replay manifest verification, projection, and sufficiency in disposable local stores."""
    with TemporaryDirectory(prefix="gleansight-portfolio-replay-") as directory:
        root = Path(directory)
        ctx = build_container(
            db_path=root / "replay.sqlite",
            index_path=root / "index",
            clock=FixedClock(report.as_of),
            embedder=HashParaphraseEmbedder(),
            approved_projection_digests=report.approved_harvest_seed_digests,
        ).ctx
        ctx.policies = (
            {report.policy.policy_id: report.policy} if report.policy_manifest_available else None
        )
        for record in report.initial_records:
            ctx.records.put(record)
        ctx.snapshots.commit(
            report.staged.plan.before.snapshot_id,
            list(report.initial_snapshot_members),
            schema_version=report.initial_snapshot_schema_version,
        )
        actual = project_inputs(ctx, report.staged, tuple(entry.input for entry in report.entries))
        for expected, observed in zip(report.entries, actual.entries, strict=True):
            if expected != observed:
                raise PortfolioError(
                    f"Contribution replay differs at projection {expected.ordinal}"
                )
    return ReplayResult(
        projections=len(report.entries),
        applied=sum(entry.outcome == "applied" for entry in report.entries),
        refused=sum(entry.outcome == "refused" for entry in report.entries),
        no_change=sum(entry.before == entry.after for entry in report.entries),
    )

from __future__ import annotations

from itertools import combinations

from research.catalog.models import ComparisonIssue, PairMetric, RunComparison, VerifiedRun


def compare_runs(runs: tuple[VerifiedRun, ...]) -> RunComparison:
    issues: list[ComparisonIssue] = []
    pairs: list[PairMetric] = []
    for left, right in combinations(runs, 2):
        incompatible: list[tuple[str, str]] = []
        for field in (
            "workflow",
            "classification",
            "verification",
            "source_sha256",
            "protocol_sha256",
            "split_sha256",
            "code_sha256",
            "seeds",
            "date_sha256",
            "origin_dates",
            "target_dates",
        ):
            if getattr(left, field) != getattr(right, field):
                incompatible.append((field, f"{field} differs; these runs are incomparable."))
        if not left.origin_dates or not right.origin_dates:
            incompatible.append(
                (
                    "paired_dates",
                    "Exact paired dates are unavailable; numerical comparison is refused.",
                )
            )
        left_metrics = {(metric.method, metric.seed): metric for metric in left.metrics}
        right_metrics = {(metric.method, metric.seed): metric for metric in right.metrics}
        if set(left_metrics) != set(right_metrics):
            incompatible.append(("methods", "The paired method/seed sets differ."))
        elif any(
            value.definition != right_metrics[key].definition for key, value in left_metrics.items()
        ):
            incompatible.append(("metric_definitions", "Metric definitions differ."))
        if incompatible:
            issues.extend(
                ComparisonIssue(
                    left_run_id=left.run_id, right_run_id=right.run_id, field=field, reason=reason
                )
                for field, reason in incompatible
            )
            continue
        for key, first in left_metrics.items():
            second = right_metrics[key]
            delta = (
                second.values.overall_rmse_bp - first.values.overall_rmse_bp
                if first.values is not None and second.values is not None
                else None
            )
            pairs.append(
                PairMetric(
                    left_run_id=left.run_id,
                    right_run_id=right.run_id,
                    method=first.method,
                    seed=first.seed,
                    definition=first.definition,
                    left=first.values,
                    right=second.values,
                    right_minus_left_rmse_bp=delta,
                )
            )
    return RunComparison(comparable=not issues, runs=runs, pairs=tuple(pairs), issues=tuple(issues))

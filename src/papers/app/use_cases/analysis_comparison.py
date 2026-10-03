"""Inspection and comparison use cases; no provider initialization or source writes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import unified_diff
from uuid import uuid4

from pydantic import JsonValue

from papers.app.use_cases.analysis_comparison_artifacts import (
    JSON_VALUE,
    RunRow,
    inspect_artifact,
    recorded_cost,
)
from papers.app.use_cases.analysis_comparison_fingerprints import fingerprint
from papers.domain.analysis_comparison import (
    CohortReport,
    CohortSelection,
    ExtractedValue,
    ExtractionDifference,
    PinnedComparison,
    RunComparison,
    RunInspection,
    RunPair,
    SavedCohort,
)
from papers.domain.errors import NotFoundError
from papers.infra.analysis_cohorts import AnalysisCohortStore
from papers.infra.piccolo.database import PiccoloDatabase


def _diff(baseline: str | None, revised: str | None) -> str:
    if baseline is None or revised is None:
        return "Diff unavailable: inspect the artifact errors on each run."
    return "\n".join(
        unified_diff(
            baseline.splitlines(),
            revised.splitlines(),
            fromfile="baseline",
            tofile="revised",
            lineterm="",
        )
    )


def _schema_text(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class AnalysisComparisonService:
    database: PiccoloDatabase

    def inspect(self, run_id: str) -> RunInspection:
        """Load a run's immutable identities, outputs, and run-scoped extracted fields."""
        raw = self.database.fetchone(
            "SELECT ar.*, j.status, pv.extraction_schema_json, p.md_fingerprint_xxh64 "
            "FROM analysis_runs ar LEFT JOIN jobs j ON j.run_id = ar.run_id "
            "AND j.type = 'analyze' LEFT JOIN prompt_versions pv "
            "ON pv.prompt_version_id = ar.prompt_version_id "
            "LEFT JOIN papers p ON p.paper_id = ar.paper_id WHERE ar.run_id = ?",
            [run_id],
        )
        if raw is None:
            message = f"Analysis run not found: {run_id}"
            raise NotFoundError(message)
        row = RunRow.model_validate(raw)
        extractions = self.database.fetchall(
            "SELECT entity_type, entity_ref, field_path, value_text, value_numeric, value_boolean "
            "FROM analysis_extractions WHERE run_id = ? AND paper_id = ? "
            "AND prompt_version_id = ? ORDER BY entity_type, entity_ref, field_path",
            [run_id, row.paper_id, row.prompt_version_id],
        )
        output_md = inspect_artifact(row, row.output_blob_path_md)
        cost = recorded_cost(row) if output_md.state in {"available", "empty"} else None
        return RunInspection(
            run_id=row.run_id,
            paper_id=row.paper_id,
            prompt_version_id=row.prompt_version_id,
            profile_id=row.profile_id,
            model_name=row.model_name,
            status=row.status or "unknown",
            error_message=row.error_message,
            validation_issues=JSON_VALUE.validate_json(row.validation_issues_json or "null"),
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            cost_usd=cost,
            cost_status="recorded" if cost is not None else "unknown",
            extraction_schema=JSON_VALUE.validate_json(row.extraction_schema_json or "null"),
            output_md=output_md,
            output_json=inspect_artifact(row, row.output_blob_path_json),
            extractions=tuple(ExtractedValue.model_validate(item) for item in extractions),
        )

    def compare(self, pair: RunPair) -> RunComparison:
        baseline = self.inspect(pair.baseline_run_id)
        revised = self.inspect(pair.revised_run_id)
        if baseline.paper_id != revised.paper_id:
            message = "Comparison requires two runs for the same paper."
            raise ValueError(message)
        left = {item.identity: item for item in baseline.extractions}
        right = {item.identity: item for item in revised.extractions}
        differences: list[ExtractionDifference] = []
        for identity in sorted(
            left.keys() | right.keys(), key=lambda key: (key[0], key[1] or "", key[2])
        ):
            before, after = left.get(identity), right.get(identity)
            change = (
                "missing_baseline"
                if before is None
                else "missing_revised"
                if after is None
                else "unchanged"
                if before == after
                else "changed"
            )
            differences.append(
                ExtractionDifference(
                    entity_type=identity[0],
                    entity_ref=identity[1],
                    field_path=identity[2],
                    change=change,
                    baseline=before,
                    revised=after,
                )
            )
        return RunComparison(
            baseline=baseline,
            revised=revised,
            schema_changed=baseline.extraction_schema != revised.extraction_schema,
            schema_diff=_diff(
                _schema_text(baseline.extraction_schema), _schema_text(revised.extraction_schema)
            ),
            output_diff=_diff(baseline.output_md.text, revised.output_md.text),
            json_output_diff=_diff(baseline.output_json.text, revised.output_json.text),
            extraction_diff=tuple(differences),
        )

    def save_cohort(self, selection: CohortSelection) -> SavedCohort:
        """Pin explicitly chosen completed runs; never reanalyze or change accepted outputs."""
        if selection.baseline_prompt_version_id == selection.revised_prompt_version_id:
            message = "A prompt revision cohort requires distinct prompt versions."
            raise ValueError(message)
        pins: list[PinnedComparison] = []
        seen: set[str] = set()
        for pair in selection.pairs:
            comparison = self.compare(pair)
            left, right = comparison.baseline, comparison.revised
            if (left.prompt_version_id, right.prompt_version_id) != (
                selection.baseline_prompt_version_id,
                selection.revised_prompt_version_id,
            ):
                message = "Cohort runs do not match the selected prompt versions."
                raise ValueError(message)
            if left.status != "succeeded" or right.status not in {"succeeded", "failed"}:
                message = "Cohorts require a successful baseline and completed revised run."
                raise ValueError(message)
            if left.paper_id in seen:
                message = "Choose exactly one run pair for each cohort paper."
                raise ValueError(message)
            if (
                selection.project_id is not None
                and self.database.fetchone(
                    "SELECT paper_id FROM paper_projects WHERE paper_id = ? AND project_id = ?",
                    [left.paper_id, selection.project_id],
                )
                is None
            ):
                message = "Cohort paper is outside the selected project."
                raise ValueError(message)
            self._require_artifacts(comparison)
            pins.append(
                PinnedComparison(
                    pair=pair,
                    paper_id=left.paper_id,
                    baseline_sha256=fingerprint(left, 2),
                    revised_sha256=fingerprint(right, 2),
                )
            )
            seen.add(left.paper_id)
        cohort = SavedCohort(
            cohort_id=str(uuid4()),
            created_at=datetime.now(UTC).isoformat(),
            selection=selection,
            runs=tuple(pins),
            fingerprint_version=2,
        )
        AnalysisCohortStore(self.database).save(cohort)
        return cohort

    def compare_cohort(self, cohort_id: str) -> CohortReport:
        cohort = AnalysisCohortStore(self.database).get(cohort_id)
        comparisons: list[RunComparison] = []
        for pin in cohort.runs:
            comparison = self.compare(pin.pair)
            if (
                fingerprint(comparison.baseline, cohort.fingerprint_version),
                fingerprint(comparison.revised, cohort.fingerprint_version),
            ) != (
                pin.baseline_sha256,
                pin.revised_sha256,
            ):
                message = f"Saved cohort source has changed: {pin.paper_id}"
                if cohort.fingerprint_version == 1:
                    message += (
                        ". Legacy cohort fingerprints include storage paths. "
                        "Re-save the cohort in its original workspace before backup."
                    )
                raise ValueError(message)
            comparisons.append(comparison)
        return CohortReport(cohort=cohort, comparisons=tuple(comparisons))

    @staticmethod
    def _require_artifacts(comparison: RunComparison) -> None:
        for run in (comparison.baseline, comparison.revised):
            if run.status == "succeeded" and run.output_md.state == "absent":
                message = f"Cannot pin successful run without its stored output: {run.run_id}"
                raise ValueError(message)
            for artifact in (run.output_md, run.output_json):
                if artifact.state == "unavailable":
                    message = f"Cannot pin unavailable output for {run.run_id}: {artifact.error}"
                    raise ValueError(message)

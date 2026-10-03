"""Provider-free public analysis inspection and saved cohort operations."""

from __future__ import annotations

from pydantic import JsonValue

from gleansight.api.models import EmptyRequest, Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.papers.common import RunId
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.analysis_comparison import AnalysisComparisonService
from papers.domain.analysis_comparison import CohortSelection, RunPair
from papers.infra.analysis_cohorts import AnalysisCohortStore


class CompareRuns(Request):
    baseline_run_id: Identifier
    revised_run_id: Identifier


class SaveCohort(Request):
    selection: CohortSelection


class CohortId(Request):
    cohort_id: Identifier


def inspect(runtime: ApiRuntime, request: RunId) -> JsonValue:
    result = AnalysisComparisonService(runtime.paper_database).inspect(request.run_id)
    return json_result(result.model_dump(mode="json"))


def compare(runtime: ApiRuntime, request: CompareRuns) -> JsonValue:
    pair = RunPair(baseline_run_id=request.baseline_run_id, revised_run_id=request.revised_run_id)
    result = AnalysisComparisonService(runtime.paper_database).compare(pair)
    return json_result(result.model_dump(mode="json"))


def save_cohort(runtime: ApiRuntime, request: SaveCohort) -> JsonValue:
    result = AnalysisComparisonService(runtime.paper_database).save_cohort(request.selection)
    return json_result(result.model_dump(mode="json"))


def get_cohort(runtime: ApiRuntime, request: CohortId) -> JsonValue:
    result = AnalysisCohortStore(runtime.paper_database).get(request.cohort_id)
    return json_result(result.model_dump(mode="json"))


def compare_cohort(runtime: ApiRuntime, request: CohortId) -> JsonValue:
    result = AnalysisComparisonService(runtime.paper_database).compare_cohort(request.cohort_id)
    return json_result(result.model_dump(mode="json"))


def list_cohorts(runtime: ApiRuntime, request: EmptyRequest) -> JsonValue:
    cohorts = AnalysisCohortStore(runtime.paper_database).list()
    return json_result([cohort.model_dump(mode="json") for cohort in cohorts])


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.analysis.cohorts.list",
            "List the latest 100 saved evaluation cohorts.",
            EmptyRequest,
            list_cohorts,
        ),
        Operation(
            "papers.analysis.inspect", "Open stored outputs and validation details.", RunId, inspect
        ),
        Operation(
            "papers.analysis.compare",
            "Compare exact runs for one paper without quality rankings.",
            CompareRuns,
            compare,
        ),
        Operation(
            "papers.analysis.cohorts.save",
            "Save exact baseline/revision run IDs and source fingerprints.",
            SaveCohort,
            save_cohort,
            ("write",),
        ),
        Operation(
            "papers.analysis.cohorts.get",
            "Retrieve a saved evaluation cohort.",
            CohortId,
            get_cohort,
        ),
        Operation(
            "papers.analysis.cohorts.compare",
            "Verify and compare every saved cohort run pair.",
            CohortId,
            compare_cohort,
        ),
    )

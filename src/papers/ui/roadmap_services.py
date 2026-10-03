from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from pydantic import JsonValue, TypeAdapter

from papers.app.composition_root import AppContainer
from papers.app.use_cases.analysis_comparison import AnalysisComparisonService
from papers.app.use_cases.citation_exports import ExportPapersUseCase
from papers.domain.analysis_comparison import (
    CohortReport,
    CohortSelection,
    RunComparison,
    RunInspection,
    RunPair,
    SavedCohort,
)
from papers.infra.analysis_cohorts import AnalysisCohortStore


class RoadmapServices(TypedDict):
    export_papers: ExportPapersUseCase
    inspect_analysis: Callable[[str], RunInspection]
    compare_analysis: Callable[[str, str], RunComparison]
    save_analysis_cohort: Callable[[CohortSelection], SavedCohort]
    compare_analysis_cohort: Callable[[str], CohortReport]
    list_analysis_cohorts: Callable[[], tuple[SavedCohort, ...]]
    list_projects: Callable[[], list[dict[str, JsonValue]]]


def build_roadmap_services(base: AppContainer, *, repo_root: Path) -> RoadmapServices:
    comparison = AnalysisComparisonService(base.db)
    cohorts = AnalysisCohortStore(base.db)

    def compare(baseline_run_id: str, revised_run_id: str) -> RunComparison:
        return comparison.compare(
            RunPair(baseline_run_id=baseline_run_id, revised_run_id=revised_run_id)
        )

    def projects() -> list[dict[str, JsonValue]]:
        rows = base.db.fetchall("SELECT project_id, name FROM projects ORDER BY name, project_id")
        return TypeAdapter(list[dict[str, JsonValue]]).validate_python(rows)

    return RoadmapServices(
        export_papers=ExportPapersUseCase(base.db, repo_root / "output" / "exports"),
        inspect_analysis=comparison.inspect,
        compare_analysis=compare,
        save_analysis_cohort=comparison.save_cohort,
        compare_analysis_cohort=comparison.compare_cohort,
        list_analysis_cohorts=cohorts.list,
        list_projects=projects,
    )

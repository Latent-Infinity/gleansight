"""Public registry operations for immutable paper exports."""

from pathlib import Path

from pydantic import JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.citation_exports import ExportPapersUseCase, verify_export
from papers.domain.citations import ExportFormat, ExportSelection


class CreateExport(Request):
    paper_ids: tuple[Identifier, ...] = ()
    project_id: Identifier | None = None
    format: ExportFormat = "bibtex"


class VerifyExport(Request):
    manifest_path: Path


def create(runtime: ApiRuntime, request: CreateExport) -> JsonValue:
    result = ExportPapersUseCase(
        runtime.paper_database, runtime.repo_root / "output" / "exports"
    ).execute(ExportSelection.model_validate(request.model_dump()))
    return json_result(
        {"manifest_path": result.manifest_path, "artifact_path": result.artifact_path}
    )


def verify(runtime: ApiRuntime, request: VerifyExport) -> JsonValue:
    verify_export(runtime.resolve(request.manifest_path))
    return {"valid": True}


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.exports.create",
            "Export selected papers or a project with provenance.",
            CreateExport,
            create,
            ("write",),
        ),
        Operation(
            "papers.exports.verify",
            "Verify an exported artifact and its manifest.",
            VerifyExport,
            verify,
        ),
    )

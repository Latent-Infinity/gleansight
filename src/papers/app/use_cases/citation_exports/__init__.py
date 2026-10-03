"""Create immutable local exports without provider access."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from papers.app.use_cases.citation_exports.snapshot import artifact_identity, read_snapshot
from papers.domain.citations import ExportManifest, ExportSelection
from papers.domain.citations_format import render
from papers.domain.errors import ValidationError
from papers.infra.piccolo.database import PiccoloDatabase


@dataclass(frozen=True, slots=True)
class ExportResult:
    manifest_path: Path
    artifact_path: Path


@dataclass(frozen=True, slots=True)
class ExportPapersUseCase:
    database: PiccoloDatabase
    output_root: Path

    def execute(self, selection: ExportSelection) -> ExportResult:
        papers, runs, extractions = read_snapshot(self.database.path.resolve(), selection)
        content, suffix = render(papers, selection.format, extractions)
        now = datetime.now(UTC)
        export_id = now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
        directory = self.output_root.resolve() / export_id
        directory.mkdir(parents=True, exist_ok=False)
        artifact = directory / f"export.{suffix}"
        with artifact.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)
        manifest = ExportManifest(
            export_id=export_id,
            created_at=now.isoformat(),
            selection=selection,
            paper_ids=tuple(paper.paper_id for paper in papers),
            papers=papers,
            runs=runs,
            missing_fields={paper.paper_id: paper.missing_fields for paper in papers},
            artifact=artifact_identity(artifact),
        )
        manifest_path = directory / "manifest.json"
        serialized = manifest.model_dump_json(indent=2) + "\n"
        with manifest_path.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
        with (directory / "manifest.sha256").open("x", encoding="ascii") as handle:
            handle.write(hashlib.sha256(serialized.encode("utf-8")).hexdigest() + "\n")
        return ExportResult(manifest_path, artifact)


def verify_export(manifest_path: Path) -> None:
    content = manifest_path.read_bytes()
    expected = manifest_path.with_suffix(".sha256").read_text(encoding="ascii").strip()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValidationError("Export manifest digest mismatch.")
    manifest = ExportManifest.model_validate_json(content)
    artifact = Path(manifest.artifact.path)
    if artifact.parent.resolve() != manifest_path.parent.resolve():
        raise ValidationError("Export artifact must be beside its manifest.")
    actual = artifact_identity(artifact)
    if actual.status != "available" or actual.sha256 != manifest.artifact.sha256:
        raise ValidationError("Export artifact is missing or its digest has changed.")

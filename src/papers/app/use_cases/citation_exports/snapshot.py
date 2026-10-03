"""Read typed citation records from one consistent SQLite snapshot."""

import hashlib
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from papers.domain.citations import (
    ArtifactIdentity,
    Citation,
    ExportSelection,
    ExtractionRow,
    RunIdentity,
)
from papers.domain.errors import NotFoundError, ValidationError


class PaperRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    paper_id: str
    title: str
    authors_json: str
    year: int | None
    venue: str | None
    md_fingerprint_xxh64: str | None


class StoredExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    extraction_id: str
    paper_id: str
    run_id: str
    prompt_version_id: str
    entity_type: str
    entity_ref: str | None
    field_path: str
    value_text: str | None
    value_numeric: Decimal | None
    value_boolean: int | None

    def exported(self) -> ExtractionRow:
        value = self.value_text
        numeric = self.value_numeric
        boolean = self.value_boolean
        return ExtractionRow(
            **self.model_dump(exclude={"value_text", "value_numeric", "value_boolean"}),
            value=value
            if value is not None
            else (
                float(numeric)
                if numeric is not None
                else bool(boolean)
                if boolean is not None
                else None
            ),
        )


def artifact_identity(path: Path) -> ArtifactIdentity:
    available = path.is_file()
    return ArtifactIdentity(
        path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest() if available else None,
        status="available" if available else "missing",
    )


def read_snapshot(
    database_path: Path, selection: ExportSelection
) -> tuple[tuple[Citation, ...], tuple[RunIdentity, ...], tuple[ExtractionRow, ...]]:
    papers: list[Citation] = []
    runs: list[RunIdentity] = []
    extractions: list[ExtractionRow] = []
    with closing(sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        ids = tuple(dict.fromkeys(selection.paper_ids))
        if selection.project_id:
            project = connection.execute(
                "SELECT 1 FROM projects WHERE project_id = ?", (selection.project_id,)
            ).fetchone()
            if project is None:
                raise NotFoundError(f"Project {selection.project_id} does not exist.")
            ids = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT paper_id FROM paper_projects WHERE project_id = ? ORDER BY paper_id",
                    (selection.project_id,),
                )
            )
        if not ids:
            raise ValidationError("The export selection contains no papers.")
        for paper_id in ids:
            row = connection.execute(
                "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Paper {paper_id} does not exist.")
            paper = PaperRecord.model_validate(dict(row))
            external_ids = TypeAdapter(dict[str, str]).validate_python(
                dict(
                    connection.execute(
                        "SELECT kind, value FROM paper_external_ids "
                        "WHERE paper_id = ? ORDER BY kind",
                        (paper_id,),
                    )
                )
            )
            doi = next(
                (value for kind, value in external_ids.items() if kind.casefold() == "doi"), None
            )
            papers.append(
                Citation(
                    **paper.model_dump(exclude={"authors_json"}),
                    authors=TypeAdapter(tuple[str, ...]).validate_json(paper.authors_json),
                    doi=doi,
                    external_ids=external_ids,
                )
            )
            for run_row in connection.execute(
                "SELECT run_id, paper_id, prompt_version_id, model_name, output_blob_path_md, "
                "output_blob_path_json FROM analysis_runs WHERE paper_id = ? ORDER BY run_id",
                (paper_id,),
            ):
                run = RunIdentity.model_validate(dict(run_row))
                artifacts = tuple(
                    artifact_identity(Path(path))
                    for path in (run.output_blob_path_md, run.output_blob_path_json)
                    if path
                )
                runs.append(run.model_copy(update={"artifacts": artifacts}))
            for extraction in connection.execute(
                "SELECT * FROM analysis_extractions WHERE paper_id = ? "
                "ORDER BY run_id, extraction_id",
                (paper_id,),
            ):
                extractions.append(StoredExtraction.model_validate(dict(extraction)).exported())
    return tuple(papers), tuple(runs), tuple(extractions)

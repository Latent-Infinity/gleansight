from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from piccolo.engine.sqlite import TransactionType
from piccolo.querystring import QueryString
from piccolo.utils.sync import run_sync

from papers.app import ports
from papers.domain.errors import NotFoundError
from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.piccolo.fts import literal_fts_query
from papers.infra.piccolo.tables import (
    AnalysisExtraction,
    AnalysisRun,
    Candidate,
    EndpointProfile,
    Job,
    Paper,
    PaperExternalId,
    PaperProject,
    PaperTag,
    Project,
    Prompt,
    PromptVersion,
    Tag,
)


@dataclass(frozen=True)
class JobRow:
    job_id: str
    type: str
    status: str
    paper_id: str | None
    run_id: str | None
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    run_after: datetime | None


def _stage_rank(stage: PipelineStage) -> int:
    order = [
        PipelineStage.imported,
        PipelineStage.downloaded,
        PipelineStage.converted,
        PipelineStage.embedded,
        PipelineStage.analyzed,
    ]
    return order.index(stage)


_EXTRACTION_CONSTRAINT_COLUMNS: dict[str, str] = {
    "value_text": "ae.value_text",
    "value_numeric": "ae.value_numeric",
    "value_boolean": "ae.value_boolean",
    "entity_type": "ae.entity_type",
    "entity_ref": "ae.entity_ref",
    "paper_id": "ae.paper_id",
    "run_id": "ae.run_id",
}

_EXTRACTION_GROUP_BY_COLUMNS: dict[str, str] = {
    "value_text": "value_text",
    "value_numeric": "value_numeric",
    "value_boolean": "value_boolean",
    "paper_id": "paper_id",
    "run_id": "run_id",
    "prompt_version_id": "prompt_version_id",
    "entity_type": "entity_type",
    "entity_ref": "entity_ref",
}


class PiccoloCandidateStore:
    """Store for candidate papers discovered from external sources."""

    def create_candidate(self, fields: dict[str, Any]) -> str:
        candidate_id = fields["candidate_id"]
        now = datetime.now(UTC)
        created_at = fields.get("created_at", now)
        updated_at = fields.get("updated_at", now)
        source = fields["source"]
        source_paper_id = fields["source_paper_id"]
        run_sync(
            Candidate._meta.db.run_querystring(
                QueryString(
                    """
                    INSERT INTO candidates(
                        candidate_id,
                        source,
                        source_paper_id,
                        title,
                        year,
                        venue,
                        authors_json,
                        abstract,
                        external_ids_json,
                        rejected_at,
                        imported_paper_id,
                        imported_at,
                        created_at,
                        updated_at
                    ) VALUES({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})
                    ON CONFLICT(source, source_paper_id) DO UPDATE SET
                        title=excluded.title,
                        year=excluded.year,
                        venue=excluded.venue,
                        authors_json=excluded.authors_json,
                        abstract=excluded.abstract,
                        external_ids_json=excluded.external_ids_json,
                        updated_at=excluded.updated_at
                    """,
                    candidate_id,
                    source,
                    source_paper_id,
                    fields["title"],
                    fields.get("year"),
                    fields.get("venue"),
                    fields.get("authors_json", "[]"),
                    fields.get("abstract"),
                    fields.get("external_ids_json"),
                    fields.get("rejected_at"),
                    fields.get("imported_paper_id"),
                    fields.get("imported_at"),
                    created_at,
                    updated_at,
                )
            )
        )
        row = (
            Candidate.select(Candidate.candidate_id)
            .where(Candidate.source == source)
            .where(Candidate.source_paper_id == source_paper_id)
            .first()
            .run_sync()
        )
        if row is None:
            return candidate_id
        return row["candidate_id"]

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = Candidate.select().where(Candidate.candidate_id == candidate_id).first().run_sync()
        if row is None:
            return None
        return dict(row)

    def get_candidate_by_source(self, source: str, source_paper_id: str) -> dict[str, Any] | None:
        row = (
            Candidate.select()
            .where(Candidate.source == source)
            .where(Candidate.source_paper_id == source_paper_id)
            .first()
            .run_sync()
        )
        if row is None:
            return None
        return dict(row)

    def list_candidates(
        self,
        imported: bool | None = None,
        rejected: bool | None = None,
    ) -> list[dict[str, Any]]:
        query = Candidate.select()

        if imported is False:
            query = query.where(Candidate.imported_at.is_null())
        elif imported is True:
            query = query.where(Candidate.imported_at.is_not_null())

        if rejected is False:
            query = query.where(Candidate.rejected_at.is_null())
        elif rejected is True:
            query = query.where(Candidate.rejected_at.is_not_null())

        rows = query.run_sync()
        return [dict(row) for row in rows]

    def mark_imported(self, candidate_id: str, paper_id: str) -> None:
        (
            Candidate.update(
                {
                    Candidate.imported_paper_id: paper_id,
                    Candidate.imported_at: datetime.now(UTC),
                    Candidate.updated_at: datetime.now(UTC),
                }
            )
            .where(Candidate.candidate_id == candidate_id)
            .run_sync()
        )

    def mark_rejected(self, candidate_id: str) -> None:
        (
            Candidate.update(
                {
                    Candidate.rejected_at: datetime.now(UTC),
                    Candidate.updated_at: datetime.now(UTC),
                }
            )
            .where(Candidate.candidate_id == candidate_id)
            .where(Candidate.rejected_at.is_null())  # Only update if not already rejected
            .run_sync()
        )


class PiccoloCandidateImporter:
    """Atomically import a candidate, its identifiers, and its download job."""

    def import_candidate(self, candidate_id: str) -> str:
        async def import_in_transaction() -> str:
            database = Candidate._meta.db
            async with database.transaction(transaction_type=TransactionType.immediate):
                candidate = await (
                    Candidate.select().where(Candidate.candidate_id == candidate_id).first().run()
                )
                if candidate is None:
                    raise NotFoundError(f"candidate not found: {candidate_id}")
                if candidate["rejected_at"] is not None:
                    raise ValueError("cannot import candidate that was already rejected")
                if imported_paper_id := candidate["imported_paper_id"]:
                    return imported_paper_id

                try:
                    authors = json.loads(candidate["authors_json"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    authors = []
                try:
                    parsed_external_ids = json.loads(candidate["external_ids_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    parsed_external_ids = {}
                external_ids = {
                    str(kind): str(value)
                    for kind, value in parsed_external_ids.items()
                    if value is not None
                }

                paper_id = str(uuid.uuid4())
                await (
                    Paper(
                        _data={
                            Paper.paper_id: paper_id,
                            Paper.title: candidate["title"],
                            Paper.year: candidate["year"],
                            Paper.venue: candidate["venue"],
                            Paper.authors_json: json.dumps(authors),
                            Paper.abstract: candidate["abstract"],
                            Paper.pipeline_stage: str(PipelineStage.imported),
                            Paper.pipeline_health: str(PipelineHealth.ok),
                        }
                    )
                    .save()
                    .run()
                )
                await database.run_querystring(
                    QueryString(
                        "INSERT INTO papers_fts(title, abstract, paper_id) VALUES({}, {}, {})",
                        candidate["title"],
                        candidate["abstract"] or "",
                        paper_id,
                    )
                )

                for kind, value in external_ids.items():
                    await (
                        PaperExternalId(
                            _data={
                                PaperExternalId.paper_external_id_id: str(uuid.uuid4()),
                                PaperExternalId.paper_id: paper_id,
                                PaperExternalId.kind: kind,
                                PaperExternalId.value: value,
                            }
                        )
                        .save()
                        .run()
                    )

                await (
                    Job(
                        _data={
                            Job.job_id: str(uuid.uuid4()),
                            Job.type: "download",
                            Job.status: "queued",
                            Job.paper_id: paper_id,
                            Job.run_id: None,
                            Job.payload_json: json.dumps(
                                {"external_ids": external_ids} if external_ids else {}
                            ),
                            Job.attempts: 0,
                            Job.max_attempts: 3,
                            Job.run_after: None,
                        }
                    )
                    .save()
                    .run()
                )
                now = datetime.now(UTC)
                await (
                    Candidate.update(
                        {
                            Candidate.imported_paper_id: paper_id,
                            Candidate.imported_at: now,
                            Candidate.updated_at: now,
                        }
                    )
                    .where(Candidate.candidate_id == candidate_id)
                    .run()
                )
                return paper_id

        return run_sync(import_in_transaction())


class PiccoloPaperStore(ports.PaperStore):
    def create_paper(self, fields: dict[str, Any]) -> str:
        paper_id = fields["paper_id"]
        title = fields["title"]
        abstract = fields.get("abstract")
        payload = {
            Paper.paper_id: paper_id,
            Paper.title: title,
            Paper.year: fields.get("year"),
            Paper.venue: fields.get("venue"),
            Paper.authors_json: json.dumps(fields.get("authors", [])),
            Paper.abstract: abstract,
            Paper.pipeline_stage: str(fields.get("pipeline_stage", PipelineStage.imported)),
            Paper.pipeline_health: str(fields.get("pipeline_health", PipelineHealth.ok)),
        }
        Paper(_data=payload).save().run_sync()
        self._upsert_paper_fts(paper_id=paper_id, title=title, abstract=abstract)
        return paper_id

    def get(self, paper_id: str) -> dict[str, Any] | None:
        row = Paper.select().where(Paper.paper_id == paper_id).first().run_sync()
        if row is None:
            return None
        data = dict(row)
        data["authors"] = json.loads(data.get("authors_json") or "[]")
        return data

    def update_metadata(self, paper_id: str, fields: dict[str, Any]) -> None:
        if not fields:
            return
        updates = dict(fields)
        if "authors" in updates:
            updates["authors_json"] = json.dumps(updates.pop("authors"))
        updates["updated_at"] = datetime.now(UTC)
        Paper.update(updates).where(Paper.paper_id == paper_id).run_sync()
        refreshed = (
            Paper.select(Paper.title, Paper.abstract)
            .where(Paper.paper_id == paper_id)
            .first()
            .run_sync()
        )
        if refreshed is not None:
            self._upsert_paper_fts(
                paper_id=paper_id,
                title=refreshed["title"],
                abstract=refreshed.get("abstract"),
            )

    def set_pdf_fingerprint(self, paper_id: str, pdf_xxh64: str) -> None:
        Paper.update({"pdf_fingerprint_xxh64": pdf_xxh64, "updated_at": datetime.now(UTC)}).where(
            Paper.paper_id == paper_id
        ).run_sync()

    def set_markdown_provenance(
        self,
        paper_id: str,
        md_xxh64: str,
        src_pdf_xxh64: str,
        converter: str,
        converter_version: str,
    ) -> None:
        Paper.update(
            {
                "md_fingerprint_xxh64": md_xxh64,
                "md_source_pdf_fingerprint_xxh64": src_pdf_xxh64,
                "md_converter": converter,
                "md_converter_version": converter_version,
                "updated_at": datetime.now(UTC),
            }
        ).where(Paper.paper_id == paper_id).run_sync()

    def set_embedding_state(
        self,
        paper_id: str,
        embedding_model: str,
        embedding_dimension: int,
        text_slice_strategy: str,
        embedded_from_md_xxh64: str,
    ) -> None:
        Paper.update(
            {
                "embedding_model": embedding_model,
                "embedding_dimension": embedding_dimension,
                "text_slice_strategy": text_slice_strategy,
                "embedded_from_md_fingerprint_xxh64": embedded_from_md_xxh64,
                "updated_at": datetime.now(UTC),
            }
        ).where(Paper.paper_id == paper_id).run_sync()

    def advance_pipeline_stage_monotonic(self, paper_id: str, new_stage: str) -> None:
        row = (
            Paper.select(Paper.pipeline_stage).where(Paper.paper_id == paper_id).first().run_sync()
        )
        if row is None:
            raise NotFoundError(f"paper not found: {paper_id}")
        current = PipelineStage(row["pipeline_stage"])
        if _stage_rank(PipelineStage(new_stage)) < _stage_rank(current):
            return  # already past this stage; monotonic means no regression, not an error
        Paper.update({"pipeline_stage": str(new_stage), "updated_at": datetime.now(UTC)}).where(
            Paper.paper_id == paper_id
        ).run_sync()

    def set_pipeline_health_error(
        self,
        paper_id: str,
        error_code: str,
        message: str,
        job_id: str | None,
    ) -> None:
        Paper.update(
            {
                "pipeline_health": str(PipelineHealth.error),
                "last_error_job_id": job_id,
                "last_error_code": error_code,
                "last_error_message": message,
                "last_error_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ).where(Paper.paper_id == paper_id).run_sync()

    def clear_pipeline_health_if_recovered(self, paper_id: str, job_type: str) -> None:
        if job_type not in {"download", "convert", "embed"}:
            return
        Paper.update(
            {
                "pipeline_health": str(PipelineHealth.ok),
                "last_error_job_id": None,
                "last_error_code": None,
                "last_error_message": None,
                "last_error_at": None,
                "updated_at": datetime.now(UTC),
            }
        ).where(Paper.paper_id == paper_id).run_sync()

    def list_papers_with_markdown(self) -> list[str]:
        rows = (
            Paper.select(Paper.paper_id).where(Paper.md_fingerprint_xxh64.is_not_null()).run_sync()
        )
        return [row["paper_id"] for row in rows]

    def delete_paper(self, paper_id: str) -> None:
        run_sync(
            Paper._meta.db.run_querystring(
                QueryString("DELETE FROM papers_fts WHERE paper_id = {}", paper_id)
            )
        )
        run_sync(
            Paper._meta.db.run_querystring(
                QueryString("DELETE FROM extractions_fts WHERE paper_id = {}", paper_id)
            )
        )
        Job.delete().where(Job.paper_id == paper_id).run_sync()
        PaperExternalId.delete().where(PaperExternalId.paper_id == paper_id).run_sync()
        PaperTag.delete().where(PaperTag.paper_id == paper_id).run_sync()
        PaperProject.delete().where(PaperProject.paper_id == paper_id).run_sync()
        AnalysisExtraction.delete().where(AnalysisExtraction.paper_id == paper_id).run_sync()
        AnalysisRun.delete().where(AnalysisRun.paper_id == paper_id).run_sync()
        Paper.delete().where(Paper.paper_id == paper_id).run_sync()

    def reset_pipeline_stage(self, paper_id: str, stage: str) -> None:
        Paper.update(
            {
                "pipeline_stage": str(stage),
                "pipeline_health": str(PipelineHealth.ok),
                "last_error_code": None,
                "last_error_message": None,
                "last_error_job_id": None,
                "last_error_at": None,
                "updated_at": datetime.now(UTC),
            }
        ).where(Paper.paper_id == paper_id).run_sync()

    def _upsert_paper_fts(self, *, paper_id: str, title: str, abstract: str | None) -> None:
        run_sync(
            Paper._meta.db.run_querystring(
                QueryString("DELETE FROM papers_fts WHERE paper_id = {}", paper_id)
            )
        )
        run_sync(
            Paper._meta.db.run_querystring(
                QueryString(
                    "INSERT INTO papers_fts(title, abstract, paper_id) VALUES({}, {}, {})",
                    title,
                    abstract or "",
                    paper_id,
                )
            )
        )


class PiccoloExtractionStore(ports.ExtractionStore):
    def upsert_extractions(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        extractions: list[ports.Extraction],
    ) -> None:
        rows = [
            {
                AnalysisExtraction.extraction_id: str(uuid.uuid4()),
                AnalysisExtraction.run_id: run_id,
                AnalysisExtraction.paper_id: paper_id,
                AnalysisExtraction.prompt_version_id: prompt_version_id,
                AnalysisExtraction.entity_type: extraction.entity_type,
                AnalysisExtraction.entity_ref: extraction.entity_ref,
                AnalysisExtraction.field_path: extraction.field_path,
                AnalysisExtraction.value_text: extraction.value_text,
                AnalysisExtraction.value_numeric: extraction.value_numeric,
                AnalysisExtraction.value_boolean: extraction.value_boolean,
            }
            for extraction in extractions
        ]
        instances = [AnalysisExtraction(_data=row) for row in rows]

        async def replace_rows() -> None:
            database = AnalysisExtraction._meta.db
            async with database.transaction():
                await database.run_querystring(
                    QueryString(
                        "DELETE FROM extractions_fts "
                        "WHERE paper_id = {} AND prompt_version_id = {}",
                        paper_id,
                        prompt_version_id,
                    )
                )
                await AnalysisExtraction.delete().where(AnalysisExtraction.run_id == run_id).run()
                if instances:
                    await AnalysisExtraction.insert(*instances).run()

                text_rows = await (
                    AnalysisExtraction.select(
                        AnalysisExtraction.value_text,
                        AnalysisExtraction.paper_id,
                        AnalysisExtraction.prompt_version_id,
                        AnalysisExtraction.entity_type,
                        AnalysisExtraction.entity_ref,
                        AnalysisExtraction.field_path,
                    )
                    .where(AnalysisExtraction.paper_id == paper_id)
                    .where(AnalysisExtraction.prompt_version_id == prompt_version_id)
                    .where(AnalysisExtraction.value_text.is_not_null())
                    .run()
                )
                for text_row in text_rows:
                    await database.run_querystring(
                        QueryString(
                            """
                            INSERT INTO extractions_fts(
                                value_text,
                                paper_id,
                                prompt_version_id,
                                entity_type,
                                entity_ref,
                                field_path
                            ) VALUES({}, {}, {}, {}, {}, {})
                            """,
                            text_row["value_text"],
                            text_row["paper_id"],
                            text_row["prompt_version_id"],
                            text_row["entity_type"],
                            text_row["entity_ref"],
                            text_row["field_path"],
                        )
                    )

        run_sync(replace_rows())

    def list_by_paper(
        self,
        paper_id: str,
        prompt_version_id: str | None = None,
        successful_only: bool = True,
    ) -> list[ports.Extraction]:
        query = AnalysisExtraction.select().where(AnalysisExtraction.paper_id == paper_id)
        if prompt_version_id:
            query = query.where(AnalysisExtraction.prompt_version_id == prompt_version_id)
        rows = query.run_sync()

        if successful_only:
            run_ids = {row["run_id"] for row in rows}
            if run_ids:
                succeeded_rows = (
                    Job.select(Job.run_id)
                    .where(Job.type == "analyze")
                    .where(Job.status == "succeeded")
                    .where(Job.run_id.is_in(list(run_ids)))
                    .run_sync()
                )
                succeeded_run_ids = {row["run_id"] for row in succeeded_rows}
                rows = [row for row in rows if row["run_id"] in succeeded_run_ids]

        return [
            _RowExtraction(
                entity_type=row["entity_type"],
                entity_ref=row["entity_ref"],
                field_path=row["field_path"],
                value_text=row["value_text"],
                value_numeric=row["value_numeric"],
                value_boolean=row["value_boolean"],
            )
            for row in rows
        ]

    def query(
        self,
        field_path: str,
        *,
        prompt_version_id: str,
        constraints: dict[str, Any],
        latest_only: bool = True,
    ) -> list[str]:
        for key in constraints:
            if key not in _EXTRACTION_CONSTRAINT_COLUMNS:
                raise ValueError(f"unsupported extraction constraint field: {key}")

        if not latest_only:
            # Simple query without run selection
            query = (
                AnalysisExtraction.select(AnalysisExtraction.paper_id)
                .where(AnalysisExtraction.field_path == field_path)
                .where(AnalysisExtraction.prompt_version_id == prompt_version_id)
            )
            for key, value in constraints.items():
                query = query.where(getattr(AnalysisExtraction, key) == value)
            rows = query.run_sync()
            return [row["paper_id"] for row in rows]

        # Query with latest successful run filtering
        from piccolo.querystring import QueryString

        constraint_sql = ""
        params = [field_path, prompt_version_id]
        for key, value in constraints.items():
            constraint_sql += f" AND {_EXTRACTION_CONSTRAINT_COLUMNS[key]} = {{}}"
            params.append(value)

        sql = f"""
            SELECT DISTINCT ae.paper_id
            FROM analysis_extractions ae
            WHERE ae.field_path = {{}}
              AND ae.prompt_version_id = {{}}
              {constraint_sql}
              AND ae.run_id IN (
                SELECT ar.run_id
                FROM analysis_runs ar
                JOIN jobs j ON j.run_id = ar.run_id
                WHERE j.type = 'analyze'
                  AND j.status = 'succeeded'
                  AND ar.prompt_version_id = {{}}
                  AND ar.created_at = (
                    SELECT MAX(ar2.created_at)
                    FROM analysis_runs ar2
                    JOIN jobs j2 ON j2.run_id = ar2.run_id
                    WHERE ar2.paper_id = ar.paper_id
                      AND ar2.prompt_version_id = ar.prompt_version_id
                      AND j2.type = 'analyze'
                      AND j2.status = 'succeeded'
                  )
              )
        """
        params.append(prompt_version_id)
        query = QueryString(sql, *params)
        rows = run_sync(AnalysisExtraction._meta.db.run_querystring(query))
        return [row["paper_id"] for row in rows]

    def search_text(
        self,
        query: str,
        *,
        prompt_version_id: str,
        field_path: str | None = None,
        entity_type: str | None = None,
        entity_ref: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        if not query.strip():
            return []

        sql = """
            SELECT DISTINCT paper_id
            FROM extractions_fts
            WHERE extractions_fts MATCH {}
              AND prompt_version_id = {}
        """
        literal_query = literal_fts_query(query)
        params: list[Any] = [literal_query, prompt_version_id]
        if field_path is not None:
            sql += " AND field_path = {}"
            params.append(field_path)
        if entity_type is not None:
            sql += " AND entity_type = {}"
            params.append(entity_type)
        if entity_ref is not None:
            sql += " AND entity_ref = {}"
            params.append(entity_ref)
        sql += " LIMIT {}"
        params.append(limit)

        rows = run_sync(AnalysisExtraction._meta.db.run_querystring(QueryString(sql, *params)))
        return [row["paper_id"] for row in rows]

    def count_by_value(
        self,
        field_path: str,
        prompt_version_id: str,
        latest_only: bool = True,
    ) -> dict[str, int]:
        if not latest_only:
            # Simple count without run selection
            from piccolo.query.functions import Count

            query = (
                AnalysisExtraction.select(
                    AnalysisExtraction.value_text,
                    Count(distinct=[AnalysisExtraction.paper_id]).as_alias("count"),
                )
                .where(AnalysisExtraction.field_path == field_path)
                .where(AnalysisExtraction.prompt_version_id == prompt_version_id)
                .where(AnalysisExtraction.value_text.is_not_null())
                .group_by(AnalysisExtraction.value_text)
            )
            rows = query.run_sync()
            return {row["value_text"]: row["count"] for row in rows}

        # Count with latest successful run filtering
        from piccolo.querystring import QueryString

        sql = """
            SELECT ae.value_text, COUNT(DISTINCT ae.paper_id) as count
            FROM analysis_extractions ae
            WHERE ae.field_path = {}
              AND ae.prompt_version_id = {}
              AND ae.value_text IS NOT NULL
              AND ae.run_id IN (
                SELECT ar.run_id
                FROM analysis_runs ar
                JOIN jobs j ON j.run_id = ar.run_id
                WHERE j.type = 'analyze'
                  AND j.status = 'succeeded'
                  AND ar.prompt_version_id = {}
                  AND ar.created_at = (
                    SELECT MAX(ar2.created_at)
                    FROM analysis_runs ar2
                    JOIN jobs j2 ON j2.run_id = ar2.run_id
                    WHERE ar2.paper_id = ar.paper_id
                      AND ar2.prompt_version_id = ar.prompt_version_id
                      AND j2.type = 'analyze'
                      AND j2.status = 'succeeded'
                  )
              )
            GROUP BY ae.value_text
        """
        query = QueryString(sql, field_path, prompt_version_id, prompt_version_id)
        rows = run_sync(AnalysisExtraction._meta.db.run_querystring(query))
        return {row["value_text"]: row["count"] for row in rows}

    def average_numeric(
        self,
        field_path: str,
        prompt_version_id: str,
        group_by: str | None = None,
        latest_only: bool = True,
    ) -> float | dict[str, float] | None:
        group_by_column = None
        if group_by is not None:
            group_by_column = _EXTRACTION_GROUP_BY_COLUMNS.get(group_by)
            if group_by_column is None:
                raise ValueError(f"unsupported extraction group_by field: {group_by}")

        if not latest_only:
            # Simple average without run selection
            from piccolo.query.functions import Avg

            if group_by and group_by_column:
                # Grouped average
                group_field = getattr(AnalysisExtraction, group_by_column)
                query = (
                    AnalysisExtraction.select(
                        group_field,
                        Avg(AnalysisExtraction.value_numeric).as_alias("avg"),
                    )
                    .where(AnalysisExtraction.field_path == field_path)
                    .where(AnalysisExtraction.prompt_version_id == prompt_version_id)
                    .where(AnalysisExtraction.value_numeric.is_not_null())
                    .group_by(group_field)
                )
                rows = query.run_sync()
                if not rows:
                    return None
                return {str(row[group_by_column]): float(row["avg"]) for row in rows}
            else:
                # Simple average
                query = (
                    AnalysisExtraction.select(Avg(AnalysisExtraction.value_numeric).as_alias("avg"))
                    .where(AnalysisExtraction.field_path == field_path)
                    .where(AnalysisExtraction.prompt_version_id == prompt_version_id)
                    .where(AnalysisExtraction.value_numeric.is_not_null())
                )
                rows = query.run_sync()
                if not rows or rows[0]["avg"] is None:
                    return None
                return float(rows[0]["avg"])

        # Average with latest successful run filtering
        from piccolo.querystring import QueryString

        if group_by_column:
            # Grouped average with latest run filtering
            sql = f"""
                SELECT ae.{group_by_column}, AVG(ae.value_numeric) as avg
                FROM analysis_extractions ae
                WHERE ae.field_path = {{}}
                  AND ae.prompt_version_id = {{}}
                  AND ae.value_numeric IS NOT NULL
                  AND ae.run_id IN (
                    SELECT ar.run_id
                    FROM analysis_runs ar
                    JOIN jobs j ON j.run_id = ar.run_id
                    WHERE j.type = 'analyze'
                      AND j.status = 'succeeded'
                      AND ar.prompt_version_id = {{}}
                      AND ar.created_at = (
                        SELECT MAX(ar2.created_at)
                        FROM analysis_runs ar2
                        JOIN jobs j2 ON j2.run_id = ar2.run_id
                        WHERE ar2.paper_id = ar.paper_id
                          AND ar2.prompt_version_id = ar.prompt_version_id
                          AND j2.type = 'analyze'
                          AND j2.status = 'succeeded'
                      )
                  )
                GROUP BY ae.{group_by_column}
            """
            query = QueryString(sql, field_path, prompt_version_id, prompt_version_id)
            rows = run_sync(AnalysisExtraction._meta.db.run_querystring(query))
            if not rows:
                return None
            return {str(row[group_by_column]): float(row["avg"]) for row in rows}
        else:
            # Simple average with latest run filtering
            sql = """
                SELECT AVG(ae.value_numeric) as avg
                FROM analysis_extractions ae
                WHERE ae.field_path = {}
                  AND ae.prompt_version_id = {}
                  AND ae.value_numeric IS NOT NULL
                  AND ae.run_id IN (
                    SELECT ar.run_id
                    FROM analysis_runs ar
                    JOIN jobs j ON j.run_id = ar.run_id
                    WHERE j.type = 'analyze'
                      AND j.status = 'succeeded'
                      AND ar.prompt_version_id = {}
                      AND ar.created_at = (
                        SELECT MAX(ar2.created_at)
                        FROM analysis_runs ar2
                        JOIN jobs j2 ON j2.run_id = ar2.run_id
                        WHERE ar2.paper_id = ar.paper_id
                          AND ar2.prompt_version_id = ar.prompt_version_id
                          AND j2.type = 'analyze'
                          AND j2.status = 'succeeded'
                      )
                  )
            """
            query = QueryString(sql, field_path, prompt_version_id, prompt_version_id)
            rows = run_sync(AnalysisExtraction._meta.db.run_querystring(query))
            if not rows or rows[0]["avg"] is None:
                return None
            return float(rows[0]["avg"])


class PiccoloJobQueue(ports.JobQueue):
    def enqueue(
        self,
        type: str,
        paper_id: str | None,
        run_id: str | None,
        payload: dict[str, Any],
        run_after: datetime | None = None,
    ) -> str:
        if type in {"download", "convert", "embed"} and paper_id is not None:
            row = (
                Job.select(Job.job_id)
                .where(Job.type == type)
                .where(Job.paper_id == paper_id)
                .where(Job.status.is_in(["queued", "running"]))
                .first()
                .run_sync()
            )
            if row is not None:
                return row["job_id"]
        if type == "analyze" and run_id is not None:
            row = (
                Job.select(Job.job_id)
                .where(Job.type == "analyze")
                .where(Job.run_id == run_id)
                .first()
                .run_sync()
            )
            if row is not None:
                return row["job_id"]
        job_id = str(uuid.uuid4())
        Job.insert(
            Job(
                _data={
                    Job.job_id: job_id,
                    Job.type: type,
                    Job.status: "queued",
                    Job.paper_id: paper_id,
                    Job.run_id: run_id,
                    Job.payload_json: json.dumps(payload),
                    Job.attempts: 0,
                    Job.max_attempts: payload.get("max_attempts", 3),
                    Job.run_after: run_after,
                }
            )
        ).run_sync()
        return job_id

    def claim_next(self, now: datetime) -> JobRow | None:
        sql = """
            UPDATE jobs
            SET status = 'running',
                attempts = attempts + 1,
                updated_at = {}
            WHERE job_id = (
                SELECT job_id
                FROM jobs
                WHERE status = 'queued'
                  AND (run_after IS NULL OR run_after <= {})
                  AND attempts < max_attempts
                ORDER BY created_at
                LIMIT 1
            )
            RETURNING job_id, type, status, paper_id, run_id,
                      payload_json, attempts, max_attempts, run_after
        """
        rows = run_sync(Job._meta.db.run_querystring(QueryString(sql, datetime.now(UTC), now)))
        if not rows:
            return None
        row = rows[0]
        return JobRow(
            job_id=row["job_id"],
            type=row["type"],
            status=row["status"],
            paper_id=row["paper_id"],
            run_id=row["run_id"],
            payload=json.loads(row["payload_json"]),
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            run_after=row["run_after"],
        )

    def mark_succeeded(self, job_id: str, metrics: dict[str, Any] | None = None) -> None:
        Job.update({"status": "succeeded", "updated_at": datetime.now(UTC)}).where(
            Job.job_id == job_id
        ).run_sync()

    def mark_retryable(
        self,
        job_id: str,
        error: str,
        run_after: datetime,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        Job.update(
            {
                "status": "queued",
                "last_error": error,
                "run_after": run_after,
                "updated_at": datetime.now(UTC),
            }
        ).where(Job.job_id == job_id).run_sync()

    def mark_failed(self, job_id: str, error: str, metrics: dict[str, Any] | None = None) -> None:
        Job.update(
            {"status": "failed", "last_error": error, "updated_at": datetime.now(UTC)}
        ).where(Job.job_id == job_id).run_sync()

    def cancel(self, job_id: str) -> None:
        Job.update({"status": "canceled", "updated_at": datetime.now(UTC)}).where(
            Job.job_id == job_id
        ).run_sync()

    def is_cancelled(self, job_id: str) -> bool:
        row = Job.select(Job.status).where(Job.job_id == job_id).first().run_sync()
        return row is not None and row["status"] == "canceled"

    def requeue_running_before(self, cutoff: datetime, error: str) -> list[str]:
        rows = (
            Job.select(Job.job_id)
            .where(Job.status == "running")
            .where(Job.updated_at < cutoff)
            .run_sync()
        )
        job_ids = [row["job_id"] for row in rows]
        if not job_ids:
            return []
        (
            Job.update(
                {
                    "status": "queued",
                    "last_error": error,
                    "run_after": None,
                    "updated_at": datetime.now(UTC),
                }
            )
            .where(Job.job_id.is_in(job_ids))
            .run_sync()
        )
        return job_ids

    def list_jobs(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = Job.select()
        if status is not None:
            query = query.where(Job.status == status)
        rows = query.order_by(Job.created_at).limit(limit).run_sync()
        return [dict(row) for row in rows]

    def delete_job(self, job_id: str) -> None:
        Job.delete().where(Job.job_id == job_id).run_sync()

    def bulk_delete_jobs(self, job_ids: list[str]) -> int:
        if not job_ids:
            return 0
        existing = Job.select(Job.job_id).where(Job.job_id.is_in(job_ids)).run_sync()
        existing_ids = [row["job_id"] for row in existing]
        if existing_ids:
            Job.delete().where(Job.job_id.is_in(existing_ids)).run_sync()
        return len(existing_ids)

    def bulk_cancel_jobs(self, job_ids: list[str]) -> int:
        if not job_ids:
            return 0
        cancellable = (
            Job.select(Job.job_id)
            .where(Job.job_id.is_in(job_ids))
            .where(Job.status.is_in(["queued", "running"]))
            .run_sync()
        )
        cancellable_ids = [row["job_id"] for row in cancellable]
        if cancellable_ids:
            (
                Job.update({Job.status: "canceled", Job.updated_at: datetime.now(UTC)})
                .where(Job.job_id.is_in(cancellable_ids))
                .run_sync()
            )
        return len(cancellable_ids)


class PiccoloPromptStore(ports.PromptStore):
    def create_prompt(
        self,
        prompt_id: str,
        name: str,
        description: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
        created_at: str | None = None,
    ) -> None:
        Prompt(
            _data={
                Prompt.prompt_id: prompt_id,
                Prompt.name: name,
                Prompt.description: description,
                Prompt.domain: domain,
                Prompt.tags_json: json.dumps(tags) if tags is not None else None,
                Prompt.created_at: created_at or datetime.now(UTC),
            }
        ).save().run_sync()

    def get_prompt(self, prompt_id: str) -> dict[str, Any] | None:
        row = Prompt.select().where(Prompt.prompt_id == prompt_id).first().run_sync()
        if row is None:
            return None
        data = dict(row)
        tags_json = data.get("tags_json")
        if tags_json:
            try:
                data["tags"] = json.loads(tags_json)
            except (json.JSONDecodeError, TypeError):
                data["tags"] = None
        return data

    def create_version(
        self,
        prompt_version_id: str,
        prompt_id: str,
        version: int,
        body: str,
        output_format: str,
        extraction_schema_json: dict[str, Any] | None = None,
    ) -> None:
        PromptVersion.insert(
            PromptVersion(
                _data={
                    PromptVersion.prompt_version_id: prompt_version_id,
                    PromptVersion.prompt_id: prompt_id,
                    PromptVersion.version: version,
                    PromptVersion.body: body,
                    PromptVersion.output_format: output_format,
                    PromptVersion.extraction_schema_json: (
                        json.dumps(extraction_schema_json) if extraction_schema_json else None
                    ),
                }
            )
        ).run_sync()

    def get_latest_version(self, prompt_id: str) -> dict[str, Any] | None:
        row = (
            PromptVersion.select()
            .where(PromptVersion.prompt_id == prompt_id)
            .order_by(PromptVersion.version, ascending=False)
            .first()
            .run_sync()
        )
        return None if row is None else dict(row)

    def get_version(self, prompt_version_id: str) -> dict[str, Any] | None:
        row = (
            PromptVersion.select()
            .where(PromptVersion.prompt_version_id == prompt_version_id)
            .first()
            .run_sync()
        )
        return None if row is None else dict(row)


class PiccoloProfileStore(ports.ProfileStore):
    def create_profile(self, profile_id: str, name: str, base_url: str) -> None:
        EndpointProfile.insert(
            EndpointProfile(
                _data={
                    EndpointProfile.profile_id: profile_id,
                    EndpointProfile.name: name,
                    EndpointProfile.base_url: base_url,
                    EndpointProfile.is_active: True,
                }
            )
        ).run_sync()

    def get(self, profile_id: str) -> dict[str, Any] | None:
        row = (
            EndpointProfile.select()
            .where(EndpointProfile.profile_id == profile_id)
            .first()
            .run_sync()
        )
        return None if row is None else dict(row)


class PiccoloAnalysisRunStore(ports.AnalysisRunStore):
    def create_run(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ) -> None:
        AnalysisRun.insert(
            AnalysisRun(
                _data={
                    AnalysisRun.run_id: run_id,
                    AnalysisRun.paper_id: paper_id,
                    AnalysisRun.prompt_version_id: prompt_version_id,
                    AnalysisRun.profile_id: profile_id,
                    AnalysisRun.model_name: model_name,
                }
            )
        ).run_sync()

    def mark_started(self, run_id: str) -> None:
        AnalysisRun.update({"started_at": datetime.now(UTC)}).where(
            AnalysisRun.run_id == run_id
        ).run_sync()

    def mark_finished(
        self,
        run_id: str,
        *,
        output_md: str | None = None,
        output_json: str | None = None,
        validation_issues_json: str | None = None,
        error_message: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
    ) -> None:
        AnalysisRun.update(
            {
                "output_blob_path_md": output_md,
                "output_blob_path_json": output_json,
                "validation_issues_json": validation_issues_json,
                "error_message": error_message,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "finished_at": datetime.now(UTC),
            }
        ).where(AnalysisRun.run_id == run_id).run_sync()

    def get_latest_successful_run(
        self,
        *,
        paper_id: str,
        prompt_version_id: str,
        profile_id: str,
        model_name: str,
    ) -> dict[str, Any] | None:
        sql = """
            SELECT ar.* FROM analysis_runs ar
            JOIN jobs j ON j.run_id = ar.run_id
            WHERE ar.paper_id = {}
              AND ar.prompt_version_id = {}
              AND ar.profile_id = {}
              AND ar.model_name = {}
              AND j.type = 'analyze'
              AND j.status = 'succeeded'
            ORDER BY ar.created_at DESC
            LIMIT 1
        """
        query = QueryString(sql, paper_id, prompt_version_id, profile_id, model_name)
        rows = run_sync(AnalysisRun._meta.db.run_querystring(query))
        data = AnalysisRun._meta.db.transform_response_to_dicts(rows)
        return data[0] if data else None

    def list_runs(self, paper_id: str) -> list[dict[str, Any]]:
        """List all analysis runs for a paper with their status from jobs table."""
        sql = """
            SELECT ar.*, j.status FROM analysis_runs ar
            JOIN jobs j ON j.run_id = ar.run_id AND j.type = 'analyze'
            WHERE ar.paper_id = {}
            ORDER BY ar.created_at DESC
        """
        query = QueryString(sql, paper_id)
        rows = run_sync(AnalysisRun._meta.db.run_querystring(query))
        data = AnalysisRun._meta.db.transform_response_to_dicts(rows)
        return data


@dataclass(frozen=True)
class _RowExtraction:
    entity_type: str
    entity_ref: str | None
    field_path: str
    value_text: str | None
    value_numeric: float | None
    value_boolean: int | None


class PiccoloTagStore(ports.TagStore):
    def create_tag(
        self,
        tag_id: str,
        name: str,
        tag_type: str,
        created_at: str | None = None,
    ) -> None:
        Tag(
            _data={
                Tag.tag_id: tag_id,
                Tag.name: name,
                Tag.type: tag_type,
                Tag.created_at: created_at or datetime.now(UTC),
                Tag.updated_at: datetime.now(UTC),
            }
        ).save().run_sync()

    def get(self, tag_id: str) -> dict[str, Any] | None:
        row = Tag.select().where(Tag.tag_id == tag_id).first().run_sync()
        return None if row is None else dict(row)

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        row = Tag.select().where(Tag.name == name).first().run_sync()
        return None if row is None else dict(row)


class PiccoloPaperTagStore(ports.PaperTagStore):
    def is_attached(self, paper_id: str, tag_id: str) -> bool:
        row = (
            PaperTag.select()
            .where(PaperTag.paper_id == paper_id)
            .where(PaperTag.tag_id == tag_id)
            .first()
            .run_sync()
        )
        return row is not None

    def attach(self, paper_id: str, tag_id: str, confidence: float | None = None) -> None:
        PaperTag(
            _data={
                PaperTag.paper_id: paper_id,
                PaperTag.tag_id: tag_id,
                PaperTag.confidence: confidence,
            }
        ).save().run_sync()


class PiccoloProjectStore(ports.ProjectStore):
    def create_project(
        self,
        project_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> None:
        Project(
            _data={
                Project.project_id: project_id,
                Project.name: name,
                Project.description: description,
                Project.created_at: created_at or datetime.now(UTC),
                Project.updated_at: datetime.now(UTC),
            }
        ).save().run_sync()

    def get(self, project_id: str) -> dict[str, Any] | None:
        row = Project.select().where(Project.project_id == project_id).first().run_sync()
        return None if row is None else dict(row)

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        row = Project.select().where(Project.name == name).first().run_sync()
        return None if row is None else dict(row)


class PiccoloPaperProjectStore(ports.PaperProjectStore):
    def is_attached(self, paper_id: str, project_id: str) -> bool:
        row = (
            PaperProject.select()
            .where(PaperProject.paper_id == paper_id)
            .where(PaperProject.project_id == project_id)
            .first()
            .run_sync()
        )
        return row is not None

    def attach(self, paper_id: str, project_id: str, label: str | None = None) -> None:
        PaperProject(
            _data={
                PaperProject.paper_id: paper_id,
                PaperProject.project_id: project_id,
                PaperProject.label: label,
            }
        ).save().run_sync()

    def list_paper_ids(self, project_id: str, label: str | None = None) -> list[str]:
        query = PaperProject.select(PaperProject.paper_id).where(
            PaperProject.project_id == project_id
        )
        if label is not None:
            query = query.where(PaperProject.label == label)
        rows = query.run_sync()
        return [row["paper_id"] for row in rows]


class PiccoloPaperExternalIdStore(ports.PaperExternalIdStore):
    """Store for paper external identifiers (ArXiv, DOI, etc.)."""

    def create_external_ids(self, paper_id: str, external_ids: dict[str, str]) -> None:
        """Create external ID records for a paper."""
        if not external_ids:
            return
        for kind, value in external_ids.items():
            # Check if this kind already exists for the paper
            existing = (
                PaperExternalId.select()
                .where(PaperExternalId.paper_id == paper_id)
                .where(PaperExternalId.kind == kind)
                .first()
                .run_sync()
            )
            if existing is not None:
                # Update existing record
                (
                    PaperExternalId.update({PaperExternalId.value: value})
                    .where(PaperExternalId.paper_id == paper_id)
                    .where(PaperExternalId.kind == kind)
                    .run_sync()
                )
            else:
                # Create new record
                PaperExternalId(
                    _data={
                        PaperExternalId.paper_external_id_id: str(uuid.uuid4()),
                        PaperExternalId.paper_id: paper_id,
                        PaperExternalId.kind: kind,
                        PaperExternalId.value: value,
                    }
                ).save().run_sync()

    def get_external_ids(self, paper_id: str) -> dict[str, str]:
        """Get all external IDs for a paper."""
        rows = (
            PaperExternalId.select(PaperExternalId.kind, PaperExternalId.value)
            .where(PaperExternalId.paper_id == paper_id)
            .run_sync()
        )
        return {row["kind"]: row["value"] for row in rows}

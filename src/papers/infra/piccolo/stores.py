from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from piccolo.querystring import QueryString
from piccolo.utils.sync import run_sync

from papers.app import ports
from papers.domain.errors import InvalidStateTransition, NotFoundError
from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.piccolo.tables import (
    AnalysisExtraction,
    AnalysisRun,
    Candidate,
    EndpointProfile,
    Job,
    Paper,
    Prompt,
    PromptVersion,
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


class PiccoloCandidateStore:
    """Store for candidate papers discovered from external sources."""

    def create_candidate(self, fields: dict[str, Any]) -> str:
        candidate_id = fields["candidate_id"]
        payload = {
            Candidate.candidate_id: candidate_id,
            Candidate.source: fields["source"],
            Candidate.source_paper_id: fields["source_paper_id"],
            Candidate.title: fields["title"],
            Candidate.year: fields.get("year"),
            Candidate.venue: fields.get("venue"),
            Candidate.authors_json: fields.get("authors_json", "[]"),
            Candidate.abstract: fields.get("abstract"),
            Candidate.external_ids_json: fields.get("external_ids_json"),
            Candidate.rejected_at: fields.get("rejected_at"),
            Candidate.imported_paper_id: fields.get("imported_paper_id"),
            Candidate.imported_at: fields.get("imported_at"),
        }
        Candidate(_data=payload).save().run_sync()
        return candidate_id

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = Candidate.select().where(Candidate.candidate_id == candidate_id).first().run_sync()
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
            Candidate.update({
                Candidate.imported_paper_id: paper_id,
                Candidate.imported_at: datetime.now(),
                Candidate.updated_at: datetime.now(),
            })
            .where(Candidate.candidate_id == candidate_id)
            .run_sync()
        )

    def mark_rejected(self, candidate_id: str) -> None:
        (
            Candidate.update({
                Candidate.rejected_at: datetime.now(),
                Candidate.updated_at: datetime.now(),
            })
            .where(Candidate.candidate_id == candidate_id)
            .where(Candidate.rejected_at.is_null())  # Only update if not already rejected
            .run_sync()
        )


class PiccoloPaperStore(ports.PaperStore):
    def create_paper(self, fields: dict[str, Any]) -> str:
        paper_id = fields["paper_id"]
        payload = {
            Paper.paper_id: paper_id,
            Paper.title: fields["title"],
            Paper.year: fields.get("year"),
            Paper.venue: fields.get("venue"),
            Paper.authors_json: json.dumps(fields.get("authors", [])),
            Paper.abstract: fields.get("abstract"),
            Paper.pipeline_stage: str(fields.get("pipeline_stage", PipelineStage.imported)),
            Paper.pipeline_health: str(fields.get("pipeline_health", PipelineHealth.ok)),
        }
        Paper(_data=payload).save().run_sync()
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
        updates["updated_at"] = datetime.now()
        Paper.update(updates).where(Paper.paper_id == paper_id).run_sync()

    def set_pdf_fingerprint(self, paper_id: str, pdf_xxh64: str) -> None:
        Paper.update({"pdf_fingerprint_xxh64": pdf_xxh64, "updated_at": datetime.now()}).where(
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
                "updated_at": datetime.now(),
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
                "updated_at": datetime.now(),
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
            raise InvalidStateTransition("cannot regress pipeline stage")
        Paper.update({"pipeline_stage": str(new_stage), "updated_at": datetime.now()}).where(
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
                "last_error_at": datetime.now(),
                "updated_at": datetime.now(),
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
                "updated_at": datetime.now(),
            }
        ).where(Paper.paper_id == paper_id).run_sync()


class PiccoloExtractionStore(ports.ExtractionStore):
    def upsert_extractions(
        self,
        run_id: str,
        paper_id: str,
        prompt_version_id: str,
        extractions: list[ports.Extraction],
    ) -> None:
        if not extractions:
            return
        rows = []
        for extraction in extractions:
            rows.append(
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
            )
        instances = [AnalysisExtraction(_data=row) for row in rows]
        AnalysisExtraction.insert(*instances).run_sync()

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
    ) -> list[str]:
        query = (
            AnalysisExtraction.select(AnalysisExtraction.paper_id)
            .where(AnalysisExtraction.field_path == field_path)
            .where(AnalysisExtraction.prompt_version_id == prompt_version_id)
        )
        for key, value in constraints.items():
            query = query.where(getattr(AnalysisExtraction, key) == value)
        rows = query.run_sync()
        return [row["paper_id"] for row in rows]


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
        row = (
            Job.select()
            .where(Job.status == "queued")
            .where((Job.run_after.is_null()) | (Job.run_after <= now))
            .where(Job.attempts < Job.max_attempts)
            .order_by(Job.created_at)
            .first()
            .run_sync()
        )
        if row is None:
            return None
        Job.update(
            {"status": "running", "attempts": row["attempts"] + 1, "updated_at": datetime.now()}
        ).where(Job.job_id == row["job_id"]).run_sync()
        return JobRow(
            job_id=row["job_id"],
            type=row["type"],
            status="running",
            paper_id=row["paper_id"],
            run_id=row["run_id"],
            payload=json.loads(row["payload_json"]),
            attempts=row["attempts"] + 1,
            max_attempts=row["max_attempts"],
            run_after=row["run_after"],
        )

    def mark_succeeded(self, job_id: str, metrics: dict[str, Any] | None = None) -> None:
        Job.update({"status": "succeeded", "updated_at": datetime.now()}).where(
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
                "updated_at": datetime.now(),
            }
        ).where(Job.job_id == job_id).run_sync()

    def mark_failed(self, job_id: str, error: str, metrics: dict[str, Any] | None = None) -> None:
        Job.update({"status": "failed", "last_error": error, "updated_at": datetime.now()}).where(
            Job.job_id == job_id
        ).run_sync()

    def cancel(self, job_id: str) -> None:
        Job.update({"status": "canceled", "updated_at": datetime.now()}).where(
            Job.job_id == job_id
        ).run_sync()

    def is_cancelled(self, job_id: str) -> bool:
        row = Job.select(Job.status).where(Job.job_id == job_id).first().run_sync()
        return row is not None and row["status"] == "canceled"


class PiccoloPromptStore(ports.PromptStore):
    def create_prompt(self, prompt_id: str, name: str, created_at: str | None = None) -> None:
        Prompt(
            _data={
                Prompt.prompt_id: prompt_id,
                Prompt.name: name,
                Prompt.created_at: created_at or datetime.now(),
            }
        ).save().run_sync()

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
        AnalysisRun.update({"started_at": datetime.now()}).where(
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
                "finished_at": datetime.now(),
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


@dataclass(frozen=True)
class _RowExtraction:
    entity_type: str
    entity_ref: str | None
    field_path: str
    value_text: str | None
    value_numeric: float | None
    value_boolean: int | None

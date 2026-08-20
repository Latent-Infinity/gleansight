from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from piccolo.engine.sqlite import SQLiteEngine
from piccolo.querystring import QueryString
from piccolo.utils.sync import run_sync

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

_TABLES = (
    Candidate,
    Paper,
    PaperExternalId,
    Project,
    Tag,
    PaperProject,
    PaperTag,
    Prompt,
    PromptVersion,
    EndpointProfile,
    AnalysisRun,
    Job,
    AnalysisExtraction,
)


@dataclass(frozen=True)
class PiccoloDatabase:
    path: Path
    _engine: SQLiteEngine = field(init=False, repr=False)

    def __post_init__(self) -> None:
        engine = SQLiteEngine(path=str(self.path))
        for table in _TABLES:
            table._meta.db = engine
        object.__setattr__(self, "_engine", engine)

    @property
    def engine(self) -> SQLiteEngine:
        return self._engine

    def initialize_schema(self) -> None:
        from papers.infra.piccolo.migrations.runner import apply_forward_migrations

        for table in _TABLES:
            table.create_table(if_not_exists=True).run_sync()
        self._create_indexes_and_fts()
        apply_forward_migrations(self)

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        query = self._to_query(sql, params)
        run_sync(self._engine.run_querystring(query))

    def fetchall(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        query = self._to_query(sql, params)
        rows = run_sync(self._engine.run_querystring(query))
        return self._engine.transform_response_to_dicts(rows)

    def fetchone(self, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
        rows = self.fetchall(sql, params)
        return rows[0] if rows else None

    def _create_indexes_and_fts(self) -> None:
        statements = [
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_source
            ON candidates(source, source_paper_id);
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_external_ids_unique
            ON paper_external_ids(kind, value);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_paper_external_ids_paper_id
            ON paper_external_ids(paper_id);
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_versions_unique
            ON prompt_versions(prompt_id, version);
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_projects_unique
            ON paper_projects(paper_id, project_id);
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_tags_unique
            ON paper_tags(paper_id, tag_id);
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique_active_stage
            ON jobs(type, paper_id)
            WHERE status IN ('queued','running') AND type IN ('download','convert','embed');
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_unique_analyze
            ON jobs(run_id)
            WHERE type = 'analyze';
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_extractions_unique
            ON analysis_extractions(run_id, entity_type, IFNULL(entity_ref,''), field_path);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_extractions_paper_field
            ON analysis_extractions(paper_id, field_path);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_extractions_field_text
            ON analysis_extractions(field_path, value_text);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_extractions_field_numeric
            ON analysis_extractions(field_path, value_numeric)
            WHERE value_numeric IS NOT NULL;
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_extractions_entity
            ON analysis_extractions(entity_type, entity_ref);
            """,
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                title,
                abstract,
                paper_id UNINDEXED
            );
            """,
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS extractions_fts USING fts5(
                value_text,
                paper_id UNINDEXED,
                prompt_version_id UNINDEXED,
                entity_type UNINDEXED,
                entity_ref UNINDEXED,
                field_path UNINDEXED
            );
            """,
        ]
        for statement in statements:
            run_sync(self._engine.run_ddl(statement))

    def _to_query(self, sql: str, params: list[Any] | None) -> QueryString:
        if not params:
            return QueryString(sql)
        template = sql.replace("?", "{}")
        return QueryString(template, *params)

"""Tests for the refactored handle_analyze handler with template rendering,
output parsing, extraction flattening, and schema validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from papers.app.job_runner.handlers import (
    HandlerContext,
    handle_analyze,
)
from papers.app.ports import LLMResponse
from papers.domain.models import OutputFormat, PipelineHealth, PipelineStage
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloExtractionStore,
    PiccoloJobQueue,
    PiccoloPaperStore,
    PiccoloProfileStore,
    PiccoloPromptStore,
)


@dataclass(frozen=True)
class _Job:
    job_id: str
    type: str
    status: str
    paper_id: str | None
    run_id: str | None
    payload: dict[str, object]
    attempts: int
    max_attempts: int
    run_after: datetime | None


class _VectorIndex:
    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        return None

    def query(self, embedding: list[float], limit: int):
        return []


class _Converter:
    def pdf_to_markdown(self, pdf_path: Path):
        return type(
            "Result",
            (),
            {
                "ok": True,
                "markdown": "This is converted markdown content. " * 6,
                "error_code": None,
                "error_message": None,
            },
        )()

    def version(self) -> str:
        return "1.0"


class _Embedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        return [1.0, 2.0, 3.0]


class _LLM:
    """Configurable fake LLM that returns a preset response."""

    def __init__(self, response_text: str = "") -> None:
        self.response_text = response_text
        self.last_prompt: str | None = None

    def complete(
        self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None
    ) -> LLMResponse:
        self.last_prompt = prompt
        return LLMResponse(
            text=self.response_text,
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.001,
        )


@pytest.fixture()
def _env(tmp_path: Path):
    """Set up database, stores, and context for analyze handler tests."""
    db = PiccoloDatabase(tmp_path / "db.sqlite")
    db.initialize_schema()

    paper_store = PiccoloPaperStore()
    prompt_store = PiccoloPromptStore()
    profile_store = PiccoloProfileStore()
    analysis_store = PiccoloAnalysisRunStore()
    extraction_store = PiccoloExtractionStore()
    job_queue = PiccoloJobQueue()
    blob_store = FileSystemBlobStore(tmp_path / "blobs")

    # Create a paper with markdown
    paper_store.create_paper(
        {
            "paper_id": "paper-1",
            "title": "Test Paper Title",
            "year": 2024,
            "venue": "TestConf",
            "authors_json": json.dumps(["Alice", "Bob"]),
            "abstract": "A test abstract.",
            "pipeline_stage": str(PipelineStage.embedded),
            "pipeline_health": str(PipelineHealth.ok),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )

    # Store markdown blob
    blob_store.put_markdown("paper-1", "# Test\nThis is markdown content.")

    # Create prompt + version
    prompt_store.create_prompt("prompt-1", "Test Prompt")
    prompt_store.create_version(
        "pv-1",
        "prompt-1",
        1,
        body="Analyze: {title}\n{markdown}",
        output_format=str(OutputFormat.json_only),
    )

    # Create endpoint profile
    profile_store.create_profile("prof-1", "test-endpoint", "http://localhost:8000")

    # Create analysis run
    analysis_store.create_run("run-1", "paper-1", "pv-1", "prof-1", "test-model")

    return {
        "db": db,
        "paper_store": paper_store,
        "prompt_store": prompt_store,
        "profile_store": profile_store,
        "analysis_store": analysis_store,
        "extraction_store": extraction_store,
        "job_queue": job_queue,
        "blob_store": blob_store,
        "tmp_path": tmp_path,
    }


def _make_context(env: dict, llm: _LLM) -> HandlerContext:
    return HandlerContext(
        paper_store=env["paper_store"],
        job_queue=env["job_queue"],
        blob_store=env["blob_store"],
        converter=_Converter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=llm,
        prompt_store=env["prompt_store"],
        profile_store=env["profile_store"],
        analysis_store=env["analysis_store"],
        extraction_store=env["extraction_store"],
    )


def _make_job(run_id: str = "run-1") -> _Job:
    return _Job(
        job_id="job-1",
        type="analyze",
        status="running",
        paper_id="paper-1",
        run_id=run_id,
        payload={
            "prompt_version_id": "pv-1",
            "profile_id": "prof-1",
            "model_name": "test-model",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )


def test_analyze_renders_template_with_paper_data(_env: dict) -> None:
    """Verify the prompt sent to LLM has paper data substituted."""
    llm = _LLM(response_text='{"result": "ok"}')
    ctx = _make_context(_env, llm)
    job = _make_job()

    result = handle_analyze(job, ctx)

    assert result.status == "succeeded"
    assert llm.last_prompt is not None
    assert "Test Paper Title" in llm.last_prompt
    assert "# Test" in llm.last_prompt  # markdown content


def test_analyze_json_only_creates_extractions(_env: dict) -> None:
    """JSON-only output should be parsed and create extraction rows."""
    llm = _LLM(response_text='{"algorithm": "SGD", "score": 9.5, "novel": true}')
    ctx = _make_context(_env, llm)
    job = _make_job()

    result = handle_analyze(job, ctx)

    assert result.status == "succeeded"
    extractions = _env["extraction_store"].list_by_paper("paper-1", successful_only=False)
    paths = {e.field_path for e in extractions}
    assert "algorithm" in paths
    assert "score" in paths
    assert "novel" in paths


def test_analyze_yaml_block_creates_extractions(_env: dict) -> None:
    """YAML block output format should parse and create extractions."""
    # Update prompt version to yaml_block
    _env["prompt_store"].create_version(
        "pv-yaml",
        "prompt-1",
        2,
        body="Analyze: {title}",
        output_format=str(OutputFormat.yaml_block),
    )
    _env["analysis_store"].create_run("run-yaml", "paper-1", "pv-yaml", "prof-1", "test-model")

    llm = _LLM(response_text="Here's my analysis:\n```yaml\nname: Foo\nscore: 4\n```\nDone.")
    ctx = _make_context(_env, llm)
    job = _Job(
        job_id="job-yaml",
        type="analyze",
        status="running",
        paper_id="paper-1",
        run_id="run-yaml",
        payload={
            "prompt_version_id": "pv-yaml",
            "profile_id": "prof-1",
            "model_name": "test-model",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    result = handle_analyze(job, ctx)

    assert result.status == "succeeded"
    extractions = _env["extraction_store"].list_by_paper(
        "paper-1", prompt_version_id="pv-yaml", successful_only=False
    )
    paths = {e.field_path for e in extractions}
    assert "name" in paths
    assert "score" in paths


def test_analyze_json_block_creates_extractions(_env: dict) -> None:
    """JSON block output format should parse and create extractions."""
    _env["prompt_store"].create_version(
        "pv-jb",
        "prompt-1",
        3,
        body="Analyze: {title}",
        output_format=str(OutputFormat.json_block),
    )
    _env["analysis_store"].create_run("run-jb", "paper-1", "pv-jb", "prof-1", "test-model")

    llm = _LLM(response_text='My analysis:\n```json\n{"key": "value"}\n```\nEnd.')
    ctx = _make_context(_env, llm)
    job = _Job(
        job_id="job-jb",
        type="analyze",
        status="running",
        paper_id="paper-1",
        run_id="run-jb",
        payload={"prompt_version_id": "pv-jb", "profile_id": "prof-1", "model_name": "test-model"},
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    result = handle_analyze(job, ctx)

    assert result.status == "succeeded"
    extractions = _env["extraction_store"].list_by_paper(
        "paper-1", prompt_version_id="pv-jb", successful_only=False
    )
    assert len(extractions) >= 1


def test_analyze_markdown_only_creates_no_extractions(_env: dict) -> None:
    """markdown_only output should succeed with zero extraction rows."""
    _env["prompt_store"].create_version(
        "pv-md",
        "prompt-1",
        4,
        body="Analyze: {title}",
        output_format=str(OutputFormat.markdown_only),
    )
    _env["analysis_store"].create_run("run-md", "paper-1", "pv-md", "prof-1", "test-model")

    llm = _LLM(response_text="# Great paper\nThis is a review.")
    ctx = _make_context(_env, llm)
    job = _Job(
        job_id="job-md",
        type="analyze",
        status="running",
        paper_id="paper-1",
        run_id="run-md",
        payload={"prompt_version_id": "pv-md", "profile_id": "prof-1", "model_name": "test-model"},
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    result = handle_analyze(job, ctx)

    assert result.status == "succeeded"
    extractions = _env["extraction_store"].list_by_paper(
        "paper-1", prompt_version_id="pv-md", successful_only=False
    )
    assert len(extractions) == 0


def test_analyze_empty_response_fails(_env: dict) -> None:
    """Empty LLM response should fail with OUTPUT_PARSE_FAILED."""
    llm = _LLM(response_text="")
    ctx = _make_context(_env, llm)
    job = _make_job()

    result = handle_analyze(job, ctx)

    assert result.status == "failed"
    assert result.error_code == "OUTPUT_PARSE_FAILED"


def test_analyze_template_needs_markdown_but_unavailable(_env: dict) -> None:
    """If template requires {markdown} but paper has no markdown, fail."""
    # Create a paper without markdown
    _env["paper_store"].create_paper(
        {
            "paper_id": "paper-nomd",
            "title": "No Markdown",
            "pipeline_stage": str(PipelineStage.imported),
            "pipeline_health": str(PipelineHealth.ok),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    _env["analysis_store"].create_run("run-nomd", "paper-nomd", "pv-1", "prof-1", "test-model")

    llm = _LLM(response_text='{"ok": true}')
    ctx = _make_context(_env, llm)
    job = _Job(
        job_id="job-nomd",
        type="analyze",
        status="running",
        paper_id="paper-nomd",
        run_id="run-nomd",
        payload={"prompt_version_id": "pv-1", "profile_id": "prof-1", "model_name": "test-model"},
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    result = handle_analyze(job, ctx)

    assert result.status == "failed"
    assert "markdown" in (result.error or "").lower()


def test_analyze_validation_failure_on_required_field(_env: dict) -> None:
    """If schema has required fields that are missing, the run should fail."""
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    _env["prompt_store"].create_version(
        "pv-schema",
        "prompt-1",
        5,
        body="Analyze: {title}",
        output_format=str(OutputFormat.json_only),
        extraction_schema_json=schema,
    )
    _env["analysis_store"].create_run("run-schema", "paper-1", "pv-schema", "prof-1", "test-model")

    # LLM returns valid JSON but missing required "name" field
    llm = _LLM(response_text='{"score": 5}')
    ctx = _make_context(_env, llm)
    job = _Job(
        job_id="job-schema",
        type="analyze",
        status="running",
        paper_id="paper-1",
        run_id="run-schema",
        payload={
            "prompt_version_id": "pv-schema",
            "profile_id": "prof-1",
            "model_name": "test-model",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    result = handle_analyze(job, ctx)

    assert result.status == "failed"
    assert result.error_code == "OUTPUT_VALIDATION_FAILED"


def test_analyze_validation_warning_succeeds(_env: dict) -> None:
    """If only optional fields fail validation, the run should succeed with warnings."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["name"],
    }
    _env["prompt_store"].create_version(
        "pv-warn",
        "prompt-1",
        6,
        body="Analyze: {title}",
        output_format=str(OutputFormat.json_only),
        extraction_schema_json=schema,
    )
    _env["analysis_store"].create_run("run-warn", "paper-1", "pv-warn", "prof-1", "test-model")

    # name present (required), score is wrong type (optional)
    llm = _LLM(response_text='{"name": "Foo", "score": "not-a-number"}')
    ctx = _make_context(_env, llm)
    job = _Job(
        job_id="job-warn",
        type="analyze",
        status="running",
        paper_id="paper-1",
        run_id="run-warn",
        payload={
            "prompt_version_id": "pv-warn",
            "profile_id": "prof-1",
            "model_name": "test-model",
        },
        attempts=1,
        max_attempts=3,
        run_after=None,
    )

    result = handle_analyze(job, ctx)

    assert result.status == "succeeded"
    # Extractions should still be stored
    extractions = _env["extraction_store"].list_by_paper(
        "paper-1", prompt_version_id="pv-warn", successful_only=False
    )
    assert len(extractions) >= 1


def test_analyze_no_schema_stores_all_extractions(_env: dict) -> None:
    """Without a schema, all parsed fields should be stored as extractions."""
    llm = _LLM(response_text='{"a": 1, "b": "two", "c": true}')
    ctx = _make_context(_env, llm)
    job = _make_job()

    result = handle_analyze(job, ctx)

    assert result.status == "succeeded"
    extractions = _env["extraction_store"].list_by_paper(
        "paper-1", prompt_version_id="pv-1", successful_only=False
    )
    paths = {e.field_path for e in extractions}
    assert "a" in paths
    assert "b" in paths
    assert "c" in paths


def test_analyze_advances_pipeline_to_analyzed(_env: dict) -> None:
    """Pipeline stage should advance to analyzed on success."""
    llm = _LLM(response_text='{"result": "ok"}')
    ctx = _make_context(_env, llm)
    job = _make_job()

    result = handle_analyze(job, ctx)

    assert result.status == "succeeded"
    paper = _env["paper_store"].get("paper-1")
    assert paper is not None
    assert paper["pipeline_stage"] == str(PipelineStage.analyzed)


def test_analyze_missing_ids() -> None:
    """paper_id and run_id are required."""
    job = _Job(
        job_id="j",
        type="analyze",
        status="running",
        paper_id=None,
        run_id=None,
        payload={},
        attempts=0,
        max_attempts=3,
        run_after=None,
    )
    # Context not needed — should fail before using it
    result = handle_analyze(
        job,
        HandlerContext(
            paper_store=PiccoloPaperStore(),
            job_queue=PiccoloJobQueue(),
            blob_store=FileSystemBlobStore(Path("/tmp/nonexistent")),
            converter=_Converter(),
            embedder=_Embedder(),
            vector_index=_VectorIndex(),
            llm_client=_LLM(),
            prompt_store=PiccoloPromptStore(),
            profile_store=PiccoloProfileStore(),
            analysis_store=PiccoloAnalysisRunStore(),
        ),
    )
    assert result.status == "failed"
    assert "paper_id" in (result.error or "")


def test_analyze_uses_profile_api_key_from_environment(
    _env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _CaptureLLM:
        def __init__(self) -> None:
            self.profile_seen: dict | None = None

        def complete(
            self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None
        ) -> LLMResponse:
            self.profile_seen = dict(profile)
            return LLMResponse(text='{"ok": true}', tokens_in=1, tokens_out=1, cost_usd=0.001)

    monkeypatch.setenv("PAPERS_ENDPOINT_API_KEY_TEST_ENDPOINT", "env-secret")
    llm = _CaptureLLM()
    ctx = _make_context(_env, llm)  # type: ignore[arg-type]
    result = handle_analyze(_make_job(), ctx)

    assert result.status == "succeeded"
    assert llm.profile_seen is not None
    assert llm.profile_seen.get("api_key") == "env-secret"


def test_analyze_computes_cost_from_profile_pricing_when_missing(_env: dict) -> None:
    class _NoCostLLM:
        def complete(
            self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None
        ) -> LLMResponse:
            return LLMResponse(text='{"ok": true}', tokens_in=200, tokens_out=100, cost_usd=None)

    _env["db"].execute(
        """
        UPDATE endpoint_profiles
        SET input_price_per_1k_tokens = ?, output_price_per_1k_tokens = ?
        WHERE profile_id = ?
        """,
        [2.0, 4.0, "prof-1"],
    )

    ctx = _make_context(_env, _NoCostLLM())  # type: ignore[arg-type]
    result = handle_analyze(_make_job(), ctx)
    assert result.status == "succeeded"

    row = _env["db"].fetchone(
        "SELECT cost_usd FROM analysis_runs WHERE run_id = ?",
        ["run-1"],
    )
    assert row is not None
    # (200 * 2 / 1000) + (100 * 4 / 1000) = 0.8
    assert float(row["cost_usd"]) == pytest.approx(0.8)

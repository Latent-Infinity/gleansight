from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nsqd.composition import build_container as build_nsqd_container
from nsqd.infra.paper_runtime import (
    ACQUISITION_PROFILE_ID,
    ACQUISITION_PROMPT_ID,
    bootstrap_analysis_defaults,
    compose_default_runtime,
    markdown_reader,
)
from nsqd.infra.papers_bridge import PapersAcquisitionBridge
from nsqd.null_adapters import FixedClock, NullPaperAcquisitionBridge
from papers.domain.errors import ConfigurationError


@dataclass
class _PromptStore:
    prompts: dict[str, dict[str, Any]] = field(default_factory=dict)
    versions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create_prompt(self, prompt_id: str, name: str, **_kwargs: Any) -> None:
        self.prompts[prompt_id] = {"prompt_id": prompt_id, "name": name}

    def get_prompt(self, prompt_id: str) -> dict[str, Any] | None:
        row = self.prompts.get(prompt_id)
        return dict(row) if row is not None else None

    def create_version(
        self,
        prompt_version_id: str,
        prompt_id: str,
        version: int,
        body: str,
        output_format: str,
        extraction_schema_json: dict[str, Any] | None = None,
    ) -> None:
        self.versions[prompt_id] = {
            "prompt_version_id": prompt_version_id,
            "prompt_id": prompt_id,
            "version": version,
            "body": body,
            "output_format": output_format,
            "extraction_schema_json": extraction_schema_json,
        }

    def get_latest_version(self, prompt_id: str) -> dict[str, Any] | None:
        row = self.versions.get(prompt_id)
        return dict(row) if row is not None else None


@dataclass
class _ProfileStore:
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create_profile(self, profile_id: str, name: str, base_url: str) -> None:
        self.rows[profile_id] = {
            "profile_id": profile_id,
            "name": name,
            "base_url": base_url,
        }

    def get(self, profile_id: str) -> dict[str, Any] | None:
        row = self.rows.get(profile_id)
        return dict(row) if row is not None else None

    def update_profile(self, profile_id: str, name: str, base_url: str) -> None:
        self.rows[profile_id] = {
            "profile_id": profile_id,
            "name": name,
            "base_url": base_url,
        }


class _FakeEmbedder:
    def model_name(self) -> str:
        return "qwen3-embedding:latest"

    def model_id(self) -> str:
        return "qwen3-embedding"

    def model_version(self) -> str:
        return "latest"

    def dimension(self) -> int:
        return 2

    def normalization_policy(self) -> str:
        return "l2"

    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0]


def test_bootstrap_analysis_defaults_is_idempotent() -> None:
    prompts = _PromptStore()
    profiles = _ProfileStore()
    first = bootstrap_analysis_defaults(
        prompt_store=prompts,
        profile_store=profiles,
        llm_base_url="http://localhost:8000",
        profile_name="default",
        model_name="custom-acquire-model",
    )
    second = bootstrap_analysis_defaults(
        prompt_store=prompts,
        profile_store=profiles,
        llm_base_url="http://localhost:8000",
        profile_name="default",
        model_name="custom-acquire-model",
    )
    third = bootstrap_analysis_defaults(
        prompt_store=prompts,
        profile_store=profiles,
        llm_base_url="http://localhost:9000",
        profile_name="updated",
        model_name="custom-acquire-model",
    )
    assert first == second == third
    assert first.prompt_id == ACQUISITION_PROMPT_ID
    assert first.profile_id == ACQUISITION_PROFILE_ID
    assert first.model_name == "custom-acquire-model"
    assert prompts.get_latest_version(ACQUISITION_PROMPT_ID) is not None
    profile = profiles.get(ACQUISITION_PROFILE_ID)
    assert profile is not None
    assert profile["name"] == "updated"
    assert profile["base_url"] == "http://localhost:9000"


def test_markdown_reader_rejects_path_outside_blob_root(tmp_path: Path) -> None:
    markdown_root = tmp_path / "md"
    markdown_root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    store = SimpleNamespace(
        _paths=SimpleNamespace(md_dir=markdown_root),
        get_markdown_path=lambda _paper_id: outside,
    )

    try:
        markdown_reader(store)("p1")
    except ValueError as exc:
        assert "outside the blob root" in str(exc)
    else:
        raise AssertionError("markdown path outside blob root must fail closed")


def test_compose_default_runtime_restores_paper_database_binding(tmp_path: Path) -> None:
    from papers.infra.piccolo.database import PiccoloDatabase
    from papers.infra.piccolo.stores import (
        PiccoloJobQueue,
        PiccoloProfileStore,
        PiccoloPromptStore,
    )

    paper_database = PiccoloDatabase(tmp_path / "papers.sqlite")
    paper_database.initialize_schema()
    prompt_store = PiccoloPromptStore()
    profile_store = PiccoloProfileStore()
    job_queue = PiccoloJobQueue()
    job_id = job_queue.enqueue("discover", None, None, {})
    papers = SimpleNamespace(
        db=paper_database,
        settings=SimpleNamespace(
            llm=SimpleNamespace(default_profile="default", default_model="acquire-model-x")
        ),
        prompt_store=prompt_store,
        profile_store=profile_store,
        job_queue=job_queue,
        candidate_store=SimpleNamespace(),
        paper_store=SimpleNamespace(),
        analysis_store=SimpleNamespace(),
        scholar_client=SimpleNamespace(),
        blob_store=None,
        job_runner=SimpleNamespace(run_next=lambda _now: False),
        external_id_store=None,
        atomic_candidate_import=None,
        project_store=None,
        tag_store=None,
        embedder=_FakeEmbedder(),
    )

    runtime = compose_default_runtime(
        papers=papers,
        nsqd_db_path=tmp_path / "nsqd.sqlite",
        nsqd_index_path=tmp_path / "nsqd-index",
        llm_base_url="http://localhost:8000",
        clock=FixedClock(datetime(2024, 1, 1, tzinfo=UTC)),
    )

    assert runtime.nsqd.database.path == tmp_path / "nsqd.sqlite"
    assert prompt_store.get_prompt(ACQUISITION_PROMPT_ID) is not None
    assert profile_store.get(ACQUISITION_PROFILE_ID) is not None
    assert [row["job_id"] for row in job_queue.list_jobs()] == [job_id]
    assert runtime.analysis_defaults.model_name == "acquire-model-x"

    incompatible_db = tmp_path / "incompatible-nsqd.sqlite"
    with sqlite3.connect(incompatible_db) as connection:
        connection.execute("CREATE TABLE nsqd_jobs (wrong_column TEXT)")
    with pytest.raises(ConfigurationError, match="schema mismatch"):
        compose_default_runtime(
            papers=papers,
            nsqd_db_path=incompatible_db,
            nsqd_index_path=tmp_path / "bad-nsqd-index",
            llm_base_url="http://localhost:8000",
            clock=FixedClock(datetime(2024, 1, 1, tzinfo=UTC)),
        )

    assert prompt_store.get_prompt(ACQUISITION_PROMPT_ID) is not None
    assert profile_store.get(ACQUISITION_PROFILE_ID) is not None
    assert [row["job_id"] for row in job_queue.list_jobs()] == [job_id]


def test_compose_default_runtime_wires_production_bridge_and_worker(tmp_path: Path) -> None:
    ran = {"count": 0}

    class _Runner:
        def run_next(self, now: datetime) -> bool:
            ran["count"] += 1
            return False

    papers = SimpleNamespace(
        settings=SimpleNamespace(
            data=SimpleNamespace(db_path=tmp_path / "app.sqlite"),
            llm=SimpleNamespace(default_profile="default", default_model="runtime-model-z"),
        ),
        candidate_store=SimpleNamespace(
            create_candidate=lambda fields: fields["candidate_id"],
            get_candidate=lambda _cid: None,
            get_candidate_by_source=lambda *_a: None,
        ),
        paper_store=SimpleNamespace(get=lambda _pid: None),
        job_queue=SimpleNamespace(enqueue=lambda **_k: "job"),
        scholar_client=SimpleNamespace(
            search=lambda **_k: [],
        ),
        prompt_store=_PromptStore(),
        profile_store=_ProfileStore(),
        analysis_store=SimpleNamespace(),
        blob_store=SimpleNamespace(get_markdown_path=lambda _pid: None),
        job_runner=_Runner(),
        atomic_candidate_import=None,
        project_store=None,
        tag_store=None,
        external_id_store=None,
        embedder=_FakeEmbedder(),
    )
    runtime = compose_default_runtime(
        papers=papers,
        nsqd_db_path=tmp_path / "nsqd.sqlite",
        nsqd_index_path=tmp_path / "nsqd-index",
        llm_base_url="http://localhost:8000",
    )
    assert runtime.nsqd.ctx.embedder is papers.embedder
    assert isinstance(runtime.nsqd.ctx.bridge, PapersAcquisitionBridge)
    assert not isinstance(runtime.nsqd.ctx.bridge, NullPaperAcquisitionBridge)
    assert runtime.analysis_defaults.prompt_id == ACQUISITION_PROMPT_ID
    assert runtime.analysis_defaults.model_name == "runtime-model-z"
    assert runtime.paper_runner.run_next(datetime(2024, 1, 1, tzinfo=UTC)) is False
    assert ran["count"] == 1
    assert runtime.nsqd.database.path == tmp_path / "nsqd.sqlite"


def test_build_container_defaults_to_no_embedder(tmp_path: Path) -> None:
    container = build_nsqd_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "nsqd-index",
    )

    assert container.ctx.embedder is None


def test_markdown_reader_handles_missing_and_unreadable_paths(tmp_path: Path) -> None:
    assert markdown_reader(None)("p1") is None
    assert markdown_reader(SimpleNamespace())("p1") is None
    assert markdown_reader(SimpleNamespace(get_markdown_path=lambda _pid: None))("p1") is None
    readable = tmp_path / "paper.md"
    readable.write_text("mechanism draft", encoding="utf-8")
    assert (
        markdown_reader(SimpleNamespace(get_markdown_path=lambda _pid: readable))("p1")
        == "mechanism draft"
    )
    missing = tmp_path / "missing.md"
    assert markdown_reader(SimpleNamespace(get_markdown_path=lambda _pid: missing))("p1") is None
    oversized = tmp_path / "oversized.md"
    oversized.write_bytes(b"x" * (10 * 1024 * 1024 + 1))
    try:
        markdown_reader(SimpleNamespace(get_markdown_path=lambda _pid: oversized))("p1")
    except ValueError as exc:
        assert "paper markdown is too large" in str(exc)
    else:
        raise AssertionError("oversized markdown must fail closed")

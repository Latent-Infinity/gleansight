from __future__ import annotations

import ast
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

import nsqd.composition as composition_module
from nsqd.composition import build_container
from nsqd.null_adapters import FixedClock
from nsqd.runner import run_job
from nsqd.skeleton import run_skeleton
from papers.config.settings import DEFAULT_OLLAMA_BASE_URL, packaged_defaults_path
from papers.config.settings import load_settings as load_paper_settings
from papers.infra.piccolo.database import PiccoloDatabase
from tests.support.import_boundary import scan_tree

REPO_ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


def test_default_local_qwen_embedder_factory_uses_no_auth_ollama_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()
    settings = load_paper_settings(defaults_path=packaged_defaults_path())

    def fake_build_configured_ollama_embedder(embedding_settings) -> object:
        captured["model"] = embedding_settings.model
        captured["dimension"] = embedding_settings.dimension
        captured["base_url"] = embedding_settings.base_url
        return sentinel

    monkeypatch.setattr(
        composition_module,
        "build_configured_ollama_embedder",
        fake_build_configured_ollama_embedder,
    )

    assert composition_module.build_local_ollama_embedder(settings.embeddings) is sentinel
    assert captured == {
        "model": "qwen3-embedding:latest",
        "dimension": 4096,
        "base_url": DEFAULT_OLLAMA_BASE_URL,
    }


def test_scanner_rejects_nsqd_infra_import_from_application(tmp_path: Path) -> None:
    package = tmp_path / "nsqd" / "app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text(
        "from nsqd.infra.piccolo.stores import PiccoloNsqdJobQueue\n",
        encoding="utf-8",
    )
    leaks = scan_tree(package)
    assert any("nsqd.infra.piccolo.stores" in item for item in leaks)


def test_nsqd_domain_does_not_call_datetime_now() -> None:
    leaks: list[str] = []
    root = REPO_ROOT / "src" / "nsqd" / "domain"
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "now":
                continue
            leaks.append(f"{path}:{node.lineno}")
    assert leaks == []


def test_job_queue_persists_injected_clock_timestamps(tmp_path: Path) -> None:
    from nsqd.infra.piccolo.stores import PiccoloNsqdJobQueue

    db = PiccoloDatabase(tmp_path / "nsqd.sqlite")
    db.initialize_schema()
    queue = PiccoloNsqdJobQueue(db, clock=FixedClock(AS_OF))
    job_id = queue.enqueue("map", {"n": 1})
    row = db.fetchone(
        "SELECT created_at, updated_at FROM nsqd_jobs WHERE job_id = ?",
        [job_id],
    )
    assert row is not None
    assert row["created_at"] == AS_OF
    assert row["updated_at"] == AS_OF
    later = datetime(2024, 6, 2, tzinfo=UTC)
    queue = PiccoloNsqdJobQueue(db, clock=FixedClock(later))
    claimed = queue.claim_job(job_id, later)
    assert claimed is not None
    queue.mark_succeeded(job_id)
    updated = db.fetchone(
        "SELECT updated_at FROM nsqd_jobs WHERE job_id = ?",
        [job_id],
    )
    assert updated is not None
    assert updated["updated_at"] == later


def test_runner_logs_utc_job_transitions(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    from nsqd.app.use_cases import empty_smoke_snapshot_id

    container = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "corpus.lancedb",
        clock=FixedClock(AS_OF),
    )
    snapshot_id = empty_smoke_snapshot_id()
    container.ctx.snapshots.commit(snapshot_id, [], schema_version=1)
    caplog.set_level(logging.INFO, logger="nsqd.runner")
    run_job(
        container,
        "map",
        {
            "snapshot_id": snapshot_id,
            "domain_policy_id": "finance/1",
            "snapshot_state": "smoke_only",
        },
        AS_OF,
    )
    extras = [record.__dict__ for record in caplog.records if record.name == "nsqd.runner"]
    assert extras
    for extra in extras:
        assert extra.get("timestamp") == AS_OF.isoformat()
        assert extra.get("job_id")
        assert extra.get("job_type") == "map"
        assert extra.get("status_from")
        assert extra.get("status_to")
    transitions = {(item.get("status_from"), item.get("status_to")) for item in extras}
    assert ("queued", "running") in transitions
    assert ("running", "succeeded") in transitions


def test_run_skeleton_remains_intentionally_unconfigured_for_smoke(tmp_path: Path) -> None:
    result = run_skeleton(
        fixture_path=REPO_ROOT / "tests" / "fixtures" / "approved" / "nsqd" / "gamma-flow.yaml",
        axiom="predictors assume stationary return signal",
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "corpus.lancedb",
        as_of=AS_OF,
    )

    assert result["grounding"]["measurement_stamp"] == {
        "embedding_model_id": "unconfigured",
        "embedding_model_version": "unconfigured",
        "embedding_dimension": 0,
        "normalization_policy": "unknown",
        "distance_metric": "cosine_distance",
        "algorithm_contract_version": "1.1",
    }

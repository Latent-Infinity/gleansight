from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from nsqd.composition import build_container
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.project_runtime import run_project
from nsqd.runner import run_job

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"


def _copy_project_fixture_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    fixture_dir = tmp_path / "approved-nsqd"
    fixture_dir.mkdir()
    for name in ("manifest.toml", "paper-a.yaml", "paper-a.md"):
        shutil.copy(FIXTURES / name, fixture_dir / name)
    return fixture_dir / "manifest.toml", fixture_dir / "paper-a.yaml", fixture_dir / "paper-a.md"


def _load_projection(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_run_project_loads_approved_fixture_through_shared_queue_runner(tmp_path: Path) -> None:
    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    db_path = tmp_path / "nsqd.sqlite"

    result = run_project(
        projection_path=projection_path,
        manifest_path=manifest_path,
        db_path=db_path,
        index_path=tmp_path / "corpus.lancedb",
        as_of=AS_OF,
    )

    assert result["status"] == "succeeded"
    assert result["created"] is True

    container = build_container(db_path=db_path, index_path=tmp_path / "corpus.lancedb")
    stored = container.ctx.records.get(str(result["record_id"]))
    assert stored is not None
    assert stored["domain_policy_id"] == "optimization/1"
    job_row = container.database.fetchone(
        "SELECT status, payload_json FROM nsqd_jobs WHERE type = 'project'"
    )
    assert job_row is not None
    assert job_row["status"] == "succeeded"
    payload_json = str(job_row["payload_json"])
    assert str(manifest_path) not in payload_json
    assert "reviewed_projection_digest" not in payload_json


def test_run_project_rejects_tampered_fixture_bytes(tmp_path: Path) -> None:
    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    projection_path.write_text(projection_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    db_path = tmp_path / "tampered.sqlite"

    with pytest.raises(ValueError, match="content hash"):
        run_project(
            projection_path=projection_path,
            manifest_path=manifest_path,
            db_path=db_path,
            index_path=tmp_path / "tampered-index",
            as_of=AS_OF,
        )

    container = build_container(db_path=db_path, index_path=tmp_path / "tampered-index")
    job_row = container.database.fetchone(
        "SELECT status, last_error FROM nsqd_jobs WHERE type = 'project'"
    )
    assert job_row is None


def test_run_project_rejects_missing_manifest_approval(tmp_path: Path) -> None:
    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    manifest_text = manifest_path.read_text(encoding="utf-8")
    marker = "[fixture.DATA-NSQD-04]"
    start = manifest_text.index(marker)
    manifest_text = manifest_text[:start].rstrip() + "\n"
    manifest_path.write_text(manifest_text, encoding="utf-8")
    db_path = tmp_path / "missing.sqlite"

    with pytest.raises(ValueError, match="not approved in manifest"):
        run_project(
            projection_path=projection_path,
            manifest_path=manifest_path,
            db_path=db_path,
            index_path=tmp_path / "missing-index",
            as_of=AS_OF,
        )

    container = build_container(db_path=db_path, index_path=tmp_path / "missing-index")
    job_row = container.database.fetchone(
        "SELECT status, last_error FROM nsqd_jobs WHERE type = 'project'"
    )
    assert job_row is None


def test_project_job_payload_cannot_self_approve_through_shared_runner(tmp_path: Path) -> None:
    container = build_container(
        db_path=tmp_path / "self-approve.sqlite",
        index_path=tmp_path / "self-approve-index",
    )
    projection = _load_projection(FIXTURES / "paper-a.yaml")
    projection["reviewed_projection_digest"] = canonical_reviewed_projection_digest(projection)

    with pytest.raises(ValueError, match="approved reviewed projection"):
        run_job(
            container,
            "project",
            {
                "domain_policy_id": "optimization/1",
                "projection": projection,
            },
            AS_OF,
        )

    job_row = container.database.fetchone(
        "SELECT status, payload_json, last_error FROM nsqd_jobs WHERE type = 'project'"
    )
    assert job_row is not None
    assert job_row["status"] == "failed"
    assert "reviewed_projection_digest" in str(job_row["payload_json"])
    assert "approved reviewed projection" in str(job_row["last_error"])

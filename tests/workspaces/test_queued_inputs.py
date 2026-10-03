import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from gleansight.api.models import Failure, Success
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from gleansight.workspaces.models import Manifest
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloJobQueue, PiccoloPaperStore
from tests.workspaces.support import api, backup


def test_queued_external_pdf_is_preserved_and_rebased(workspace: Path, tmp_path: Path) -> None:
    runtime = ApiRuntime(ApiConfiguration(repo_root=workspace))
    runtime.paper_database.bind_tables()
    source = tmp_path / "incoming.pdf"
    source.write_bytes(b"%PDF-1.4\nQueued paper input\n")
    job_id = PiccoloJobQueue().enqueue("download", "paper-1", None, {"source_path": str(source)})
    PiccoloPaperStore().create_paper({"paper_id": "history-paper", "title": "Earlier paper"})
    terminal = PiccoloJobQueue().enqueue(
        "download", "history-paper", None, {"source_path": "/gone/old.pdf"}
    )
    runtime.paper_database.execute(
        "UPDATE jobs SET status = 'succeeded' WHERE job_id = ?", [terminal]
    )
    bundle = backup(workspace)
    manifest = Manifest.model_validate_json((bundle / "manifest.json").read_bytes())
    entry = next(item for item in manifest.files if item.source == source)
    assert entry.target.startswith("external-inputs/")
    destination = tmp_path / "restored"
    result = api(workspace, approval=True).call(
        "workspaces.restore", {"backup_path": str(bundle), "destination": str(destination)}
    )
    assert isinstance(result, Success), result
    restored_db = PiccoloDatabase(destination / "data/db/app.sqlite", bind_on_init=False)
    row = restored_db.fetchone("SELECT status, payload_json FROM jobs WHERE job_id = ?", [job_id])
    assert row is not None and row["status"] == "queued"
    payload = TypeAdapter(dict[str, str]).validate_json(row["payload_json"])
    assert Path(payload["source_path"]).read_bytes() == source.read_bytes()
    assert Path(payload["source_path"]).is_relative_to(destination)
    history = restored_db.fetchone("SELECT payload_json FROM jobs WHERE job_id = ?", [terminal])
    assert history == runtime.paper_database.fetchone(
        "SELECT payload_json FROM jobs WHERE job_id = ?", [terminal]
    )


@pytest.mark.parametrize("mode", ["text", "fake_pdf", "symlink", "credentials", "missing"])
def test_external_input_guards(workspace: Path, tmp_path: Path, mode: str) -> None:
    runtime = ApiRuntime(ApiConfiguration(repo_root=workspace))
    runtime.paper_database.bind_tables()
    source = tmp_path / ("credentials.pdf" if mode == "credentials" else "incoming.pdf")
    source.write_bytes(b"%PDF-1.4\ninput\n")
    if mode == "text":
        source = tmp_path / "input.txt"
        source.write_text("text")
    elif mode == "fake_pdf":
        source.write_text("not a PDF")
    elif mode == "symlink":
        link = tmp_path / "link.pdf"
        link.symlink_to(source)
        source = link
    elif mode == "missing":
        source.unlink()
    PiccoloJobQueue().enqueue("download", "paper-1", None, {"source_path": str(source)})
    result = api(workspace).call("workspaces.backup", {})
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"


def test_claim_cannot_start_during_capture(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gleansight.workspaces import backup as module

    runtime = ApiRuntime(ApiConfiguration(repo_root=workspace))
    runtime.paper_database.bind_tables()
    job = PiccoloJobQueue().enqueue("convert", "paper-1", None, {})
    original = module.snapshot_database
    blocked: list[bool] = []

    def snapshot(source: Path, destination: Path) -> None:
        with closing(sqlite3.connect(runtime.settings.data.db_path, timeout=0)) as writer:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                writer.execute("UPDATE jobs SET status = 'running' WHERE job_id = ?", (job,))
            blocked.append(True)
        original(source, destination)

    monkeypatch.setattr(module, "snapshot_database", snapshot)
    bundle = backup(workspace)
    assert blocked and (bundle / "manifest.json").is_file()


@pytest.mark.parametrize("phase", ["starting", "running", "paused", "stopping"])
def test_supervisor_activity_refuses_backup(workspace: Path, phase: str) -> None:
    db = ApiRuntime(ApiConfiguration(repo_root=workspace)).paper_database
    db.execute(
        "CREATE TABLE IF NOT EXISTS supervised_workers "
        "(worker_id TEXT PRIMARY KEY, desired_state TEXT, phase TEXT, document_json TEXT)"
    )
    db.execute(
        "INSERT INTO supervised_workers VALUES (?, ?, ?, ?)",
        ["worker", "running", phase, json.dumps({"active_job_id": None})],
    )
    result = api(workspace).call("workspaces.backup", {})
    assert isinstance(result, Failure)
    assert result.error.code == "conflict"

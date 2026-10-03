from pathlib import Path

from pydantic import TypeAdapter

from gleansight.api.models import Failure, Success
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.infra.piccolo.database import PiccoloDatabase
from tests.workspaces.support import api, backup


def test_verified_restore_preserves_authority(workspace: Path, tmp_path: Path) -> None:
    bundle = backup(workspace)
    destination = tmp_path / "restored"
    result = api(workspace, approval=True).call(
        "workspaces.restore", {"backup_path": str(bundle), "destination": str(destination)}
    )
    assert isinstance(result, Success), result
    fields = TypeAdapter(dict[str, str]).validate_python(result.data)
    restored = ApiRuntime(
        ApiConfiguration(repo_root=destination, config_path=Path(fields["config_path"]))
    )
    paper = restored.paper_database.fetchone(
        "SELECT title FROM papers WHERE paper_id = ?", ["paper-1"]
    )
    assert paper is not None and paper["title"] == "Preserved research"
    nsqd = PiccoloDatabase(destination / "data/nsqd/nsqd.sqlite", bind_on_init=False)
    digest = nsqd.fetchone("SELECT digest FROM nsqd_approved_projection_digests")
    assert digest is not None and digest["digest"] == "a" * 64
    assert (destination / "evidence/source.md").read_bytes() == (
        workspace / "evidence/source.md"
    ).read_bytes()
    assert not list(destination.rglob(".env"))
    assert fields["index_disposition"] == "rebuild_required"
    project = restored.paper_database.fetchone("SELECT paper_id, project_id FROM paper_projects")
    assert project is not None and project["project_id"] == "project-1"
    run = restored.paper_database.fetchone(
        "SELECT * FROM analysis_runs WHERE run_id = ?", ["run-1"]
    )
    assert run is not None and run["prompt_version_id"] == "prompt-1"
    assert str(run["output_blob_path_json"]).startswith(str(destination))
    assert (
        Path(str(run["output_blob_path_json"])).read_bytes()
        == (workspace / "data/blobs/analysis/run-1/output.json").read_bytes()
    )
    source_nsqd = PiccoloDatabase(workspace / "data/nsqd/nsqd.sqlite", bind_on_init=False)
    assert source_nsqd.fetchone("SELECT payload_json FROM nsqd_corpus_records") == (
        nsqd.fetchone("SELECT payload_json FROM nsqd_corpus_records")
    )


def test_restore_requires_approval(workspace: Path, tmp_path: Path) -> None:
    bundle = backup(workspace)
    result = api(workspace).call(
        "workspaces.restore",
        {"backup_path": str(bundle), "destination": str(tmp_path / "restored")},
    )
    assert isinstance(result, Failure)
    assert result.error.code == "approval_required"

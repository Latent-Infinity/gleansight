import hashlib
import json
from pathlib import Path

import pytest

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Failure, Success
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from gleansight.workspaces.models import Manifest
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.piccolo.stores import PiccoloPaperStore
from tests.workspaces.support import api, backup


@pytest.mark.parametrize(
    "change", ["duplicates", "missing_database", "no_databases", "unsafe_config", "reserved_target"]
)
def test_invalid_manifest_contracts_are_rejected(workspace: Path, change: str) -> None:
    bundle = backup(workspace)
    path = bundle / "manifest.json"
    value = json.loads(path.read_text())
    if change == "duplicates":
        value["files"].append(value["files"][0])
    elif change == "missing_database":
        value["files"] = [item for item in value["files"] if item["category"] != "database"]
    elif change == "no_databases":
        value["databases"] = []
    elif change == "unsafe_config":
        value["workspace"]["data_paths"] = {"db_path": "../escape"}
    else:
        value["files"][0]["target"] = ".gleansight-restore.toml"
    payload = json.dumps(value).encode()
    path.write_bytes(payload)
    (bundle / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest())
    result = api(workspace).call("workspaces.verify", {"backup_path": str(bundle)})
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"


def test_missing_manifest_is_rejected(workspace: Path) -> None:
    result = api(workspace).call("workspaces.verify", {"backup_path": str(workspace / "missing")})
    assert isinstance(result, Failure)


def test_no_database_does_not_create_a_workspace(tmp_path: Path) -> None:
    result = api(tmp_path).call("workspaces.backup", {})
    assert isinstance(result, Failure)
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("kind", ["secret", "symlink", "outside"])
def test_required_unsafe_artifact_is_rejected(workspace: Path, tmp_path: Path, kind: str) -> None:
    evidence = workspace / "evidence" / "unsafe.json"
    if kind == "secret":
        evidence.write_text(json.dumps({"source_path": str(workspace / ".env")}))
    elif kind == "symlink":
        evidence.symlink_to(workspace / "evidence/source.md")
    else:
        external = tmp_path / "external.md"
        external.write_text("External unconfigured file")
        evidence.write_text(json.dumps({"source_path": str(external)}))
    result = api(workspace).call("workspaces.backup", {})
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"


def test_configured_external_resources_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    external = tmp_path / "storage"
    external.mkdir()
    config = root / "settings.toml"
    values = {
        "db_path": str(external / "papers.sqlite"),
        "blobs_dir": str(external / "blobs"),
        "blobs_pdf_dir": str(external / "blobs/pdf"),
        "blobs_md_dir": str(external / "blobs/md"),
        "blobs_analysis_dir": str(external / "blobs/analysis"),
    }
    config.write_text(
        "[data]\n" + "\n".join(f"{key} = {json.dumps(value)}" for key, value in values.items())
    )
    configuration = ApiConfiguration(repo_root=root, config_path=config, allow_approvals=True)
    runtime = ApiRuntime(configuration)
    db = runtime.paper_database
    PiccoloPaperStore().create_paper({"paper_id": "external-paper", "title": "External"})
    blobs = FileSystemBlobStore(runtime.settings.data.blobs_dir)
    _, fingerprint = blobs.put_markdown("external-paper", "External paper bytes")
    db.execute("UPDATE papers SET md_fingerprint_xxh64 = ?", [fingerprint])
    client = GleansightAPI(configuration)
    created = client.call("workspaces.backup", {})
    assert isinstance(created, Success) and isinstance(created.data, dict)
    bundle = created.data["backup_path"]
    assert isinstance(bundle, str)
    manifest = Manifest.model_validate_json((Path(bundle) / "manifest.json").read_bytes())
    assert any(entry.target == "data/blobs/md/external-paper.md" for entry in manifest.files)
    destination = tmp_path / "restored"
    destination.mkdir()
    result = client.call(
        "workspaces.restore", {"backup_path": bundle, "destination": str(destination)}
    )
    assert isinstance(result, Success), result
    assert (destination / "data/blobs/md/external-paper.md").read_text() == "External paper bytes"


def test_transitive_authority_artifacts_are_preserved(workspace: Path) -> None:
    packet = workspace / "evidence/archive/reviews/v1/packet"
    packet.mkdir(parents=True)
    (packet / "projection.yaml").write_text("source_excerpt_path: excerpt.md\nvalue: 研究\n")
    (packet / "excerpt.md").write_text("Immutable source excerpt")
    (packet / "manifest.toml").write_text('[fixture.paper]\npath = "projection.yaml"\n')
    output = workspace / "output/review/run-1"
    output.mkdir(parents=True)
    (output / "findings.md").write_text("Generated report")
    (packet / "review.json").write_text(
        json.dumps({"reports": [{"path": "output/review/run-1/findings.md"}]})
    )
    bundle = backup(workspace)
    manifest = Manifest.model_validate_json((bundle / "manifest.json").read_bytes())
    assert any(
        entry.category == "archive" and entry.target.endswith("projection.yaml")
        for entry in manifest.files
    )
    assert any(
        entry.category == "generated" and entry.target.endswith("findings.md")
        for entry in manifest.files
    )
    for entry in manifest.files:
        if entry.category != "database":
            assert entry.source.read_bytes() == (bundle / entry.bundle_path).read_bytes()


def test_required_reference_through_symlink_directory_is_rejected(
    workspace: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "private-inputs"
    outside.mkdir()
    (outside / "source.md").write_text("External file must not enter the bundle")
    (workspace / "linked").symlink_to(outside, target_is_directory=True)
    (workspace / "evidence/unsafe.json").write_text(
        json.dumps({"source_path": str(workspace / "linked/source.md")})
    )
    result = api(workspace).call("workspaces.backup", {})
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"


def test_separately_configured_markdown_directory_is_captured(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    config = root / "settings.toml"
    config.write_text('[data]\nblobs_md_dir = "separate-markdown"\n')
    configuration = ApiConfiguration(repo_root=root, config_path=config)
    runtime = ApiRuntime(configuration)
    database = runtime.paper_database
    PiccoloPaperStore().create_paper({"paper_id": "split-paper", "title": "Split storage"})
    blobs = FileSystemBlobStore(runtime.settings.data.blobs_dir)
    original, fingerprint = blobs.put_markdown("split-paper", "Separate configured artifact")
    configured = runtime.settings.data.blobs_md_dir / "split-paper.md"
    configured.parent.mkdir(parents=True)
    original.rename(configured)
    database.execute("UPDATE papers SET md_fingerprint_xxh64 = ?", [fingerprint])
    result = GleansightAPI(configuration).call("workspaces.backup", {})
    assert isinstance(result, Success), result
    assert isinstance(result.data, dict)
    bundle = Path(str(result.data["backup_path"]))
    manifest = Manifest.model_validate_json((bundle / "manifest.json").read_bytes())
    entry = next(item for item in manifest.files if item.source == configured)
    assert (bundle / entry.bundle_path).read_text() == "Separate configured artifact"

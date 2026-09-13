from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from nsqd.domain.tau_review import autonomous_tau_review_packet_digest
from scripts import (
    run_tau_candidate_acquisition,
    run_tau_label_collection,
)


def test_candidate_acquisition_defaults_to_fresh_workflow_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "packet" / "manifest.json"
    manifest.parent.mkdir()
    fixture = manifest.parent / "candidate.yaml"
    fixture.write_text("id: candidate\n", encoding="utf-8")
    from nsqd.app.use_cases import artifact_hash_for

    candidate_hash = artifact_hash_for({"id": "candidate"})
    manifest.write_text(
        json.dumps(
            {
                "snapshot_id": "snapshot",
                "corpus_version": 11,
                "candidates": [
                    {
                        "candidate_id": "candidate",
                        "candidate_artifact_hash": candidate_hash,
                        "candidate_fixture": fixture.name,
                        "domain_policy_id": "finance/1",
                        "axiom": "axiom",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "output" / "tau-candidate-acquisition" / "run"
    monkeypatch.setattr(
        run_tau_candidate_acquisition,
        "create_run_directory",
        lambda _root, _workflow, _output=None: (
            run_dir.mkdir(parents=True, exist_ok=True) or run_dir
        ),
    )
    monkeypatch.setattr(
        run_tau_candidate_acquisition,
        "_run",
        lambda command, *, timeout_s: (
            f"candidate={candidate_hash}" if "diverge" in command else '{"grounding_class":"near"}'
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_tau_candidate_acquisition.py", "--manifest", str(manifest)],
    )

    assert run_tau_candidate_acquisition.main() == 0

    output = run_dir / "acquired-candidates.json"
    assert output.is_file()
    assert not (manifest.parent / "acquired-candidates.json").exists()


def test_candidate_acquisition_explicit_checkpoint_resumes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    packet_dir = tmp_path / "packet"
    packet_dir.mkdir()
    manifest = packet_dir / "manifest.json"
    candidate_hash = "a" * 64
    manifest.write_text(
        json.dumps(
            {
                "snapshot_id": "snapshot",
                "corpus_version": 11,
                "candidates": [
                    {
                        "candidate_id": "candidate",
                        "candidate_artifact_hash": candidate_hash,
                        "candidate_fixture": "unused.yaml",
                        "domain_policy_id": "finance/1",
                        "axiom": "axiom",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "run" / "acquired-candidates.json"
    output.parent.mkdir()
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_manifest": str(manifest),
                "snapshot_id": "snapshot",
                "corpus_version": 11,
                "candidates": [{"candidate_artifact_hash": candidate_hash}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run_tau_candidate_acquisition,
        "_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed candidate must be skipped")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_tau_candidate_acquisition.py",
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ],
    )

    assert run_tau_candidate_acquisition.main() == 0


def test_label_collection_defaults_checkpoints_to_fresh_workflow_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    packet_dir = tmp_path / "immutable-packet"
    packet_dir.mkdir()
    (packet_dir / "candidate-hashes.json").write_text(
        json.dumps({"finance/1": [], "optimization/1": []}),
        encoding="utf-8",
    )
    run_dir = tmp_path / "output" / "tau-label-collection" / "run"
    monkeypatch.setattr(
        run_tau_label_collection,
        "create_run_directory",
        lambda _root, _workflow, _output=None: (
            run_dir.mkdir(parents=True, exist_ok=True) or run_dir
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_tau_label_collection.py",
            "--packet-dir",
            str(packet_dir),
            "--worker-index",
            "0",
            "--worker-count",
            "1",
        ],
    )

    assert run_tau_label_collection.main() == 0
    assert (run_dir / "autonomous-label-rows").is_dir()
    assert set(packet_dir.iterdir()) == {packet_dir / "candidate-hashes.json"}


def test_label_collection_explicit_output_run_resumes_without_writing_packet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    packet_dir = tmp_path / "immutable-packet"
    packet_dir.mkdir()
    candidate_hash = "a" * 64
    (packet_dir / "candidate-hashes.json").write_text(
        json.dumps(
            {
                "finance/1": [{"candidate_artifact_hash": candidate_hash}],
                "optimization/1": [],
            }
        ),
        encoding="utf-8",
    )
    output_run = tmp_path / "existing-run"
    checkpoint_dir = output_run / "autonomous-label-rows"
    checkpoint_dir.mkdir(parents=True)
    row = {"candidate_artifact_hash": candidate_hash, "final_label": "novel"}
    (checkpoint_dir / f"{candidate_hash}.json").write_text(
        json.dumps({"rows": [row], "packet_digest": autonomous_tau_review_packet_digest([row])}),
        encoding="utf-8",
    )

    def reject_subprocess(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("resume must not execute a model subprocess")

    monkeypatch.setattr(run_tau_label_collection.subprocess, "run", reject_subprocess)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_tau_label_collection.py",
            "--packet-dir",
            str(packet_dir),
            "--output-dir",
            str(output_run),
            "--worker-index",
            "0",
            "--worker-count",
            "1",
        ],
    )

    assert run_tau_label_collection.main() == 0
    assert set(packet_dir.iterdir()) == {packet_dir / "candidate-hashes.json"}


def test_label_collection_relative_output_resumes_repo_run_from_changed_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    packet_dir = tmp_path / "immutable-packet"
    packet_dir.mkdir()
    (packet_dir / "candidate-hashes.json").write_text(
        json.dumps({"finance/1": [], "optimization/1": []}),
        encoding="utf-8",
    )
    relative_output = Path("output/tau-label-collection/existing-run")
    output_run = repository / relative_output
    output_run.mkdir(parents=True)
    caller_cwd = tmp_path / "caller"
    caller_cwd.mkdir()
    monkeypatch.chdir(caller_cwd)
    monkeypatch.setattr(run_tau_label_collection, "REPO_ROOT", repository)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_tau_label_collection.py",
            "--packet-dir",
            str(packet_dir),
            "--output-dir",
            str(relative_output),
            "--worker-index",
            "0",
            "--worker-count",
            "1",
        ],
    )

    assert run_tau_label_collection.main() == 0
    assert (output_run / "autonomous-label-rows").is_dir()
    assert not (caller_cwd / relative_output).exists()

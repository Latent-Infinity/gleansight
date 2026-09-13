from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import (
    build_balanced_tau_packet,
    build_tau_evidence_summary,
    build_tau_near_duplicate_candidates,
)


def test_balanced_packet_defaults_both_reports_to_one_fresh_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    packet_dir = tmp_path / "immutable-packet"
    packet_dir.mkdir()
    run_dir = tmp_path / "output" / "balanced-tau-packet" / "run"
    selected = [
        {
            "candidate_artifact_hash": "b" * 64,
            "domain_policy_id": "finance/1",
            "final_label": "novel",
            "input": str(packet_dir / "label.json"),
            "measurement_artifact_digest": "c" * 64,
            "source_packet_digest": "d" * 64,
        }
    ]
    monkeypatch.setattr(build_balanced_tau_packet, "select_balanced_rows", lambda _path: selected)
    monkeypatch.setattr(
        build_balanced_tau_packet,
        "create_run_directory",
        lambda _root, _workflow, _output=None: (
            run_dir.mkdir(parents=True, exist_ok=True) or run_dir
        ),
    )
    monkeypatch.setattr(
        build_balanced_tau_packet.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="evaluation ok", stderr=""),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_balanced_tau_packet.py", "--packet-dir", str(packet_dir)],
    )

    assert build_balanced_tau_packet.main() == 0
    assert (run_dir / "balanced-selection.json").is_file()
    assert not any(packet_dir.iterdir())


def test_balanced_packet_relative_outputs_are_repo_relative_from_changed_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    packet_dir = tmp_path / "immutable-packet"
    packet_dir.mkdir()
    relative_selection = Path("output/balanced-tau-packet/run/selection.json")
    relative_evaluation = Path("output/balanced-tau-packet/run/evaluation.json")
    commands: list[list[str]] = []
    monkeypatch.setattr(build_balanced_tau_packet, "REPO_ROOT", repository)
    monkeypatch.setattr(build_balanced_tau_packet, "select_balanced_rows", lambda _path: [])

    def record_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="evaluation ok", stderr="")

    monkeypatch.setattr(build_balanced_tau_packet.subprocess, "run", record_run)
    caller_cwd = tmp_path / "caller"
    caller_cwd.mkdir()
    monkeypatch.chdir(caller_cwd)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_balanced_tau_packet.py",
            "--packet-dir",
            str(packet_dir),
            "--selection-output",
            str(relative_selection),
            "--evaluation-output",
            str(relative_evaluation),
        ],
    )

    assert build_balanced_tau_packet.main() == 0
    assert (repository / relative_selection).is_file()
    assert str(repository / relative_evaluation) in commands[0]
    assert not (caller_cwd / "output").exists()


def test_near_duplicate_builder_defaults_to_fresh_workflow_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "output" / "tau-near-duplicate-candidates" / "run"
    monkeypatch.setattr(
        build_tau_near_duplicate_candidates,
        "create_run_directory",
        lambda _root, _workflow, _output=None: (
            run_dir.mkdir(parents=True, exist_ok=True) or run_dir
        ),
    )
    monkeypatch.setattr(
        build_tau_near_duplicate_candidates,
        "build_packet",
        lambda _root, output_dir: {"counts_by_policy": {}, "output_dir": str(output_dir)},
    )
    monkeypatch.setattr(sys, "argv", ["build_tau_near_duplicate_candidates.py"])

    assert build_tau_near_duplicate_candidates.main() == 0
    assert (run_dir / "manifest.json").is_file()


def test_evidence_summary_defaults_to_fresh_output_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    packet_dir = tmp_path / "immutable-packet"
    packet_dir.mkdir()
    (packet_dir / "balanced-selection.json").write_text('{"rows_sha256":"rows"}', encoding="utf-8")
    (packet_dir / "balanced-evaluation.json").write_text(
        json.dumps(
            {
                "rows": [],
                "packet_digest": "digest",
                "packet": {
                    "selected_tau": 0.5,
                    "approved_pair_count": 0,
                    "ambiguous_pair_count": 0,
                    "counts_by_policy": {},
                    "thresholds": {},
                },
            }
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "output" / "tau-evidence-summary" / "run"
    monkeypatch.setattr(
        build_tau_evidence_summary,
        "create_run_directory",
        lambda _root, _workflow, _output=None: (
            run_dir.mkdir(parents=True, exist_ok=True) or run_dir
        ),
    )
    monkeypatch.setattr(build_tau_evidence_summary, "_file_sha256", lambda _path: "hash")
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_tau_evidence_summary.py", "--packet-dir", str(packet_dir)],
    )

    assert build_tau_evidence_summary.main() == 0
    assert (run_dir / "evidence-summary.json").is_file()
    assert {path.name for path in packet_dir.iterdir()} == {
        "balanced-selection.json",
        "balanced-evaluation.json",
    }

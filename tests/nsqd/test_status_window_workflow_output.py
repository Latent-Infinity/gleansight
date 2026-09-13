from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nsqd.infrastructure.workflow_output import create_run_directory
from tests.nsqd.status_window_receipt_replay_support import HARVESTED_AT, REPO_ROOT

WORKFLOW = "status-window-replay"
RUN_NAME = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{12}$")
RUN_FILES = {
    "calendar-replay-artifact.json",
    "extracted-timestamp-rows.json",
    "report.md",
    "review-summary.json",
    "run-metadata.json",
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "python", "scripts/replay_status_window_ablation.py", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_default_run_directories_are_utc_named_and_collision_safe(tmp_path: Path) -> None:
    first = create_run_directory(tmp_path, WORKFLOW)
    second = create_run_directory(tmp_path, WORKFLOW)

    assert first.parent == tmp_path / "output" / WORKFLOW
    assert second.parent == first.parent
    assert RUN_NAME.fullmatch(first.name)
    assert RUN_NAME.fullmatch(second.name)
    assert second != first
    assert first.is_dir()
    assert second.is_dir()


def test_explicit_temp_run_directory_is_created_once(tmp_path: Path) -> None:
    output_dir = tmp_path / "explicit-run"

    assert create_run_directory(REPO_ROOT, WORKFLOW, output_dir) == output_dir
    with pytest.raises(FileExistsError):
        create_run_directory(REPO_ROOT, WORKFLOW, output_dir)


@pytest.mark.parametrize("protected", ("docs", "evidence", "src", "tests", "data"))
def test_repository_protected_trees_cannot_be_output_destinations(protected: str) -> None:
    with pytest.raises(ValueError, match="output"):
        create_run_directory(REPO_ROOT, WORKFLOW, REPO_ROOT / protected / "replay")


def test_explicit_temp_cli_writes_complete_fresh_run_metadata(tmp_path: Path) -> None:
    output_dir = tmp_path / "status-window-run"
    before = datetime.now(UTC)

    completed = _run("--output-dir", str(output_dir))

    after = datetime.now(UTC)
    assert completed.returncode == 0, completed.stderr
    assert {path.name for path in output_dir.iterdir()} == RUN_FILES
    result = json.loads(completed.stdout)
    assert result["output_dir"] == str(output_dir)
    metadata = json.loads((output_dir / "run-metadata.json").read_text(encoding="utf-8"))
    generated_at = datetime.fromisoformat(metadata["generated_at_utc"].replace("Z", "+00:00"))
    assert before <= generated_at <= after
    assert metadata["modeled_historical_timestamp_utc"] == HARVESTED_AT
    assert metadata["workflow"] == WORKFLOW
    assert metadata["run_id"] == output_dir.name
    assert set(metadata["artifact_sha256"]) == RUN_FILES - {"run-metadata.json"}
    assert "review_pending" not in (output_dir / "report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("flag", ("--verify-current-receipt", "--verify-retained-replay"))
def test_validation_only_modes_do_not_create_output(flag: str, tmp_path: Path) -> None:
    output_dir = tmp_path / "must-not-exist"

    _run(flag, "--output-dir", str(output_dir))

    assert not output_dir.exists()


def test_cli_rejects_existing_output_without_clobbering(tmp_path: Path) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    sentinel = output_dir / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")

    completed = _run("--output-dir", str(output_dir))

    assert completed.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert set(output_dir.iterdir()) == {sentinel}


def test_cli_rejects_docs_output_without_creating_it() -> None:
    output_dir = REPO_ROOT / "docs" / "status-window-replay-output"

    completed = _run("--output-dir", str(output_dir))

    assert completed.returncode != 0
    assert not output_dir.exists()


def test_help_documents_fresh_default_output_convention() -> None:
    completed = _run("--help")

    assert completed.returncode == 0, completed.stderr
    assert "output/status-window-replay/<UTC-run-id>" in completed.stdout

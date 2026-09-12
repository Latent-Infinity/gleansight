from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.nsqd.status_window_receipt_replay_support import (
    HARVESTED_AT,
    REPO_ROOT,
    _artifact,
    _load_replay_module,
    _records,
)


def test_output_confinement_accepts_sealed_and_system_temp_destinations(tmp_path: Path) -> None:
    replay = _load_replay_module()

    assert replay._require_output_dir(replay.OUTPUT_DIR) == replay.OUTPUT_DIR.resolve()
    assert replay._require_output_dir(tmp_path / "replay") == (tmp_path / "replay").resolve()


def test_verify_current_receipt_runs_exact_historical_verifier(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    replay = _load_replay_module()
    calls = 0

    def verify_receipt() -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal calls
        calls += 1
        return {}, {}

    monkeypatch.setattr(replay, "_verify_historical_receipt", verify_receipt)
    monkeypatch.setattr(
        sys, "argv", ["replay_status_window_ablation.py", "--verify-current-receipt"]
    )

    assert replay.main() == 0
    assert calls == 1
    assert json.loads(capsys.readouterr().out)["verified_current_receipt"] is True


def test_replay_script_rejects_untrusted_packet_arg_and_confines_output_dir(tmp_path: Path) -> None:
    rejected = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/replay_status_window_ablation.py",
            "--packet-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0

    replay = _load_replay_module()
    assert replay._require_output_dir(replay.OUTPUT_DIR) == replay.OUTPUT_DIR.resolve()

    safe_temp = tmp_path / "status-window-replay"
    assert replay._require_output_dir(safe_temp) == safe_temp.resolve()

    tmp_alias = Path("/tmp") / "status-window-replay-alias"
    assert replay._require_output_dir(tmp_alias) == tmp_alias.resolve(strict=False)

    tempdir_alias = Path(tempfile.gettempdir()) / "status-window-replay-tempdir-alias"
    assert replay._require_output_dir(tempdir_alias) == tempdir_alias.resolve(strict=False)

    blocked_repo = REPO_ROOT / "docs" / "unsafe-status-window-replay"
    with pytest.raises(ValueError, match="sealed output directory|allowlisted system temp root"):
        replay._require_output_dir(blocked_repo)

    escaped = tmp_path / "nested" / ".." / "escape"
    with pytest.raises(ValueError, match="parent traversal"):
        replay._require_output_dir(escaped)

    symlink_parent = tmp_path / "symlink-parent"
    symlink_parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        replay._require_output_dir(symlink_parent / "status-window-replay")

    real = tmp_path / "real-dir"
    real.mkdir()
    symlink_leaf = tmp_path / "symlink-leaf"
    symlink_leaf.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        replay._require_output_dir(symlink_leaf)


def test_repository_confinement_takes_precedence_over_system_temp_ancestry() -> None:
    replay = _load_replay_module()

    with pytest.raises(ValueError, match="sealed output directory"):
        replay._require_output_dir(REPO_ROOT / "nested-replay-output")


def test_dangling_output_directory_symlink_is_rejected_before_cli_writes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "outside-target"
    output_link = tmp_path / "dangling-output"
    output_link.symlink_to(target, target_is_directory=True)

    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/replay_status_window_ablation.py",
            "--output-dir",
            str(output_link),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert output_link.is_symlink()
    assert not target.exists()
    assert all(
        not (target / name).exists()
        for name in (
            "calendar-replay-artifact.json",
            "extracted-timestamp-rows.json",
            "review-summary.json",
            "README.md",
            "succession.json",
            "packet-manifest.json",
        )
    )


@pytest.mark.parametrize(
    "child_name",
    (
        "calendar-replay-artifact.json",
        "extracted-timestamp-rows.json",
        "review-summary.json",
        "README.md",
        "succession.json",
        "packet-manifest.json",
    ),
)
@pytest.mark.parametrize("dangling", (False, True), ids=("existing", "dangling"))
def test_output_child_symlink_is_rejected_before_any_write(
    tmp_path: Path, child_name: str, *, dangling: bool
) -> None:
    replay = _load_replay_module()
    output_dir = tmp_path / "replay"
    output_dir.mkdir()
    child_names = (
        "calendar-replay-artifact.json",
        "extracted-timestamp-rows.json",
        "review-summary.json",
        "README.md",
        "succession.json",
        "packet-manifest.json",
    )
    sentinel = b"unchanged-sentinel"
    outside = tmp_path / "outside"
    if not dangling:
        outside.write_bytes(sentinel)
    for name in child_names:
        path = output_dir / name
        if name == child_name:
            path.symlink_to(outside)
        else:
            path.write_bytes(sentinel)
    artifact = _artifact(
        current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
        boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="symlink"):
        replay._write_outputs(output_dir, records=_records(), artifact=artifact)

    if dangling:
        assert not outside.exists()
    else:
        assert outside.read_bytes() == sentinel
    assert all(
        (output_dir / name).read_bytes() == sentinel for name in child_names if name != child_name
    )


def test_portable_retained_rows_require_snapshot_and_version_bindings(monkeypatch) -> None:
    replay = _load_replay_module()
    load_json = replay._retained._io._load_json

    def load_with_wrong_snapshot(path: Path) -> dict[str, Any]:
        payload = load_json(path)
        if path.name == replay._io.ROWS_NAME:
            payload = json.loads(json.dumps(payload))
            payload["snapshot_id"] = "wrong-snapshot"
        return payload

    monkeypatch.setattr(replay._retained._io, "_load_json", load_with_wrong_snapshot)

    with pytest.raises(ValueError, match="snapshot_id|corpus_version"):
        replay._load_retained_records()


def test_portable_retained_rows_require_approved_projection_membership(monkeypatch) -> None:
    replay = _load_replay_module()
    approved = replay._approved_projection_rows()
    approved.pop(_records()[0]["record_id"])
    monkeypatch.setattr(replay, "_approved_projection_rows", lambda: approved)

    with pytest.raises(ValueError, match="approved projection"):
        replay._load_retained_records()


def test_extract_records_rejects_projection_identity_mismatch(monkeypatch) -> None:
    replay = _load_replay_module()
    approved_row = {
        "projected_record_id": "approved-record-id",
        "source_paper_id": "shared-paper",
        "domain_policy_id": "finance/1",
        "type": "paper",
        "coordinates": {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
    }

    class FakeConnection:
        def __init__(self):
            self.row_factory = None

        def execute(self, query: str, params: tuple[str, ...]):
            if "nsqd_corpus_snapshots" in query:
                return _RowResult(
                    [
                        {
                            "corpus_version": 11,
                            "record_ids_json": json.dumps(["persisted-record-id"] * 11),
                        }
                    ]
                )
            if "nsqd_corpus_records" in query:
                return _RowResult(
                    [
                        {
                            "payload_json": json.dumps(
                                {
                                    "record_id": "persisted-record-id",
                                    "source_paper_id": "shared-paper",
                                    "domain_policy_id": "finance/1",
                                    "harvested_at": HARVESTED_AT,
                                }
                            )
                        }
                    ]
                )
            raise AssertionError(query)

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        replay, "_approved_projection_rows", lambda: {"persisted-record-id": approved_row}
    )
    monkeypatch.setattr(replay, "_connect_read_only", lambda _path: FakeConnection())

    with pytest.raises(ValueError, match="projection_record_id"):
        replay._extract_records(Path("/tmp/nsqd.sqlite"))


class _RowResult:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

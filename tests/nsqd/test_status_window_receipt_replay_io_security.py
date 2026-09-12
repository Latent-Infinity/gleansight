from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import nsqd.domain.trusted_files as trusted_files
from tests.nsqd.status_window_receipt_replay_support import (
    _artifact,
    _load_replay_module,
    _records,
)


def test_verified_repo_read_rejects_leaf_swapped_to_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    approved = tmp_path / "approved"
    approved.mkdir()
    candidate = approved / "row.json"
    candidate.write_bytes(b'{"trusted": true}')
    outside = tmp_path / "outside.json"
    outside.write_bytes(b'{"secret": true}')
    original_open = trusted_files.os.open

    def swap_before_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == candidate.name and dir_fd is not None:
            candidate.unlink()
            candidate.symlink_to(outside)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(trusted_files.os, "open", swap_before_open)

    with pytest.raises(ValueError, match="symlink|unsafe"):
        trusted_files.read_verified_repo_file(
            repo_root=tmp_path,
            relative_path=Path("approved/row.json"),
            expected_root=Path("approved"),
            field="retained_path",
            max_bytes=1024,
        )


def test_retained_json_read_rejects_oversize_and_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replay = _load_replay_module()
    retained = tmp_path / "retained"
    retained.mkdir()
    oversized = retained / "oversized.json"
    oversized.write_text(json.dumps({"value": "x" * 64}), encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text('{"value": "outside"}', encoding="utf-8")
    linked = retained / "linked.json"
    linked.symlink_to(outside)
    monkeypatch.setattr(replay._io, "MAX_PACKET_FILE_BYTES", 32)

    with pytest.raises(ValueError, match="byte limit"):
        replay._io._load_json(oversized)
    with pytest.raises(ValueError, match="symlink|unsafe"):
        replay._io._load_json(linked)


def test_output_child_swap_cannot_redirect_replay_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replay = _load_replay_module()
    output_dir = tmp_path / "replay"
    output_dir.mkdir()
    outside = tmp_path / "outside.json"
    sentinel = b"outside-sentinel"
    outside.write_bytes(sentinel)
    artifact_path = output_dir / replay._io.ARTIFACT_NAME
    artifact = _artifact(
        current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
        boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
    )
    original_dumps = replay._packet.json.dumps
    swapped = False

    def swap_child_during_serialization(*args, **kwargs) -> str:
        nonlocal swapped
        if not swapped:
            swapped = True
            artifact_path.symlink_to(outside)
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(replay._packet.json, "dumps", swap_child_during_serialization)

    with pytest.raises(ValueError, match="symlink|unsafe"):
        replay._write_outputs(output_dir, records=_records(), artifact=artifact)

    assert outside.read_bytes() == sentinel


def test_output_directory_swap_cannot_redirect_replay_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    replay = _load_replay_module()
    output_dir = tmp_path / "replay"
    output_dir.mkdir()
    displaced = tmp_path / "displaced"
    outside = tmp_path / "outside"
    outside.mkdir()
    artifact = _artifact(
        current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
        boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
    )
    original_dumps = replay._packet.json.dumps
    swapped = False

    def swap_directory_during_serialization(*args, **kwargs) -> str:
        nonlocal swapped
        if not swapped:
            swapped = True
            output_dir.rename(displaced)
            output_dir.symlink_to(outside, target_is_directory=True)
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(replay._packet.json, "dumps", swap_directory_during_serialization)

    with pytest.raises(ValueError, match="symlink|unsafe"):
        replay._write_outputs(output_dir, records=_records(), artifact=artifact)

    assert list(outside.iterdir()) == []

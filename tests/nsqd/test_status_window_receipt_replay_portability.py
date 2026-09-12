from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_default_rebuild_uses_portable_retained_replay_without_scratch_sqlite(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "portable-rebuild"

    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/replay_status_window_ablation.py",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["verified_retained_replay"] is True
    assert result["verified_current_receipt"] is False
    assert (output_dir / "calendar-replay-artifact.json").is_file()


def test_verify_retained_replay_is_portable_and_does_not_claim_current_receipt() -> None:
    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/replay_status_window_ablation.py",
            "--verify-retained-replay",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "record_count": 11,
        "snapshot_id": "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5",
        "verified_current_receipt": False,
        "verified_retained_replay": True,
    }

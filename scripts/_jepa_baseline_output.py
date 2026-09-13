from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from nsqd.infrastructure.workflow_output import create_run_directory

WORKFLOW: Final = "jepa-baseline-replay"
MODELED_AT_UTC: Final = "2026-09-02T06:45:00Z"


def fresh_scratch_path() -> Path:
    return Path(tempfile.gettempdir()) / f"nsqd-jepa-baselines-{uuid.uuid4().hex}"


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_replay_bundle(
    *,
    repo_root: Path,
    output_dir: Path | None,
    scratch_dir: Path,
    result: dict[str, Any],
) -> Path:
    run_root = create_run_directory(repo_root, WORKFLOW, output_dir)
    summary_bytes = _json_bytes(result)
    receipt_bytes = _json_bytes(result["execution_receipt"])
    report_bytes = (
        "# JEPA baseline replay\n\n"
        "This run reproducibly replayed the retained Operator A and B baseline artifacts "
        "against the approved corpus in an isolated scratch runtime.\n\n"
        f"- Snapshot: `{result['snapshot_id']}`\n"
        f"- Corpus version: `{result['corpus_version']}`\n"
        f"- Operator A artifacts: `{len(result['generated_operator_a'])}`\n"
        f"- Operator B artifacts: `{len(result['generated_operator_b'])}`\n"
        f"- Modeled clock: `{MODELED_AT_UTC}`\n"
        f"- Scratch runtime: `{scratch_dir}`\n"
    ).encode()
    artifacts = {
        "execution-receipt.json": receipt_bytes,
        "replay-summary.json": summary_bytes,
        "report.md": report_bytes,
    }
    for name, content in artifacts.items():
        (run_root / name).write_bytes(content)
    metadata = {
        "schema_version": 1,
        "workflow": WORKFLOW,
        "mode": "fresh_local_replay",
        "run_id": run_root.name,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "modeled_at_utc": MODELED_AT_UTC,
        "scratch_dir": str(scratch_dir),
        "artifact_sha256": {
            name: hashlib.sha256(content).hexdigest() for name, content in artifacts.items()
        },
    }
    (run_root / "run-metadata.json").write_bytes(_json_bytes(metadata))
    return run_root

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from nsqd.domain.artifact_paths import resolve_artifact_path
from nsqd.domain.snapshot import canonical_json, sha256_hex
from nsqd.domain.tau_review import autonomous_tau_review_packet_digest
from nsqd.infrastructure.workflow_output import create_run_directory

POLICIES = ("finance/1", "optimization/1")
LABELS = ("near_duplicate", "novel")
TARGET_PER_CLASS = 30
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = "balanced-tau-packet"


def select_balanced_rows(packet_dir: Path) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {
        (policy, label): [] for policy in POLICIES for label in LABELS
    }
    for path in sorted((packet_dir / "autonomous-label-rows").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list) or len(raw_rows) != 1:
            raise ValueError(f"label checkpoint must contain exactly one row: {path}")
        row = raw_rows[0]
        if not isinstance(row, dict):
            raise ValueError(f"label checkpoint row must be an object: {path}")
        if payload.get("packet_digest") != autonomous_tau_review_packet_digest([row]):
            raise ValueError(f"label checkpoint digest drift: {path}")
        policy_id = str(row.get("domain_policy_id") or "")
        label = str(row.get("final_label") or "")
        if (policy_id, label) not in grouped:
            continue
        grouped[(policy_id, label)].append(
            {
                "candidate_artifact_hash": str(row["candidate_artifact_hash"]),
                "domain_policy_id": policy_id,
                "final_label": label,
                "input": str(path),
                "measurement_artifact_digest": str(row["measurement_artifact_digest"]),
                "source_packet_digest": str(payload["packet_digest"]),
            }
        )
    selected: list[dict[str, str]] = []
    for policy_id in POLICIES:
        for label in LABELS:
            rows = sorted(
                grouped[(policy_id, label)],
                key=lambda row: row["candidate_artifact_hash"],
            )
            if len(rows) < TARGET_PER_CLASS:
                raise ValueError(
                    f"{policy_id} requires {TARGET_PER_CLASS} {label} rows; found {len(rows)}"
                )
            selected.extend(rows[:TARGET_PER_CLASS])
    hashes = [row["candidate_artifact_hash"] for row in selected]
    measurements = [row["measurement_artifact_digest"] for row in selected]
    if len(hashes) != len(set(hashes)):
        raise ValueError("selected candidate artifact hashes must be unique")
    if len(measurements) != len(set(measurements)):
        raise ValueError("selected measurement artifact digests must be unique")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument(
        "--selection-output",
        type=Path,
        help=(
            "Selection file (default: "
            "output/balanced-tau-packet/<UTC-run-id>/balanced-selection.json)"
        ),
    )
    parser.add_argument(
        "--evaluation-output",
        type=Path,
        help=(
            "Evaluation file (default: "
            "output/balanced-tau-packet/<UTC-run-id>/balanced-evaluation.json)"
        ),
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--subprocess-timeout-s", type=int, default=300)
    args = parser.parse_args()
    if args.subprocess_timeout_s < 1:
        parser.error("subprocess timeout must be positive")

    packet_dir = (
        args.packet_dir
        if args.packet_dir.is_absolute()
        else resolve_artifact_path(REPO_ROOT, args.packet_dir)
    )
    run_dir: Path | None = None
    if args.selection_output is None or args.evaluation_output is None:
        run_dir = create_run_directory(REPO_ROOT, WORKFLOW)
    if args.selection_output is None:
        assert run_dir is not None
        selection_output = run_dir / "balanced-selection.json"
    else:
        selection_output = (
            args.selection_output
            if args.selection_output.is_absolute()
            else REPO_ROOT / args.selection_output
        ).resolve(strict=False)
    if args.evaluation_output is None:
        assert run_dir is not None
        evaluation_output = run_dir / "balanced-evaluation.json"
    else:
        evaluation_output = (
            args.evaluation_output
            if args.evaluation_output.is_absolute()
            else REPO_ROOT / args.evaluation_output
        ).resolve(strict=False)
    for output_path in (selection_output, evaluation_output):
        if output_path.exists():
            raise FileExistsError(output_path)
        if output_path.parent != run_dir:
            try:
                create_run_directory(REPO_ROOT, WORKFLOW, output_path.parent)
            except FileExistsError:
                pass

    selected = select_balanced_rows(packet_dir)
    selection = {
        "schema_version": 1,
        "selection_rule": "policy then label then candidate artifact hash; first 30",
        "target_per_class_per_policy": TARGET_PER_CLASS,
        "rows": selected,
        "rows_sha256": sha256_hex(canonical_json(selected)),
    }
    selection_output.write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    command = [sys.executable, "-m", "nsqd", "evaluate-autonomous-tau-reviews"]
    for row in selected:
        command.extend(("--candidate-artifact-hash", row["candidate_artifact_hash"]))
    for row in selected:
        command.extend(("--input", row["input"]))
    command.extend(("--output", str(evaluation_output), "--require-balanced"))
    if args.config is not None:
        command.extend(("--config", str(args.config)))
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=args.subprocess_timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("balanced evaluation subprocess timed out") from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

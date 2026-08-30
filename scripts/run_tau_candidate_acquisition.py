from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

from nsqd.app.use_cases import artifact_hash_for


def _mapping(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return {str(key): item for key, item in value.items()}


def _run(command: list[str], *, timeout_s: int) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("candidate acquisition subprocess timed out") from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _write_checkpoint(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", choices=("finance/1", "optimization/1"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--subprocess-timeout-s", type=int, default=300)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("limit must be positive")
    if args.subprocess_timeout_s < 1:
        parser.error("subprocess timeout must be positive")

    manifest = _mapping(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        name="manifest",
    )
    raw_rows = manifest.get("candidates")
    if not isinstance(raw_rows, list):
        raise ValueError("manifest candidates must be a list")
    rows = [_mapping(row, name="candidate row") for row in raw_rows]
    rows = [
        row for row in rows if args.policy is None or row.get("domain_policy_id") == args.policy
    ]
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        raise ValueError("no candidates selected")

    output: dict[str, object]
    if args.output.exists():
        output = _mapping(
            json.loads(args.output.read_text(encoding="utf-8")),
            name="checkpoint",
        )
    else:
        output = {
            "schema_version": 1,
            "source_manifest": str(args.manifest),
            "snapshot_id": manifest["snapshot_id"],
            "corpus_version": manifest["corpus_version"],
            "candidates": [],
        }
    completed_rows = output.get("candidates")
    if not isinstance(completed_rows, list):
        raise ValueError("checkpoint candidates must be a list")
    completed_rows = [_mapping(row, name="checkpoint candidate") for row in completed_rows]
    output["candidates"] = completed_rows
    completed = {
        str(row["candidate_artifact_hash"])
        for row in completed_rows
        if isinstance(row, dict) and row.get("candidate_artifact_hash")
    }

    fixture_dir = args.manifest.parent
    for position, row in enumerate(rows, start=1):
        expected_hash = str(row["candidate_artifact_hash"])
        if expected_hash in completed:
            print(f"skip {position}/{len(rows)} {expected_hash}", flush=True)
            continue
        fixture_path = fixture_dir / str(row["candidate_fixture"])
        if fixture_path.is_symlink():
            raise ValueError(f"candidate fixture must not be a symlink: {fixture_path}")
        fixture = fixture_path.resolve()
        try:
            fixture.relative_to(fixture_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"candidate fixture escapes manifest directory: {fixture}") from exc
        payload = yaml.safe_load(fixture.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or artifact_hash_for(payload) != expected_hash:
            raise ValueError(f"candidate fixture hash drift: {fixture}")
        common_store_args: list[str] = []
        if args.db is not None:
            common_store_args.extend(("--db", str(args.db)))
        if args.index is not None:
            common_store_args.extend(("--index", str(args.index)))
        diverge_stdout = _run(
            [
                sys.executable,
                "-m",
                "nsqd",
                "diverge",
                "--candidate-fixture",
                str(fixture),
                "--axiom",
                str(row["axiom"]),
                "--snapshot-id",
                str(manifest["snapshot_id"]),
                "--domain-policy-id",
                str(row["domain_policy_id"]),
                "--snapshot-state",
                "calibration",
                *common_store_args,
            ],
            timeout_s=args.subprocess_timeout_s,
        )
        if diverge_stdout != f"candidate={expected_hash}":
            raise ValueError(f"diverge returned unexpected artifact hash: {diverge_stdout}")
        ground_stdout = _run(
            [
                sys.executable,
                "-m",
                "nsqd",
                "ground",
                "--candidate-artifact-hash",
                expected_hash,
                "--snapshot-id",
                str(manifest["snapshot_id"]),
                "--corpus-version",
                str(manifest["corpus_version"]),
                "--snapshot-state",
                "calibration",
                *common_store_args,
            ],
            timeout_s=args.subprocess_timeout_s,
        )
        grounding = _mapping(json.loads(ground_stdout), name="ground output")
        completed_rows.append(
            {
                "candidate_id": row["candidate_id"],
                "candidate_artifact_hash": expected_hash,
                "domain_policy_id": row["domain_policy_id"],
                "grounding_class": grounding.get("grounding_class"),
            }
        )
        completed.add(expected_hash)
        _write_checkpoint(args.output, output)
        print(f"ok {position}/{len(rows)} {expected_hash}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from nsqd.domain.tau_review import autonomous_tau_review_packet_digest


def load_checkpoint(path: Path, *, candidate_artifact_hash: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid label checkpoint: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid label checkpoint: {path}")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError(f"invalid label checkpoint: {path}")
    row = {str(key): value for key, value in rows[0].items()}
    if row.get("candidate_artifact_hash") != candidate_artifact_hash:
        raise ValueError(f"label checkpoint candidate mismatch: {path}")
    if payload.get("packet_digest") != autonomous_tau_review_packet_digest([row]):
        raise ValueError(f"label checkpoint digest drift: {path}")
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--worker-index", type=int, required=True)
    parser.add_argument("--worker-count", type=int, required=True)
    parser.add_argument("--policy", choices=("finance/1", "optimization/1"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--target-label", choices=("near_duplicate", "novel", "ambiguous"))
    parser.add_argument("--target-count", type=int)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--subprocess-timeout-s", type=int, default=900)
    args = parser.parse_args()
    if args.worker_count < 1 or not 0 <= args.worker_index < args.worker_count:
        parser.error("worker index must be within worker count")
    if args.limit is not None and args.limit < 1:
        parser.error("limit must be positive")
    if (args.target_label is None) != (args.target_count is None):
        parser.error("target label and target count must be provided together")
    if args.target_count is not None and args.target_count < 1:
        parser.error("target count must be positive")
    if args.subprocess_timeout_s < 1:
        parser.error("subprocess timeout must be positive")

    packet_dir: Path = args.packet_dir
    manifest_path = args.candidate_manifest or packet_dir / "candidate-hashes.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    policies = (args.policy,) if args.policy else ("finance/1", "optimization/1")
    if isinstance(payload.get("candidates"), list):
        hashes = [
            row["candidate_artifact_hash"]
            for row in payload["candidates"]
            if row.get("domain_policy_id") in policies
        ]
    else:
        hashes = [row["candidate_artifact_hash"] for policy in policies for row in payload[policy]]
    selected = hashes[args.worker_index :: args.worker_count]
    if args.limit is not None:
        selected = selected[: args.limit]
    output_dir = packet_dir / "autonomous-label-rows"
    output_dir.mkdir(exist_ok=True)
    target_matches = 0
    if args.target_label is not None:
        for digest in selected:
            output = output_dir / f"{digest}.json"
            if not output.exists():
                continue
            row = load_checkpoint(output, candidate_artifact_hash=digest)
            if row.get("final_label") == args.target_label:
                target_matches += 1

    for position, digest in enumerate(selected, start=1):
        if args.target_count is not None and target_matches >= args.target_count:
            print(f"target {args.target_label}={target_matches}", flush=True)
            return 0
        output = output_dir / f"{digest}.json"
        if output.exists():
            load_checkpoint(output, candidate_artifact_hash=digest)
            print(f"skip {position}/{len(selected)} {digest}", flush=True)
            continue
        command = [
            sys.executable,
            "-m",
            "nsqd",
            "autonomous-tau-review",
            "--candidate-artifact-hash",
            digest,
            "--output",
            str(output),
            "--config",
            str(packet_dir / "labeling-run-qwen3-8b.toml"),
        ]
        for attempt in range(1, args.retries + 1):
            try:
                result = subprocess.run(
                    command,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=args.subprocess_timeout_s,
                )
            except subprocess.TimeoutExpired:
                print(
                    f"retry {attempt}/{args.retries} {position}/{len(selected)} {digest}: "
                    "subprocess timed out",
                    flush=True,
                )
                output.unlink(missing_ok=True)
                time.sleep(5)
                continue
            if result.returncode == 0:
                print(f"ok {position}/{len(selected)} {digest}", flush=True)
                if args.target_label is not None:
                    row = load_checkpoint(output, candidate_artifact_hash=digest)
                    if row.get("final_label") == args.target_label:
                        target_matches += 1
                break
            print(
                f"retry {attempt}/{args.retries} {position}/{len(selected)} {digest}: "
                f"subprocess exited {result.returncode}",
                flush=True,
            )
            output.unlink(missing_ok=True)
            time.sleep(5)
        else:
            print(f"failed {digest}", file=sys.stderr, flush=True)
            return 1
    if args.target_count is not None and target_matches < args.target_count:
        print(
            f"target shortfall {args.target_label}={target_matches}/{args.target_count}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

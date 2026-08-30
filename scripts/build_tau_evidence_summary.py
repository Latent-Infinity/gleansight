from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from nsqd.domain.novelty import NOVELTY_THRESHOLD_TAU
from nsqd.domain.snapshot import sha256_hex


def _file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    selection_path = args.packet_dir / "balanced-selection.json"
    evaluation_path = args.packet_dir / "balanced-evaluation.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    prompt_versions: Counter[str] = Counter()
    models: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    escalations: Counter[str] = Counter()
    adjudication_count = 0
    call_count = 0
    for row in evaluation["rows"]:
        for call in row["rounds"]:
            call_count += 1
            prompt_versions[str(call["prompt_version_id"])] += 1
            models[str(call["model"])] += 1
            providers[str(call["provider"])] += 1
        adjudication = row.get("adjudication")
        if adjudication is not None:
            adjudication_count += 1
            call_count += 1
            prompt_versions[str(adjudication["prompt_version_id"])] += 1
            models[str(adjudication["model"])] += 1
            providers[str(adjudication["provider"])] += 1
        escalation = row.get("escalation")
        if escalation is not None:
            escalations[str(escalation["reason"])] += 1
    artifacts = {
        "candidate_packet": args.packet_dir / "candidates.json",
        "candidate_hashes": args.packet_dir / "candidate-hashes.json",
        "measurement_inventory": args.packet_dir / "inventory.json",
        "measurements": args.packet_dir / "measurements.jsonl",
        "reserve_manifest": args.packet_dir / "reserve-near-duplicate-candidates/manifest.json",
        "reserve_acquisition": (
            args.packet_dir / "reserve-near-duplicate-candidates/acquired-candidates.json"
        ),
        "balanced_selection": selection_path,
        "balanced_evaluation": evaluation_path,
    }
    summary = {
        "schema_version": 1,
        "runtime_tau": NOVELTY_THRESHOLD_TAU,
        "selected_tau_recommendation": evaluation["packet"]["selected_tau"],
        "packet_digest": evaluation["packet_digest"],
        "approved_pair_count": evaluation["packet"]["approved_pair_count"],
        "ambiguous_pair_count": evaluation["packet"]["ambiguous_pair_count"],
        "counts_by_policy": evaluation["packet"]["counts_by_policy"],
        "thresholds": evaluation["packet"]["thresholds"],
        "selection_rows_sha256": selection["rows_sha256"],
        "call_count": call_count,
        "adjudication_count": adjudication_count,
        "escalations": dict(sorted(escalations.items())),
        "prompt_versions": dict(sorted(prompt_versions.items())),
        "models": dict(sorted(models.items())),
        "providers": dict(sorted(providers.items())),
        "artifact_sha256": {name: _file_sha256(path) for name, path in artifacts.items()},
    }
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

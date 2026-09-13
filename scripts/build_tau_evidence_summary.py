from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from nsqd.domain.artifact_paths import resolve_artifact_path
from nsqd.domain.novelty import NOVELTY_THRESHOLD_TAU
from nsqd.domain.snapshot import sha256_hex
from nsqd.infrastructure.workflow_output import create_run_directory

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = "tau-evidence-summary"


def _file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Summary file (default: output/tau-evidence-summary/<UTC-run-id>/evidence-summary.json)"
        ),
    )
    args = parser.parse_args()

    packet_dir = (
        args.packet_dir
        if args.packet_dir.is_absolute()
        else resolve_artifact_path(REPO_ROOT, args.packet_dir)
    )
    if args.output is None:
        output = create_run_directory(REPO_ROOT, WORKFLOW) / "evidence-summary.json"
    else:
        output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
        if output.exists():
            raise FileExistsError(output)
        try:
            create_run_directory(REPO_ROOT, WORKFLOW, output.parent)
        except FileExistsError:
            pass

    selection_path = packet_dir / "balanced-selection.json"
    evaluation_path = packet_dir / "balanced-evaluation.json"
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
        "candidate_packet": packet_dir / "candidates.json",
        "candidate_hashes": packet_dir / "candidate-hashes.json",
        "measurement_inventory": packet_dir / "inventory.json",
        "measurements": packet_dir / "measurements.jsonl",
        "reserve_manifest": packet_dir / "reserve-near-duplicate-candidates/manifest.json",
        "reserve_acquisition": (
            packet_dir / "reserve-near-duplicate-candidates/acquired-candidates.json"
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
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

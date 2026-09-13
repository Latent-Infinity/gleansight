from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from papers.domain import (
    InvestigationPlanValidationContext,
    investigation_plan_schema,
    parse_investigation_plan_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_ROOT = REPO_ROOT / "evidence/archive/reviews/v1/nsqd-jepa-ideas-gaps-2026-09-01"
BASELINE_SCRIPT = REPO_ROOT / "scripts" / "replay_jepa_operator_baselines.py"
REPORT_SCRIPT = REPO_ROOT / "scripts" / "report_jepa_ideas_gaps.py"


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"expected importable script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_cli_owns_output_bundle_and_auto_scratch(tmp_path: Path, monkeypatch) -> None:
    replay = _load_script("jepa_replay_output_test", BASELINE_SCRIPT)
    output_dir = tmp_path / "baseline-output"
    captured_scratch: list[Path] = []

    def fake_replay(packet_dir: Path, scratch_dir: Path, *, verify_current_receipt: bool):
        assert packet_dir == replay.PACKET_DIR
        assert verify_current_receipt is False
        assert not scratch_dir.exists()
        captured_scratch.append(scratch_dir)
        scratch_dir.mkdir()
        return {
            "snapshot_id": "snapshot-1",
            "corpus_version": 11,
            "model": {"manifest_digest": "a" * 64, "blob_digest": "b" * 64},
            "generated_operator_a": [{"candidate_id": "A-1"}],
            "generated_operator_b": [{"candidate_id": "B-1"}],
            "execution_receipt": {"candidate_count": 2, "card_count": 2},
            "receipt_runtime": {"candidate_payloads": {}, "frontier_card_payloads": {}},
        }

    monkeypatch.setattr(replay, "_replay", fake_replay)
    monkeypatch.setattr(sys, "argv", [str(BASELINE_SCRIPT), "--output-dir", str(output_dir)])
    before = datetime.now(UTC)

    assert replay.main() == 0

    after = datetime.now(UTC)
    assert {path.name for path in output_dir.iterdir()} == {
        "execution-receipt.json",
        "replay-summary.json",
        "report.md",
        "run-metadata.json",
    }
    metadata = json.loads((output_dir / "run-metadata.json").read_text(encoding="utf-8"))
    generated = datetime.fromisoformat(metadata["generated_at_utc"].replace("Z", "+00:00"))
    assert before <= generated <= after
    assert metadata["modeled_at_utc"] == "2026-09-02T06:45:00Z"
    assert metadata["workflow"] == "jepa-baseline-replay"
    assert metadata["mode"] == "fresh_local_replay"
    assert set(metadata["artifact_sha256"]) == {
        "execution-receipt.json",
        "replay-summary.json",
        "report.md",
    }
    for name, expected in metadata["artifact_sha256"].items():
        assert hashlib.sha256((output_dir / name).read_bytes()).hexdigest() == expected
    assert captured_scratch[0].name.startswith("nsqd-jepa-baselines-")
    assert captured_scratch[0].parent.resolve() == Path(tempfile.gettempdir()).resolve()
    captured_scratch[0].rmdir()


def test_baseline_verification_mode_does_not_create_output(tmp_path: Path, monkeypatch) -> None:
    replay = _load_script("jepa_replay_verify_test", BASELINE_SCRIPT)
    output_dir = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        replay,
        "_load_json",
        lambda _path: {"execution_receipt": {}, "scratch_runtime": {}},
    )
    monkeypatch.setattr(
        replay,
        "verify_scratch_execution_receipt",
        lambda _receipt, *, scratch_runtime: {
            "candidate_payloads": {},
            "frontier_card_payloads": {},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [str(BASELINE_SCRIPT), "--verify-current-receipt", "--output-dir", str(output_dir)],
    )

    assert replay.main() == 0
    assert not output_dir.exists()


def test_baseline_verify_resolves_explicit_legacy_packet_from_changed_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replay = _load_script("jepa_replay_legacy_packet_test", BASELINE_SCRIPT)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(BASELINE_SCRIPT),
            "--packet-dir",
            "docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01",
            "--verify-current-receipt",
        ],
    )

    with pytest.raises(ValueError, match="scratch runtime db_path is missing"):
        replay.main()


def test_retained_evidence_report_cli_writes_investigation_bundle(tmp_path: Path) -> None:
    output_dir = tmp_path / "jepa-report"
    before = datetime.now(UTC)

    completed = subprocess.run(
        ["uv", "run", "python", str(REPORT_SCRIPT), "--output-dir", str(output_dir)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    after = datetime.now(UTC)

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["output_dir"] == str(output_dir)
    assert result["mode"] == "retained_evidence_synthesis"
    assert result["gap_count"] == 4
    assert result["hypothesis_count"] == 3
    assert {path.name for path in output_dir.iterdir()} == {
        "cited-excerpts",
        "provenance.json",
        "report-data.json",
        "report.md",
    }
    report_data = json.loads((output_dir / "report-data.json").read_text(encoding="utf-8"))
    assert report_data["schema_version"] == 2
    assert report_data["report_state"] == {
        "execution_performed": False,
        "runtime_authorized": False,
        "scope": "retained_evidence_synthesis_and_investigation_planning",
        "status": "not_started",
    }
    plan = report_data["investigation_plan"]
    parsed_plan = parse_investigation_plan_json(
        json.dumps(plan),
        InvestigationPlanValidationContext(
            expected_question=plan["question"],
            allowed_source_ids=frozenset(source["paper_id"] for source in plan["sources"]),
            allowed_execution_evidence_refs=frozenset(),
        ),
    )
    assert len(plan["directions"]) == 3
    assert parsed_plan.question == plan["question"]
    assert plan["baseline_replication"]["strategy"] == "constrained_reproduction"
    assert len(report_data["coverage_matrix"]) == 5
    assert len(report_data["gaps"]) == 4
    assert len(report_data["retained_hypotheses"]) == 3
    for hypothesis in report_data["retained_hypotheses"]:
        assert hypothesis["experiment"]["design"]
        assert hypothesis["experiment"]["baselines"]
        assert hypothesis["experiment"]["primary_metric"]
        assert hypothesis["experiment"]["reject_condition"]
        assert hypothesis["overlap_caveat"]
    provenance = json.loads((output_dir / "provenance.json").read_text(encoding="utf-8"))
    generated = datetime.fromisoformat(provenance["generated_at_utc"].replace("Z", "+00:00"))
    assert before <= generated <= after
    assert provenance["schema_version"] == 2
    assert set(provenance["source_artifact_sha256"]) == {
        "operator-e-broader-prior-art.json",
        "results.json",
        "source-ledger.json",
    }
    source_inputs = {
        name: (PACKET_ROOT / name).read_bytes() for name in provenance["source_artifact_sha256"]
    }
    assert provenance["source_artifact_sha256"] == {
        name: hashlib.sha256(content).hexdigest() for name, content in source_inputs.items()
    }
    input_bundle = b"".join(
        name.encode("utf-8") + b"\0" + len(content).to_bytes(8, "big") + content
        for name, content in sorted(source_inputs.items())
    )
    schema_bytes = json.dumps(
        investigation_plan_schema(), sort_keys=True, separators=(",", ":")
    ).encode()
    assert provenance["input_bundle_sha256"] == hashlib.sha256(input_bundle).hexdigest()
    assert (
        provenance["investigation_plan_schema_sha256"] == hashlib.sha256(schema_bytes).hexdigest()
    )
    assert provenance["mode"] == "retained_evidence_synthesis"
    assert provenance["new_literature_search_performed"] is False
    assert provenance["new_backtest_performed"] is False
    assert provenance["source_cutoffs_utc"] == [
        "2026-09-01T00:00:00Z",
        "2026-09-03T00:00:00Z",
    ]
    assert len(list((output_dir / "cited-excerpts").iterdir())) == 5
    for citation in provenance["citations"]:
        copied = output_dir / citation["copied_path"]
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == citation["excerpt_sha256"]


def test_jepa_cli_help_exposes_output_conventions() -> None:
    for script, convention in (
        (BASELINE_SCRIPT, "output/jepa-baseline-replay/<UTC-run-id>"),
        (REPORT_SCRIPT, "output/jepa-finance-gap-analysis/<UTC-run-id>"),
    ):
        completed = subprocess.run(
            ["uv", "run", "python", str(script), "--help"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert "--output-dir" in completed.stdout
        assert convention in completed.stdout

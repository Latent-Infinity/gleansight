from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from nsqd.domain.status_window_replay import (
    EXPECTED_EXTRACTED_RECORDS_DIGEST,
    SEALED_AT_UTC,
    SUMMARY_PACKET_KIND,
    build_status_window_replay_summary,
    derive_boundary_sensitivity_as_of,
    validate_status_window_replay_artifact,
)
from tests.nsqd.status_window_receipt_replay_support import REPO_ROOT, _artifact, _records

COLLECTORS = (
    "tests/nsqd/test_operator_activation_packets.py",
    "tests/nsqd/test_operator_approval_boundary.py",
    "tests/nsqd/test_operator_authority_surface.py",
    "tests/nsqd/test_operator_c.py",
    "tests/nsqd/test_operator_c_evidence_packet.py",
    "tests/nsqd/test_operator_c_evidence_cycle_2.py",
    "tests/nsqd/test_operator_c_evidence_cycle_3.py",
    "tests/nsqd/test_operator_c_evidence_cycle_3_review.py",
    "tests/nsqd/test_operator_c_followup.py",
    "tests/nsqd/test_operator_d_contract.py",
    "tests/nsqd/test_operator_d_contract_edges.py",
    "tests/nsqd/test_operator_e.py",
    "tests/nsqd/test_operator_e_cooccurrence.py",
    "tests/nsqd/test_operator_e_report_only_candidates.py",
    "tests/nsqd/test_operator_e_broader_prior_art.py",
    "tests/nsqd/test_operator_e_runtime.py",
    "tests/nsqd/test_operator_f_contract.py",
    "tests/nsqd/test_operator_f_validation_target.py",
    "tests/nsqd/test_operator_f_pilot.py",
    "tests/nsqd/test_operator_f_pilot_inputs.py",
    "tests/nsqd/test_operator_f_pilot_result_validation.py",
    "tests/nsqd/test_operator_f_readiness.py",
    "tests/nsqd/test_operator_g_contract.py",
    "tests/nsqd/test_operator_g_census.py",
    "tests/nsqd/test_operator_g_census_boundaries.py",
    "tests/nsqd/test_operator_g_evidence_trust.py",
    "tests/nsqd/test_operator_g_readiness.py",
    "tests/nsqd/test_operator_g_readiness_semantics.py",
    "tests/nsqd/test_operator_baselines.py",
    "tests/nsqd/test_status_window_ablation.py",
    "tests/nsqd/test_status_window_receipt_replay.py",
    "tests/nsqd/test_status_window_receipt_replay_validation.py",
    "tests/nsqd/test_status_window_receipt_replay_projection_identity.py",
    "tests/nsqd/test_status_window_receipt_replay_script_boundaries.py",
    "tests/nsqd/test_map.py",
    "tests/nsqd/test_cli.py",
    "tests/nsqd/test_operator_a.py",
    "tests/nsqd/test_operator_b.py",
)
PORTABILITY_INSERTION_INDEX = COLLECTORS.index("tests/nsqd/test_map.py")
AUTHORITY_COLLECTORS = (
    COLLECTORS[0],
    "tests/nsqd/test_operator_activation_authority_clarification.py",
    *COLLECTORS[1:PORTABILITY_INSERTION_INDEX],
    "tests/nsqd/test_status_window_receipt_replay_portability.py",
    *COLLECTORS[PORTABILITY_INSERTION_INDEX:],
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_of_line(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("**As of:**"):
            return line
    raise AssertionError(f"As of line missing in {path}")


def _current_g_readiness_reference(text: str) -> tuple[Path, str]:
    match = re.search(r"current census is `([^`]+)` \(`([0-9a-f]{64})`\)", text)
    assert match is not None
    return Path(match.group(1)), match.group(2)


def _ev_n20_command(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| EV-N20 |"):
            return line.split("|", 4)[3].strip()
    raise AssertionError(f"EV-N20 line missing in {path}")


def _pytest_collectors(command: str) -> tuple[str, ...]:
    tokens = shlex.split(command)
    start = tokens.index("pytest") + 1
    return tuple(
        token for token in tokens[start:] if token.startswith("tests/") and token.endswith(".py")
    )


def _readme_collectors(text: str) -> tuple[str, ...]:
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line == "uv run pytest \\")
    return tuple(line.strip(" \\") for line in lines[start + 1 :] if line.startswith("  tests/"))


def test_status_window_replay_artifact_validates_zero_delta_and_boundary_sensitivity() -> None:
    current_as_of = datetime(2026, 9, 2, 6, 45, tzinfo=UTC)
    boundary_as_of = datetime(2028, 9, 2, 6, 45, tzinfo=UTC)
    report = _artifact(current_as_of=current_as_of, boundary_as_of=boundary_as_of)
    validated = validate_status_window_replay_artifact(report)
    assert validated["sealed_at_utc"] == SEALED_AT_UTC
    assert validated["extracted_records_digest"] == EXPECTED_EXTRACTED_RECORDS_DIGEST
    assert validated["scenarios"][0]["policy_results"]["finance/1"]["zero_delta"] is True
    assert validated["scenarios"][1]["policy_results"]["finance/1"]["lifecycle_delta_count"] == 6
    assert (
        validated["scenarios"][1]["policy_results"]["optimization/1"]["lifecycle_delta_count"] == 5
    )
    assert validated["scenarios"][1]["policy_results"]["finance/1"]["cell_status_delta_count"] == 0
    assert validated["runtime_status_window_days"] == 730


def test_summary_is_derived_from_validated_artifact() -> None:
    artifact = validate_status_window_replay_artifact(
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        )
    )
    summary = build_status_window_replay_summary(
        artifact,
        rows_sha256="rows-sha",
        artifact_sha256="artifact-sha",
    )
    assert summary["packet_kind"] == SUMMARY_PACKET_KIND
    assert summary["current_as_of_zero_delta"] is True
    assert summary["runtime_status_window_days"] == artifact["runtime_status_window_days"]
    assert (
        summary["calendar_window_months"]
        == artifact["scenarios"][0]["policy_results"]["finance/1"]["calendar_window_months"]
    )
    assert summary["boundary_sensitivity_note"] == artifact["scenarios"][1]["scenario_note"]
    assert summary["evidence_sufficient_scope"] == artifact["evidence_sufficient_scope"]
    assert summary["baseline_receipt_sqlite_sha256"] == artifact["source_receipt"]["sqlite_sha256"]
    assert summary["sealed_at_utc"] == artifact["sealed_at_utc"]
    assert summary["artifacts"]["calendar-replay-artifact.json"] == "artifact-sha"
    assert summary["artifacts"]["extracted-timestamp-rows.json"] == "rows-sha"


def test_ev_n20_commands_match_exactly_between_authority_docs() -> None:
    plan_command = _ev_n20_command(REPO_ROOT / "docs" / "development-plan-ns-qd.md")
    evidence_command = _ev_n20_command(REPO_ROOT / "docs" / "evidence-index.md")
    assert plan_command == evidence_command
    assert "tests/nsqd/test_status_window_receipt_replay.py" in plan_command
    assert "scripts/replay_status_window_ablation.py --verify-retained-replay" in plan_command
    assert "scripts/replay_status_window_ablation.py --verify-current-receipt" not in plan_command
    assert "scripts/replay_status_window_ablation.py --output-dir" not in plan_command
    assert _pytest_collectors(plan_command) == AUTHORITY_COLLECTORS
    assert _pytest_collectors(evidence_command) == AUTHORITY_COLLECTORS


def test_current_g_digest_matches_readiness_manifest() -> None:
    plan = (REPO_ROOT / "docs" / "development-plan-ns-qd.md").read_text(encoding="utf-8")
    relative_packet_root, plan_digest = _current_g_readiness_reference(plan)
    packet_root = REPO_ROOT / relative_packet_root
    manifest = json.loads((packet_root / "packet-manifest.json").read_text(encoding="utf-8"))
    digest = manifest["packet_digest"]
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert plan_digest == digest
    stale_plan = plan.replace(plan_digest, "0" * 64, 1)
    _, stale_digest = _current_g_readiness_reference(stale_plan)
    assert stale_digest != digest


def test_boundary_sensitivity_is_derived_from_receipt_bound_harvested_at() -> None:
    boundary_as_of = derive_boundary_sensitivity_as_of(_records())
    assert boundary_as_of == datetime(2028, 9, 2, 6, 45, tzinfo=UTC)


def test_replay_script_rebuild_is_byte_reproducible(tmp_path: Path) -> None:
    output_dir = tmp_path / "status-window-replay"
    command = [
        "uv",
        "run",
        "python",
        "scripts/replay_status_window_ablation.py",
        "--output-dir",
        str(output_dir),
    ]

    first = subprocess.run(command, check=False, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    first_digests = {
        name: _sha256(output_dir / name)
        for name in (
            "calendar-replay-artifact.json",
            "extracted-timestamp-rows.json",
            "review-summary.json",
        )
    }
    first_readme = (output_dir / "README.md").read_text(encoding="utf-8")

    second = subprocess.run(command, check=False, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    second_digests = {
        name: _sha256(output_dir / name)
        for name in (
            "calendar-replay-artifact.json",
            "extracted-timestamp-rows.json",
            "review-summary.json",
        )
    }
    second_readme = (output_dir / "README.md").read_text(encoding="utf-8")

    assert second_digests == first_digests
    assert second_readme == first_readme
    assert "## Verify" in second_readme
    readme_lines = second_readme.splitlines()
    assert any(line.startswith("uv run pytest") and line.endswith("\\") for line in readme_lines)
    assert any(
        line.startswith("  tests/nsqd/test_status_window_receipt_replay.py") and line.endswith("\\")
        for line in readme_lines
    )
    assert any(
        line.startswith("  tests/nsqd/test_operator_e_broader_prior_art.py") and line.endswith("\\")
        for line in readme_lines
    )
    assert any(
        line.startswith("uv run python scripts/replay_status_window_ablation.py")
        and line.endswith("\\")
        for line in readme_lines
    )
    assert "  --verify-current-receipt" in readme_lines
    assert (
        "  --output-dir docs/reviews/nsqd-status-window-calendar-replay-2026-09-11-command-sync"
        in readme_lines
    )
    assert _readme_collectors(first_readme) == COLLECTORS
    assert _readme_collectors(second_readme) == COLLECTORS


def test_authority_docs_as_of_dates_match_current_g_census() -> None:
    assert _as_of_line(REPO_ROOT / "docs" / "evidence-index.md") == "**As of:** 2026-09-09"
    assert _as_of_line(REPO_ROOT / "docs" / "fact-ledger.md") == "**As of:** 2026-09-09"


def test_jepa_readme_records_completed_execution_bundle_review() -> None:
    readme = (
        REPO_ROOT / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01" / "README.md"
    ).read_text(encoding="utf-8")
    assert "completed execution-bundle review" in readme
    assert "pending execution-bundle review" not in readme

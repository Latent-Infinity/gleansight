from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from nsqd.domain.project import canonical_reviewed_projection_digest, projection_record_id
from nsqd.domain.snapshot import canonical_json, sha256_hex
from nsqd.domain.status import STATUS_WINDOW_DAYS
from nsqd.domain.status_window_replay import (
    BOUNDARY_SENSITIVITY_SCENARIO_NOTE,
    CURRENT_AS_OF_SCENARIO_NOTE,
    EXPECTED_EXTRACTED_RECORDS_DIGEST,
    PROVENANCE_CAVEAT,
    SEALED_AT_UTC,
    STATUS_WINDOW_REPLAY_PACKET_KIND,
    SUMMARY_PACKET_KIND,
    build_status_window_replay_summary,
    compare_status_window_semantics,
    derive_boundary_sensitivity_as_of,
    status_window_replay_artifact_digest,
    validate_status_window_replay_artifact,
)

HARVESTED_AT = "2026-09-02T06:45:00+00:00"
REPO_ROOT = Path(__file__).resolve().parents[2]
SEALED_ARTIFACT_PATH = (
    REPO_ROOT
    / "docs"
    / "reviews"
    / "nsqd-status-window-calendar-replay-2026-09-02"
    / "calendar-replay-artifact.json"
)


def _records() -> list[dict[str, object]]:
    artifact = json.loads(SEALED_ARTIFACT_PATH.read_text(encoding="utf-8"))
    return cast(list[dict[str, object]], artifact["extracted_records"])


def _artifact(*, current_as_of: datetime, boundary_as_of: datetime) -> dict[str, object]:
    records = _records()
    report = {
        "schema_version": 1,
        "packet_kind": STATUS_WINDOW_REPLAY_PACKET_KIND,
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "evidence_sufficient": True,
        "evidence_sufficient_scope": "human_decision_only",
        "runtime_status_window_days": STATUS_WINDOW_DAYS,
        "sealed_at_utc": SEALED_AT_UTC,
        "harvested_at_provenance_caveat": PROVENANCE_CAVEAT,
        "extracted_records_digest": sha256_hex(canonical_json(records)),
        "source_receipt": {
            "snapshot_id": "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5",
            "corpus_version": 11,
            "record_count": 11,
            "sqlite_sha256": "ab339287d8e9fcea662a1b8cb9557302bde356573cb4834a9b374a4cd375a2b7",
            "harvested_at_utc": HARVESTED_AT,
            "receipt_verified_exact": True,
        },
        "extracted_records": records,
        "scenarios": [
            {
                "scenario_id": "current_as_of",
                "scenario_kind": "observed_current_as_of",
                "as_of_utc": current_as_of.isoformat(),
                "scenario_note": CURRENT_AS_OF_SCENARIO_NOTE,
                "policy_results": {
                    "finance/1": compare_status_window_semantics(
                        records,
                        domain_policy_id="finance/1",
                        as_of=current_as_of,
                        snapshot_state="production_valid",
                    ),
                    "optimization/1": compare_status_window_semantics(
                        records,
                        domain_policy_id="optimization/1",
                        as_of=current_as_of,
                        snapshot_state="production_valid",
                    ),
                },
            },
            {
                "scenario_id": "boundary_sensitivity",
                "scenario_kind": "boundary_sensitivity",
                "as_of_utc": boundary_as_of.isoformat(),
                "scenario_note": BOUNDARY_SENSITIVITY_SCENARIO_NOTE,
                "policy_results": {
                    "finance/1": compare_status_window_semantics(
                        records,
                        domain_policy_id="finance/1",
                        as_of=boundary_as_of,
                        snapshot_state="production_valid",
                    ),
                    "optimization/1": compare_status_window_semantics(
                        records,
                        domain_policy_id="optimization/1",
                        as_of=boundary_as_of,
                        snapshot_state="production_valid",
                    ),
                },
            },
        ],
    }
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    return report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_replay_module():
    spec = importlib.util.spec_from_file_location(
        "status_window_replay_script", REPO_ROOT / "scripts" / "replay_status_window_ablation.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _as_of_line(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("**As of:**"):
            return line
    raise AssertionError(f"As of line missing in {path}")


def _ev_n20_command(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| EV-N20 |"):
            return line.split("|", 4)[3].strip()
    raise AssertionError(f"EV-N20 line missing in {path}")


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


def test_status_window_replay_artifact_rejects_tampering_and_policy_leakage() -> None:
    current_as_of = datetime(2026, 9, 2, 6, 45, tzinfo=UTC)
    boundary_as_of = datetime(2028, 9, 2, 6, 45, tzinfo=UTC)
    report = _artifact(current_as_of=current_as_of, boundary_as_of=boundary_as_of)

    tampered = {**report, "artifact_digest": "0" * 64}
    with pytest.raises(ValueError, match="artifact_digest"):
        validate_status_window_replay_artifact(tampered)

    tampered = cast(
        dict[str, Any], _artifact(current_as_of=current_as_of, boundary_as_of=boundary_as_of)
    )
    cast(dict[str, Any], tampered["source_receipt"])["record_count"] = 10
    with pytest.raises(ValueError, match="source_receipt"):
        validate_status_window_replay_artifact(tampered)

    tampered = cast(
        dict[str, Any], _artifact(current_as_of=current_as_of, boundary_as_of=boundary_as_of)
    )
    scenarios = cast(list[dict[str, Any]], tampered["scenarios"])
    cast(dict[str, Any], cast(dict[str, Any], scenarios[1]["policy_results"])["finance/1"])[
        "domain_policy_id"
    ] = "optimization/1"
    with pytest.raises(ValueError, match=r"policy_results\[finance/1\]"):
        validate_status_window_replay_artifact(tampered)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("schema_version", 2, "schema_version"),
        ("packet_kind", "wrong", "packet_kind"),
        ("authorization_state", "runtime", "authorization_state"),
        ("runtime_authorized", True, "runtime_authorized"),
        ("evidence_sufficient", False, "evidence_sufficient"),
        ("evidence_sufficient_scope", "runtime", "human_decision_only"),
        ("runtime_status_window_days", 731, "730 days"),
        ("sealed_at_utc", "2026-09-03T05:32:09Z", "sealed_at_utc"),
        ("harvested_at_provenance_caveat", "wrong", "provenance caveat"),
        ("extracted_records", "wrong", "extracted_records"),
        ("source_receipt", "wrong", "source_receipt"),
    ],
)
def test_status_window_replay_artifact_rejects_invalid_top_level_fields(
    field: str,
    value: object,
    match: str,
) -> None:
    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    report[field] = value
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match=match):
        validate_status_window_replay_artifact(report)


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda report: cast(dict[str, Any], report).pop("sealed_at_utc"),
            "sealed_at_utc",
        ),
        (
            lambda report: cast(dict[str, Any], report).__setitem__(
                "generated_at_utc", SEALED_AT_UTC
            ),
            "generated_at_utc",
        ),
    ],
)
def test_status_window_replay_artifact_rejects_malformed_sealed_metadata(
    mutator: Any,
    match: str,
) -> None:
    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    mutator(report)
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match=match):
        validate_status_window_replay_artifact(report)


def test_status_window_replay_artifact_rejects_invalid_scenario_shape() -> None:
    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    report["scenarios"] = [{"scenario_id": "current_as_of"}]
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match="scenarios"):
        validate_status_window_replay_artifact(report)

    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    scenarios = cast(list[dict[str, Any]], report["scenarios"])
    scenarios[0]["scenario_kind"] = "wrong"
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match="scenario_kind"):
        validate_status_window_replay_artifact(report)

    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    scenarios = cast(list[dict[str, Any]], report["scenarios"])
    scenarios[0]["as_of_utc"] = "2026-09-02T06:45:01+00:00"
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match="as_of_utc"):
        validate_status_window_replay_artifact(report)


def test_compare_requires_utc_and_boundary_derivation_handles_leap_day() -> None:
    with pytest.raises(ValueError, match="UTC"):
        compare_status_window_semantics(
            _records(),
            domain_policy_id="finance/1",
            as_of=datetime(2026, 9, 2, 6, 45),
            snapshot_state="production_valid",
        )

    leap_day_records = [dict(row) for row in _records()]
    for row in leap_day_records:
        row["harvested_at"] = "2024-02-29T06:45:00+00:00"
    with pytest.raises(ValueError, match="could not derive"):
        derive_boundary_sensitivity_as_of(leap_day_records)


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda report: cast(list[dict[str, Any]], report["extracted_records"]).append(
                dict(cast(list[dict[str, Any]], report["extracted_records"])[0])
            ),
            "exactly 11",
        ),
        (
            lambda report: cast(list[dict[str, Any]], report["extracted_records"]).__setitem__(
                0,
                {
                    **cast(list[dict[str, Any]], report["extracted_records"])[0],
                    "record_id": "synthetic-record-0",
                },
            ),
            "extracted_records_digest",
        ),
        (
            lambda report: cast(list[dict[str, Any]], report["extracted_records"]).__setitem__(
                0,
                cast(list[dict[str, Any]], report["extracted_records"])[1],
            ),
            "record ids must be unique",
        ),
        (
            lambda report: cast(list[dict[str, Any]], report["extracted_records"]).__setitem__(
                0,
                {
                    **cast(list[dict[str, Any]], report["extracted_records"])[0],
                    "domain_policy_id": "optimization/1",
                },
            ),
            "6 finance and 5 optimization",
        ),
    ],
)
def test_validation_rejects_invalid_extracted_records(
    mutator: Any,
    match: str,
) -> None:
    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    mutator(report)
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match=match):
        validate_status_window_replay_artifact(report)

    report = cast(
        dict[str, Any],
        _artifact(
            current_as_of=datetime(2026, 9, 2, 6, 45, tzinfo=UTC),
            boundary_as_of=datetime(2028, 9, 2, 6, 45, tzinfo=UTC),
        ),
    )
    records = cast(list[dict[str, Any]], report["extracted_records"])
    records[0]["harvested_at"] = "2026-09-02T06:45:00"
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    with pytest.raises(ValueError, match="harvested_at rows"):
        validate_status_window_replay_artifact(report)


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
    assert "scripts/replay_status_window_ablation.py --verify-current-receipt" in plan_command
    assert (
        "scripts/replay_status_window_ablation.py --output-dir "
        "docs/reviews/nsqd-status-window-calendar-replay-2026-09-02" in plan_command
    )


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
        "  --output-dir docs/reviews/nsqd-status-window-calendar-replay-2026-09-02" in readme_lines
    )


def test_replay_script_rejects_untrusted_packet_arg_and_confines_output_dir(tmp_path: Path) -> None:
    rejected = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/replay_status_window_ablation.py",
            "--packet-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0

    replay = _load_replay_module()
    assert replay._require_output_dir(replay.OUTPUT_DIR) == replay.OUTPUT_DIR.resolve()

    safe_temp = tmp_path / "status-window-replay"
    assert replay._require_output_dir(safe_temp) == safe_temp.resolve()

    tmp_alias = Path("/tmp") / "status-window-replay-alias"
    assert replay._require_output_dir(tmp_alias) == tmp_alias.resolve(strict=False)

    tempdir_alias = Path(tempfile.gettempdir()) / "status-window-replay-tempdir-alias"
    assert replay._require_output_dir(tempdir_alias) == tempdir_alias.resolve(strict=False)

    blocked_repo = REPO_ROOT / "docs" / "unsafe-status-window-replay"
    with pytest.raises(ValueError, match="sealed output directory|allowlisted system temp root"):
        replay._require_output_dir(blocked_repo)

    escaped = tmp_path / "nested" / ".." / "escape"
    with pytest.raises(ValueError, match="parent traversal"):
        replay._require_output_dir(escaped)

    symlink_parent = tmp_path / "symlink-parent"
    symlink_parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        replay._require_output_dir(symlink_parent / "status-window-replay")

    real = tmp_path / "real-dir"
    real.mkdir()
    symlink_leaf = tmp_path / "symlink-leaf"
    symlink_leaf.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        replay._require_output_dir(symlink_leaf)


def test_authority_docs_as_of_dates_match_v1_6_50() -> None:
    assert _as_of_line(REPO_ROOT / "docs" / "evidence-index.md") == "**As of:** 2026-09-03"
    assert _as_of_line(REPO_ROOT / "docs" / "fact-ledger.md") == "**As of:** 2026-09-03"


def test_approved_projection_rows_use_exact_projection_record_identity(monkeypatch) -> None:
    replay = _load_replay_module()

    finance_manifest = {
        "fixture": {
            "ROW-1": {
                "id": "ROW-1",
                "kind": "corpus-paper-paraphrase",
                "path": "row-1.yaml",
                "domain_policy_id": "finance/1",
                "source_paper_id": "shared-paper",
                "content_sha256": "c1",
                "reviewed_projection_sha256": "d1",
                "review_status": "approved",
                "reviewer": "product",
                "approved_at": "2026-09-03T00:00:00+00:00",
            },
            "ROW-2": {
                "id": "ROW-2",
                "kind": "corpus-paper-paraphrase",
                "path": "row-2.yaml",
                "domain_policy_id": "finance/1",
                "source_paper_id": "shared-paper",
                "content_sha256": "c2",
                "reviewed_projection_sha256": "d2",
                "review_status": "approved",
                "reviewer": "product",
                "approved_at": "2026-09-03T00:00:00+00:00",
            },
        }
    }

    payloads = {
        "row-1.yaml": {
            "id": "ROW-1",
            "source_paper_id": "shared-paper",
            "domain_policy_id": "finance/1",
            "source_abstract_sha256": "abs-1",
            "source_markdown_sha256": "md-1",
            "paraphrase_sha256": "para-1",
            "paraphrase": "one",
            "paraphrase_source": "model_assisted",
            "source": "doi:one",
            "coordinates": {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
            "human_reviewer": "product",
            "human_approved_at": "2026-09-03T00:00:00+00:00",
            "review_status": "approved",
            "type": "paper",
        },
        "row-2.yaml": {
            "id": "ROW-2",
            "source_paper_id": "shared-paper",
            "domain_policy_id": "finance/1",
            "source_abstract_sha256": "abs-2",
            "source_markdown_sha256": "md-2",
            "paraphrase_sha256": "para-2",
            "paraphrase": "two",
            "paraphrase_source": "model_assisted",
            "source": "doi:two",
            "coordinates": {
                "mechanism": "flow-driven",
                "target": "drawdown",
                "horizon": "intraday",
            },
            "human_reviewer": "product",
            "human_approved_at": "2026-09-03T00:00:00+00:00",
            "review_status": "approved",
            "type": "paper",
        },
    }

    finance_manifest["fixture"]["ROW-1"]["content_sha256"] = hashlib.sha256(
        json.dumps(payloads["row-1.yaml"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    finance_manifest["fixture"]["ROW-1"]["reviewed_projection_sha256"] = (
        canonical_reviewed_projection_digest(payloads["row-1.yaml"])
    )
    finance_manifest["fixture"]["ROW-2"]["content_sha256"] = hashlib.sha256(
        json.dumps(payloads["row-2.yaml"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    finance_manifest["fixture"]["ROW-2"]["reviewed_projection_sha256"] = (
        canonical_reviewed_projection_digest(payloads["row-2.yaml"])
    )

    def fake_read_verified_repo_text(**kwargs):
        rel = kwargs["relative_path"].as_posix()
        if rel.endswith("final/manifest.toml") or rel.endswith("approved/nsqd/manifest.toml"):
            return "unused-manifest"
        raise AssertionError(rel)

    seen = 0

    def fake_tomllib_loads(_text: str):
        nonlocal seen
        seen += 1
        return finance_manifest if seen == 1 else {"fixture": {}}

    def fake_load_verified_yaml_mapping(**kwargs):
        rel = kwargs["relative_path"].name
        return dict(payloads[rel])

    def fake_read_verified_repo_file(**kwargs):
        rel = kwargs["relative_path"].name
        return json.dumps(payloads[rel], sort_keys=True).encode("utf-8")

    monkeypatch.setattr(replay, "read_verified_repo_text", fake_read_verified_repo_text)
    monkeypatch.setattr(replay.tomllib, "loads", fake_tomllib_loads)
    monkeypatch.setattr(replay, "load_verified_yaml_mapping", fake_load_verified_yaml_mapping)
    monkeypatch.setattr(
        replay, "read_verified_repo_file", fake_read_verified_repo_file, raising=False
    )

    rows = replay._approved_projection_rows()
    first_id = projection_record_id(payloads["row-1.yaml"])
    second_id = projection_record_id(payloads["row-2.yaml"])
    assert set(rows) == {first_id, second_id}
    assert rows[first_id]["coordinates"] != rows[second_id]["coordinates"]


def test_approved_projection_rows_reject_duplicate_projected_record_ids(monkeypatch) -> None:
    replay = _load_replay_module()
    payloads = {
        "row-1.yaml": {
            "id": "ROW-1",
            "source_paper_id": "shared-paper",
            "domain_policy_id": "finance/1",
            "source_abstract_sha256": "abs-1",
            "source_markdown_sha256": "md-1",
            "paraphrase_sha256": "para-1",
            "paraphrase": "one",
            "paraphrase_source": "model_assisted",
            "source": "doi:one",
            "coordinates": {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
            "human_reviewer": "product",
            "human_approved_at": "2026-09-03T00:00:00+00:00",
            "review_status": "approved",
            "type": "paper",
        },
        "row-2.yaml": {
            "id": "ROW-2",
            "source_paper_id": "shared-paper",
            "domain_policy_id": "finance/1",
            "source_abstract_sha256": "abs-1",
            "source_markdown_sha256": "md-1",
            "paraphrase_sha256": "para-1",
            "paraphrase": "one",
            "paraphrase_source": "model_assisted",
            "source": "doi:one",
            "coordinates": {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
            "human_reviewer": "product",
            "human_approved_at": "2026-09-03T00:00:00+00:00",
            "review_status": "approved",
            "type": "paper",
        },
    }
    digest = canonical_reviewed_projection_digest(payloads["row-1.yaml"])
    content_sha_row_1 = hashlib.sha256(
        json.dumps(payloads["row-1.yaml"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    content_sha_row_2 = hashlib.sha256(
        json.dumps(payloads["row-2.yaml"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    manifest = {
        "fixture": {
            "ROW-1": {
                "id": "ROW-1",
                "kind": "corpus-paper-paraphrase",
                "path": "row-1.yaml",
                "domain_policy_id": "finance/1",
                "source_paper_id": "shared-paper",
                "content_sha256": content_sha_row_1,
                "reviewed_projection_sha256": digest,
                "review_status": "approved",
                "reviewer": "product",
                "approved_at": "2026-09-03T00:00:00+00:00",
            },
            "ROW-2": {
                "id": "ROW-2",
                "kind": "corpus-paper-paraphrase",
                "path": "row-2.yaml",
                "domain_policy_id": "finance/1",
                "source_paper_id": "shared-paper",
                "content_sha256": content_sha_row_2,
                "reviewed_projection_sha256": digest,
                "review_status": "approved",
                "reviewer": "product",
                "approved_at": "2026-09-03T00:00:00+00:00",
            },
        }
    }
    seen = 0

    monkeypatch.setattr(replay, "read_verified_repo_text", lambda **kwargs: "unused-manifest")

    def fake_tomllib_loads(_text: str):
        nonlocal seen
        seen += 1
        return manifest if seen == 1 else {"fixture": {}}

    monkeypatch.setattr(replay.tomllib, "loads", fake_tomllib_loads)
    monkeypatch.setattr(
        replay,
        "load_verified_yaml_mapping",
        lambda **kwargs: dict(payloads[kwargs["relative_path"].name]),
    )
    monkeypatch.setattr(
        replay,
        "read_verified_repo_file",
        lambda **kwargs: json.dumps(payloads[kwargs["relative_path"].name], sort_keys=True).encode(
            "utf-8"
        ),
        raising=False,
    )

    with pytest.raises(ValueError, match="duplicate projected_record_id"):
        replay._approved_projection_rows()


def test_extract_records_rejects_projection_identity_mismatch(monkeypatch) -> None:
    replay = _load_replay_module()
    approved_row = {
        "projected_record_id": "approved-record-id",
        "source_paper_id": "shared-paper",
        "domain_policy_id": "finance/1",
        "type": "paper",
        "coordinates": {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
    }

    class FakeConnection:
        def __init__(self):
            self.row_factory = None

        def execute(self, query: str, params: tuple[str, ...]):
            if "nsqd_corpus_snapshots" in query:
                return _RowResult(
                    [
                        {
                            "corpus_version": 11,
                            "record_ids_json": json.dumps(["persisted-record-id"] * 11),
                        }
                    ]
                )
            if "nsqd_corpus_records" in query:
                return _RowResult(
                    [
                        {
                            "payload_json": json.dumps(
                                {
                                    "record_id": "persisted-record-id",
                                    "source_paper_id": "shared-paper",
                                    "domain_policy_id": "finance/1",
                                    "harvested_at": HARVESTED_AT,
                                }
                            )
                        }
                    ]
                )
            raise AssertionError(query)

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        replay, "_approved_projection_rows", lambda: {"persisted-record-id": approved_row}
    )
    monkeypatch.setattr(replay, "_connect_read_only", lambda _path: FakeConnection())

    with pytest.raises(ValueError, match="projection_record_id"):
        replay._extract_records(Path("/tmp/nsqd.sqlite"))


class _RowResult:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_jepa_readme_records_completed_execution_bundle_review() -> None:
    readme = (
        REPO_ROOT / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01" / "README.md"
    ).read_text(encoding="utf-8")
    assert "completed execution-bundle review" in readme
    assert "pending execution-bundle review" not in readme

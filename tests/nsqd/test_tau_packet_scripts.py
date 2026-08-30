from __future__ import annotations

import json
from pathlib import Path

import pytest

from nsqd.domain.tau_review import autonomous_tau_review_packet_digest
from scripts.build_balanced_tau_packet import select_balanced_rows
from scripts.run_tau_label_collection import load_checkpoint


def _write_label(
    output_dir: Path,
    *,
    policy_id: str,
    label: str,
    index: int,
) -> None:
    candidate_hash = f"{index:064x}"
    row = {
        "candidate_artifact_hash": candidate_hash,
        "domain_policy_id": policy_id,
        "final_label": label,
        "measurement_artifact_digest": f"{index + 1000:064x}",
    }
    payload = {
        "rows": [row],
        "packet_digest": autonomous_tau_review_packet_digest([row]),
    }
    (output_dir / f"{candidate_hash}.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_select_balanced_rows_is_deterministic_and_exact(tmp_path: Path) -> None:
    output_dir = tmp_path / "autonomous-label-rows"
    output_dir.mkdir()
    index = 1
    for policy_id in ("finance/1", "optimization/1"):
        for label in ("near_duplicate", "novel"):
            for _ in range(31):
                _write_label(
                    output_dir,
                    policy_id=policy_id,
                    label=label,
                    index=index,
                )
                index += 1

    selected = select_balanced_rows(tmp_path)

    assert len(selected) == 120
    assert len({row["candidate_artifact_hash"] for row in selected}) == 120
    for policy_id in ("finance/1", "optimization/1"):
        for label in ("near_duplicate", "novel"):
            assert (
                sum(
                    row["domain_policy_id"] == policy_id and row["final_label"] == label
                    for row in selected
                )
                == 30
            )


def test_select_balanced_rows_rejects_shortfall(tmp_path: Path) -> None:
    (tmp_path / "autonomous-label-rows").mkdir()

    with pytest.raises(ValueError, match="finance/1 requires 30 near_duplicate rows"):
        select_balanced_rows(tmp_path)


def test_label_checkpoint_loader_rejects_corrupt_existing_output(tmp_path: Path) -> None:
    checkpoint = tmp_path / "bad.json"
    checkpoint.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid label checkpoint"):
        load_checkpoint(checkpoint, candidate_artifact_hash="a" * 64)

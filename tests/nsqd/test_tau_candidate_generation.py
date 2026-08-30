from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import yaml

from scripts.build_tau_near_duplicate_candidates import build_packet


def test_near_duplicate_candidate_packet_is_deterministic_and_label_free(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = build_packet(root, first_dir)
    second = build_packet(root, second_dir)

    assert first == second
    assert first["counts_by_policy"] == {"finance/1": 30, "optimization/1": 30}
    rows = first["candidates"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    typed_rows = cast(list[dict[str, object]], rows)
    assert len(rows) == 60
    hashes = {str(row["candidate_artifact_hash"]) for row in typed_rows}
    assert len(hashes) == 60
    forbidden = {
        "label",
        "measurement",
        "measured_at",
        "measurement_artifact_digest",
        "expected_outcomes",
    }
    for row in typed_rows:
        fixture = yaml.safe_load((first_dir / str(row["candidate_fixture"])).read_text())
        assert isinstance(fixture, dict)
        assert fixture["kind"] == "candidate-requirement-card"
        assert forbidden.isdisjoint(fixture)
        assert "near_duplicate" not in json.dumps(fixture)

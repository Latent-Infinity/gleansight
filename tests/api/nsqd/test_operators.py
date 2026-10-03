"""Experimental operator activation still comes only from trusted local configuration."""

import json
from pathlib import Path
from typing import Literal

import pytest
from pydantic import TypeAdapter

from nsqd.domain.diverge import select_target_cell
from nsqd.domain.status import CellStatus
from tests.api.nsqd.test_workflows import FIXTURES, ScratchRuntime, invoke, mapping
from tests.nsqd.test_operator_b import _candidate as transfer_candidate
from tests.nsqd.test_operator_e_runtime import BRIDGE, _candidate


@pytest.mark.parametrize("operator", ["B", "E"])
def test_supported_operators_obey_config_allowlist(
    tmp_path: Path, operator: Literal["B", "E"]
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(f'[nsqd]\nenabled_operators = ["A", "{operator}"]\n', encoding="utf-8")
    runtime = ScratchRuntime(tmp_path, config_path=config)
    smoke = mapping(
        invoke(
            runtime,
            "nsqd.skeleton.run",
            {
                "candidate_fixture": str(FIXTURES / "gamma-flow.yaml"),
                "axiom": "stationarity",
            },
        )
    )
    mapped = mapping(
        invoke(
            runtime,
            "nsqd.snapshots.map",
            {
                "snapshot_id": smoke["snapshot_id"],
                "domain_policy_id": "finance/1",
            },
        )
    )
    target = select_target_cell(
        TypeAdapter(dict[str, CellStatus]).validate_python(mapped["cell_statuses"])
    )
    descriptor = dict(part.split("=", 1) for part in target.split("|"))
    candidate = tmp_path / "combination.json"
    candidate.write_text(
        json.dumps(
            {"B": transfer_candidate, "E": _candidate}[operator](research_descriptor=descriptor)
        ),
        encoding="utf-8",
    )
    result = mapping(
        invoke(
            runtime,
            "nsqd.candidates.diverge",
            {
                "candidate_fixture": str(candidate),
                "axiom": BRIDGE,
                "axiom_cell_id": target,
                "target_cell_id": target,
                "snapshot_id": smoke["snapshot_id"],
                "domain_policy_id": "finance/1",
                "operator": operator,
            },
        )
    )
    stored = mapping(
        invoke(runtime, "nsqd.candidates.get", {"id": result["candidate_artifact_hash"]})
    )
    assert mapping(stored["payload"])["operator"] == operator

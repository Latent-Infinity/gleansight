"""Acquisition composes real local paper services without contacting providers."""

from pathlib import Path

from gleansight.api.runtime import ApiRuntime
from tests.api.nsqd.test_workflows import FIXTURES, ScratchRuntime, invoke, mapping


def test_acquisition_uses_configured_paper_runtime_and_persists_decline(tmp_path: Path) -> None:
    seed = ScratchRuntime(tmp_path)
    smoke = mapping(
        invoke(
            seed,
            "nsqd.skeleton.run",
            {
                "candidate_fixture": str(FIXTURES / "gamma-flow.yaml"),
                "axiom": "stationarity",
            },
        )
    )
    runtime = ApiRuntime(seed.configuration)
    result = mapping(
        invoke(
            runtime,
            "nsqd.corpus.acquire",
            {
                "snapshot_id": smoke["snapshot_id"],
                "domain_policy_id": "finance/1",
                "human_decision": "decline",
            },
        )
    )
    assert result["stopped"] == "human_decline"
    assert result["projected"] is False
    cycle = mapping(invoke(runtime, "nsqd.cycles.get", {"id": result["cycle_id"]}))
    assert mapping(cycle["payload"])["stopped"] == "human_decline"
    verdict = mapping(
        invoke(
            runtime,
            "nsqd.verdicts.get",
            {
                "snapshot_id": smoke["snapshot_id"],
                "domain_policy_id": "finance/1",
            },
        )
    )
    assert verdict
    assert runtime.papers.settings.data.root.is_relative_to(tmp_path)

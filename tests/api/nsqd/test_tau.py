"""Tau API uses persisted provenance and real evaluators with a deterministic LLM port."""

from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter

from gleansight.api.nsqd import tau
from nsqd.app.use_cases import AutonomousTauLabelingUseCase, TauMeasurementEvidenceUseCase
from nsqd.composition import NsqdContainer
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from papers.config.settings import Settings
from tests.api.nsqd.test_workflows import ScratchRuntime, invoke, mapping
from tests.nsqd.test_autonomous_tau_review import (
    APPROVED_PROJECTION_DIGESTS,
    FakeLLMClient,
    _local_round_responses,
    _measurement_row,
    _settings,
)


def test_tau_export_inventory_review_and_evaluate_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = ScratchRuntime(tmp_path)
    runtime.settings.nsqd.autonomous_tau = _settings()
    row = TypeAdapter(dict[str, JsonValue]).validate_python(_measurement_row(evidence=0.62))
    candidate_hash = str(row["candidate_artifact_hash"])
    runtime.nsqd.ctx.candidates.put_artifact(
        candidate_hash,
        {
            "candidate": row["candidate"],
            "generator_run_id": "gen-1",
            "grounding": row,
        },
    )
    digests = PiccoloApprovedDigestStore(runtime.nsqd.database)
    for digest in APPROVED_PROJECTION_DIGESTS:
        digests.add(digest, approved_at=runtime.nsqd.clock.now())
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))

    def build(*, container: NsqdContainer, settings: Settings) -> AutonomousTauLabelingUseCase:
        return AutonomousTauLabelingUseCase(
            measurement_evidence=TauMeasurementEvidenceUseCase(
                candidates=container.ctx.candidates,
                approved_projection_digests=digests.list_digests(),
            ),
            llm_client=client,
            clock=container.clock,
            settings=settings.nsqd.autonomous_tau,
        )

    monkeypatch.setattr(tau, "build_autonomous_tau_use_case", build)
    request: dict[str, JsonValue] = {"candidate_artifact_hashes": [candidate_hash]}
    exported = mapping(invoke(runtime, "nsqd.tau.export", request))
    assert candidate_hash in str(exported["jsonl"])
    assert mapping(invoke(runtime, "nsqd.tau.inventory", request))
    reviewed = mapping(invoke(runtime, "nsqd.tau.review", request))
    report_path = Path(str(reviewed["output"]))
    assert report_path.is_relative_to(tmp_path / "output/autonomous-tau-review")
    assert report_path.stat().st_size > 0
    assert len(client.calls) == 8
    evaluated = mapping(
        invoke(runtime, "nsqd.tau.evaluate", {**request, "inputs": [str(report_path)]})
    )
    evaluation_path = Path(str(evaluated["output"]))
    assert evaluation_path.is_relative_to(tmp_path / "output/evaluate-autonomous-tau-reviews")
    assert evaluation_path.stat().st_size > 0
    assert mapping(mapping(evaluated["report"])["packet"])["approved_pair_count"] == 1

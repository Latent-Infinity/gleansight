from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from nsqd.app.use_cases import (
    AutonomousTauLabelingUseCase,
    AutonomousTauPacketEvaluationUseCase,
    TauMeasurementEvidenceUseCase,
)
from nsqd.domain.novelty import NOVELTY_THRESHOLD_TAU
from nsqd.domain.project import PROJECTOR_VERSION, canonical_reviewed_projection_digest
from nsqd.domain.snapshot import sha256_hex
from nsqd.domain.tau_measurement import tau_measurement_artifact_digest
from nsqd.domain.tau_review import (
    TAU_REVIEW_ROUNDS,
    _validated_response_metadata,
    autonomous_tau_review_packet_digest,
    evaluate_autonomous_tau_packet,
    evaluate_balanced_autonomous_tau_packet,
    should_audit_tau_measurement,
)
from nsqd.null_adapters import FixedClock, NullNsqdCandidateStore
from papers.app.ports import LLMResponse
from papers.config.settings import NsqdAutonomousTauSettings

AS_OF = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
POLICIES = ("finance/1", "optimization/1")


class FakeLLMClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "profile": deepcopy(profile),
                "model": model,
                "timeout_s": timeout_s,
            }
        )
        if not self._responses:
            raise AssertionError("unexpected llm call")
        item = self._responses.pop(0)
        return LLMResponse(
            text=json.dumps(item["body"], sort_keys=True),
            tokens_in=11,
            tokens_out=7,
            cost_usd=None,
            response_metadata=deepcopy(item.get("metadata")),
        )


def _approved_neighbor(*, policy_id: str, rank: int) -> dict[str, object]:
    paraphrase = f"approved {policy_id} neighbor {rank}"
    projection: dict[str, object] = {
        "domain_policy_id": policy_id,
        "paraphrase": paraphrase,
        "paraphrase_source": "model_assisted",
        "source_paper_id": f"paper-{policy_id}-{rank}",
        "source": f"doi:10.1/{policy_id}-{rank}",
        "source_abstract_sha256": sha256_hex(f"abstract {policy_id} {rank}".encode()),
        "source_markdown_sha256": sha256_hex(f"markdown {policy_id} {rank}".encode()),
        "paraphrase_sha256": sha256_hex(paraphrase.encode()),
        "human_reviewer": "human-reviewer",
        "human_approved_at": AS_OF.isoformat(),
        "review_status": "approved",
    }
    return {
        "record_id": f"record-{policy_id}-{rank}",
        "source_id": projection["source"],
        "source_paper_id": projection["source_paper_id"],
        "domain_policy_id": policy_id,
        "text_digest": projection["paraphrase_sha256"],
        "projector_version": PROJECTOR_VERSION,
        "reviewed_projection_digest": canonical_reviewed_projection_digest(projection),
        "reviewed_projection": projection,
        "distance": rank / 10,
        "rank": rank,
    }


APPROVED_PROJECTION_DIGESTS = frozenset(
    str(_approved_neighbor(policy_id=policy_id, rank=rank)["reviewed_projection_digest"])
    for policy_id in POLICIES
    for rank in range(1, 6)
)


def _measurement_row(
    *,
    policy_id: str = "finance/1",
    index: int = 0,
    evidence: float = 0.4,
    snapshot_state: str = "production_valid",
) -> dict[str, object]:
    pair_id = f"{policy_id}:pair:{index}"
    candidate_hash = sha256_hex(pair_id.encode("utf-8"))
    candidate_text = f"candidate text {pair_id}"
    snapshot_digest = sha256_hex(f"snapshot:{policy_id}".encode())
    neighbors = [_approved_neighbor(policy_id=policy_id, rank=rank) for rank in range(1, 6)]
    mean_distance = sum(float(item["distance"]) for item in neighbors) / len(neighbors)
    row: dict[str, object] = {
        "pair_id": pair_id,
        "candidate_artifact_hash": candidate_hash,
        "domain_policy_id": policy_id,
        "snapshot_id": snapshot_digest,
        "snapshot_digest": snapshot_digest,
        "snapshot_state": snapshot_state,
        "corpus_version": 11,
        "candidate": {
            "artifact_hash": candidate_hash,
            "paraphrase": candidate_text,
            "text_digest": sha256_hex(candidate_text.encode("utf-8")),
        },
        "neighbor": dict(neighbors[0]),
        "neighbors": neighbors,
        "measurement": {
            "evidence_mean_distance": mean_distance,
            "k": 5,
            "distances": [float(item["distance"]) for item in neighbors],
            "embedding_model_id": "qwen3-embedding:latest",
            "embedding_model_version": "latest",
            "embedding_dimension": 4096,
            "normalization_policy": "l2",
            "distance_metric": "cosine_distance",
            "algorithm_contract_version": "1.1",
            "measured_at": AS_OF.isoformat(),
        },
    }
    row["measurement_artifact_digest"] = tau_measurement_artifact_digest(row)
    return row


def _seed_measurement(store: NullNsqdCandidateStore, row: dict[str, object]) -> str:
    digest = str(row["candidate_artifact_hash"])
    store.put_artifact(
        digest,
        {
            "candidate": deepcopy(row["candidate"]),
            "generator_run_id": "gen-1",
            "grounding": deepcopy(row),
        },
    )
    return digest


def _settings(**overrides: object) -> NsqdAutonomousTauSettings:
    payload: dict[str, Any] = {
        "rounds": TAU_REVIEW_ROUNDS,
        "timeout_s": 30,
        "seed": 17,
        "writer": {
            "agent_id": "tau-writer-local-v1",
            "provider": "ollama",
            "model": "qwen3.6:35b-a3b-q4_K_M",
            "version": "2026-08-24",
            "profile": "tau-writer-local",
            "base_url": "http://127.0.0.1:11434",
            "api_key": "",
        },
        "reviewer": {
            "agent_id": "tau-reviewer-local-v1",
            "provider": "ollama",
            "model": "qwen3.6:35b-a3b-q4_K_M",
            "version": "2026-08-24",
            "profile": "tau-reviewer-local",
            "base_url": "http://127.0.0.1:11434",
            "api_key": "",
        },
        "adjudicator": {
            "agent_id": "tau-adjudicator-frontier-v1",
            "provider": "codex_subscription",
            "model": "gpt-5.6-terra",
            "version": "config-2026-08-29",
            "profile": "tau-adjudicator-frontier",
            "base_url": "",
            "api_key": "",
            "executable_path": "codex",
            "reasoning_effort": "high",
        },
        "audit": {
            "sample_rate": 0.0,
            "policy_revision": "tau-audit/1",
        },
    }
    payload.update(overrides)
    return NsqdAutonomousTauSettings.model_validate(payload)


def _response(
    *,
    pair_id: str,
    label: str,
    rationale: str,
    role: str,
    agent_id: str,
    returned_model: str | None = None,
    created: int = 1_756_485_600,
) -> dict[str, Any]:
    if returned_model is None:
        returned_model = "gpt-5.6-terra" if role == "adjudicator" else "qwen3.6:35b-a3b-q4_K_M"
    if role == "adjudicator":
        metadata = {
            "provider": "codex_subscription",
            "requested_model": returned_model,
            "codex_cli_version": "0.150.1",
            "reasoning_effort": "high",
            "auth_mode": "chatgpt",
            "identity_source": "requested_and_reroute_checked",
        }
    else:
        metadata = {
            "model": returned_model,
            "system_fingerprint": f"fp:{role}:{agent_id}",
            "created": created,
        }
    return {
        "body": {
            "pair_id": pair_id,
            "label": label,
            "rationale": rationale,
            "role": role,
            "agent_id": agent_id,
        },
        "metadata": metadata,
    }


def _local_round_responses(*, pair_id: str, label: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for round_index in range(1, TAU_REVIEW_ROUNDS + 1):
        results.append(
            _response(
                pair_id=pair_id,
                label=label,
                rationale=f"writer round {round_index}: final label {label}",
                role="writer",
                agent_id="tau-writer-local-v1",
            )
        )
        results.append(
            _response(
                pair_id=pair_id,
                label=label,
                rationale=f"reviewer round {round_index}: final label {label}",
                role="reviewer",
                agent_id="tau-reviewer-local-v1",
            )
        )
    return results


def _use_case(
    client: FakeLLMClient,
    store: NullNsqdCandidateStore,
    settings: NsqdAutonomousTauSettings,
) -> AutonomousTauLabelingUseCase:
    return AutonomousTauLabelingUseCase(
        measurement_evidence=TauMeasurementEvidenceUseCase(
            candidates=store,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
        ),
        llm_client=client,
        clock=FixedClock(AS_OF),
        settings=settings,
    )


def test_autonomous_labeling_accepts_final_agreement_and_preserves_runtime_tau() -> None:
    row = _measurement_row(evidence=0.62)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))

    result = _use_case(client, store, _settings()).run([candidate_hash])

    assert result["packet_digest"] == autonomous_tau_review_packet_digest(result["rows"])
    assert result["packet"]["approved_pair_count"] == 1
    reviewed = cast(dict[str, Any], result["rows"][0])
    assert reviewed["final_label"] == "novel"
    assert reviewed["escalation"] is None
    assert len(reviewed["rounds"]) == 8
    assert reviewed["rounds"][0]["response_metadata"]["model"] == "qwen3.6:35b-a3b-q4_K_M"
    assert reviewed["rounds"][0]["response_metadata"]["created"] == 1_756_485_600
    assert NOVELTY_THRESHOLD_TAU == 0.45
    assert len(client.calls) == 8


def test_autonomous_packet_evaluation_revalidates_persisted_measurements() -> None:
    row = _measurement_row(evidence=0.62)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))
    labeled = _use_case(client, store, _settings()).run([candidate_hash])
    evaluator = AutonomousTauPacketEvaluationUseCase(
        measurement_evidence=TauMeasurementEvidenceUseCase(
            candidates=store,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
        ),
        audit_policy_revision="tau-audit/1",
        audit_sample_rate=0.0,
    )

    result = evaluator.run([candidate_hash], labeled["rows"])

    assert result == labeled
    with pytest.raises(ValueError, match="reviewed candidate hashes must exactly match"):
        evaluator.run([candidate_hash], [])


def test_packet_evaluation_rederives_required_deterministic_audit() -> None:
    row = next(
        candidate
        for index in range(1_000)
        if should_audit_tau_measurement(
            str((candidate := _measurement_row(index=index))["measurement_artifact_digest"]),
            audit_policy_revision="tau-audit/1",
            sample_rate=0.10,
        )
    )
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))
    labeled = _use_case(client, store, _settings()).run([candidate_hash])

    with pytest.raises(ValueError, match="adjudication is required"):
        evaluate_autonomous_tau_packet(
            labeled["rows"],
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset({str(row["measurement_artifact_digest"])}),
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.10,
        )


def test_balanced_autonomous_packet_reports_highest_admissible_tau() -> None:
    store = NullNsqdCandidateStore()
    hashes: list[str] = []
    responses: list[dict[str, Any]] = []
    trusted_digests: set[str] = set()
    for policy_id in POLICIES:
        for label, evidence in (("near_duplicate", 0.1), ("novel", 0.8)):
            for index in range(30):
                row = _measurement_row(
                    policy_id=policy_id,
                    index=index if label == "near_duplicate" else index + 30,
                )
                neighbors = cast(list[dict[str, Any]], row["neighbors"])
                distances = [evidence + (rank - 3) * 0.01 for rank in range(1, 6)]
                for neighbor, distance in zip(neighbors, distances, strict=True):
                    neighbor["distance"] = distance
                row["neighbor"] = dict(neighbors[0])
                measurement = cast(dict[str, Any], row["measurement"])
                measurement["distances"] = distances
                measurement["evidence_mean_distance"] = evidence
                row["measurement_artifact_digest"] = tau_measurement_artifact_digest(row)
                hashes.append(_seed_measurement(store, row))
                trusted_digests.add(str(row["measurement_artifact_digest"]))
                responses.extend(_local_round_responses(pair_id=str(row["pair_id"]), label=label))
    labeled = _use_case(FakeLLMClient(responses), store, _settings()).run(hashes)

    result = evaluate_balanced_autonomous_tau_packet(
        labeled["rows"],
        approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
        trusted_measurement_digests=frozenset(trusted_digests),
        audit_policy_revision="tau-audit/1",
        audit_sample_rate=0.0,
    )

    assert result["selected_tau"] == 0.6
    assert result["approved_pair_count"] == 120
    assert result["counts_by_policy"] == {
        policy_id: {"near_duplicate": 30, "novel": 30} for policy_id in POLICIES
    }
    assert NOVELTY_THRESHOLD_TAU == 0.45


def test_autonomous_labeling_validates_all_rows_before_first_model_call() -> None:
    valid = _measurement_row(index=90)
    invalid = _measurement_row(index=91)
    invalid_neighbors = cast(list[dict[str, Any]], invalid["neighbors"])
    invalid_projection = cast(dict[str, Any], deepcopy(invalid_neighbors[0]["reviewed_projection"]))
    invalid_projection["source_paper_id"] = "paper-finance/1-unapproved"
    invalid_projection["source"] = "doi:10.1/finance/1-unapproved"
    invalid_projection["source_markdown_sha256"] = sha256_hex(b"unapproved-markdown")
    invalid_projection["source_abstract_sha256"] = sha256_hex(b"unapproved-abstract")
    invalid_neighbors[0]["reviewed_projection"] = invalid_projection
    invalid_neighbors[0]["source_id"] = invalid_projection["source"]
    invalid_neighbors[0]["source_paper_id"] = invalid_projection["source_paper_id"]
    invalid_neighbors[0]["reviewed_projection_digest"] = canonical_reviewed_projection_digest(
        invalid_projection
    )
    invalid["neighbor"] = dict(invalid_neighbors[0])
    invalid["measurement_artifact_digest"] = tau_measurement_artifact_digest(invalid)
    store = NullNsqdCandidateStore()
    valid_hash = _seed_measurement(store, valid)
    invalid_hash = _seed_measurement(store, invalid)
    client = FakeLLMClient(_local_round_responses(pair_id=str(valid["pair_id"]), label="novel"))

    with pytest.raises(ValueError, match="approved projection"):
        _use_case(client, store, _settings()).run([valid_hash, invalid_hash])
    assert client.calls == []


def test_autonomous_labeling_escalates_final_disagreement_and_ambiguity() -> None:
    disagree_row = _measurement_row(index=1, evidence=0.22)
    ambiguous_row = _measurement_row(index=2, evidence=0.51)
    store = NullNsqdCandidateStore()
    disagree_hash = _seed_measurement(store, disagree_row)
    ambiguous_hash = _seed_measurement(store, ambiguous_row)
    responses = _local_round_responses(
        pair_id=str(disagree_row["pair_id"]), label="near_duplicate"
    )[:-1]
    responses.append(
        _response(
            pair_id=str(disagree_row["pair_id"]),
            label="novel",
            rationale="reviewer round 4: final label novel",
            role="reviewer",
            agent_id="tau-reviewer-local-v1",
        )
    )
    responses.append(
        _response(
            pair_id=str(disagree_row["pair_id"]),
            label="novel",
            rationale="adjudicator resolves to novel",
            role="adjudicator",
            agent_id="tau-adjudicator-frontier-v1",
        )
    )
    responses.extend(
        _local_round_responses(pair_id=str(ambiguous_row["pair_id"]), label="ambiguous")
    )
    responses.append(
        _response(
            pair_id=str(ambiguous_row["pair_id"]),
            label="ambiguous",
            rationale="adjudicator keeps ambiguous",
            role="adjudicator",
            agent_id="tau-adjudicator-frontier-v1",
        )
    )
    client = FakeLLMClient(responses)

    result = _use_case(client, store, _settings()).run([disagree_hash, ambiguous_hash])

    first = cast(dict[str, Any], result["rows"][0])
    second = cast(dict[str, Any], result["rows"][1])
    assert first["final_label"] == "novel"
    assert first["escalation"]["reason"] == "final_disagreement"
    assert first["adjudication"]["role"] == "adjudicator"
    assert second["final_label"] == "ambiguous"
    assert second["escalation"]["reason"] == "final_ambiguity"
    assert result["packet"]["approved_pair_count"] == 1
    assert result["packet"]["ambiguous_pair_count"] == 1


def test_autonomous_labeling_rejects_unknown_candidate_hash_before_any_llm_call() -> None:
    client = FakeLLMClient([])
    use_case = _use_case(client, NullNsqdCandidateStore(), _settings())
    with pytest.raises(ValueError, match="unknown candidate artifact hash"):
        use_case.run(["f" * 64])
    assert client.calls == []


def test_autonomous_labeling_rejects_invalid_measurement_provenance_before_adjudication() -> None:
    row = _measurement_row(index=3)
    row["corpus_version"] = 12
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))
    with pytest.raises(ValueError, match="measurement digest"):
        _use_case(client, store, _settings()).run([candidate_hash])
    assert client.calls == []


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"system_fingerprint": "fp:writer:tau-writer-local-v1", "created": 1}, "returned model"),
        (
            {
                "model": "wrong-model",
                "system_fingerprint": "fp:writer:tau-writer-local-v1",
                "created": 1,
            },
            "returned model",
        ),
    ],
)
def test_autonomous_labeling_fails_closed_on_missing_or_mismatched_returned_model(
    metadata: dict[str, object],
    message: str,
) -> None:
    row = _measurement_row(index=92)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    responses = _local_round_responses(pair_id=str(row["pair_id"]), label="novel")
    responses[0]["metadata"] = metadata
    client = FakeLLMClient(responses)

    with pytest.raises(ValueError, match=message):
        _use_case(client, store, _settings()).run([candidate_hash])


def test_autonomous_labeling_uses_strict_json_schema_payload() -> None:
    row = _measurement_row(index=93)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))

    _use_case(client, store, _settings()).run([candidate_hash])

    schema = client.calls[0]["profile"]["chat_options"]["response_format"]["json_schema"]
    prompt = client.calls[0]["prompt"]
    assert "Prompt version: tau-writer/3" in prompt
    assert '"ordered_neighbors"' in prompt
    assert '"reviewed_projection"' not in prompt
    assert '"human_reviewer"' not in prompt
    assert schema["name"] == "tau_label"
    assert schema["strict"] is True
    assert schema["schema"] == {
        "type": "object",
        "properties": {
            "pair_id": {"type": "string", "enum": [str(row["pair_id"])]},
            "label": {
                "type": "string",
                "enum": ["near_duplicate", "novel", "ambiguous"],
            },
            "rationale": {"type": "string", "minLength": 1, "maxLength": 320},
        },
        "required": ["pair_id", "label", "rationale"],
        "additionalProperties": False,
    }


def test_codex_config_is_required_only_when_escalation_occurs() -> None:
    row = _measurement_row(index=94)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    local_only = _settings(
        adjudicator={
            "agent_id": "tau-adjudicator-frontier-v1",
            "provider": "codex_subscription",
            "model": "gpt-5-codex",
            "version": "2026-08-01",
            "profile": "tau-adjudicator-frontier",
            "base_url": "",
            "api_key": "",
            "executable_path": "",
            "reasoning_effort": "",
        }
    )
    local_client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))
    result = _use_case(local_client, store, local_only).run([candidate_hash])
    reviewed = cast(dict[str, Any], result["rows"][0])
    assert reviewed["adjudication"] is None

    escalated_client = FakeLLMClient(
        _local_round_responses(pair_id=str(row["pair_id"]), label="ambiguous")
    )
    with pytest.raises(ValueError, match="codex adjudicator route is not configured"):
        _use_case(escalated_client, store, local_only).run([candidate_hash])


def test_local_writer_route_must_be_configured_before_any_model_call() -> None:
    row = _measurement_row(index=95)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))
    settings = _settings(
        writer={
            "agent_id": "tau-writer-local-v1",
            "provider": "ollama",
            "model": "qwen3.6:35b-a3b-q4_K_M",
            "version": "2026-08-24",
            "profile": "tau-writer-local",
            "base_url": "",
            "api_key": "",
        }
    )

    with pytest.raises(ValueError, match="writer route is not configured"):
        _use_case(client, store, settings).run([candidate_hash])
    assert client.calls == []


def test_packet_validation_rejects_overlapping_identities_missing_metadata_and_short_rounds() -> (
    None
):
    row = _measurement_row(index=4)
    trusted = frozenset({str(row["measurement_artifact_digest"])})
    call = {
        "round": 1,
        "role": "writer",
        "agent_id": "same-agent",
        "provider": "ollama",
        "model": "qwen3.6:35b-a3b-q4_K_M",
        "version": "2026-08-24",
        "profile": "shared-profile",
        "prompt_version_id": "tau-writer/2",
        "prompt": "writer prompt",
        "prompt_sha256": sha256_hex(b"writer prompt"),
        "input_payload": {"pair_id": row["pair_id"]},
        "input_sha256": sha256_hex(
            json.dumps({"pair_id": row["pair_id"]}, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ),
        "output_text": json.dumps(
            {"pair_id": row["pair_id"], "label": "novel", "rationale": "novel"},
            separators=(",", ":"),
        ),
        "output_sha256": sha256_hex(
            json.dumps(
                {"pair_id": row["pair_id"], "label": "novel", "rationale": "novel"},
                separators=(",", ":"),
            ).encode("utf-8")
        ),
        "label": "novel",
        "rationale": "novel",
        "called_at": AS_OF.isoformat(),
        "response_metadata": {"model": "qwen3.6:35b-a3b-q4_K_M", "created": 1},
    }
    packet = {
        "pair_id": row["pair_id"],
        "candidate_artifact_hash": row["candidate_artifact_hash"],
        "domain_policy_id": row["domain_policy_id"],
        "snapshot_id": row["snapshot_id"],
        "snapshot_digest": row["snapshot_digest"],
        "snapshot_state": row["snapshot_state"],
        "corpus_version": row["corpus_version"],
        "candidate": row["candidate"],
        "neighbor": row["neighbor"],
        "neighbors": row["neighbors"],
        "measurement": row["measurement"],
        "measurement_artifact_digest": row["measurement_artifact_digest"],
        "rounds": [deepcopy(call) for _ in range(7)],
        "final_label": "novel",
        "final_rationale": "novel",
        "adjudication": None,
        "escalation": None,
    }
    with pytest.raises(ValueError, match="at least 8 local round calls"):
        evaluate_autonomous_tau_packet(
            [packet],
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=trusted,
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )

    packet["rounds"] = [deepcopy(call) for _ in range(8)]
    rounds = packet["rounds"]
    assert isinstance(rounds, list)
    for index, item in enumerate(rounds, start=1):
        item["round"] = ((index - 1) // 2) + 1
        item["role"] = "writer" if index % 2 == 1 else "reviewer"
        item["prompt_version_id"] = "tau-writer/2" if item["role"] == "writer" else "tau-reviewer/2"
    with pytest.raises(ValueError, match="writer and reviewer identities must differ"):
        evaluate_autonomous_tau_packet(
            [packet],
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=trusted,
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )

    for index, item in enumerate(rounds, start=1):
        item["agent_id"] = "tau-writer-local-v1" if index % 2 == 1 else "tau-reviewer-local-v1"
        item["profile"] = "tau-writer-local" if index % 2 == 1 else "tau-reviewer-local"
    rounds[0].pop("provider")
    with pytest.raises(ValueError, match="provider is required"):
        evaluate_autonomous_tau_packet(
            [packet],
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=trusted,
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )


def test_packet_validation_rejects_digest_drift() -> None:
    row = _measurement_row(index=5)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))
    result = _use_case(client, store, _settings()).run([candidate_hash])
    tampered = cast(list[dict[str, Any]], deepcopy(result["rows"]))
    tampered[0]["rounds"][0]["output_text"] = (
        '{"pair_id":"tampered","label":"novel","rationale":"tampered"}'
    )
    with pytest.raises(ValueError, match="output digest drift"):
        evaluate_autonomous_tau_packet(
            tampered,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset({str(row["measurement_artifact_digest"])}),
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )


def test_packet_validation_rejects_unsupported_prompt_version() -> None:
    row = _measurement_row(index=94)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    result = _use_case(
        FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel")),
        store,
        _settings(),
    ).run([candidate_hash])
    tampered = cast(list[dict[str, Any]], deepcopy(result["rows"]))
    rounds = cast(list[dict[str, Any]], tampered[0]["rounds"])
    rounds[0]["prompt_version_id"] = "tau-writer/999"

    with pytest.raises(ValueError, match="unsupported writer prompt version"):
        evaluate_autonomous_tau_packet(
            tampered,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset({str(row["measurement_artifact_digest"])}),
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )


def test_packet_validation_escalates_schema_inconsistency_and_requires_distinct_adjudicator() -> (
    None
):
    row = _measurement_row(index=6)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    responses = _local_round_responses(pair_id=str(row["pair_id"]), label="novel")
    responses[-1] = _response(
        pair_id=str(row["pair_id"]),
        label="novel",
        rationale="reviewer round 4: final label near_duplicate",
        role="reviewer",
        agent_id="tau-reviewer-local-v1",
    )
    responses.append(
        _response(
            pair_id=str(row["pair_id"]),
            label="novel",
            rationale="adjudicator final novel",
            role="adjudicator",
            agent_id="tau-adjudicator-frontier-v1",
        )
    )
    client = FakeLLMClient(responses)
    result = _use_case(client, store, _settings()).run([candidate_hash])
    reviewed = cast(dict[str, Any], result["rows"][0])
    assert reviewed["escalation"]["reason"] == "schema_rationale_inconsistency"

    tampered = cast(list[dict[str, Any]], deepcopy(result["rows"]))
    adjudication = cast(dict[str, Any], tampered[0]["adjudication"])
    assert isinstance(adjudication, dict)
    adjudication["agent_id"] = "tau-writer-local-v1"
    with pytest.raises(ValueError, match="adjudicator identity must differ"):
        evaluate_autonomous_tau_packet(
            tampered,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset({str(row["measurement_artifact_digest"])}),
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )


def test_autonomous_labeling_escalates_deterministic_audit() -> None:
    row = next(
        candidate
        for index in range(1_000)
        if should_audit_tau_measurement(
            str((candidate := _measurement_row(index=index))["measurement_artifact_digest"]),
            audit_policy_revision="tau-audit/1",
            sample_rate=0.10,
        )
    )
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(
        _local_round_responses(pair_id=str(row["pair_id"]), label="novel")
        + [
            _response(
                pair_id=str(row["pair_id"]),
                label="novel",
                rationale="adjudicator audit keeps novel",
                role="adjudicator",
                agent_id="tau-adjudicator-frontier-v1",
            )
        ]
    )
    result = _use_case(
        client,
        store,
        _settings(audit={"sample_rate": 0.10, "policy_revision": "tau-audit/1"}),
    ).run([candidate_hash])

    reviewed = cast(dict[str, Any], result["rows"][0])
    assert reviewed["escalation"] == {
        "reason": "deterministic_audit",
        "audit_policy_revision": "tau-audit/1",
    }


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"pair_id": "wrong", "label": "novel", "rationale": "novel"}, "pair_id"),
        (
            {"pair_id": "finance/1:pair:11", "label": "blocked", "rationale": "novel"},
            "label is invalid",
        ),
        (
            {"pair_id": "finance/1:pair:11", "label": "novel", "rationale": ""},
            "rationale is required",
        ),
        (
            {"pair_id": "finance/1:pair:11", "label": "novel", "rationale": "x" * 321},
            "rationale exceeds the maximum length",
        ),
    ],
)
def test_autonomous_labeling_rejects_invalid_llm_outputs(
    body: dict[str, str],
    message: str,
) -> None:
    row = _measurement_row(index=11)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(
        [
            {
                "body": body,
                "metadata": {
                    "model": "qwen3.6:35b-a3b-q4_K_M",
                    "system_fingerprint": "fp:test",
                    "created": 1,
                },
            }
        ]
    )

    with pytest.raises(ValueError, match=message):
        _use_case(client, store, _settings()).run([candidate_hash])


def test_packet_validation_rejects_extra_rounds_bad_order_and_unneeded_adjudication() -> None:
    row = _measurement_row(index=12)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))
    result = _use_case(client, store, _settings()).run([candidate_hash])
    trusted = frozenset({str(row["measurement_artifact_digest"])})

    too_many = cast(list[dict[str, Any]], deepcopy(result["rows"]))
    extra_round = deepcopy(too_many[0]["rounds"][0])
    too_many[0]["rounds"].append(extra_round)
    with pytest.raises(ValueError, match="exactly 8 local round calls"):
        evaluate_autonomous_tau_packet(
            too_many,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=trusted,
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )

    bad_order = cast(list[dict[str, Any]], deepcopy(result["rows"]))
    bad_order[0]["rounds"][0]["role"] = "reviewer"
    with pytest.raises(ValueError, match="writer then reviewer"):
        evaluate_autonomous_tau_packet(
            bad_order,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=trusted,
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )

    unnecessary = cast(list[dict[str, Any]], deepcopy(result["rows"]))
    unnecessary[0]["adjudication"] = deepcopy(unnecessary[0]["rounds"][0])
    with pytest.raises(ValueError, match="adjudication must be absent"):
        evaluate_autonomous_tau_packet(
            unnecessary,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=trusted,
            audit_policy_revision="tau-audit/1",
            audit_sample_rate=0.0,
        )


def test_deterministic_audit_sampling_is_stable_and_config_driven() -> None:
    first = _measurement_row(index=7)
    second = _measurement_row(index=8)
    decision_a = should_audit_tau_measurement(
        str(first["measurement_artifact_digest"]),
        audit_policy_revision="tau-audit/1",
        sample_rate=0.10,
    )
    decision_b = should_audit_tau_measurement(
        str(first["measurement_artifact_digest"]),
        audit_policy_revision="tau-audit/1",
        sample_rate=0.10,
    )
    reordered = [second, first]
    assert reordered[1]["measurement_artifact_digest"] == first["measurement_artifact_digest"]
    assert decision_a is decision_b
    changed_revision = should_audit_tau_measurement(
        str(first["measurement_artifact_digest"]),
        audit_policy_revision="tau-audit/2",
        sample_rate=0.10,
    )
    assert isinstance(changed_revision, bool)


def test_packet_digest_changes_with_metadata_changes() -> None:
    row = _measurement_row(index=9)
    store = NullNsqdCandidateStore()
    candidate_hash = _seed_measurement(store, row)
    client = FakeLLMClient(_local_round_responses(pair_id=str(row["pair_id"]), label="novel"))
    result = _use_case(client, store, _settings()).run([candidate_hash])
    rows = result["rows"]
    digest = autonomous_tau_review_packet_digest(rows)
    changed = cast(list[dict[str, Any]], deepcopy(rows))
    changed[0]["rounds"][0]["provider"] = "different-provider"
    assert autonomous_tau_review_packet_digest(changed) != digest


def test_settings_validation_requires_distinct_agent_identities() -> None:
    with pytest.raises(ValueError, match="writer and reviewer agent_id values must differ"):
        _settings(
            reviewer={
                "agent_id": "tau-writer-local-v1",
                "provider": "ollama",
                "model": "qwen3.6:35b-a3b-q4_K_M",
                "version": "2026-08-24",
                "profile": "tau-reviewer-local",
                "base_url": "http://127.0.0.1:11434",
                "api_key": "",
            }
        )


def test_tau_review_metadata_validation_rejects_bad_codex_metadata() -> None:
    with pytest.raises(ValueError, match="requires codex_subscription provider"):
        _validated_response_metadata(
            {
                "provider": "ollama",
                "model": "gpt-5.6-terra",
                "response_metadata": {
                    "provider": "codex_subscription",
                    "requested_model": "gpt-5.6-terra",
                    "codex_cli_version": "0.150.1",
                    "reasoning_effort": "high",
                    "auth_mode": "chatgpt",
                    "identity_source": "requested_and_reroute_checked",
                },
            }
        )
    with pytest.raises(ValueError, match="codex auth mode must be chatgpt"):
        _validated_response_metadata(
            {
                "provider": "codex_subscription",
                "model": "gpt-5.6-terra",
                "response_metadata": {
                    "provider": "codex_subscription",
                    "requested_model": "gpt-5.6-terra",
                    "codex_cli_version": "0.150.1",
                    "reasoning_effort": "high",
                    "auth_mode": "api_key",
                    "identity_source": "requested_and_reroute_checked",
                },
            }
        )
    with pytest.raises(ValueError, match="codex provider metadata is invalid"):
        _validated_response_metadata(
            {
                "provider": "codex_subscription",
                "model": "gpt-5.6-terra",
                "response_metadata": {
                    "provider": "wrong",
                    "requested_model": "gpt-5.6-terra",
                    "codex_cli_version": "0.150.1",
                    "reasoning_effort": "high",
                    "auth_mode": "chatgpt",
                    "identity_source": "requested_and_reroute_checked",
                },
            }
        )


def test_tau_review_metadata_validation_rejects_bad_openai_metadata_types() -> None:
    with pytest.raises(ValueError, match="system_fingerprint must be a string"):
        _validated_response_metadata(
            {
                "provider": "ollama",
                "model": "qwen3.6:35b-a3b-q4_K_M",
                "response_metadata": {
                    "model": "qwen3.6:35b-a3b-q4_K_M",
                    "system_fingerprint": 7,
                },
            }
        )
    with pytest.raises(ValueError, match="created must be an integer timestamp"):
        _validated_response_metadata(
            {
                "provider": "ollama",
                "model": "qwen3.6:35b-a3b-q4_K_M",
                "response_metadata": {
                    "model": "qwen3.6:35b-a3b-q4_K_M",
                    "created": "bad",
                },
            }
        )

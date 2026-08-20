from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from nsqd.domain.card import card_decision, missing_card_fields
from nsqd.domain.descriptor import cell_id_from_descriptor
from nsqd.domain.elite import choose_elite
from nsqd.domain.grounding import classify_local
from nsqd.domain.harvest import OPTIONAL_RECORD_FIELDS, harvest_records_from_payload
from nsqd.domain.novelty import SnapshotState, mean_cosine_distance, novelty_term
from nsqd.domain.snapshot import (
    canonical_json,
    normalize_source,
    record_content_hash,
    sha256_hex,
    snapshot_id,
)
from nsqd.domain.viability import score_dpred, score_dval, score_fals, score_mech, viability
from nsqd.ports import (
    Clock,
    CorpusIndex,
    CorpusRecordStore,
    CorpusSnapshotStore,
    FrontierCardStore,
    HarvestStore,
    NsqdCandidateStore,
)


def empty_smoke_snapshot_id() -> str:
    return snapshot_id(records=[], schema_version=1)


def candidate_body(candidate: dict[str, Any]) -> dict[str, Any]:
    return deepcopy({key: value for key, value in candidate.items() if key != "expected_outcomes"})


def artifact_hash_for(candidate: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(candidate_body(candidate)))


def _require_snapshot_state(snapshot_state: str) -> SnapshotState:
    if snapshot_state == "smoke_only":
        return "smoke_only"
    if snapshot_state == "calibration":
        return "calibration"
    if snapshot_state == "production_valid":
        return "production_valid"
    raise ValueError(
        "invalid snapshot_state: expected one of smoke_only, calibration, production_valid"
    )


@dataclass(frozen=True)
class HarvestUseCase:
    harvest: HarvestStore
    clock: Clock

    def run(self, payload: Any) -> dict[str, Any]:
        items = harvest_records_from_payload(payload)
        harvested_at = self.clock.now().isoformat()
        records: list[dict[str, Any]] = []
        for item in items:
            rec_type = item["type"]
            paraphrase = item["paraphrase"]
            source = item["source"]
            assert isinstance(rec_type, str)
            assert isinstance(paraphrase, str)
            assert isinstance(source, str)
            digest = record_content_hash(
                type=rec_type,
                paraphrase=paraphrase,
                source=source,
            )
            record = {
                "record_id": digest,
                "content_hash": digest,
                "type": rec_type,
                "paraphrase": paraphrase,
                "source": source,
                "harvested_at": harvested_at,
            }
            record.update(
                {key: deepcopy(item[key]) for key in OPTIONAL_RECORD_FIELDS if key in item}
            )
            records.append(record)

        committed = self.harvest.commit(records, schema_version=1)
        return {
            "record_ids": list(committed.record_ids),
            "snapshot_id": committed.snapshot_id,
            "corpus_version": committed.corpus_version,
        }


@dataclass(frozen=True)
class DivergeUseCase:
    candidates: NsqdCandidateStore
    clock: Clock

    def run(self, *, candidate: dict[str, Any], axiom: str, generator_run_id: str) -> str:
        body = candidate_body(candidate)
        digest = artifact_hash_for(candidate)
        self.candidates.put_artifact(
            digest,
            {
                "candidate": body,
                "axiom": axiom,
                "operator": "A",
                "generator_run_id": generator_run_id,
                "generated_at": self.clock.now().isoformat(),
            },
        )
        return digest


@dataclass(frozen=True)
class GroundUseCase:
    snapshots: CorpusSnapshotStore
    records: CorpusRecordStore
    index: CorpusIndex
    candidates: NsqdCandidateStore

    def run(
        self,
        *,
        candidate_artifact_hash: str,
        snapshot_id: str,
        corpus_version: int,
    ) -> dict[str, Any]:
        artifact = self._require_artifact(candidate_artifact_hash)
        self._require_snapshot(snapshot_id)
        record_ids = self.snapshots.record_ids(snapshot_id)
        rows = [self.records.get(record_id) for record_id in record_ids]
        present = [row for row in rows if row is not None]
        source = str(artifact["candidate"].get("source") or "")
        normalized_source = normalize_source(source) if source else ""
        exact = any(
            normalize_source(str(row.get("source") or "")) == normalized_source
            and normalized_source != ""
            for row in present
        )
        terminology = any("terminology" in set(row.get("tags") or []) for row in present)
        evidence = mean_cosine_distance([])
        if present:
            query = artifact["candidate"].get("query_vector")
            if isinstance(query, list) and query:
                hits = self.index.query(snapshot_id, [float(x) for x in query], k=5)
                evidence = mean_cosine_distance([hit.distance for hit in hits])
        code_or_benchmark = any(row.get("type") in {"code", "benchmark"} for row in present)
        klass, confidence, layers = classify_local(
            exact_source_hit=exact,
            terminology_hit=terminology,
            evidence=evidence,
            code_or_benchmark_hit=code_or_benchmark,
        )
        result = {
            "grounding_class": klass,
            "confidence": confidence,
            "layers": [asdict(layer) for layer in layers],
            "evidence": evidence,
            "snapshot_id": snapshot_id,
            "corpus_version": corpus_version,
        }
        updated = dict(artifact)
        updated["grounding"] = result
        self.candidates.put_artifact(candidate_artifact_hash, updated)
        return result

    def _require_artifact(self, candidate_artifact_hash: str) -> dict[str, Any]:
        artifact = self.candidates.get_artifact(candidate_artifact_hash)
        if artifact is None:
            raise ValueError("unknown candidate_artifact_hash")
        return artifact

    def _require_snapshot(self, snapshot_id: str) -> None:
        if self.snapshots.get(snapshot_id) is None:
            raise ValueError("unknown snapshot_id")


@dataclass(frozen=True)
class ScoreUseCase:
    candidates: NsqdCandidateStore
    cards: FrontierCardStore
    snapshots: CorpusSnapshotStore
    records: CorpusRecordStore

    def run(
        self,
        *,
        candidate_artifact_hash: str,
        evaluator_run_id: str,
        snapshot_id: str,
        corpus_version: int,
        snapshot_state: str,
        live_candidate: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if live_candidate is not None:
            raise ValueError("evaluator must load the artifact by hash")
        artifact = self.candidates.get_artifact(candidate_artifact_hash)
        if artifact is None:
            raise ValueError("unknown candidate_artifact_hash")
        if evaluator_run_id == artifact["generator_run_id"]:
            raise ValueError("evaluator_run_id must differ from generator_run_id")
        grounding = artifact.get("grounding")
        if not isinstance(grounding, dict):
            raise ValueError("candidate must be grounded before scoring")
        if grounding.get("snapshot_id") != snapshot_id:
            raise ValueError("snapshot_id does not match grounded artifact")
        if grounding.get("corpus_version") != corpus_version:
            raise ValueError("corpus_version does not match grounded artifact")
        validated_snapshot_state = _require_snapshot_state(snapshot_state)
        candidate = artifact["candidate"]
        evidence = grounding.get("evidence")
        nov = novelty_term(
            evidence=evidence if isinstance(evidence, float) or evidence is None else None,
            snapshot_state=validated_snapshot_state,
            grounding_class=grounding["grounding_class"],
        )
        domain_pack = str(candidate.get("domain_pack") or "finance/1")
        mech = score_mech(candidate, domain_pack=domain_pack)
        fals = score_fals(candidate)
        dpred = score_dpred(candidate)
        dval = score_dval(candidate)
        via = viability(nov=nov, mech=mech, fals=fals, dpred=dpred, dval=dval)
        cell_id = cell_id_from_descriptor(candidate.get("research_descriptor") or {})
        decision = card_decision(via)
        card = {
            "card_id": candidate_artifact_hash,
            "cell_id": cell_id,
            "title": candidate.get("title") or "",
            "generating_operator": artifact["operator"],
            "snapshot_id": snapshot_id,
            "corpus_version": corpus_version,
            "viability": via,
            "nov": nov,
            "mech": mech,
            "fals": fals,
            "dpred": dpred,
            "dval": dval,
            "candidate_artifact_hash": candidate_artifact_hash,
            "card_decision": decision,
            "evaluator_run_id": evaluator_run_id,
            "generator_run_id": artifact["generator_run_id"],
        }
        missing = missing_card_fields(card)
        card["missing_fields"] = missing
        if missing:
            raise ValueError(f"card missing required fields: {missing}")
        evaluated = dict(artifact)
        evaluated["novelty"] = {
            "evidence": evidence,
            "term": nov,
            "snapshot_id": snapshot_id,
            "snapshot_state": validated_snapshot_state,
            "corpus_version": corpus_version,
            "measurement_stamp": {
                "embedding_model_id": "none",
                "embedding_model_version": "none",
                "normalization_policy": "none",
                "distance_metric": "cosine_distance",
                "algorithm_contract_version": "1.1",
            },
        }
        self.candidates.put_artifact(candidate_artifact_hash, evaluated)
        self.cards.put_card(card)
        return {
            "evidence": evidence,
            "nov": nov,
            "mech": mech,
            "fals": fals,
            "dpred": dpred,
            "dval": dval,
            "viability": via,
            "card": card,
            "evaluator_run_id": evaluator_run_id,
        }


@dataclass(frozen=True)
class ArchiveInsertUseCase:
    cards: FrontierCardStore

    def run(self, card: dict[str, Any]) -> dict[str, Any]:
        cell_id = str(card["cell_id"])
        current = self.cards.elite_for_cell(cell_id)
        if int(card.get("viability") or 0) <= 0:
            return {"inserted": False, "reason": "viability_zero", "elite": current}
        chosen = choose_elite(cell_elite=current, candidate=card)
        assert chosen is not None
        self.cards.set_elite(cell_id, str(chosen["card_id"]))
        replaced = current is None or str(current.get("card_id")) != str(chosen["card_id"])
        return {
            "inserted": replaced and str(chosen["card_id"]) == str(card["card_id"]),
            "reason": None,
            "elite": chosen,
        }

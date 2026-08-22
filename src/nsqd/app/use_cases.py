from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from nsqd.domain.card import (
    card_decision,
    corpus_ingest_rejection,
    missing_card_fields,
    needs_re_score,
)
from nsqd.domain.coverage import evaluate_rank_guard
from nsqd.domain.elite import choose_elite
from nsqd.domain.grounding import classify_local
from nsqd.domain.harvest import (
    OPTIONAL_RECORD_FIELDS,
    HarvestRejected,
    harvest_records_from_payload,
)
from nsqd.domain.novelty import SnapshotState, mean_cosine_distance, novelty_term
from nsqd.domain.policy import (
    FINANCE_POLICY,
    archive_cell_key,
    get_policy,
    records_for_policy,
    require_compatible_dval_rubric,
    require_domain_policy_id,
)
from nsqd.domain.project import (
    PROJECTOR_VERSION,
    canonical_reviewed_projection_bytes,
    canonical_reviewed_projection_digest,
    is_abstract_substitution,
    is_data_nsqd_04,
    normalize_paraphrase,
    projection_identity,
    projection_record_id,
)
from nsqd.domain.snapshot import (
    canonical_json,
    is_utc_datetime,
    normalize_source,
    record_content_hash,
    sha256_hex,
    snapshot_id,
)
from nsqd.domain.status import CellStatus
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


MAX_REVIEWED_PROJECTION_BYTES = 65_536


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
            domain_policy_id = str(item["domain_policy_id"])
            assert isinstance(rec_type, str)
            assert isinstance(paraphrase, str)
            assert isinstance(source, str)
            try:
                policy_id = get_policy(domain_policy_id.strip()).policy_id
            except ValueError as exc:
                raise HarvestRejected(str(exc)) from exc
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
                "domain_policy_id": policy_id,
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
class ProjectPaperUseCase:
    harvest: HarvestStore
    records: CorpusRecordStore
    clock: Clock
    approved_projection_digests: frozenset[str]

    def run(self, *, domain_policy_id: str, projection: dict[str, Any]) -> dict[str, Any]:
        if not domain_policy_id.strip():
            raise ValueError("domain_policy_id is required")
        policy = get_policy(domain_policy_id.strip())
        card_reason = corpus_ingest_rejection(projection)
        if card_reason is not None:
            raise ValueError(card_reason)
        if str(projection.get("review_status") or "") != "approved":
            raise ValueError("paraphrase must be human-approved")
        paraphrase = projection.get("paraphrase")
        if not isinstance(paraphrase, str) or not paraphrase.strip():
            raise ValueError("empty paraphrase")
        normalized_paraphrase = normalize_paraphrase(paraphrase)
        human_reviewer = projection.get("human_reviewer")
        if not isinstance(human_reviewer, str) or not human_reviewer.strip():
            raise ValueError("human_reviewer is required")
        normalized_human_reviewer = human_reviewer.strip()
        human_approved_at = projection.get("human_approved_at")
        normalized_human_approved_at = self._normalize_utc_timestamp(human_approved_at)
        paraphrase_source = projection.get("paraphrase_source")
        if not isinstance(paraphrase_source, str) or not paraphrase_source.strip():
            raise ValueError("paraphrase_source is required")
        normalized_paraphrase_source = paraphrase_source.strip()
        raw_abstract = projection.get("abstract")
        abstract = raw_abstract if isinstance(raw_abstract, str) else None
        source_paper_id = projection.get("source_paper_id")
        if not isinstance(source_paper_id, str) or not source_paper_id.strip():
            raise ValueError("source_paper_id is required")
        normalized_source_paper_id = source_paper_id.strip()
        projection_policy_id = projection.get("domain_policy_id")
        if not isinstance(projection_policy_id, str) or not projection_policy_id.strip():
            raise ValueError("projection.domain_policy_id is required")
        normalized_projection_policy_id = projection_policy_id.strip()
        if normalized_projection_policy_id != policy.policy_id:
            raise ValueError("projection.domain_policy_id must match explicit domain_policy_id")
        if is_data_nsqd_04(projection) and policy.policy_id == "finance/1":
            raise ValueError("DATA-NSQD-04 cannot credit finance/1")
        if is_data_nsqd_04(projection) and policy.policy_id != "optimization/1":
            raise ValueError("DATA-NSQD-04 projects only into optimization/1")
        source_abstract_sha256 = self._require_sha256(
            "source_abstract_sha256",
            projection.get("source_abstract_sha256"),
        )
        source_markdown_sha256 = self._require_sha256(
            "source_markdown_sha256",
            projection.get("source_markdown_sha256"),
        )
        paraphrase_sha256 = self._require_sha256(
            "paraphrase_sha256",
            projection.get("paraphrase_sha256"),
        )
        if sha256_hex(normalized_paraphrase.encode("utf-8")) != paraphrase_sha256:
            raise ValueError("paraphrase_sha256 does not match normalized paraphrase bytes")
        if paraphrase_sha256 == source_abstract_sha256:
            raise ValueError("abstract is not a mechanism paraphrase")
        if is_abstract_substitution(paraphrase=normalized_paraphrase, abstract=abstract):
            raise ValueError("abstract is not a mechanism paraphrase")
        canonical_projection = canonical_reviewed_projection_bytes(
            {
                **projection,
                "domain_policy_id": normalized_projection_policy_id,
                "human_approved_at": normalized_human_approved_at,
                "human_reviewer": normalized_human_reviewer,
                "paraphrase": normalized_paraphrase,
                "paraphrase_source": normalized_paraphrase_source,
                "source_paper_id": normalized_source_paper_id,
            }
        )
        if len(canonical_projection) > MAX_REVIEWED_PROJECTION_BYTES:
            raise ValueError("reviewed projection payload is too large")
        reviewed_projection_digest = canonical_reviewed_projection_digest(
            {
                **projection,
                "domain_policy_id": normalized_projection_policy_id,
                "human_approved_at": normalized_human_approved_at,
                "human_reviewer": normalized_human_reviewer,
                "paraphrase": normalized_paraphrase,
                "paraphrase_source": normalized_paraphrase_source,
                "source_paper_id": normalized_source_paper_id,
            }
        )
        if reviewed_projection_digest not in self.approved_projection_digests:
            raise ValueError("projection is not an approved reviewed projection")
        identity = {
            "source_paper_id": normalized_source_paper_id,
            "domain_policy_id": policy.policy_id,
            "source_abstract_sha256": source_abstract_sha256,
            "source_markdown_sha256": source_markdown_sha256,
            "paraphrase_sha256": paraphrase_sha256,
        }
        source = f"paper:{normalized_source_paper_id}"
        content_hash = record_content_hash(
            type="paper",
            paraphrase=normalized_paraphrase,
            source=source,
        )
        record_id = projection_record_id(identity)
        existing = self.records.get(record_id)
        if existing is not None and projection_identity(existing) == projection_identity(identity):
            committed = self.harvest.commit([existing], schema_version=1)
            return {
                "created": False,
                "record_id": str(existing["record_id"]),
                "snapshot_id": committed.snapshot_id,
                "corpus_version": committed.corpus_version,
            }
        record = {
            "record_id": record_id,
            "content_hash": content_hash,
            "type": "paper",
            "paraphrase": normalized_paraphrase,
            "source": source,
            "harvested_at": self.clock.now().isoformat(),
            "domain_policy_id": policy.policy_id,
            "source_paper_id": normalized_source_paper_id,
            "review_status": "approved",
            "paraphrase_source": normalized_paraphrase_source,
            "human_reviewer": normalized_human_reviewer,
            "human_approved_at": normalized_human_approved_at,
            "projector_version": PROJECTOR_VERSION,
            "source_abstract_sha256": identity["source_abstract_sha256"],
            "source_markdown_sha256": identity["source_markdown_sha256"],
            "paraphrase_sha256": identity["paraphrase_sha256"],
        }
        committed = self.harvest.commit([record], schema_version=1)
        return {
            "created": True,
            "record_id": record_id,
            "snapshot_id": committed.snapshot_id,
            "corpus_version": committed.corpus_version,
        }

    @staticmethod
    def _require_sha256(name: str, value: object) -> str:
        digest = str(value or "")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        return digest

    @staticmethod
    def _normalize_utc_timestamp(value: object) -> str:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("human_approved_at must be a UTC timestamp") from exc
        if not is_utc_datetime(value):
            raise ValueError("human_approved_at must be a UTC timestamp")
        assert isinstance(value, datetime)
        return value.isoformat()


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
        policy_id = require_domain_policy_id(artifact["candidate"])
        get_policy(policy_id)
        record_ids = self.snapshots.record_ids(snapshot_id)
        rows = [self.records.get(record_id) for record_id in record_ids]
        present = records_for_policy(
            [row for row in rows if row is not None],
            policy_id,
        )
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
                allowed_ids = frozenset(str(row["record_id"]) for row in present)
                hits = self.index.query(
                    snapshot_id,
                    [float(x) for x in query],
                    k=5,
                    allowed_record_ids=allowed_ids,
                )
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
        policy_id = require_domain_policy_id(candidate)
        policy = get_policy(policy_id)
        require_compatible_dval_rubric(candidate, policy)
        mech = score_mech(candidate, domain_pack=policy_id)
        fals = score_fals(candidate)
        dpred = score_dpred(candidate)
        dval = score_dval(candidate)
        via = viability(nov=nov, mech=mech, fals=fals, dpred=dpred, dval=dval)
        cell_id = policy.cell_id(candidate.get("research_descriptor") or {})
        policy_id = policy.policy_id
        decision = card_decision(via)
        card = {
            "card_id": candidate_artifact_hash,
            "domain_policy_id": policy_id,
            "cell_id": cell_id,
            "archive_cell_key": archive_cell_key(domain_policy_id=policy_id, cell_id=cell_id),
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
        normalized_card = _normalize_archive_card(card, allow_legacy_missing_policy=False)
        archive_key = str(normalized_card["archive_cell_key"])
        current = self.cards.elite_for_cell(archive_key)
        if int(normalized_card.get("viability") or 0) <= 0:
            return {"inserted": False, "reason": "viability_zero", "elite": current}
        chosen = choose_elite(cell_elite=current, candidate=normalized_card)
        assert chosen is not None
        self.cards.set_elite(archive_key, str(chosen["card_id"]))
        replaced = current is None or str(current.get("card_id")) != str(chosen["card_id"])
        return {
            "inserted": replaced and str(chosen["card_id"]) == str(normalized_card["card_id"]),
            "reason": None,
            "elite": chosen,
        }


@dataclass(frozen=True)
class RankArchiveUseCase:
    cell_statuses: dict[str, CellStatus]
    domain_policy_id: str

    def run(
        self,
        *,
        elite_cell_ids: set[str],
    ) -> dict[str, float | int | bool]:
        universe = get_policy(self.domain_policy_id).universe()
        return evaluate_rank_guard(
            elite_cell_ids=elite_cell_ids,
            cell_statuses=self.cell_statuses,
            universe=universe,
        )


def _reconcile_archive(
    cards: FrontierCardStore,
    card: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    normalized_card = _normalize_archive_card(card, allow_legacy_missing_policy=True)
    if normalized_card != card:
        cards.put_card(normalized_card)
    archived = ArchiveInsertUseCase(cards=cards).run(normalized_card)
    archive_key = str(normalized_card["archive_cell_key"])
    elite = cards.elite_for_cell(archive_key)
    if int(normalized_card.get("viability") or 0) <= 0 and elite is not None:
        if str(elite.get("card_id")) == str(normalized_card["card_id"]):
            cards.set_elite(archive_key, None)
            elite = None
    archived = {**archived, "elite": elite}
    return archived, elite, normalized_card


def _normalize_archive_card(
    card: dict[str, Any], *, allow_legacy_missing_policy: bool
) -> dict[str, Any]:
    normalized = dict(card)
    cell_id = normalized.get("cell_id")
    if not isinstance(cell_id, str) or not cell_id:
        raise ValueError("cell_id is required")

    domain_policy_id = normalized.get("domain_policy_id")
    if not isinstance(domain_policy_id, str) or not domain_policy_id.strip():
        if not allow_legacy_missing_policy:
            raise ValueError("domain_policy_id is required")
        supplied_archive_key = normalized.get("archive_cell_key")
        if supplied_archive_key is not None:
            raise ValueError("legacy card requires explicit domain_policy_id")
        if cell_id not in FINANCE_POLICY.universe():
            raise ValueError("legacy card requires explicit domain_policy_id")
        domain_policy_id = FINANCE_POLICY.policy_id
    else:
        domain_policy_id = domain_policy_id.strip()

    policy = get_policy(domain_policy_id)
    if cell_id not in policy.universe():
        raise ValueError("cell_id is outside the registered policy universe")

    derived_archive_key = archive_cell_key(domain_policy_id=policy.policy_id, cell_id=cell_id)
    supplied_archive_key = normalized.get("archive_cell_key")
    if supplied_archive_key is not None and supplied_archive_key != derived_archive_key:
        raise ValueError("archive_cell_key does not match the policy-scoped cell key")

    normalized["domain_policy_id"] = policy.policy_id
    normalized["archive_cell_key"] = derived_archive_key
    return normalized


@dataclass(frozen=True)
class RescoreUseCase:
    snapshots: CorpusSnapshotStore
    records: CorpusRecordStore
    index: CorpusIndex
    candidates: NsqdCandidateStore
    cards: FrontierCardStore

    def run(
        self,
        *,
        card_id: str,
        current_snapshot_id: str,
        current_corpus_version: int,
        snapshot_state: str,
        evaluator_run_id: str,
    ) -> dict[str, Any]:
        card = self.cards.get_card(card_id)
        if card is None:
            raise ValueError("unknown card_id")
        snapshot = self.snapshots.get(current_snapshot_id)
        if snapshot is None:
            raise ValueError("unknown current_snapshot_id")
        if int(snapshot["corpus_version"]) != current_corpus_version:
            raise ValueError("current_corpus_version does not match snapshot")
        if not needs_re_score(
            card_snapshot_id=str(card["snapshot_id"]),
            current_snapshot_id=current_snapshot_id,
        ):
            archived, elite, normalized_card = _reconcile_archive(self.cards, card)
            return {
                "needs_re_score": False,
                "card": normalized_card,
                "archive": archived,
                "elite": elite,
            }
        candidate_artifact_hash = str(card["candidate_artifact_hash"])
        GroundUseCase(
            snapshots=self.snapshots,
            records=self.records,
            index=self.index,
            candidates=self.candidates,
        ).run(
            candidate_artifact_hash=candidate_artifact_hash,
            snapshot_id=current_snapshot_id,
            corpus_version=current_corpus_version,
        )
        scored = ScoreUseCase(
            candidates=self.candidates,
            cards=self.cards,
            snapshots=self.snapshots,
            records=self.records,
        ).run(
            candidate_artifact_hash=candidate_artifact_hash,
            evaluator_run_id=evaluator_run_id,
            snapshot_id=current_snapshot_id,
            corpus_version=current_corpus_version,
            snapshot_state=snapshot_state,
        )
        new_card = scored["card"]
        archived, elite, normalized_card = _reconcile_archive(self.cards, new_card)
        return {
            "needs_re_score": True,
            "card": normalized_card,
            "archive": archived,
            "elite": elite,
        }

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from typing import Any

from nsqd.domain.acquisition import (
    CANDIDATES_PER_BATCH,
    QUERY_BATCH_LIMIT,
    RECHECK_CYCLE_LIMIT,
    STAGED_IMPORT_LIMIT,
    acquisition_cycle_id,
    acquisition_route,
    render_acquisition_query,
)
from nsqd.domain.card import (
    card_decision,
    corpus_ingest_rejection,
    missing_card_fields,
    needs_re_score,
)
from nsqd.domain.coverage import evaluate_rank_guard
from nsqd.domain.diverge import (
    DEFAULT_ENABLED_OPERATORS,
    normalize_axiom_rows,
    parent_card_id_for_target,
    require_elite_viability,
    require_no_axiom_inversion,
    require_operator,
    require_operator_b_target,
    select_target_cell,
)
from nsqd.domain.elite import choose_elite
from nsqd.domain.grounding import (
    LIVE_SEARCH_BUDGET,
    GroundingClass,
    apply_live_hits,
    classify_local,
    live_escalation_allowed,
)
from nsqd.domain.harvest import (
    OPTIONAL_RECORD_FIELDS,
    HarvestRejected,
    harvest_records_from_payload,
)
from nsqd.domain.novelty import (
    NOVELTY_K,
    NOVELTY_THRESHOLD_TAU,
    UNSET_TAU_SEMANTICS,
    SnapshotState,
    apply_novelty_threshold,
    mean_cosine_distance,
    novelty_term,
    require_snapshot_state,
)
from nsqd.domain.policy import (
    FINANCE_POLICY,
    DomainPolicy,
    archive_cell_key,
    get_policy,
    records_for_policy,
    require_compatible_dval_rubric,
    require_domain_policy_id,
    verdict_key,
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
from nsqd.domain.status import (
    CellStatus,
    record_lifecycle,
    require_cell_status,
    require_status_window_days,
    status_table,
    status_window,
)
from nsqd.domain.sufficiency import (
    SEARCHABLE_FAILURES,
    decide_snapshot_state,
    evaluate_sufficiency,
    sufficiency_search_context,
)
from nsqd.domain.viability import score_dpred, score_dval, score_fals, score_mech, viability
from nsqd.ports import (
    AcquisitionCycleStore,
    Clock,
    CorpusIndex,
    CorpusRecordStore,
    CorpusSnapshotStore,
    FrontierCardStore,
    HarvestStore,
    HybridPaperSearch,
    LivePaperSearch,
    MorphospaceStore,
    NsqdCandidateStore,
    PaperAcquisitionBridge,
    ParaphraseEmbedder,
    PolicyVerdictStore,
)


def empty_smoke_snapshot_id() -> str:
    return snapshot_id(records=[], schema_version=1)


MAX_REVIEWED_PROJECTION_BYTES = 65_536


def candidate_body(candidate: dict[str, Any]) -> dict[str, Any]:
    return deepcopy({key: value for key, value in candidate.items() if key != "expected_outcomes"})


def artifact_hash_for(candidate: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(candidate_body(candidate)))


def _grounding_queries(candidate: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    for key in ("paraphrase", "title", "source", "one_sentence_claim"):
        value = candidate.get(key)
        if not isinstance(value, str):
            continue
        text = " ".join(value.split())
        if text and text not in queries:
            queries.append(text)
    return queries


def _nonempty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _string_keyed_mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(key, str):
            normalized[key] = item
    return normalized


def _hybrid_prior_art(result: object) -> list[dict[str, Any]]:
    if not isinstance(result, list):
        return []
    hits: list[dict[str, Any]] = []
    for raw_item in result:
        item = _string_keyed_mapping(raw_item)
        if item is None:
            continue
        paper_id = _nonempty_string(item.get("paper_id"))
        score = item.get("score")
        if (
            paper_id is None
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not isfinite(float(score))
            or float(score) <= 0.0
        ):
            continue
        hits.append({"source": "hybrid", "paper_id": paper_id, "score": float(score)})
    return hits


def _live_prior_art(result: object) -> list[dict[str, Any]]:
    if not isinstance(result, list):
        return []
    hits: list[dict[str, Any]] = []
    for raw_item in result:
        item = _string_keyed_mapping(raw_item)
        if item is None:
            continue
        source_paper_id = _nonempty_string(item.get("source_paper_id"))
        title = _nonempty_string(item.get("title"))
        if source_paper_id is None or title is None:
            continue
        hits.append(
            {
                "source": "scholar",
                "source_paper_id": source_paper_id,
                "title": title,
            }
        )
    return hits


def _invoke_hybrid_search(client: HybridPaperSearch, query: str) -> list[dict[str, Any]]:
    return _hybrid_prior_art(client.search(query, LIVE_SEARCH_BUDGET))


def _invoke_live_search(client: LivePaperSearch, query: str) -> list[dict[str, Any]]:
    return _live_prior_art(client.search(query, {}, 1, 1, 0))


def _corpus_prior_art(
    record: dict[str, Any] | None,
    *,
    distance: float | None = None,
) -> dict[str, Any] | None:
    if record is None:
        return None
    record_id = _nonempty_string(record.get("record_id"))
    if record_id is None:
        return None
    prior_art: dict[str, Any] = {"source": "corpus", "record_id": record_id}
    record_type = _nonempty_string(record.get("type"))
    if record_type is not None:
        prior_art["record_type"] = record_type
    if distance is not None:
        prior_art["distance"] = distance
    return prior_art


def _require_snapshot_state(snapshot_state: str) -> SnapshotState:
    return require_snapshot_state(snapshot_state)


def _index_paraphrases(
    index: CorpusIndex | None,
    embedder: ParaphraseEmbedder | None,
    *,
    snapshot_id: str,
    records: list[dict[str, Any]],
) -> None:
    if index is None or embedder is None:
        return
    for record in records:
        record_id = record.get("record_id")
        paraphrase = record.get("paraphrase")
        if not isinstance(record_id, str) or not record_id.strip():
            continue
        if not isinstance(paraphrase, str) or not paraphrase.strip():
            continue
        index.upsert(snapshot_id, record_id, embedder.embed(paraphrase))


def _query_vector(
    candidate: dict[str, Any],
    embedder: ParaphraseEmbedder | None,
) -> list[float] | None:
    query = candidate.get("query_vector")
    if isinstance(query, list) and query:
        return [float(value) for value in query]
    if embedder is None:
        return None
    paraphrase = candidate.get("paraphrase")
    if not isinstance(paraphrase, str) or not paraphrase.strip():
        return None
    return embedder.embed(paraphrase)


def _measurement_stamp(
    embedder: ParaphraseEmbedder | None,
    *,
    vector: list[float] | None = None,
) -> dict[str, Any]:
    if embedder is not None:
        return {
            "embedding_model_id": embedder.model_id(),
            "embedding_model_version": embedder.model_version(),
            "embedding_dimension": embedder.dimension(),
            "normalization_policy": embedder.normalization_policy(),
            "distance_metric": "cosine_distance",
            "algorithm_contract_version": "1.1",
        }
    return {
        "embedding_model_id": "unconfigured",
        "embedding_model_version": "unconfigured",
        "embedding_dimension": 0 if vector is None else len(vector),
        "normalization_policy": "unknown",
        "distance_metric": "cosine_distance",
        "algorithm_contract_version": "1.1",
    }


def _persisted_measurement_stamp(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return _measurement_stamp(None)


@dataclass(frozen=True)
class HarvestUseCase:
    harvest: HarvestStore
    clock: Clock
    index: CorpusIndex | None = None
    embedder: ParaphraseEmbedder | None = None

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
        _index_paraphrases(
            self.index,
            self.embedder,
            snapshot_id=committed.snapshot_id,
            records=records,
        )
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
    index: CorpusIndex | None = None
    embedder: ParaphraseEmbedder | None = None

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
        raw_source = projection.get("source")
        if raw_source is None:
            source = f"paper:{normalized_source_paper_id}"
        elif not isinstance(raw_source, str) or not raw_source.strip():
            raise ValueError("projection.source must be a non-empty string")
        else:
            source = normalize_source(raw_source)
        raw_coordinates = projection.get("coordinates")
        coordinates: dict[str, str] | None = None
        if raw_coordinates is not None:
            if not isinstance(raw_coordinates, dict):
                raise ValueError("projection.coordinates must be a mapping")
            axis_names = {name for name, _values in policy.axes}
            if set(raw_coordinates) != axis_names:
                raise ValueError("projection.coordinates must match policy axes")
            coordinates = {}
            for axis_name, _values in policy.axes:
                axis_value = raw_coordinates.get(axis_name)
                if not isinstance(axis_value, str) or not axis_value.strip():
                    raise ValueError("projection.coordinates values must be non-empty strings")
                coordinates[axis_name] = normalize_paraphrase(axis_value)
            policy.cell_id(coordinates)
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
        reviewed_projection = {
            **projection,
            "domain_policy_id": normalized_projection_policy_id,
            "human_approved_at": normalized_human_approved_at,
            "human_reviewer": normalized_human_reviewer,
            "paraphrase": normalized_paraphrase,
            "paraphrase_source": normalized_paraphrase_source,
            "source_paper_id": normalized_source_paper_id,
        }
        if raw_source is not None:
            reviewed_projection["source"] = source
        if coordinates is not None:
            reviewed_projection["coordinates"] = coordinates
        canonical_projection = canonical_reviewed_projection_bytes(reviewed_projection)
        if len(canonical_projection) > MAX_REVIEWED_PROJECTION_BYTES:
            raise ValueError("reviewed projection payload is too large")
        reviewed_projection_digest = canonical_reviewed_projection_digest(reviewed_projection)
        if reviewed_projection_digest not in self.approved_projection_digests:
            raise ValueError("projection is not an approved reviewed projection")
        identity = {
            "source_paper_id": normalized_source_paper_id,
            "domain_policy_id": policy.policy_id,
            "source_abstract_sha256": source_abstract_sha256,
            "source_markdown_sha256": source_markdown_sha256,
            "paraphrase_sha256": paraphrase_sha256,
        }
        content_hash = record_content_hash(
            type="paper",
            paraphrase=normalized_paraphrase,
            source=source,
        )
        record_id = projection_record_id(identity)
        existing = self.records.get(record_id)
        if existing is not None and projection_identity(existing) == projection_identity(identity):
            existing_digest = existing.get("reviewed_projection_digest")
            if existing_digest is None:
                raise ValueError(
                    "existing projection is missing reviewed_projection_digest; "
                    "an explicit immutable migration is required"
                )
            if existing_digest != reviewed_projection_digest:
                raise ValueError("existing projection has different reviewed projection metadata")
            committed = self.harvest.commit([existing], schema_version=1)
            _index_paraphrases(
                self.index,
                self.embedder,
                snapshot_id=committed.snapshot_id,
                records=[existing],
            )
            return {
                "created": False,
                "record_id": str(existing["record_id"]),
                "snapshot_id": committed.snapshot_id,
                "corpus_version": committed.corpus_version,
                "reviewed_projection_digest": reviewed_projection_digest,
            }
        record: dict[str, Any] = {
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
            "reviewed_projection_digest": reviewed_projection_digest,
        }
        if coordinates is not None:
            record["coordinates"] = coordinates
        committed = self.harvest.commit([record], schema_version=1)
        _index_paraphrases(
            self.index,
            self.embedder,
            snapshot_id=committed.snapshot_id,
            records=[record],
        )
        return {
            "created": True,
            "record_id": record_id,
            "snapshot_id": committed.snapshot_id,
            "corpus_version": committed.corpus_version,
            "reviewed_projection_digest": reviewed_projection_digest,
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
    cards: FrontierCardStore
    clock: Clock
    enabled_operators: frozenset[str] = DEFAULT_ENABLED_OPERATORS

    def run(
        self,
        *,
        candidate: dict[str, Any],
        generator_run_id: str,
        axiom: str | None = None,
        axioms: list[Any] | None = None,
        operator: str = "A",
        parent_card_id: str | None = None,
        target_cell_id: str | None = None,
        cell_statuses: dict[str, CellStatus] | None = None,
    ) -> str:
        validated_operator = require_operator(
            operator,
            enabled_operators=self.enabled_operators,
        )
        source = axioms if axioms is not None else ([axiom] if axiom is not None else [])
        rows = normalize_axiom_rows(source)
        body = candidate_body(candidate)
        policy_id = require_domain_policy_id(body)
        policy = get_policy(policy_id)
        resolved_target = self._resolve_target(
            policy_id=policy.policy_id,
            universe=policy.universe(),
            target_cell_id=target_cell_id,
            cell_statuses=cell_statuses,
        )
        self._require_axiom_cells(rows=rows, universe=policy.universe(), target=resolved_target)
        if validated_operator == "B":
            self._require_operator_b_occupancy(
                candidate=body,
                source_axioms=source,
                rows=rows,
                policy=policy,
                target=resolved_target,
                cell_statuses=cell_statuses,
            )
        actual_elite = self._elite_for_target(
            policy_id=policy.policy_id, target_cell_id=resolved_target
        )
        actual_elite_card_id = None if actual_elite is None else str(actual_elite["card_id"])
        parent = parent_card_id_for_target(
            elite_card_id=actual_elite_card_id,
            parent_card_id=parent_card_id,
        )
        digest = artifact_hash_for(candidate)
        payload = {
            "candidate": body,
            "axiom": rows[0]["statement"],
            "axioms": rows,
            "operator": validated_operator,
            "parent_card_id": parent,
            "target_cell_id": resolved_target,
            "generator_run_id": generator_run_id,
            "generated_at": self.clock.now().isoformat(),
        }
        if self.candidates.put_artifact_if_absent(digest, payload):
            return digest
        existing = self.candidates.get_artifact(digest)
        if existing is None:
            raise RuntimeError("candidate artifact conflict could not be loaded")
        if self._generation_semantics(existing) != self._generation_semantics(payload):
            raise ValueError("immutable artifact conflict")
        return digest

    def _require_operator_b_occupancy(
        self,
        *,
        candidate: dict[str, Any],
        source_axioms: list[Any],
        rows: list[dict[str, str]],
        policy: DomainPolicy,
        target: str | None,
        cell_statuses: dict[str, CellStatus] | None,
    ) -> None:
        if target is None or cell_statuses is None:
            raise ValueError("Operator B requires an ALG-SEL target and status table")
        require_operator_b_target(
            target,
            cell_statuses,
            elite_viability=self._elite_viability_for_cells(
                policy_id=policy.policy_id,
                cell_ids=cell_statuses,
            ),
        )
        require_no_axiom_inversion(candidate=candidate, axioms=source_axioms)
        descriptor = candidate.get("research_descriptor")
        if not isinstance(descriptor, dict) or policy.cell_id(descriptor) != target:
            raise ValueError("research_descriptor must resolve to the Operator B target")
        if not any(row.get("cell_id") == target for row in rows):
            raise ValueError("Operator B requires a target-bound axiom")

    @staticmethod
    def _require_axiom_cells(
        *,
        rows: list[dict[str, str]],
        universe: frozenset[str],
        target: str | None,
    ) -> None:
        for row in rows:
            cell_id = row.get("cell_id")
            if cell_id is None:
                continue
            if cell_id not in universe:
                raise ValueError("axiom cell is outside the registered policy universe")
            if target is None or cell_id != target:
                raise ValueError("axiom cell_id must match the ALG-SEL target")

    def _resolve_target(
        self,
        *,
        policy_id: str,
        universe: frozenset[str],
        target_cell_id: str | None,
        cell_statuses: dict[str, CellStatus] | None,
    ) -> str | None:
        validated_target = None
        if target_cell_id is not None:
            validated_target = target_cell_id.strip()
            if validated_target not in universe:
                raise ValueError("target cell is outside the registered policy universe")
        if cell_statuses is None:
            if validated_target is not None:
                raise ValueError("cell_statuses are required when target_cell_id is provided")
            return validated_target
        if not cell_statuses:
            raise ValueError("cell_statuses must not be empty")
        for cell_id, status in cell_statuses.items():
            if cell_id not in universe:
                raise ValueError("target cell is outside the registered policy universe")
            require_cell_status(status)
        if set(cell_statuses) != universe:
            raise ValueError("cell_statuses must match the selected policy universe")
        selected = select_target_cell(
            cell_statuses,
            elite_viability=self._elite_viability_for_cells(
                policy_id=policy_id, cell_ids=cell_statuses
            ),
        )
        if validated_target is not None and validated_target != selected:
            raise ValueError("target_cell_id disagrees with ALG-SEL")
        return selected

    def _elite_viability_for_cells(
        self,
        *,
        policy_id: str,
        cell_ids: Mapping[str, CellStatus],
    ) -> dict[str, int]:
        viability: dict[str, int] = {}
        for cell_id in cell_ids:
            elite = self._elite_for_target(policy_id=policy_id, target_cell_id=cell_id)
            if elite is None:
                continue
            viability[cell_id] = require_elite_viability(elite.get("viability"))
        return viability

    def _elite_for_target(
        self,
        *,
        policy_id: str,
        target_cell_id: str | None,
    ) -> dict[str, Any] | None:
        if target_cell_id is None:
            return None
        return self.cards.elite_for_cell(
            archive_cell_key(domain_policy_id=policy_id, cell_id=target_cell_id)
        )

    @staticmethod
    def _generation_semantics(artifact: dict[str, Any]) -> dict[str, Any]:
        axiom = artifact.get("axiom")
        axioms = artifact.get("axioms")
        if axioms is None and isinstance(axiom, str):
            axioms = [{"statement": axiom}]
        return {
            "candidate": artifact.get("candidate"),
            "axiom": axiom,
            "axioms": axioms,
            "operator": artifact.get("operator", "A"),
            "parent_card_id": artifact.get("parent_card_id"),
            "target_cell_id": artifact.get("target_cell_id"),
            "generator_run_id": artifact.get("generator_run_id"),
        }


@dataclass(frozen=True)
class GroundUseCase:
    snapshots: CorpusSnapshotStore
    records: CorpusRecordStore
    index: CorpusIndex
    candidates: NsqdCandidateStore
    live_search: LivePaperSearch | None = None
    hybrid_search: HybridPaperSearch | None = None
    embedder: ParaphraseEmbedder | None = None

    def run(
        self,
        *,
        candidate_artifact_hash: str,
        snapshot_id: str,
        corpus_version: int,
        snapshot_state: str = "smoke_only",
    ) -> dict[str, Any]:
        artifact = self._require_artifact(candidate_artifact_hash)
        snapshot = self._require_snapshot(snapshot_id)
        if int(snapshot["corpus_version"]) != corpus_version:
            raise ValueError("corpus_version does not match snapshot")
        validated_state = _require_snapshot_state(snapshot_state)
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
        exact_row = next(
            (
                row
                for row in present
                if normalize_source(str(row.get("source") or "")) == normalized_source
                and normalized_source != ""
            ),
            None,
        )
        terminology_row = next(
            (row for row in present if "terminology" in set(row.get("tags") or [])),
            None,
        )
        query = _query_vector(artifact["candidate"], self.embedder)
        measurement_stamp = _measurement_stamp(self.embedder, vector=query)
        evidence = mean_cosine_distance([])
        nearest_hit = None
        if present:
            if query is not None:
                allowed_ids = frozenset(str(row["record_id"]) for row in present)
                hits = self.index.query(
                    snapshot_id,
                    query,
                    k=NOVELTY_K,
                    allowed_record_ids=allowed_ids,
                )
                evidence = mean_cosine_distance([hit.distance for hit in hits])
                nearest_hit = hits[0] if hits else None
        code_or_benchmark_row = next(
            (row for row in present if row.get("type") in {"code", "benchmark"}),
            None,
        )
        klass, confidence, layers = classify_local(
            exact_source_hit=exact_row is not None,
            terminology_hit=terminology_row is not None,
            evidence=evidence,
            code_or_benchmark_hit=code_or_benchmark_row is not None,
        )
        local_prior_art = _corpus_prior_art(exact_row)
        if local_prior_art is None:
            local_prior_art = _corpus_prior_art(terminology_row)
        if local_prior_art is None and nearest_hit is not None:
            nearest_record = next(
                (row for row in present if row.get("record_id") == nearest_hit.record_id),
                None,
            )
            local_prior_art = _corpus_prior_art(
                nearest_record,
                distance=nearest_hit.distance,
            )
        if local_prior_art is None:
            local_prior_art = _corpus_prior_art(code_or_benchmark_row)
        live_hits, live_calls = self._escalate_live(
            candidate=artifact["candidate"],
            snapshot_state=validated_state,
            local_class=klass,
        )
        klass, confidence = apply_live_hits(
            local_class=klass,
            local_confidence=confidence,
            live_hits=live_hits,
        )
        result = {
            "grounding_class": klass,
            "confidence": confidence,
            "layers": [asdict(layer) for layer in layers],
            "evidence": evidence,
            "snapshot_id": snapshot_id,
            "corpus_version": corpus_version,
            "live_call_count": len(live_calls),
            "live_calls": live_calls,
            "measurement_stamp": measurement_stamp,
            "closest_prior_art": live_hits[0] if live_hits else local_prior_art,
        }
        updated = dict(artifact)
        updated["grounding"] = result
        self.candidates.put_artifact(candidate_artifact_hash, updated)
        return result

    def _escalate_live(
        self,
        *,
        candidate: dict[str, Any],
        snapshot_state: str,
        local_class: GroundingClass,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not live_escalation_allowed(
            snapshot_state=snapshot_state,
            local_class=local_class,
        ):
            return [], []
        backends: list[str] = []
        if self.hybrid_search is not None:
            backends.append("hybrid")
        if self.live_search is not None:
            backends.append("live")
        live_calls: list[dict[str, Any]] = []
        for query in _grounding_queries(candidate):
            for source in backends:
                if len(live_calls) >= LIVE_SEARCH_BUDGET:
                    return [], live_calls
                if source == "hybrid":
                    assert self.hybrid_search is not None
                    hits = _invoke_hybrid_search(self.hybrid_search, query)
                else:
                    assert self.live_search is not None
                    hits = _invoke_live_search(self.live_search, query)
                live_calls.append(
                    {
                        "source": source,
                        "query_sha256": sha256_hex(query.encode("utf-8")),
                        "hit": bool(hits),
                    }
                )
                if hits:
                    return hits, live_calls
        return [], live_calls

    def _require_artifact(self, candidate_artifact_hash: str) -> dict[str, Any]:
        artifact = self.candidates.get_artifact(candidate_artifact_hash)
        if artifact is None:
            raise ValueError("unknown candidate_artifact_hash")
        return artifact

    def _require_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError("unknown snapshot_id")
        return snapshot


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
        reported_evidence = evidence if isinstance(evidence, float) or evidence is None else None
        nov = apply_novelty_threshold(
            novelty_term(
                evidence=reported_evidence,
                snapshot_state=validated_snapshot_state,
                grounding_class=grounding["grounding_class"],
            ),
            evidence=reported_evidence,
            tau=NOVELTY_THRESHOLD_TAU,
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
            "tau": NOVELTY_THRESHOLD_TAU,
            "tau_semantics": UNSET_TAU_SEMANTICS,
            "snapshot_id": snapshot_id,
            "snapshot_state": validated_snapshot_state,
            "corpus_version": corpus_version,
            "measurement_stamp": _persisted_measurement_stamp(grounding.get("measurement_stamp")),
        }
        self.candidates.put_artifact(candidate_artifact_hash, evaluated)
        self.cards.put_card(card)
        return {
            "evidence": evidence,
            "nov": nov,
            "tau": NOVELTY_THRESHOLD_TAU,
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


@dataclass(frozen=True)
class MapSnapshotUseCase:
    snapshots: CorpusSnapshotStore
    records: CorpusRecordStore
    morph: MorphospaceStore
    clock: Clock

    def run(
        self,
        *,
        snapshot_id: str,
        domain_policy_id: str,
        snapshot_state: str,
        expected_cell_ids: frozenset[str] | None = None,
        window_days: int | None = None,
    ) -> dict[str, Any]:
        if not isinstance(domain_policy_id, str) or not domain_policy_id.strip():
            raise ValueError("domain_policy_id is required")
        policy = get_policy(domain_policy_id.strip())
        _require_snapshot_state(snapshot_state)
        if self.snapshots.get(snapshot_id) is None:
            raise ValueError("unknown snapshot_id")
        rows: list[dict[str, Any]] = []
        for record_id in self.snapshots.record_ids(snapshot_id):
            row = self.records.get(record_id)
            if row is not None:
                rows.append(row)
        inspected = frozenset(
            cell_id
            for cell_id in policy.universe()
            if self.morph.get_cell(
                archive_cell_key(domain_policy_id=policy.policy_id, cell_id=cell_id)
            )
            is not None
        )
        expected = policy.expected_cells if expected_cell_ids is None else expected_cell_ids
        resolved_window_days = require_status_window_days(window_days)
        return {
            "snapshot_id": snapshot_id,
            "domain_policy_id": policy.policy_id,
            "window_days": resolved_window_days,
            "cell_statuses": status_table(
                rows,
                domain_policy_id=policy.policy_id,
                as_of=self.clock.now(),
                snapshot_state=snapshot_state,
                inspected_cell_ids=inspected,
                expected_cell_ids=expected,
                window=status_window(resolved_window_days),
            ),
        }


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
    live_search: LivePaperSearch | None = None
    hybrid_search: HybridPaperSearch | None = None
    embedder: ParaphraseEmbedder | None = None

    def run(
        self,
        *,
        card_id: str,
        current_snapshot_id: str,
        current_corpus_version: int,
        snapshot_state: str,
        evaluator_run_id: str,
    ) -> dict[str, Any]:
        validated_state = _require_snapshot_state(snapshot_state)
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
            live_search=self.live_search,
            hybrid_search=self.hybrid_search,
            embedder=self.embedder,
        ).run(
            candidate_artifact_hash=candidate_artifact_hash,
            snapshot_id=current_snapshot_id,
            corpus_version=current_corpus_version,
            snapshot_state=validated_state,
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
            snapshot_state=validated_state,
        )
        new_card = scored["card"]
        archived, elite, normalized_card = _reconcile_archive(self.cards, new_card)
        return {
            "needs_re_score": True,
            "card": normalized_card,
            "archive": archived,
            "elite": elite,
        }


@dataclass(frozen=True)
class PromoteSnapshotUseCase:
    snapshots: CorpusSnapshotStore
    records: CorpusRecordStore
    verdicts: PolicyVerdictStore
    clock: Clock
    policies: Mapping[str, DomainPolicy] | None = None
    approved_harvest_seed_digests: frozenset[str] = frozenset()

    def run(
        self,
        *,
        snapshot_id: str,
        domain_policy_id: str,
        target: str,
    ) -> dict[str, Any]:
        if self.snapshots.get(snapshot_id) is None:
            raise ValueError("unknown snapshot_id")
        resolved_policy = _resolve_evaluation_policy(
            domain_policy_id,
            self.policies.get(domain_policy_id.strip()) if self.policies is not None else None,
        )
        rows: list[dict[str, Any]] = []
        for record_id in self.snapshots.record_ids(snapshot_id):
            row = self.records.get(record_id)
            if row is not None:
                rows.append(row)
        as_of = self.clock.now()
        approved_manifest = self.policies is not None and resolved_policy.policy_id in self.policies
        if target == "calibration":
            approved_manifest = approved_manifest and bool(resolved_policy.recall_probes)
        if target == "production_valid" and resolved_policy.policy_id == "finance/1":
            approved_manifest = (
                approved_manifest
                and bool(resolved_policy.recall_probes)
                and bool(resolved_policy.expected_cells)
                and resolved_policy.min_records > 0
            )
        failures = evaluate_sufficiency(
            rows,
            policy=resolved_policy,
            as_of=as_of,
            disagreement=any(row.get("disagreement_unresolved") is True for row in rows),
            approved_manifest=approved_manifest,
        )
        search_context = sufficiency_search_context(
            rows,
            policy=resolved_policy,
            as_of=as_of,
        )
        state = decide_snapshot_state(
            failures,
            target=target,
            domain_policy_id=resolved_policy.policy_id,
            harvest_seed_approved=_has_approved_harvest_seed(
                rows,
                domain_policy_id=resolved_policy.policy_id,
                as_of=as_of,
                approved_digests=self.approved_harvest_seed_digests,
            ),
            recall_probe_listed=bool(resolved_policy.recall_probes),
        )
        verdict = {
            "snapshot_id": snapshot_id,
            "domain_policy_id": resolved_policy.policy_id,
            "state": state,
            "failures": list(failures),
            "target": target,
            "search_context": search_context,
        }
        self.verdicts.put_verdict(
            snapshot_id=snapshot_id,
            domain_policy_id=resolved_policy.policy_id,
            verdict=verdict,
        )
        return {
            "key": verdict_key(snapshot_id=snapshot_id, domain_policy_id=resolved_policy.policy_id),
            "state": state,
            "failures": failures,
            "verdict": verdict,
            "search_context": search_context,
        }


@dataclass(frozen=True)
class AcquireCorpusUseCase:
    cycles: AcquisitionCycleStore
    promote: PromoteSnapshotUseCase
    bridge: PaperAcquisitionBridge
    project: ProjectPaperUseCase

    def run(
        self,
        *,
        snapshot_id: str,
        domain_policy_id: str,
        target: str,
        human_decision: str | None = None,
        approved_projections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if human_decision not in {None, "decline", "approve"}:
            raise ValueError("human_decision must be decline or approve when provided")
        resolved_policy = _resolve_evaluation_policy(
            domain_policy_id,
            (
                self.promote.policies.get(domain_policy_id.strip())
                if self.promote.policies is not None
                else None
            ),
        )
        promoted = self.promote.run(
            snapshot_id=snapshot_id,
            domain_policy_id=resolved_policy.policy_id,
            target=target,
        )
        route = acquisition_route(promoted["failures"])
        if route != "search":
            return {
                "route": route,
                "stopped": (
                    "manual"
                    if route == "manual"
                    else ("sufficient" if promoted["state"] != "insufficient" else "policy_blocked")
                ),
                "projected": False,
                "state": promoted["state"],
                "cycle_id": None,
                "failures": promoted["failures"],
            }
        query, filters, failure_context = self._query_plan(resolved_policy.policy_id, promoted)
        cycle_id = acquisition_cycle_id(
            snapshot_id=snapshot_id,
            domain_policy_id=resolved_policy.policy_id,
            failure_signature=promoted["failures"],
            rendered_query=query,
            filters=filters,
        )
        existing = self.cycles.get(cycle_id)
        if existing is not None:
            if human_decision == "decline":
                existing = {**existing, "stopped": "human_decline"}
                return self._persist_cycle(existing)
            if existing.get("stopped") == "in_progress":
                return self._stage_candidates(
                    existing,
                    query=query,
                    filters=filters,
                    failure_context=(
                        _string_keyed_mapping(existing.get("failure_context")) or failure_context
                    ),
                    resume=True,
                )
            if human_decision == "approve":
                return self._approve_and_recheck(
                    existing,
                    domain_policy_id=resolved_policy.policy_id,
                    target=target,
                    approved_projections=approved_projections or [],
                )
            return existing
        result: dict[str, Any] = {
            "route": "search",
            "stopped": "in_progress",
            "projected": False,
            "state": promoted["state"],
            "cycle_id": cycle_id,
            "snapshot_id": snapshot_id,
            "failures": promoted["failures"],
            "rendered_query": query,
            "search_filters": dict(filters),
            "failure_context": failure_context,
            "staged": [],
            "staged_identities": [],
            "staged_entries": [],
            "drafts": [],
            "batches": 0,
            "rechecks": 0,
            "alias_cycle_ids": [],
        }
        if human_decision == "decline":
            result["stopped"] = "human_decline"
            return self._persist_cycle(result)
        if human_decision == "approve":
            raise ValueError("no pending acquisition cycle to approve")
        self._persist_cycle(result)
        return self._stage_candidates(
            result,
            query=query,
            filters=filters,
            failure_context=failure_context,
            resume=False,
        )

    def _query_plan(
        self, policy_id: str, promoted: dict[str, Any]
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        searchable = [code for code in promoted["failures"] if code in SEARCHABLE_FAILURES]
        failure = searchable[0]
        search_context = promoted["search_context"]
        missing_cells = search_context["missing_cell_ids"]
        missing_probes = search_context["missing_recall_probes"]
        unmet_record_types = search_context["unmet_record_types"]
        cell_id = missing_cells[0] if failure == "expected_cell_empty" and missing_cells else None
        probe = missing_probes[0] if failure == "recall_probe_missing" and missing_probes else None
        probe_id = str(probe["probe_id"]) if probe is not None else None
        if probe is not None:
            record_type = str(probe["record_type"])
        elif failure == "domain_minima_unmet" and unmet_record_types:
            record_type = str(unmet_record_types[0])
        else:
            record_type = "paper"
        query = render_acquisition_query(
            policy_id=policy_id,
            failure=failure,
            cell_id=cell_id,
            probe_id=probe_id,
            record_type=record_type,
        )
        return (
            query,
            {"type": record_type},
            {
                "failures": list(promoted["failures"]),
                "search_context": deepcopy(search_context),
            },
        )

    def _persist_cycle(self, result: dict[str, Any]) -> dict[str, Any]:
        self._sync_staged_state(result)
        self.cycles.put_cycle(str(result["cycle_id"]), result)
        aliases = result.get("alias_cycle_ids")
        if isinstance(aliases, list):
            for alias in aliases:
                alias_id = str(alias)
                if alias_id and alias_id != str(result["cycle_id"]):
                    self.cycles.put_cycle(alias_id, result)
        return result

    def _stage_candidates(
        self,
        result: dict[str, Any],
        *,
        query: str,
        filters: dict[str, str],
        failure_context: dict[str, Any],
        resume: bool,
        skip_identities: set[str] | None = None,
    ) -> dict[str, Any]:
        staged_entries = self._staged_entries(result)
        self._sync_staged_state(result, staged_entries)
        staged = [str(item["paper_id"]) for item in staged_entries]
        staged_identities = [
            str(item["identity"])
            for item in staged_entries
            if isinstance(item.get("identity"), str) and item["identity"].strip()
        ]
        pass_limit = len(staged) + STAGED_IMPORT_LIMIT
        seen_candidates = set(staged_identities)
        seen_candidates.update(f"paper_id:{paper_id}" for paper_id in staged)
        if skip_identities:
            seen_candidates.update(skip_identities)
        result["stopped"] = "in_progress"
        self._persist_cycle(result)
        try:
            self._complete_pending_staged_entries(result, staged_entries)
            for _batch in range(QUERY_BATCH_LIMIT):
                if len(staged) >= pass_limit:
                    break
                discovered = self.bridge.discover(query, filters)[:CANDIDATES_PER_BATCH]
                result["batches"] = int(result.get("batches") or 0) + 1
                self._persist_cycle(result)
                fresh: list[dict[str, Any]] = []
                for candidate in discovered:
                    identity = _acquisition_candidate_identity(candidate)
                    if identity is None or identity in seen_candidates:
                        continue
                    seen_candidates.add(identity)
                    fresh.append(candidate)
                if not fresh:
                    break
                shortlisted = self.bridge.shortlist(
                    fresh,
                    limit=min(CANDIDATES_PER_BATCH, pass_limit - len(staged)),
                    insufficiency_query=query,
                    filters=filters,
                    failure_context=failure_context,
                )
                if any(item.get("review_status") == "approved" for item in shortlisted):
                    raise ValueError("LLM output cannot approve corpus evidence")
                fresh_by_identity = {
                    identity: candidate
                    for candidate in fresh
                    if (identity := _acquisition_candidate_identity(candidate)) is not None
                }
                shortlisted_identities: set[str] = set()
                for candidate in shortlisted:
                    if len(staged) >= pass_limit:
                        break
                    identity = _acquisition_candidate_identity(candidate)
                    if identity is None or identity not in fresh_by_identity:
                        raise ValueError("shortlist candidate was not discovered")
                    if identity in shortlisted_identities:
                        continue
                    shortlisted_identities.add(identity)
                    paper_id = self.bridge.stage_import(fresh_by_identity[identity])
                    if not isinstance(paper_id, str) or not paper_id.strip():
                        raise ValueError("stage_import returned an invalid paper_id")
                    paper_id = paper_id.strip()
                    staged_entry = self._build_staged_entry(
                        fresh_by_identity[identity],
                        identity=identity,
                        paper_id=paper_id,
                    )
                    staged_entries.append(staged_entry)
                    self._sync_staged_state(result, staged_entries)
                    self._persist_cycle(result)
                    self._complete_staged_entry(result, staged_entries, staged_entry)
                    staged = [str(item["paper_id"]) for item in staged_entries]
                    staged_identities = [
                        str(item["identity"])
                        for item in staged_entries
                        if isinstance(item.get("identity"), str) and item["identity"].strip()
                    ]
                if len(discovered) < CANDIDATES_PER_BATCH:
                    break
        except Exception:
            result["stopped"] = "manual_recovery"
            self._persist_cycle(result)
            raise
        result["stopped"] = "pending_human_approval" if staged else "no_new_candidates"
        if resume:
            result["stopped"] = "pending_human_approval" if staged else result["stopped"]
        self._persist_cycle(result)
        return result

    def _approve_and_recheck(
        self,
        cycle: dict[str, Any],
        *,
        domain_policy_id: str,
        target: str,
        approved_projections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if cycle.get("stopped") not in {
            "pending_human_approval",
            "no_new_candidates",
            "no_approved_snapshot_delta",
        }:
            return cycle
        staged_identities = {str(item) for item in cycle.get("staged_identities") or []}
        if not approved_projections:
            raise ValueError("approved projections are required")
        snapshot_before = str(cycle.get("snapshot_id") or "")
        failures_before = list(cycle.get("failures") or [])
        projected_snapshot = snapshot_before
        for projection in approved_projections:
            source_paper_id = projection.get("source_paper_id")
            if (
                not isinstance(source_paper_id, str)
                or f"source_paper_id:{source_paper_id.strip()}" not in staged_identities
            ):
                raise ValueError("approved projection is not the staged source paper")
            projected = self.project.run(
                domain_policy_id=domain_policy_id,
                projection=projection,
            )
            projected_snapshot = str(projected["snapshot_id"])
        promoted = self.promote.run(
            snapshot_id=projected_snapshot,
            domain_policy_id=domain_policy_id,
            target=target,
        )
        if projected_snapshot == snapshot_before and list(promoted["failures"]) == failures_before:
            updated = {
                **cycle,
                "projected": True,
                "snapshot_id": projected_snapshot,
                "state": promoted["state"],
                "failures": promoted["failures"],
                "stopped": "no_approved_snapshot_delta",
            }
            return self._persist_cycle(updated)
        rechecks = int(cycle.get("rechecks") or 0) + 1
        updated = {
            **cycle,
            "projected": True,
            "snapshot_id": projected_snapshot,
            "state": promoted["state"],
            "failures": promoted["failures"],
            "rechecks": rechecks,
        }
        if promoted["state"] != "insufficient":
            updated["stopped"] = "sufficient"
            return self._persist_cycle(updated)
        if rechecks >= RECHECK_CYCLE_LIMIT:
            updated["stopped"] = "recheck_budget"
            return self._persist_cycle(updated)
        if acquisition_route(promoted["failures"]) != "search":
            updated["stopped"] = "policy_blocked"
            return self._persist_cycle(updated)
        query, filters, failure_context = self._query_plan(domain_policy_id, promoted)
        alias_id = acquisition_cycle_id(
            snapshot_id=projected_snapshot,
            domain_policy_id=domain_policy_id,
            failure_signature=promoted["failures"],
            rendered_query=query,
            filters=filters,
        )
        existing_aliases = updated.get("alias_cycle_ids")
        aliases = (
            [str(item) for item in existing_aliases] if isinstance(existing_aliases, list) else []
        )
        if alias_id not in aliases:
            aliases.append(alias_id)
        updated["alias_cycle_ids"] = aliases
        updated["rendered_query"] = query
        updated["search_filters"] = dict(filters)
        updated["failure_context"] = failure_context
        return self._stage_candidates(
            updated,
            query=query,
            filters=filters,
            failure_context=failure_context,
            resume=False,
            skip_identities=staged_identities,
        )

    def _complete_pending_staged_entries(
        self, result: dict[str, Any], staged_entries: list[dict[str, Any]]
    ) -> None:
        for staged_entry in staged_entries:
            if isinstance(staged_entry.get("draft"), dict):
                continue
            self._complete_staged_entry(result, staged_entries, staged_entry)

    def _complete_staged_entry(
        self,
        result: dict[str, Any],
        staged_entries: list[dict[str, Any]],
        staged_entry: dict[str, Any],
    ) -> None:
        paper_id = str(staged_entry["paper_id"])
        if not staged_entry.get("analysis_enqueued"):
            self.bridge.enqueue_analyze(paper_id)
            staged_entry["analysis_enqueued"] = True
            self._sync_staged_state(result, staged_entries)
            self._persist_cycle(result)
        draft = self.bridge.draft_projection(paper_id)
        if draft.get("review_status") == "approved":
            raise ValueError("LLM output cannot approve corpus evidence")
        staged_entry["draft"] = self._review_draft(staged_entry, draft)
        self._sync_staged_state(result, staged_entries)
        self._persist_cycle(result)

    @staticmethod
    def _build_staged_entry(
        candidate: dict[str, Any], *, identity: str, paper_id: str
    ) -> dict[str, Any]:
        staged_entry: dict[str, Any] = {
            "paper_id": paper_id,
            "identity": identity,
            "analysis_enqueued": False,
        }
        candidate_id = candidate.get("candidate_id")
        if isinstance(candidate_id, str) and candidate_id.strip():
            staged_entry["candidate_id"] = candidate_id.strip()
        source_paper_id = candidate.get("source_paper_id")
        if isinstance(source_paper_id, str) and source_paper_id.strip():
            staged_entry["source_paper_id"] = source_paper_id.strip()
        title = candidate.get("title")
        if isinstance(title, str) and title.strip():
            staged_entry["title"] = title.strip()
        return staged_entry

    @staticmethod
    def _review_draft(staged_entry: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
        reviewed = dict(draft)
        reviewed.setdefault("paper_id", str(staged_entry["paper_id"]))
        source_paper_id = staged_entry.get("source_paper_id")
        if isinstance(source_paper_id, str) and source_paper_id.strip():
            reviewed.setdefault("source_paper_id", source_paper_id)
        title = staged_entry.get("title")
        if isinstance(title, str) and title.strip():
            reviewed.setdefault("title", title)
        return reviewed

    @staticmethod
    def _staged_entries(result: dict[str, Any]) -> list[dict[str, Any]]:
        raw_entries = result.get("staged_entries")
        if isinstance(raw_entries, list):
            return [dict(item) for item in raw_entries if isinstance(item, dict)]
        staged = [str(item) for item in result.get("staged") or []]
        staged_identities = [str(item) for item in result.get("staged_identities") or []]
        entries: list[dict[str, Any]] = []
        for index, paper_id in enumerate(staged):
            entry: dict[str, Any] = {"paper_id": paper_id, "analysis_enqueued": False}
            if index < len(staged_identities) and staged_identities[index].strip():
                entry["identity"] = staged_identities[index].strip()
            entries.append(entry)
        return entries

    @staticmethod
    def _sync_staged_state(
        result: dict[str, Any], staged_entries: list[dict[str, Any]] | None = None
    ) -> None:
        entries = (
            staged_entries
            if staged_entries is not None
            else AcquireCorpusUseCase._staged_entries(result)
        )
        normalized_entries: list[dict[str, Any]] = []
        staged: list[str] = []
        staged_identities: list[str] = []
        drafts: list[dict[str, Any]] = []
        for raw_entry in entries:
            paper_id = _nonempty_string(raw_entry.get("paper_id"))
            if paper_id is None:
                continue
            entry: dict[str, Any] = {
                "paper_id": paper_id,
                "analysis_enqueued": bool(raw_entry.get("analysis_enqueued")),
            }
            identity = _nonempty_string(raw_entry.get("identity"))
            if identity is not None:
                entry["identity"] = identity
                staged_identities.append(identity)
            candidate_id = _nonempty_string(raw_entry.get("candidate_id"))
            if candidate_id is not None:
                entry["candidate_id"] = candidate_id
            source_paper_id = _nonempty_string(raw_entry.get("source_paper_id"))
            if source_paper_id is not None:
                entry["source_paper_id"] = source_paper_id
            title = _nonempty_string(raw_entry.get("title"))
            if title is not None:
                entry["title"] = title
            draft = _string_keyed_mapping(raw_entry.get("draft"))
            if draft is not None:
                reviewed = AcquireCorpusUseCase._review_draft(entry, draft)
                entry["draft"] = reviewed
                drafts.append(reviewed)
            normalized_entries.append(entry)
            staged.append(paper_id)
        result["staged_entries"] = normalized_entries
        result["staged"] = staged
        result["staged_identities"] = staged_identities
        result["drafts"] = drafts


def _has_approved_harvest_seed(
    records: list[dict[str, Any]],
    *,
    domain_policy_id: str,
    as_of: datetime,
    approved_digests: frozenset[str],
) -> bool:
    if domain_policy_id != "finance/1":
        return True
    for row in records_for_policy(records, domain_policy_id):
        if record_lifecycle(row, as_of=as_of) == "invalid":
            continue
        if row.get("review_status") != "approved":
            continue
        if row.get("projector_version") != PROJECTOR_VERSION:
            continue
        digest = row.get("reviewed_projection_digest")
        if not isinstance(digest, str) or digest not in approved_digests:
            continue
        if canonical_reviewed_projection_digest(row) != digest:
            continue
        source_paper_id = row.get("source_paper_id")
        paraphrase = row.get("paraphrase")
        if not isinstance(source_paper_id, str) or not source_paper_id.strip():
            continue
        if not isinstance(paraphrase, str) or not paraphrase.strip():
            continue
        normalized_paraphrase = normalize_paraphrase(paraphrase)
        source = row.get("source")
        if not isinstance(source, str) or not source.strip():
            continue
        if normalize_source(source) != source:
            continue
        if row.get("paraphrase_sha256") != sha256_hex(normalized_paraphrase.encode("utf-8")):
            continue
        if row.get("record_id") != projection_record_id(row):
            continue
        if row.get("content_hash") != record_content_hash(
            type="paper",
            paraphrase=normalized_paraphrase,
            source=str(row["source"]),
        ):
            continue
        reviewer = row.get("human_reviewer")
        approved_at = row.get("human_approved_at")
        if not isinstance(reviewer, str) or not reviewer.strip():
            continue
        if isinstance(approved_at, str):
            try:
                approved_at = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(approved_at, datetime) and is_utc_datetime(approved_at):
            return True
    return False


def _acquisition_candidate_identity(candidate: dict[str, Any]) -> str | None:
    source_paper_id = candidate.get("source_paper_id")
    if isinstance(source_paper_id, str) and source_paper_id.strip():
        return f"source_paper_id:{source_paper_id.strip()}"
    return None


def _resolve_evaluation_policy(domain_policy_id: str, policy: DomainPolicy | None) -> DomainPolicy:
    registered = get_policy(domain_policy_id.strip())
    if policy is None:
        return registered
    if policy.policy_id != registered.policy_id:
        raise ValueError("policy does not match domain_policy_id")
    return policy

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from nsqd.domain.snapshot import canonical_json, sha256_hex

E_POLICIES = ("finance/1", "optimization/1")
OPERATOR_E_ATYPICALITY_INTERPRETATION = "corpus rarity only; not novelty or value"
OPERATOR_E_ALGORITHM_IDENTITY = "operator-e-atypical-combination/1"
_RARITY_ONLY_BRIDGES = frozenset({"low co-occurrence", "rarity only", "zero co-occurrence"})
OPERATOR_E_BROADER_PRIOR_ART_PACKET_KIND = "operator_e_broader_prior_art_evidence"
OPERATOR_E_BROADER_PRIOR_ART_SOURCE = (
    "../nsqd-jepa-ideas-gaps-2026-09-01/operator-e-broader-prior-art.json"
)
OPERATOR_E_BROADER_PRIOR_ART_SEALED_AT_UTC = "2026-09-03T08:26:14Z"
OPERATOR_E_BROADER_PRIOR_ART_CUTOFF_UTC = "2026-09-03T00:00:00Z"
OPERATOR_E_SOURCE_CANDIDATE_PATH = "operator-e-report-only-candidates.json"
OPERATOR_E_SOURCE_CANDIDATE_SHA256 = (
    "c2fee6a3a925dd8c55812c533b588972bd98ee036ed13481ac6a573b362f3783"
)
OPERATOR_E_BROADER_PRIOR_ART_PACKET_DIGEST = (
    "044ed4cd4c1e7486c391e690b4aa1a2e301cb3a1942b6ec1c581e897969cbcb1"
)
OPERATOR_E_BROADER_PRIOR_ART_BINDINGS = (
    {
        "artifact_id": "E-REPORT-01",
        "artifact_hash": "9bb6044553a17738cea566c0f2c4563094d39e1353b4d2163d764a8fda3f2aa0",
        "source_idea_id": "JEPA-IDEA-01",
        "conclusion": "strong_component_overlap_combination_unresolved",
    },
    {
        "artifact_id": "E-REPORT-02",
        "artifact_hash": "e8d0d1dc3e4b7c79f1374b3b2a364fd5f9e5080452acaef8922890bfb25e5084",
        "source_idea_id": "JEPA-IDEA-02",
        "conclusion": "strong_mechanism_overlap_combination_unresolved",
    },
    {
        "artifact_id": "E-REPORT-03",
        "artifact_hash": "b3edc59a50717fb3347cf3f34c04bdca9c87d3a7cb41c0e5b297a892fd02c415",
        "source_idea_id": "JEPA-IDEA-03",
        "conclusion": "strong_component_overlap_combination_unresolved",
    },
)
OPERATOR_E_BROADER_PRIOR_ART_ALLOWED_CONCLUSIONS = frozenset(
    {
        "strong_component_overlap_combination_unresolved",
        "strong_mechanism_overlap_combination_unresolved",
    }
)
OPERATOR_E_BOUNDED_ABSENCE_INTERPRETATION = "bounded absence is not proof of novelty"
OPERATOR_E_NOVELTY_CLAIM = "not_established"
EXPECTED_BROADER_PRIOR_ART_KNOWN_LIMITATIONS = frozenset(
    {
        "primary verification used arXiv abstract pages plus DOI or venue metadata "
        "only where exposed by arXiv",
        "failed librarian sessions produced no evidence and are not counted in this packet",
        "no claim of exhaustive ACM, IEEE, SSRN, or full-text coverage is made",
        "bounded absence is not proof of novelty",
        "the packet is report-only evidence groundwork and does not establish "
        "evidence sufficiency or runtime authorization",
    }
)
EXPECTED_BROADER_PRIOR_ART_PRIMARY_SOURCES = {
    "arXiv:2601.14354": {
        "title": (
            "VJEPA: Variational Joint Embedding Predictive Architectures as "
            "Probabilistic World Models"
        ),
        "authors": ["Yongchao Huang"],
        "submitted_at_utc": "2026-01-20",
        "revised_at_utc": None,
        "primary_url": "https://arxiv.org/abs/2601.14354",
        "doi": "10.48550/arXiv.2601.14354",
    },
    "arXiv:2603.20111": {
        "title": (
            "Var-JEPA: A Variational Formulation of the Joint-Embedding Predictive "
            "Architecture - Bridging Predictive and Generative Self-Supervised Learning"
        ),
        "authors": ["Moritz Gögl", "Christopher Yau"],
        "submitted_at_utc": "2026-03-20",
        "revised_at_utc": "2026-08-28",
        "primary_url": "https://arxiv.org/abs/2603.20111",
        "doi": "10.48550/arXiv.2603.20111",
    },
    "arXiv:2605.00126": {
        "title": (
            "SPLICE: Latent Diffusion over JEPA Embeddings for Conformal Time-Series "
            + "Inpainting"
        ),
        "authors": ["Arnaud Zinflou"],
        "submitted_at_utc": "2026-04-30",
        "revised_at_utc": None,
        "primary_url": "https://arxiv.org/abs/2605.00126",
        "doi": "10.48550/arXiv.2605.00126",
    },
    "arXiv:2507.05470": {
        "title": (
            "Temporal Conformal Prediction (TCP): A Distribution-Free Statistical and "
            "Machine Learning Framework for Adaptive Risk Forecasting"
        ),
        "authors": ["Agnideep Aich", "Ashit Baran Aich", "Dipak C. Jain"],
        "submitted_at_utc": "2025-07-07",
        "revised_at_utc": "2026-01-22",
        "primary_url": "https://arxiv.org/abs/2507.05470",
        "doi": "10.48550/arXiv.2507.05470",
    },
    "arXiv:2607.24875": {
        "title": (
            "FinAbstain: Uncertainty-Calibrated Multimodal RAG for Selective Financial "
            + "Forecasting"
        ),
        "authors": ["Dorothy Torres", "Wei Cheng", "Henan Huang"],
        "submitted_at_utc": "2026-07-27",
        "revised_at_utc": None,
        "primary_url": "https://arxiv.org/abs/2607.24875",
        "doi": "10.48550/arXiv.2607.24875",
    },
    "arXiv:2605.28520": {
        "title": (
            "GS-FUSE: Granger-Supervised Gated Fusion and Multi-Granularity Alignment "
            "for Event-Driven Financial Forecasting"
        ),
        "authors": ["Yang Zhang", "En Chun", "Ziyun Mao", "Yulu Wu", "Jun Wang"],
        "submitted_at_utc": "2026-05-27",
        "revised_at_utc": None,
        "primary_url": "https://arxiv.org/abs/2605.28520",
        "doi": "10.48550/arXiv.2605.28520",
    },
    "arXiv:2502.04592": {
        "title": (
            "CAMEF: Causal-Augmented Multi-Modality Event-Driven Financial Forecasting "
            "by Integrating Time Series Patterns and Salient Macroeconomic Announcements"
        ),
        "authors": ["Yang Zhang", "Wenbo Yang", "Jun Wang", "Qiang Ma", "Jie Xiong"],
        "submitted_at_utc": "2025-02-07",
        "revised_at_utc": "2025-08-08",
        "primary_url": "https://arxiv.org/abs/2502.04592",
        "doi": "10.48550/arXiv.2502.04592",
    },
    "arXiv:2604.16411": {
        "title": (
            "CGCMA: Conditionally-Gated Cross-Modal Attention for Event-Conditioned "
            "Asynchronous Fusion"
        ),
        "authors": ["Yunxiang Guo"],
        "submitted_at_utc": "2026-04-01",
        "revised_at_utc": None,
        "primary_url": "https://arxiv.org/abs/2604.16411",
        "doi": "10.48550/arXiv.2604.16411",
    },
    "arXiv:2605.11130": {
        "title": (
            "HEPA: A Self-Supervised Horizon-Conditioned Event Predictive Architecture "
            "for Time Series"
        ),
        "authors": [
            "Jonas Petersen",
            "Gian-Alessandro Lombardi",
            "Riccardo Maggioni",
            "Camilla Mazzoleni",
            "Federico Martelli",
            "Philipp Petersen",
        ],
        "submitted_at_utc": "2026-05-11",
        "revised_at_utc": "2026-06-03",
        "primary_url": "https://arxiv.org/abs/2605.11130",
        "doi": "10.48550/arXiv.2605.11130",
    },
    "arXiv:2409.17392": {
        "title": (
            "Trading through Earnings Seasons using Self-Supervised Contrastive "
            "Representation Learning"
        ),
        "authors": ["Zhengxin Joseph Ye", "Bjoern Schuller"],
        "submitted_at_utc": "2024-09-25",
        "revised_at_utc": None,
        "primary_url": "https://arxiv.org/abs/2409.17392",
        "doi": "10.48550/arXiv.2409.17392",
    },
    "arXiv:2602.04643": {
        "title": (
            "SC-JEPA: Stabilizing Latent Predictive Learning for Time-Series Anomaly "
            + "Prediction"
        ),
        "authors": ["Yanan He", "Yunshi Wen", "Xin Wang", "Tengfei Ma"],
        "submitted_at_utc": "2026-02-04",
        "revised_at_utc": "2026-07-17",
        "primary_url": "https://arxiv.org/abs/2602.04643",
        "doi": "10.48550/arXiv.2602.04643",
    },
    "arXiv:2606.07031": {
        "title": (
            "CF-JEPA: Mask-free forward prediction with asymmetric encoder utilization "
            "for time-series representation learning"
        ),
        "authors": ["Jaehoon Lee", "Sunghyun Sim"],
        "submitted_at_utc": "2026-06-05",
        "revised_at_utc": None,
        "primary_url": "https://arxiv.org/abs/2606.07031",
        "doi": "10.48550/arXiv.2606.07031",
    },
    "arXiv:2112.10139": {
        "title": "Denoised Labels for Financial Time-Series Data via Self-Supervised Learning",
        "authors": ["Yanqing Ma", "Carmine Ventre", "Maria Polukarov"],
        "submitted_at_utc": "2021-12-19",
        "revised_at_utc": None,
        "primary_url": "https://arxiv.org/abs/2112.10139",
        "doi": "10.48550/arXiv.2112.10139",
    },
}


def bind_operator_e_inventory(
    packet: Mapping[str, object],
    *,
    approved_records: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    if packet.get("operator") != "E":
        raise ValueError("operator E binder requires operator E packet")
    if packet.get("authorization_state") != "report_only":
        raise ValueError("operator E binder requires report_only authorization_state")
    if packet.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if packet.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    combinations = packet.get("candidate_combinations")
    if not isinstance(combinations, list) or combinations:
        raise ValueError(
            "operator E candidate combinations: candidate_combinations must be an empty list"
        )
    candidate_outputs = packet.get("candidate_outputs")
    if not isinstance(candidate_outputs, list) or candidate_outputs:
        raise ValueError("operator E candidate_outputs must be an empty list")
    inventory = _required_string_keyed_mapping(
        packet.get("approved_component_inventory"),
        "approved_component_inventory",
    )
    same_policy: dict[str, list[str]] = {}
    for policy_id in E_POLICIES:
        record_ids = _required_string_list(inventory.get(policy_id), policy_id)
        if len(set(record_ids)) != len(record_ids):
            raise ValueError(f"operator E inventory for {policy_id} has a duplicate record_id")
        bound_ids: list[str] = []
        for record_id in record_ids:
            record = approved_records.get(record_id)
            if record is None:
                raise ValueError(f"unknown record {record_id}")
            if record.get("kind") == "candidate-requirement-card":
                raise ValueError("requirement-card is not an Operator E component")
            if record.get("kind") != "corpus-paper-paraphrase":
                raise ValueError("operator E records must be approved paraphrases")
            if record.get("review_status") != "approved":
                raise ValueError("operator E records must be approved")
            record_policy = _required_string(record, "domain_policy_id")
            if record_policy != policy_id:
                raise ValueError("component domain_policy_id does not match inventory policy")
            bound_ids.append(record_id)
        same_policy[policy_id] = bound_ids
    unexpected = set(inventory) - set(E_POLICIES)
    if unexpected:
        raise ValueError("operator E inventory contains unknown domain policies")
    co_occurrence_snapshots = _co_occurrence_declarations(
        packet.get("co_occurrence_snapshots", {}),
        same_policy=same_policy,
    )
    raw_report_only = packet.get("report_only_candidate_artifacts")
    report_only_candidate_artifacts = (
        None if raw_report_only is None else _report_only_candidate_declaration(raw_report_only)
    )
    raw_broader_prior_art = packet.get("broader_prior_art_evidence")
    broader_prior_art_evidence = (
        None
        if raw_broader_prior_art is None
        else _broader_prior_art_declaration(raw_broader_prior_art)
    )
    return {
        "tracks": {
            "same_policy": same_policy,
            "cross_policy": {
                "pooled": False,
                "source_domain_policy_ids": list(E_POLICIES),
                "target_domain_policy_ids": list(E_POLICIES),
            },
        },
        "candidate_combinations": [],
        "candidate_outputs": [],
        "co_occurrence_snapshots": co_occurrence_snapshots,
        "co_occurrence_snapshot_id": None,
        "report_only_candidate_artifacts": report_only_candidate_artifacts,
        "broader_prior_art_evidence": broader_prior_art_evidence,
        "evidence_sufficient": False,
        "runtime_authorized": False,
        "algorithm_identity": "not_run",
    }


def bind_operator_e_cooccurrence_snapshot(
    inventory: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> dict[str, Any]:
    if inventory.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if inventory.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    combinations = inventory.get("candidate_combinations")
    if not isinstance(combinations, list) or combinations:
        raise ValueError(
            "operator E candidate combinations: candidate_combinations must be an empty list"
        )
    candidate_outputs = inventory.get("candidate_outputs")
    if not isinstance(candidate_outputs, list) or candidate_outputs:
        raise ValueError("operator E candidate_outputs must be an empty list")
    tracks = _required_string_keyed_mapping(inventory.get("tracks"), "tracks")
    same_policy = _required_string_keyed_mapping(tracks.get("same_policy"), "same_policy")
    record_ids = _required_string_list(snapshot.get("record_ids"), "record_ids")
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("co-occurrence snapshot has a duplicate record_id")
    inventory_ids: dict[str, set[str]] = {}
    all_ids: set[str] = set()
    for policy_id, values in same_policy.items():
        inventory_ids[policy_id] = set(_required_string_list(values, policy_id))
        all_ids.update(inventory_ids[policy_id])
    for record_id in record_ids:
        if record_id not in all_ids:
            raise ValueError(f"{record_id} is not in the Operator E inventory")
    matching = [
        policy_id for policy_id, bound_ids in inventory_ids.items() if set(record_ids) <= bound_ids
    ]
    if len(matching) != 1:
        raise ValueError("co-occurrence snapshot must occupy exactly one same-policy inventory")
    policy_id = matching[0]
    expected_track = f"same_policy:{policy_id}"
    declared_track = snapshot.get("track")
    if declared_track is not None and declared_track != expected_track:
        raise ValueError("snapshot track does not match inventory policy")
    feature_matrix = _required_string_keyed_mapping(
        snapshot.get("feature_matrix"), "feature_matrix"
    )
    feature_evidence = _required_string_keyed_mapping(
        snapshot.get("feature_evidence"), "feature_evidence"
    )
    if set(feature_matrix) != set(record_ids):
        raise ValueError("feature_matrix keys must match record_ids")
    expected_evidence_keys: set[str] = set()
    for record_id in record_ids:
        features = _required_string_list(feature_matrix.get(record_id), record_id)
        if len(set(features)) != len(features):
            raise ValueError(f"feature_matrix for {record_id} has a duplicate feature")
        for feature in features:
            evidence_key = f"{record_id}:{feature}"
            expected_evidence_keys.add(evidence_key)
    if set(feature_evidence) != expected_evidence_keys:
        raise ValueError("feature_evidence keys must exactly match record feature pairs")
    for evidence_key in expected_evidence_keys:
        evidence_ids = _required_string_list(feature_evidence.get(evidence_key), evidence_key)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError(f"feature_evidence for {evidence_key} has a duplicate evidence id")
    preimage = {
        "record_ids": record_ids,
        "feature_matrix": feature_matrix,
        "feature_evidence": feature_evidence,
    }
    snapshot_id = sha256_hex(canonical_json(preimage))
    declared_id = snapshot.get("snapshot_id")
    if declared_id != snapshot_id:
        raise ValueError("snapshot_id does not match canonical co-occurrence digest")
    declarations = _required_string_keyed_mapping(
        inventory.get("co_occurrence_snapshots"), "co_occurrence_snapshots"
    )
    declaration = _required_string_keyed_mapping(declarations.get(expected_track), expected_track)
    packet_declared_id = _required_sha256(declaration, "snapshot_id")
    if packet_declared_id != snapshot_id:
        raise ValueError("snapshot_id does not match packet-declared snapshot_id")
    declared_record_ids = _required_string_list(declaration.get("record_ids"), "record_ids")
    if declared_record_ids != record_ids:
        raise ValueError("record_ids do not match packet-declared record_ids")
    source = _required_string(snapshot, "source")
    declared_source = _required_string(declaration, "source")
    if source != declared_source:
        raise ValueError("source does not match packet-declared source")
    source_packet_digest = _required_sha256(snapshot, "source_packet_digest")
    declared_source_packet_digest = _required_sha256(declaration, "source_packet_digest")
    if source_packet_digest != declared_source_packet_digest:
        raise ValueError("source_packet_digest does not match packet-declared source_packet_digest")
    review_summary_packet_digest = _required_sha256(snapshot, "review_summary_packet_digest")
    declared_review_summary_packet_digest = _required_sha256(
        declaration, "review_summary_packet_digest"
    )
    if review_summary_packet_digest != declared_review_summary_packet_digest:
        raise ValueError(
            "review_summary_packet_digest does not match packet-declared review digest"
        )
    declared_interpretation = _required_string(declaration, "atypicality_interpretation")
    if declared_interpretation != OPERATOR_E_ATYPICALITY_INTERPRETATION:
        raise ValueError("atypicality_interpretation does not match the canonical rarity contract")
    return {
        "source": source,
        "source_packet_digest": source_packet_digest,
        "review_summary_packet_digest": review_summary_packet_digest,
        "co_occurrence_snapshot_id": snapshot_id,
        "co_occurrence_track": expected_track,
        "co_occurrence_record_ids": list(record_ids),
        "atypicality_interpretation": declared_interpretation,
        "candidate_combinations": [],
        "candidate_outputs": [],
        "operator_a_baseline_status": "not_executed",
        "operator_b_baseline_status": "not_executed",
        "evidence_sufficient": False,
        "runtime_authorized": False,
    }


def bind_operator_e_report_only_candidates(
    inventory: Mapping[str, object],
    candidates: Mapping[str, object],
    *,
    review_summary: Mapping[str, object],
) -> dict[str, Any]:
    if inventory.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if inventory.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    combinations = inventory.get("candidate_combinations")
    if not isinstance(combinations, list) or combinations:
        raise ValueError(
            "operator E candidate combinations: candidate_combinations must be an empty list"
        )
    candidate_outputs = inventory.get("candidate_outputs")
    if not isinstance(candidate_outputs, list) or candidate_outputs:
        raise ValueError("operator E candidate_outputs must be an empty list")
    declaration = _report_only_candidate_declaration(
        inventory.get("report_only_candidate_artifacts")
    )
    if candidates.get("packet_kind") != "operator_e_report_only_candidates":
        raise ValueError("report-only candidate packet_kind is invalid")
    if candidates.get("authorization_state") != "report_only":
        raise ValueError("operator E binder requires report_only authorization_state")
    if candidates.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if candidates.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    if candidates.get("schema_version") != 1:
        raise ValueError("report-only candidate schema_version is invalid")
    _required_string(candidates, "derived_at_utc")
    source_results_path = _required_string(candidates, "source_results_path")
    source_results_sha256 = _required_sha256(candidates, "source_results_sha256")
    source_snapshot_id = _required_sha256(candidates, "source_snapshot_id")
    corpus_version = _required_int(candidates, "corpus_version")
    if review_summary.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if review_summary.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    if review_summary.get("operator_activation_requested") is not False:
        raise ValueError("completed human usefulness review does not authorize Operator E")
    accounting = _required_string_keyed_mapping(
        review_summary.get("accounting_revision"), "accounting_revision"
    )
    if accounting.get("operator_e_authorization_state") != "unauthorized":
        raise ValueError("completed human usefulness review does not authorize Operator E")
    review_status = _required_string(accounting, "human_usefulness_review_status")
    review = _required_string_keyed_mapping(
        review_summary.get("human_usefulness_review"), "human_usefulness_review"
    )
    if review_status == "completed":
        if review.get("descriptive_only") is not True:
            raise ValueError("completed human usefulness review is descriptive only")
        if review.get("statistical_significance_inference") is not False:
            raise ValueError("completed human usefulness review is descriptive only")
    artifact_sha256 = _required_string_keyed_mapping(
        review_summary.get("artifact_sha256"), "artifact_sha256"
    )
    declared_source_digest = str(declaration["source_packet_digest"])
    source_name = str(declaration["source"]).rsplit("/", 1)[-1]
    if _required_sha256(artifact_sha256, source_name) != declared_source_digest:
        raise ValueError("source_packet_digest does not match the named candidate packet")
    results_name = source_results_path.rsplit("/", 1)[-1]
    if _required_sha256(artifact_sha256, results_name) != source_results_sha256:
        raise ValueError("source_results_sha256 does not match the named results packet")
    review_packet_digest = _required_sha256(review_summary, "packet_digest")
    if review_packet_digest != declaration["review_summary_packet_digest"]:
        raise ValueError(
            "review_summary_packet_digest does not match the packet-declared review digest"
        )
    tracks = _required_string_keyed_mapping(inventory.get("tracks"), "tracks")
    same_policy = _required_string_keyed_mapping(tracks.get("same_policy"), "same_policy")
    inventory_ids: set[str] = set()
    for policy_id, values in same_policy.items():
        inventory_ids.update(_required_string_list(values, policy_id))
    raw_candidates = candidates.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("candidates is required")
    artifact_ids: list[str] = []
    source_idea_ids: set[str] = set()
    seen: set[str] = set()
    for raw_candidate in raw_candidates:
        candidate = _required_string_keyed_mapping(raw_candidate, "candidates")
        artifact_id = _required_string(candidate, "artifact_id")
        if artifact_id in seen:
            raise ValueError("report-only candidate artifacts have a duplicate artifact_id")
        seen.add(artifact_id)
        if candidate.get("authorization_state") != "report_only":
            raise ValueError("operator E binder requires report_only authorization_state")
        if candidate.get("runtime_authorized") is not False:
            raise ValueError("runtime_authorized must be false")
        if candidate.get("evidence_sufficient") is not False:
            raise ValueError("evidence_sufficient must be false")
        if candidate.get("human_usefulness_score") is not None:
            raise ValueError("human_usefulness_score must remain null")
        source_idea_id = _required_string(candidate, "source_idea_id")
        if source_idea_id in source_idea_ids:
            raise ValueError("report-only candidate artifacts have a duplicate source_idea_id")
        source_idea_ids.add(source_idea_id)
        _required_string(candidate, "title")
        component_ids = _required_string_list(candidate.get("component_ids"), "component_ids")
        if len(set(component_ids)) != len(component_ids):
            raise ValueError("report-only candidate has a duplicate component_id")
        for component_id in component_ids:
            if component_id not in inventory_ids:
                raise ValueError(f"{component_id} is not in the Operator E inventory")
        _required_string_list(candidate.get("supporting_fact_ids"), "supporting_fact_ids")
        _required_sha256(candidate, "co_occurrence_snapshot_id")
        if _required_sha256(candidate, "source_snapshot_id") != source_snapshot_id:
            raise ValueError("source_snapshot_id does not match the candidate packet")
        if _required_int(candidate, "corpus_version") != corpus_version:
            raise ValueError("corpus_version does not match the candidate packet")
        atypicality = _required_string_keyed_mapping(candidate.get("atypicality"), "atypicality")
        interpretation = _required_string(atypicality, "interpretation")
        if interpretation != OPERATOR_E_ATYPICALITY_INTERPRETATION:
            raise ValueError(
                "atypicality_interpretation does not match the canonical rarity contract"
            )
        nearest = candidate.get("nearest_prior_combinations")
        if not isinstance(nearest, list):
            raise ValueError("nearest_prior_combinations is required")
        _required_string(candidate, "mechanistic_bridge")
        falsifiable_test = _required_string_keyed_mapping(
            candidate.get("falsifiable_test"), "falsifiable_test"
        )
        _required_string(falsifiable_test, "design")
        _required_string(falsifiable_test, "primary_metric")
        _required_string_list(falsifiable_test.get("secondary_metrics"), "secondary_metrics")
        _required_string(falsifiable_test, "failure_condition")
        _required_string(candidate, "prior_art_status")
        declared_artifact_hash = _required_sha256(candidate, "artifact_hash")
        if report_only_operator_e_candidate_hash(candidate) != declared_artifact_hash:
            raise ValueError("artifact_hash does not match canonical candidate content")
        artifact_ids.append(artifact_id)
    declared_ids = _required_string_list(declaration.get("artifact_ids"), "artifact_ids")
    if artifact_ids != declared_ids:
        raise ValueError("artifact_ids do not match packet-declared artifact_ids")
    if sha256_hex(canonical_json(candidates)) != declaration["source_content_digest"]:
        raise ValueError("candidates do not match the canonical candidate packet")
    return {
        "source": declaration["source"],
        "source_packet_digest": declared_source_digest,
        "source_content_digest": declaration["source_content_digest"],
        "review_summary_packet_digest": review_packet_digest,
        "report_only_artifact_ids": artifact_ids,
        "passed_to_diverge": False,
        "human_usefulness_review_status": review_status,
        "human_usefulness_review_authorizes_operator_e": False,
        "candidate_combinations": [],
        "candidate_outputs": [],
        "algorithm_identity": "not_run",
        "evidence_sufficient": False,
        "runtime_authorized": False,
    }


def require_operator_e_combination(candidate: Mapping[str, object]) -> dict[str, Any]:
    if candidate.get("generation_method") == "rarity_only_negative_control":
        raise ValueError("Operator E rejects rarity-only generation")
    track = _required_string(candidate, "combination_track")
    if track not in {"same_policy", "cross_policy"}:
        raise ValueError("Operator E combination_track must be same_policy or cross_policy")
    target_policy = _required_string(candidate, "domain_policy_id")
    if target_policy not in E_POLICIES:
        raise ValueError("Operator E domain_policy_id is not an E track policy")
    raw_components = candidate.get("components")
    if not isinstance(raw_components, Sequence) or isinstance(raw_components, (str, bytes)):
        raise ValueError("components is required")
    component_ids: list[str] = []
    component_policies: list[str] = []
    seen: set[str] = set()
    for raw_component in raw_components:
        component = _required_string_keyed_mapping(raw_component, "components")
        record_id = _required_string(component, "id")
        if record_id in seen:
            raise ValueError("Operator E component_ids must be unique")
        seen.add(record_id)
        if component.get("kind") == "candidate-requirement-card":
            raise ValueError("requirement-card is not an Operator E component")
        if component.get("kind") != "corpus-paper-paraphrase":
            raise ValueError("operator E records must be approved paraphrases")
        if component.get("review_status") != "approved":
            raise ValueError("operator E records must be approved")
        policy_id = _required_string(component, "domain_policy_id")
        if policy_id not in E_POLICIES:
            raise ValueError("Operator E component domain_policy_id is not an E track policy")
        component_ids.append(record_id)
        component_policies.append(policy_id)
    if len(component_ids) < 2:
        raise ValueError("Operator E requires at least two component_ids")
    bridge = _required_string(candidate, "mechanistic_bridge")
    if bridge.casefold() in _RARITY_ONLY_BRIDGES:
        raise ValueError("Operator E rejects rarity-only generation")
    atypicality = _required_string_keyed_mapping(candidate.get("atypicality"), "atypicality")
    interpretation = _required_string(atypicality, "interpretation")
    if interpretation != OPERATOR_E_ATYPICALITY_INTERPRETATION:
        raise ValueError("atypicality_interpretation does not match the canonical rarity contract")
    nearest = candidate.get("nearest_prior_combinations")
    if not isinstance(nearest, list):
        raise ValueError("nearest_prior_combinations is required")
    source_policy: str | None = None
    snapshot_id: str | None = None
    if track == "same_policy":
        if any(policy_id != target_policy for policy_id in component_policies):
            raise ValueError("same_policy Operator E components must share domain_policy_id")
        snapshot_id = _required_sha256(candidate, "co_occurrence_snapshot_id")
    else:
        source_policy = _required_string(candidate, "source_domain_policy_id")
        if source_policy not in E_POLICIES:
            raise ValueError("Operator E source_domain_policy_id is not an E track policy")
        if source_policy == target_policy:
            raise ValueError("cross_policy Operator E requires distinct source and target policies")
        expected = {source_policy, target_policy}
        if set(component_policies) != expected:
            raise ValueError(
                "cross_policy Operator E components must bind source and target policies"
            )
        snapshot = candidate.get("co_occurrence_snapshot_id")
        if snapshot is not None:
            snapshot_id = _required_sha256(candidate, "co_occurrence_snapshot_id")
    return {
        "algorithm_identity": OPERATOR_E_ALGORITHM_IDENTITY,
        "combination_track": track,
        "domain_policy_id": target_policy,
        "source_domain_policy_id": source_policy,
        "component_ids": component_ids,
        "mechanistic_bridge": bridge,
        "atypicality_interpretation": interpretation,
        "nearest_prior_combinations": list(nearest),
        "co_occurrence_snapshot_id": snapshot_id,
        "runtime_authorized": False,
    }


def _co_occurrence_declarations(
    value: object,
    *,
    same_policy: Mapping[str, Sequence[str]],
) -> dict[str, dict[str, object]]:
    declarations = _required_string_keyed_mapping(value, "co_occurrence_snapshots")
    normalized: dict[str, dict[str, object]] = {}
    for track, raw_declaration in declarations.items():
        declaration = _required_string_keyed_mapping(raw_declaration, track)
        prefix = "same_policy:"
        if not track.startswith(prefix):
            raise ValueError("co-occurrence snapshot track must be same_policy")
        policy_id = track.removeprefix(prefix)
        policy_record_ids = same_policy.get(policy_id)
        if policy_record_ids is None:
            raise ValueError("co-occurrence snapshot track has no matching inventory policy")
        record_ids = _required_string_list(declaration.get("record_ids"), "record_ids")
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("co-occurrence snapshot declaration has a duplicate record_id")
        if not set(record_ids) <= set(policy_record_ids):
            raise ValueError("co-occurrence snapshot declaration contains an unbound record_id")
        normalized[track] = {
            "source": _required_string(declaration, "source"),
            "source_packet_digest": _required_sha256(declaration, "source_packet_digest"),
            "review_summary_packet_digest": _required_sha256(
                declaration, "review_summary_packet_digest"
            ),
            "snapshot_id": _required_sha256(declaration, "snapshot_id"),
            "record_ids": record_ids,
            "atypicality_interpretation": _required_string(
                declaration, "atypicality_interpretation"
            ),
        }
    return normalized


def _broader_prior_art_declaration(value: object) -> dict[str, object]:
    declaration = _required_string_keyed_mapping(value, "broader_prior_art_evidence")
    artifact_ids = _required_string_list(declaration.get("artifact_ids"), "artifact_ids")
    if artifact_ids != [row["artifact_id"] for row in OPERATOR_E_BROADER_PRIOR_ART_BINDINGS]:
        raise ValueError("artifact_ids do not match the broader prior art packet")
    if declaration.get("passed_to_diverge") is not False:
        raise ValueError("broader prior art evidence must not be passed to DivergeUseCase")
    if declaration.get("human_evidence_decision_authorizes_operator_e") is not False:
        raise ValueError("broader prior art evidence does not authorize Operator E")
    return {
        "source": _required_string(declaration, "source"),
        "source_packet_digest": _required_sha256(declaration, "source_packet_digest"),
        "source_candidate_sha256": _required_sha256(declaration, "source_candidate_sha256"),
        "artifact_ids": artifact_ids,
        "primary_source_count": _required_int(declaration, "primary_source_count"),
        "passed_to_diverge": False,
        "human_evidence_decision_authorizes_operator_e": False,
    }


def _report_only_candidate_declaration(value: object) -> dict[str, object]:
    declaration = _required_string_keyed_mapping(value, "report_only_candidate_artifacts")
    artifact_ids = _required_string_list(declaration.get("artifact_ids"), "artifact_ids")
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError("report-only candidate artifacts have a duplicate artifact_id")
    if declaration.get("passed_to_diverge") is not False:
        raise ValueError("report-only candidate artifacts must not be passed to DivergeUseCase")
    if declaration.get("human_usefulness_review_authorizes_operator_e") is not False:
        raise ValueError("completed human usefulness review does not authorize Operator E")
    return {
        "source": _required_string(declaration, "source"),
        "source_packet_digest": _required_sha256(declaration, "source_packet_digest"),
        "source_content_digest": _required_sha256(declaration, "source_content_digest"),
        "review_summary_packet_digest": _required_sha256(
            declaration, "review_summary_packet_digest"
        ),
        "artifact_ids": artifact_ids,
        "passed_to_diverge": False,
        "human_usefulness_review_authorizes_operator_e": False,
    }


def _required_string_keyed_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} is required")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field} keys must be strings")
        result[key] = item
    return result


def _required_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} is required")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} values must be strings")
        result.append(item.strip())
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _required_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_int(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} is required")
    return value


def _required_sha256(payload: Mapping[str, object], field: str) -> str:
    value = _required_string(payload, field)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def operator_e_broader_prior_art_packet_digest(packet: Mapping[str, object]) -> str:
    body = {key: value for key, value in packet.items() if key != "packet_digest"}
    return sha256_hex(canonical_json(body))


def report_only_operator_e_candidate_hash(candidate: Mapping[str, object]) -> str:
    body = {key: value for key, value in candidate.items() if key != "artifact_hash"}
    return sha256_hex(canonical_json(body))


def validate_operator_e_broader_prior_art_evidence(packet: Mapping[str, object]) -> dict[str, Any]:
    payload = _required_string_keyed_mapping(packet, "operator_e_broader_prior_art_evidence")
    if payload.get("schema_version") != 1:
        raise ValueError("schema_version is invalid")
    if payload.get("packet_kind") != OPERATOR_E_BROADER_PRIOR_ART_PACKET_KIND:
        raise ValueError("packet_kind is invalid")
    if payload.get("authorization_state") != "report_only":
        raise ValueError("authorization_state must be report_only")
    if payload.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if payload.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    if payload.get("algorithm_identity") != "not_run":
        raise ValueError("algorithm_identity must be not_run")
    if payload.get("candidate_combinations") != []:
        raise ValueError("candidate_combinations must be an empty list")
    if payload.get("candidate_outputs") != []:
        raise ValueError("candidate_outputs must be an empty list")
    if payload.get("corpus_fact_writes") != 0:
        raise ValueError("corpus_fact_writes must be 0")
    if payload.get("sealed_at_utc") != OPERATOR_E_BROADER_PRIOR_ART_SEALED_AT_UTC:
        raise ValueError("sealed_at_utc is invalid")
    if payload.get("cutoff_utc") != OPERATOR_E_BROADER_PRIOR_ART_CUTOFF_UTC:
        raise ValueError("cutoff_utc is invalid")
    source_packet = _required_string_keyed_mapping(
        payload.get("source_candidate_packet"), "source_candidate_packet"
    )
    if source_packet.get("path") != OPERATOR_E_SOURCE_CANDIDATE_PATH:
        raise ValueError("path is invalid")
    if _required_sha256(source_packet, "sha256") != OPERATOR_E_SOURCE_CANDIDATE_SHA256:
        raise ValueError("sha256 is invalid")
    bindings = source_packet.get("artifact_bindings")
    if not isinstance(bindings, list) or len(bindings) != len(
        OPERATOR_E_BROADER_PRIOR_ART_BINDINGS
    ):
        raise ValueError("artifact_bindings are required")
    if [
        _required_string(_required_string_keyed_mapping(row, "artifact_bindings"), "artifact_id")
        for row in bindings
    ] != [row["artifact_id"] for row in OPERATOR_E_BROADER_PRIOR_ART_BINDINGS]:
        raise ValueError("artifact_id is invalid")
    for raw_binding, expected in zip(bindings, OPERATOR_E_BROADER_PRIOR_ART_BINDINGS, strict=True):
        binding = _required_string_keyed_mapping(raw_binding, "artifact_bindings")
        if _required_string(binding, "artifact_id") != expected["artifact_id"]:
            raise ValueError("artifact_id is invalid")
        if _required_sha256(binding, "artifact_hash") != expected["artifact_hash"]:
            raise ValueError("artifact_hash is invalid")
        if _required_string(binding, "source_idea_id") != expected["source_idea_id"]:
            raise ValueError("source_idea_id is invalid")
    if (
        payload.get("source_snapshot_id")
        != "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5"
    ):
        raise ValueError("source_snapshot_id is invalid")
    if payload.get("corpus_version") != 11:
        raise ValueError("corpus_version is invalid")
    search_protocol = _required_string_keyed_mapping(
        payload.get("search_protocol"), "search_protocol"
    )
    if search_protocol.get("query_count") != 3:
        raise ValueError("query_count is invalid")
    if search_protocol.get("novelty_claim") != OPERATOR_E_NOVELTY_CLAIM:
        raise ValueError("novelty_claim is invalid")
    if search_protocol.get("absence_interpretation") != OPERATOR_E_BOUNDED_ABSENCE_INTERPRETATION:
        raise ValueError("absence_interpretation is invalid")
    if search_protocol.get("failed_librarian_sessions_counted") is not False:
        raise ValueError("failed_librarian_sessions_counted must be false")
    if search_protocol.get("unique_primary_record_count") != len(
        EXPECTED_BROADER_PRIOR_ART_PRIMARY_SOURCES
    ):
        raise ValueError("unique_primary_record_count is invalid")
    primary_sources = payload.get("primary_sources")
    if not isinstance(primary_sources, list) or len(primary_sources) != len(
        EXPECTED_BROADER_PRIOR_ART_PRIMARY_SOURCES
    ):
        raise ValueError("primary_sources are required")
    seen_ids: set[str] = set()
    for raw_source in primary_sources:
        source = _required_string_keyed_mapping(raw_source, "primary_sources")
        stable_id = _required_string(source, "stable_id")
        if stable_id in seen_ids:
            raise ValueError("stable_id must be unique")
        seen_ids.add(stable_id)
        expected = EXPECTED_BROADER_PRIOR_ART_PRIMARY_SOURCES.get(stable_id)
        if expected is None:
            raise ValueError("stable_id is invalid")
        if _required_string(source, "title") != expected["title"]:
            raise ValueError("title is invalid")
        if _required_string(source, "primary_url") != expected["primary_url"]:
            raise ValueError("primary_url is invalid")
        if _required_string(source, "submitted_at_utc") != expected["submitted_at_utc"]:
            raise ValueError("submitted_at_utc is invalid")
        revised = source.get("revised_at_utc")
        if revised != expected["revised_at_utc"]:
            raise ValueError("revised_at_utc is invalid")
        if _required_string(source, "doi") != expected["doi"]:
            raise ValueError("doi is invalid")
        if source.get("evidence_locator") != "arXiv abstract":
            raise ValueError("evidence_locator is invalid")
        if _required_string_list(source.get("authors"), "authors") != expected["authors"]:
            raise ValueError("authors are invalid")
        _required_string_list(source.get("component_tags"), "component_tags")
        _required_string(source, "evidence_summary")
        _required_string(source, "limitations")
    candidate_assessments = payload.get("candidate_assessments")
    if not isinstance(candidate_assessments, list) or len(candidate_assessments) != 3:
        raise ValueError("candidate_assessments are required")
    source_ids = set(EXPECTED_BROADER_PRIOR_ART_PRIMARY_SOURCES)
    by_artifact = {row["artifact_id"]: row for row in OPERATOR_E_BROADER_PRIOR_ART_BINDINGS}
    seen_artifacts: set[str] = set()
    for raw_assessment in candidate_assessments:
        assessment = _required_string_keyed_mapping(raw_assessment, "candidate_assessments")
        artifact_id = _required_string(assessment, "artifact_id")
        if artifact_id in seen_artifacts:
            raise ValueError("artifact_id must be unique")
        seen_artifacts.add(artifact_id)
        expected = by_artifact.get(artifact_id)
        if expected is None:
            raise ValueError("artifact_id is invalid")
        if _required_sha256(assessment, "artifact_hash") != expected["artifact_hash"]:
            raise ValueError("artifact_hash is invalid")
        if _required_string(assessment, "source_idea_id") != expected["source_idea_id"]:
            raise ValueError("source_idea_id is invalid")
        if (
            _required_string(assessment, "source_candidate_packet_path")
            != OPERATOR_E_SOURCE_CANDIDATE_PATH
        ):
            raise ValueError("source_candidate_packet_path is invalid")
        if (
            _required_sha256(assessment, "source_candidate_packet_sha256")
            != OPERATOR_E_SOURCE_CANDIDATE_SHA256
        ):
            raise ValueError("source_candidate_packet_sha256 is invalid")
        conclusion = _required_string(assessment, "conclusion")
        if (
            conclusion != expected["conclusion"]
            or conclusion not in OPERATOR_E_BROADER_PRIOR_ART_ALLOWED_CONCLUSIONS
        ):
            raise ValueError("conclusion is invalid")
        if _required_string(assessment, "novelty_claim") != OPERATOR_E_NOVELTY_CLAIM:
            raise ValueError("novelty_claim is invalid")
        if (
            _required_string(assessment, "absence_interpretation")
            != OPERATOR_E_BOUNDED_ABSENCE_INTERPRETATION
        ):
            raise ValueError("absence_interpretation is invalid")
        _required_string(assessment, "narrowed_overlap_conclusion")
        _required_string(assessment, "remaining_question")
        nearest = assessment.get("nearest_prior_combinations")
        if not isinstance(nearest, list) or not nearest:
            raise ValueError("nearest_prior_combinations is required")
        for combo in nearest:
            combo_payload = _required_string_keyed_mapping(combo, "nearest_prior_combinations")
            combo_source_ids = _required_string_list(combo_payload.get("source_ids"), "source_ids")
            if not set(combo_source_ids) <= source_ids:
                raise ValueError("source_ids are invalid")
            _required_string(combo_payload, "overlap_summary")
    known_limitations = _required_string_list(payload.get("known_limitations"), "known_limitations")
    if set(known_limitations) != EXPECTED_BROADER_PRIOR_ART_KNOWN_LIMITATIONS:
        raise ValueError("known_limitations are invalid")
    forbidden_inferences = _required_string_list(
        payload.get("forbidden_inferences"), "forbidden_inferences"
    )
    expected_forbidden = {
        "bounded absence proves novelty",
        "the packet authorizes Operator E",
        "the packet authorizes runtime generation",
        "the packet establishes evidence sufficiency",
        "the broader packet turns report-only artifacts into candidate_combinations",
    }
    if set(forbidden_inferences) != expected_forbidden:
        raise ValueError("forbidden_inferences are invalid")
    if payload.get("packet_digest") != OPERATOR_E_BROADER_PRIOR_ART_PACKET_DIGEST:
        raise ValueError("packet_digest does not match the canonical broader prior-art packet")
    if operator_e_broader_prior_art_packet_digest(payload) != payload.get("packet_digest"):
        raise ValueError("packet_digest is invalid")
    return payload


def bind_operator_e_broader_prior_art_evidence(
    inventory: Mapping[str, object],
    packet: Mapping[str, object],
) -> dict[str, Any]:
    if inventory.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if inventory.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    if inventory.get("candidate_combinations") != []:
        raise ValueError("candidate_combinations must be an empty list")
    if inventory.get("candidate_outputs") != []:
        raise ValueError("candidate_outputs must be an empty list")
    declaration = _broader_prior_art_declaration(inventory.get("broader_prior_art_evidence"))
    validated = validate_operator_e_broader_prior_art_evidence(packet)
    if declaration["source"] != OPERATOR_E_BROADER_PRIOR_ART_SOURCE:
        raise ValueError("broader prior art source is invalid")
    if declaration["source_packet_digest"] != validated["packet_digest"]:
        raise ValueError("source_packet_digest does not match broader prior art packet_digest")
    if declaration["source_candidate_sha256"] != validated["source_candidate_packet"]["sha256"]:
        raise ValueError("source_candidate_sha256 does not match the broader prior art packet")
    artifact_ids = [row["artifact_id"] for row in OPERATOR_E_BROADER_PRIOR_ART_BINDINGS]
    if declaration["artifact_ids"] != artifact_ids:
        raise ValueError("artifact_ids do not match the broader prior art packet")
    if declaration["primary_source_count"] != len(validated["primary_sources"]):
        raise ValueError("primary_source_count does not match the broader prior art packet")
    return {
        "source": declaration["source"],
        "source_packet_digest": declaration["source_packet_digest"],
        "report_only_artifact_ids": artifact_ids,
        "primary_source_count": len(validated["primary_sources"]),
        "novelty_claim": validated["search_protocol"]["novelty_claim"],
        "candidate_combinations": [],
        "candidate_outputs": [],
        "algorithm_identity": "not_run",
        "evidence_sufficient": False,
        "runtime_authorized": False,
    }

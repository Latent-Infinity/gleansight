from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    fact_id: str
    record_id: str
    claim: str


@dataclass(frozen=True, slots=True)
class Gap:
    gap_id: str
    title: str
    inference: str
    uncertainty: str
    supporting_evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class Experiment:
    design: str
    baselines: str
    primary_metric: str
    secondary_metrics: tuple[str, ...]
    reject_condition: str


@dataclass(frozen=True, slots=True)
class RetainedHypothesis:
    hypothesis_id: str
    title: str
    mechanistic_bridge: str
    supporting_evidence: tuple[EvidenceRef, ...]
    experiment: Experiment
    overlap_caveat: str
    remaining_question: str

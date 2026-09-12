from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final, Literal

from nsqd.domain.operator_f_evaluation_types import (
    FoldAssignment,
    FoldDefinition,
    JsonValue,
    OperatorFSourceGroup,
    ShuffleAssignment,
    ShuffleDefinition,
    TrackLabel,
    TrackReplay,
    ValidationTarget,
)
from nsqd.domain.snapshot import canonical_json, sha256_hex

FOLD_SEED: Final = "operator-f/evidence-resolution/source-grouped-five-fold/v1"
SHUFFLE_SEED: Final[
    Literal["operator-f/evidence-resolution/source-grouped-five-fold/v1:shuffled-validation-target"]
] = "operator-f/evidence-resolution/source-grouped-five-fold/v1:shuffled-validation-target"


@dataclass(frozen=True, slots=True)
class OperatorFEvaluationError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def partition_source_groups(
    source_groups: tuple[OperatorFSourceGroup, ...],
) -> tuple[tuple[OperatorFSourceGroup, ...], tuple[OperatorFSourceGroup, ...]]:
    eligible = tuple(
        sorted(
            (
                record
                for record in source_groups
                if record.registered_coordinates is not None
                and record.validation_target is not None
            ),
            key=lambda record: record.canonical_work_identity,
        )
    )
    excluded = tuple(
        sorted(
            (record for record in source_groups if record not in eligible),
            key=lambda record: record.canonical_work_identity,
        )
    )
    return eligible, excluded


def build_folds(eligible: tuple[OperatorFSourceGroup, ...]) -> FoldDefinition:
    ranked = sorted(
        (
            hashlib.sha256(f"{FOLD_SEED}:{record.canonical_work_identity}".encode()).hexdigest(),
            record.canonical_work_identity,
        )
        for record in eligible
    )
    assignments = tuple(
        FoldAssignment(
            canonical_work_identity=identity,
            digest=digest,
            fold_index=rank % 5,
        )
        for rank, (digest, identity) in enumerate(ranked)
    )
    return FoldDefinition(
        algorithm="sha256_seeded_source_group_round_robin/v1",
        seed=FOLD_SEED,
        preimage="utf8(seed + ':' + canonical_source_group_identity)",
        ordering="ascending_sha256_then_canonical_source_group_identity",
        assignment="zero_based_rank_modulo_5",
        assignments=assignments,
    )


def build_shuffle(identities: tuple[str, ...]) -> ShuffleDefinition:
    ranked = tuple(
        identity
        for _, identity in sorted(
            (
                hashlib.sha256(f"{SHUFFLE_SEED}:{identity}".encode()).hexdigest(),
                identity,
            )
            for identity in identities
        )
    )
    if len(ranked) < 2:
        assignments = tuple(
            ShuffleAssignment(
                canonical_work_identity=identity,
                receives_validation_target_from=identity,
            )
            for identity in ranked
        )
        fixed_point_free = not ranked
    else:
        assignments = tuple(
            ShuffleAssignment(
                canonical_work_identity=identity,
                receives_validation_target_from=ranked[(index + 1) % len(ranked)],
            )
            for index, identity in enumerate(ranked)
        )
        fixed_point_free = True
    return ShuffleDefinition(
        algorithm="sha256_seeded_permutation_within_eligible_population/v1",
        seed=(
            "operator-f/evidence-resolution/source-grouped-five-fold/v1:shuffled-validation-target"
        ),
        fixed_point_free=fixed_point_free,
        assignments=assignments,
    )


def build_tracks(
    labels_by_identity: tuple[tuple[str, ValidationTarget], ...],
    folds: FoldDefinition,
    shuffle: ShuffleDefinition,
) -> tuple[TrackReplay, TrackReplay, TrackReplay]:
    identities = tuple(identity for identity, _ in labels_by_identity)
    labels: dict[str, ValidationTarget] = dict(labels_by_identity)
    candidate_labels = tuple(
        TrackLabel(canonical_work_identity=identity, validation_target=labels[identity])
        for identity in identities
    )
    shuffled_labels = tuple(
        TrackLabel(
            canonical_work_identity=assignment.canonical_work_identity,
            validation_target=labels[assignment.receives_validation_target_from],
        )
        for assignment in sorted(
            shuffle.assignments,
            key=lambda item: item.canonical_work_identity,
        )
    )
    return (
        TrackReplay(
            track_id="current_registered_axes",
            eligible_source_group_identities=identities,
            fold_assignments=folds.assignments,
            labels=(),
        ),
        TrackReplay(
            track_id="current_axes_plus_validation_target",
            eligible_source_group_identities=identities,
            fold_assignments=folds.assignments,
            labels=candidate_labels,
        ),
        TrackReplay(
            track_id="current_axes_plus_shuffled_validation_target",
            eligible_source_group_identities=identities,
            fold_assignments=folds.assignments,
            labels=shuffled_labels,
        ),
    )


def require_identical_tracks(tracks: tuple[TrackReplay, TrackReplay, TrackReplay]) -> None:
    populations = {track.eligible_source_group_identities for track in tracks}
    if len(populations) != 1:
        raise OperatorFEvaluationError("track population mismatch")
    folds = {track.fold_assignments for track in tracks}
    if len(folds) != 1:
        raise OperatorFEvaluationError("track fold mismatch")


def result_digest(payload: dict[str, JsonValue]) -> str:
    preimage = dict(payload)
    preimage["result_digest"] = None
    return sha256_hex(canonical_json(preimage))

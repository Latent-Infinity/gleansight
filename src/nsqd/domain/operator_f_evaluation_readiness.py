from __future__ import annotations

from typing import Final, Literal, Self

import pydantic

from nsqd.domain.operator_f_evaluation_support import FOLD_SEED, build_shuffle, build_tracks
from nsqd.domain.operator_f_evaluation_types import (
    FoldDefinition,
    RegisteredCoordinates,
    ShuffleDefinition,
    TrackReplay,
    ValidationTarget,
)
from nsqd.domain.operator_f_evaluation_validation import (
    NonBlank,
    OperatorFValidationError,
    Sha256,
)

_EXPECTED_GROUPS: Final = (
    (
        "N11-FIN-01",
        "doi:10.2139/ssrn.6855118",
        "a53a3709784dc063af81e969f9e006497f4913634c2d3f9c5eee8eb9fae7f0cb",
        "d7a85481038ba3a52dbb713656cb98837479ee402b3732a637279934ced40dd2",
        False,
        "representation_fidelity",
    ),
    (
        "N11-FIN-02",
        "arxiv:2409.17392",
        "c2b1566e4bcde1ca7795a850cd2e2c173d36fa5a7dab6302d7c41d4ad54b8ec9",
        "8899b360fd7093286af98a343bf13a2f8529beef2786e6eadbfde00da942cfef",
        True,
        "predictive_task",
    ),
    (
        "N11-FIN-03",
        "doi:10.1016/j.eswa.2024.123538",
        "6cb8c419012687cf59234d898665ed6a5f9001809a570638530f4b5caa045620",
        "74382586d45e0dc0353dd695f95bddfe3e6664ce9337f7f1392a11aa43636389",
        True,
        "economic_utility",
    ),
    (
        "N11-FIN-04",
        "arxiv:2512.12727",
        "5e72b16c73c9d80d90805f65ec8e5445a6aabbfa7af54e9e9327086ad893daef",
        "a03a700f8944c2eea86ef1da143daec03f0368c8eef9d30dc0bed8ee20d36944",
        True,
        "economic_utility",
    ),
    (
        "N11-FIN-05",
        "doi:10.1145/3533271.3561687",
        "cdfc67f7ff9c8ff8f39139df3e2906f6a6229d818418ce834868911f76edb6e9",
        "1347adc049591baac68831c9ce2a50817f7fd8feb116c51e2f26e5ab57bd634d",
        False,
        "predictive_task",
    ),
)


class _FrozenModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, extra="forbid", strict=True)


class OperatorFHistoricalSourceGroup(_FrozenModel):
    record_id: NonBlank
    canonical_work_identity: NonBlank
    approved_projection_sha256: Sha256
    approved_excerpt_sha256: Sha256
    registered_coordinates: RegisteredCoordinates | None
    validation_target: ValidationTarget


class OperatorFHistoricalReadinessInputs(_FrozenModel):
    readiness_sha256: Literal["a1af10fcccd421aa2491ca6d75fba6bf29c127585bf7031adc367b4dc4c511dd"]
    historical_pilot_result_sha256: Literal[
        "888d1e7c9d3fab43713b76dad3c66749466d00ac5313a0e8de87b3f4b542252a"
    ]
    authorization_state: Literal["report_only"]
    approval_scope: Literal["evaluation_only"]
    runtime_authorized: Literal[False]
    schema_admission_authorized: Literal[False]
    evidence_sufficient: Literal[False]
    successor_approvals_available: Literal[False]
    source_groups: tuple[OperatorFHistoricalSourceGroup, ...]

    @pydantic.model_validator(mode="after")
    def require_exact_historical_inventory(self) -> Self:
        observed = tuple(
            (
                group.record_id,
                group.canonical_work_identity,
                group.approved_projection_sha256,
                group.approved_excerpt_sha256,
                group.registered_coordinates is not None,
                group.validation_target,
            )
            for group in self.source_groups
        )
        if observed != _EXPECTED_GROUPS:
            raise OperatorFValidationError(
                "historical Operator F readiness inventory does not match"
            )
        return self


def historical_replay_components(
    inputs: OperatorFHistoricalReadinessInputs,
) -> tuple[
    tuple[tuple[str, ...], tuple[str, ...]],
    FoldDefinition,
    ShuffleDefinition,
    tuple[TrackReplay, TrackReplay, TrackReplay],
]:
    eligible = tuple(
        sorted(
            (group for group in inputs.source_groups if group.registered_coordinates is not None),
            key=lambda group: group.canonical_work_identity,
        )
    )
    excluded = tuple(
        sorted(
            (group for group in inputs.source_groups if group.registered_coordinates is None),
            key=lambda group: group.canonical_work_identity,
        )
    )
    fold_definition = FoldDefinition(
        algorithm="sha256_seeded_source_group_round_robin/v1",
        seed=FOLD_SEED,
        preimage="utf8(seed + ':' + canonical_source_group_identity)",
        ordering="ascending_sha256_then_canonical_source_group_identity",
        assignment="zero_based_rank_modulo_5",
        assignments=(),
    )
    targets: dict[str, ValidationTarget] = {
        "representation_fidelity": "representation_fidelity",
        "predictive_task": "predictive_task",
        "economic_utility": "economic_utility",
        "calibrated_risk": "calibrated_risk",
    }
    labels: tuple[tuple[str, ValidationTarget], ...] = tuple(
        (group.canonical_work_identity, targets[group.validation_target]) for group in eligible
    )
    shuffle = build_shuffle(tuple(identity for identity, _ in labels))
    tracks = build_tracks(labels, fold_definition, shuffle)
    identities = (
        tuple(group.canonical_work_identity for group in eligible),
        tuple(group.canonical_work_identity for group in excluded),
    )
    return identities, fold_definition, shuffle, tracks

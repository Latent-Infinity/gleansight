from __future__ import annotations

from nsqd.domain import operator_f_evaluation as operator_f
from tests.nsqd.operator_f_evaluation_historical_support import (
    historical_current_readiness_inputs,
)


def test_exact_historical_current_inventory_projects_only_to_blocked_unavailable() -> None:
    trusted = historical_current_readiness_inputs()

    result = operator_f.evaluate_operator_f_historical_readiness(trusted)

    assert isinstance(result, operator_f.OperatorFUnavailableResult)
    assert result.eligible_source_group_identities == (
        "arxiv:2409.17392",
        "arxiv:2512.12727",
        "doi:10.1016/j.eswa.2024.123538",
    )
    assert result.excluded_source_group_identities == (
        "doi:10.1145/3533271.3561687",
        "doi:10.2139/ssrn.6855118",
    )
    assert result.blocker == "insufficient_eligible_source_groups"
    assert result.authorization_state == "report_only"
    assert result.evidence_sufficient is False
    assert result.fold_definition.assignments == ()
    assert all(metric.state == "unavailable" for metric in result.metrics)
    assert (
        result.result_digest == "ff17865c52b736aaafd19015ee5f101dfb87f3df7a36e9a2102bfc25f30f0c81"
    )


def test_historical_projection_cannot_enter_successor_evaluation() -> None:
    trusted = historical_current_readiness_inputs()

    assert not isinstance(trusted, operator_f.OperatorFEvaluationInputs)
    assert trusted.successor_approvals_available is False

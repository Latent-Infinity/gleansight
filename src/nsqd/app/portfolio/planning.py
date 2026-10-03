from __future__ import annotations

from nsqd.domain.acquisition import acquisition_route, render_acquisition_query
from nsqd.domain.acquisition_portfolio import (
    AcquisitionPortfolio,
    Deficit,
    PortfolioCaps,
    PortfolioQuery,
    SufficiencyObservation,
    digest_json,
    model_digest,
)


def plan_portfolio(before: SufficiencyObservation, caps: PortfolioCaps) -> AcquisitionPortfolio:
    context = before.search_context.model_copy(
        update={
            "missing_cell_ids": tuple(sorted(set(before.search_context.missing_cell_ids))),
            "missing_recall_probes": tuple(
                sorted(
                    set(before.search_context.missing_recall_probes),
                    key=lambda probe: (probe.probe_id, probe.source, probe.record_type),
                )
            ),
            "unmet_record_types": tuple(sorted(set(before.search_context.unmet_record_types))),
        }
    )
    before = before.model_copy(
        update={"failures": tuple(sorted(set(before.failures))), "search_context": context}
    )
    route = acquisition_route(list(before.failures))
    deficits: list[Deficit] = []
    if route == "search":
        for cell in context.missing_cell_ids:
            if "expected_cell_empty" in before.failures:
                deficits.append(
                    Deficit(
                        deficit_id=digest_json(["cell", cell]),
                        failure="expected_cell_empty",
                        cell_id=cell,
                        record_type="paper",
                    )
                )
        for probe in context.missing_recall_probes:
            if "recall_probe_missing" in before.failures:
                deficits.append(
                    Deficit(
                        deficit_id=digest_json(
                            ["probe", probe.probe_id, probe.source, probe.record_type]
                        ),
                        failure="recall_probe_missing",
                        probe_id=probe.probe_id,
                        source=probe.source,
                        record_type=probe.record_type,
                    )
                )
        if "domain_minima_unmet" in before.failures:
            for record_type in context.unmet_record_types or ("paper",):
                deficits.append(
                    Deficit(
                        deficit_id=digest_json(["type", record_type]),
                        failure="domain_minima_unmet",
                        record_type=record_type,
                    )
                )
    selected = deficits[: min(caps.max_deficits, caps.max_queries)]
    queries: dict[str, PortfolioQuery] = {}
    for deficit in selected:
        text = render_acquisition_query(
            policy_id=before.domain_policy_id,
            failure=deficit.failure,
            cell_id=deficit.cell_id,
            probe_id=deficit.probe_id,
            record_type=deficit.record_type,
        )
        query_id = digest_json([text, deficit.record_type])
        previous = queries.get(query_id)
        targets = (*previous.target_ids, deficit.deficit_id) if previous else (deficit.deficit_id,)
        queries[query_id] = PortfolioQuery(
            query_id=query_id, text=text, record_type=deficit.record_type, target_ids=targets
        )
    provisional = AcquisitionPortfolio.model_validate(
        {
            "portfolio_id": "0" * 64,
            "before": before,
            "route": route,
            "caps": caps,
            "deficits": selected,
            "queries": tuple(queries.values()),
            "omitted_deficits": len(deficits) - len(selected),
        }
    )
    return provisional.model_copy(update={"portfolio_id": model_digest(provisional)})

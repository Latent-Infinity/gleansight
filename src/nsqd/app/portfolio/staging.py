from __future__ import annotations

from pydantic import JsonValue, TypeAdapter

from nsqd.app.portfolio.planning import plan_portfolio
from nsqd.domain.acquisition_portfolio import (
    AcquisitionPortfolio,
    PortfolioError,
    RetrievalBinding,
    SourceBinding,
    StagedPortfolio,
    Text,
)
from nsqd.ports import PaperAcquisitionBridge


def stage_portfolio(plan: AcquisitionPortfolio, bridge: PaperAcquisitionBridge) -> StagedPortfolio:
    if plan_portfolio(plan.before, plan.caps) != plan:
        raise PortfolioError("Portfolio identity or target bindings changed")
    sources: dict[str, SourceBinding] = {}
    retrievals: list[RetrievalBinding] = []
    counts = dict.fromkeys((item.deficit_id for item in plan.deficits), 0)
    for query in plan.queries:
        raw = bridge.discover(query.text, {"type": query.record_type})[
            : plan.caps.candidates_per_query
        ]
        discovered: dict[str, dict[str, JsonValue]] = {}
        for item in raw:
            candidate = TypeAdapter(dict[str, JsonValue]).validate_python(item)
            source_id = TypeAdapter(Text).validate_python(candidate.get("source_paper_id"))
            discovered.setdefault(source_id, candidate)
        available = min(
            plan.caps.per_deficit_sources - counts[target] for target in query.target_ids
        )
        shared = sorted(source for source in discovered if source in sources)
        fresh = sorted(source for source in discovered if source not in sources)
        candidates = shared + fresh[: plan.caps.max_sources - len(sources)]
        chosen: list[str] = []
        if candidates and available:
            shortlist = bridge.shortlist(
                [discovered[source] for source in candidates],
                limit=min(available, len(candidates)),
                insufficiency_query=query.text,
                filters={"type": query.record_type},
                failure_context={
                    "target_ids": list(query.target_ids),
                    "failures": list(plan.before.failures),
                    "search_context": plan.before.search_context.model_dump(mode="json"),
                },
            )
            for raw_choice in shortlist:
                choice = TypeAdapter(dict[str, JsonValue]).validate_python(raw_choice)
                if choice.get("review_status") == "approved":
                    raise PortfolioError("LLM output cannot approve corpus evidence")
                source_id = TypeAdapter(Text).validate_python(choice.get("source_paper_id"))
                if source_id not in candidates:
                    raise PortfolioError(
                        "Shortlisted source was not an eligible discovered candidate"
                    )
                if source_id in chosen:
                    continue
                if len(chosen) >= available:
                    raise PortfolioError("Shortlist exceeds the per-deficit source cap")
                previous = sources.get(source_id)
                if previous is None:
                    paper_id = TypeAdapter(Text).validate_python(
                        bridge.stage_import(discovered[source_id])
                    )
                    if any(source.paper_id == paper_id for source in sources.values()):
                        raise PortfolioError(
                            "Different source identities resolved to the same imported paper"
                        )
                    bridge.enqueue_analyze(paper_id)
                    draft = TypeAdapter(dict[str, JsonValue]).validate_python(
                        bridge.draft_projection(paper_id)
                    )
                    if draft.get("review_status") == "approved":
                        raise PortfolioError("LLM output cannot approve corpus evidence")
                    if draft.get("source_paper_id", source_id) != source_id:
                        raise PortfolioError("Draft source does not match the discovered source")
                    previous = SourceBinding(
                        source_paper_id=source_id,
                        paper_id=paper_id,
                        target_ids=(),
                        query_ids=(),
                        draft=draft,
                    )
                sources[source_id] = previous.model_copy(
                    update={
                        "query_ids": tuple(sorted(set((*previous.query_ids, query.query_id)))),
                        "target_ids": tuple(sorted(set((*previous.target_ids, *query.target_ids)))),
                    }
                )
                chosen.append(source_id)
                for target in query.target_ids:
                    if target not in previous.target_ids:
                        counts[target] += 1
        retrievals.append(
            RetrievalBinding(
                query_id=query.query_id,
                target_ids=query.target_ids,
                discovered_source_ids=tuple(sorted(discovered)),
                shortlisted_source_ids=tuple(chosen),
            )
        )
    return StagedPortfolio(plan=plan, retrievals=tuple(retrievals), sources=tuple(sources.values()))

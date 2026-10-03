from __future__ import annotations

from nsqd.app.portfolio.planning import plan_portfolio
from nsqd.domain.acquisition_portfolio import PortfolioError, StagedPortfolio


def validate_staged(staged: StagedPortfolio) -> None:
    plan = staged.plan
    if plan_portfolio(plan.before, plan.caps) != plan:
        raise PortfolioError("Portfolio identity or target bindings changed")
    queries = {query.query_id: query for query in plan.queries}
    if len(staged.sources) > plan.caps.max_sources:
        raise PortfolioError("Staged sources exceed the global cap")
    sources = {source.source_paper_id: source for source in staged.sources}
    if len(sources) != len(staged.sources) or len(
        {source.paper_id for source in staged.sources}
    ) != len(sources):
        raise PortfolioError("Staged source identities are not unique")
    rows = {row.query_id: row for row in staged.retrievals}
    if set(rows) != set(queries) or len(rows) != len(staged.retrievals):
        raise PortfolioError("Retrievals do not match the planned queries")
    for query_id, row in rows.items():
        if row.target_ids != queries[query_id].target_ids:
            raise PortfolioError("Retrieval target binding changed")
        if len(row.discovered_source_ids) > plan.caps.candidates_per_query:
            raise PortfolioError("Discovery exceeds the per-query cap")
        if len(row.shortlisted_source_ids) != len(set(row.shortlisted_source_ids)):
            raise PortfolioError("Shortlist contains duplicate source identities")
        if not set(row.shortlisted_source_ids) <= set(row.discovered_source_ids) & set(sources):
            raise PortfolioError("Shortlist includes an undiscovered or unstaged source")
    for source_id, source in sources.items():
        expected_queries = tuple(
            sorted(key for key, row in rows.items() if source_id in row.shortlisted_source_ids)
        )
        expected_targets = tuple(
            sorted({target for key in expected_queries for target in queries[key].target_ids})
        )
        if (
            not expected_queries
            or source.query_ids != expected_queries
            or source.target_ids != expected_targets
        ):
            raise PortfolioError("Source target bindings do not match its retrievals")
        if source.draft.get("review_status") == "approved":
            raise PortfolioError("Drafts cannot approve corpus evidence")
    for deficit in plan.deficits:
        if (
            sum(deficit.deficit_id in source.target_ids for source in staged.sources)
            > plan.caps.per_deficit_sources
        ):
            raise PortfolioError("Sources exceed the per-deficit cap")

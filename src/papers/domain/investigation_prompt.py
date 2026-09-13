from __future__ import annotations

import json
from collections.abc import Sequence

from papers.domain.investigation_plan import InvestigationPlan, SourceReference

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


def investigation_plan_schema() -> dict[str, JsonValue]:
    return InvestigationPlan.model_json_schema()


def build_investigation_plan_prompt(
    question: str,
    context: str,
    sources: Sequence[SourceReference],
) -> str:
    source_catalog = "\n".join(
        f"- Paper ID: {source.paper_id}; title: {source.title or 'unknown'}" for source in sources
    )
    schema_json = json.dumps(investigation_plan_schema(), sort_keys=True)
    return f"""Create an investigation plan from the retrieved research corpus.
Return only one JSON object conforming exactly to the supplied JSON Schema.

Select and justify a core paper to replicate first. exact_replication targets the original protocol
without substitutions; unknown prerequisites may block that planned target, and direct paper-metric
comparison remains disallowed until protocol equivalence and metric comparability are reported with
citations. constrained_reproduction substitutes unavailable protocol elements and must list every
deviation as a concrete reported or proposed value. conceptual_reimplementation tests the mechanism
only, must name its concrete deviations, and must not compare paper metrics. If the substitute is
unknown, keep the exact target and mark its relevant step blocked, or name a proposed conceptual
deviation and its uncertainty; never use an unknown null deviation as a substitution.
Only after the baseline, include adjacent mechanisms relevant to the question. This is planning, not
executed work: use not_started by default and never claim verification without execution evidence.

Separate facts, inferences, and proposals with claim_kind. For every requirement, set
evidence_status to reported, proposed, or unknown. Cite paper IDs for reported claims; give an
uncertainty rationale for unsupported proposals and unknowns. Do not invent data access, licenses,
splits, time horizons, granularity, architecture, code, checkpoints, hardware, VRAM, or GPU-hour
values. Numeric values need an explicit basis or assumption and paper-reported numbers need
citations; unknown is a null value.
Assess whether the missing-information inventory is complete. An empty inventory is allowed only
when completeness is supported as complete; otherwise list concrete missing items. Do not put
"No missing information" or "None identified" in that list; represent that claim with an empty
inventory and a supported complete assessment.
Address cost feasibility, temporal/data leakage, and metric comparability in the relevant direction,
assumption, success criterion, missing-information item, or stop/advance rule.

Retrieved source catalog:
{source_catalog}

Corpus context:
{context}

Investigation question:
{question}

JSON Schema:
{schema_json}"""

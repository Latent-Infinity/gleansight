from __future__ import annotations

import json

from papers.domain.ideation import Critique, EvidenceMap, GenerationOutput


def build_generation_prompt(question: str, evidence: EvidenceMap) -> str:
    evidence_json = evidence.model_dump_json(indent=2)
    schema = json.dumps(GenerationOutput.model_json_schema(), sort_keys=True)
    return f"""Create an evidence map and up to six draft investigation ideas.
Return only one JSON object conforming exactly to the supplied JSON Schema. Produce at most three
ideas for this bounded run; zero ideas is valid. Use null for unknown optional values.
Treat quotes as immutable: cite only supplied excerpt IDs and never invent or alter quotations.
Evidence cards must distinguish paper_claim, inference, and unknown across method, data, evaluation,
limitations, counterevidence, and future_work where supported. Do not imply full-paper analysis:
coverage is limited to selected excerpts. Ideas must be source-bound and avoid global novelty
claims.
Each idea needs a gap, mechanism, citations, known overlap, falsifiable question, smallest test,
data/model/compute assumptions, and explicit feasibility uncertainty. This is drafting, not
approval.

Question: {question}

Frozen evidence map:
{evidence_json}

JSON Schema:
{schema}"""


def build_critique_prompt(generation: GenerationOutput, evidence: EvidenceMap) -> str:
    payload = generation.model_dump_json(indent=2)
    evidence_json = evidence.model_dump_json(indent=2)
    schema = json.dumps(Critique.model_json_schema(), sort_keys=True)
    return f"""Independently critique every supplied draft idea exactly once.
Return only one JSON object conforming exactly to the supplied JSON Schema. Use only known idea IDs.
For each idea choose keep, revise, or reject and assess overlap, contradiction, and uncertainty.
Set duplicate_of only for a known earlier or otherwise acyclic canonical idea. Do not claim novelty.
Check every cited claim against the exact frozen excerpts, including contradictions and unsupported
inferences. Treat the excerpt text as evidence and the draft generation as proposals to audit.
Set evidence_excerpt_ids to exact excerpt IDs from the frozen evidence map, or an empty list when no
excerpt supports the critique. Never use evidence-card IDs or invent evidence references.

Frozen evidence map:
{evidence_json}

Draft generation:
{payload}

JSON Schema:
{schema}"""

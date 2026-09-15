from __future__ import annotations

from papers.domain.ideation import Critique, EvidenceMap, GenerationOutput


def render_ideation_report(
    evidence: EvidenceMap, generation: GenerationOutput, critique: Critique
) -> str:
    lines = [
        "# Project Ideation Report",
        "",
        f"**Project:** {evidence.project_name} (`{evidence.project_id}`)",
        f"**Question:** {generation.question}",
        "",
        "## Evidence Coverage",
        "",
        evidence.coverage_note,
    ]
    for paper in evidence.inventory:
        status = "missing" if paper.markdown_missing else "partial" if paper.partial else "complete"
        lines.append(
            f"- `{paper.paper_id}` {paper.title}: {status}; "
            f"selected {paper.selected_bytes}/{paper.markdown_bytes} bytes"
        )
    lines.extend(["", "## Evidence Cards"])
    for card in generation.evidence_cards:
        statement = card.statement or "Unknown"
        refs = ", ".join(card.excerpt_ids) or "none"
        uncertainty = f" Uncertainty: {card.uncertainty}" if card.uncertainty else ""
        lines.append(
            f"- `{card.card_id}` [{card.category.value}/{card.claim_kind.value}] "
            f"{statement} (excerpts: {refs}).{uncertainty}"
        )
    lines.extend(["", "## Draft Ideas"])
    if not generation.ideas:
        lines.append("No source-bound draft ideas were produced.")
    reviews = {review.idea_id: review for review in critique.reviews}
    for idea in generation.ideas:
        review = reviews[idea.idea_id]
        lines.extend(
            [
                "",
                f"### {idea.title} (`{idea.idea_id}`)",
                f"- Gap: {idea.gap}",
                f"- Mechanism: {idea.mechanism}",
                f"- Evidence: {', '.join(idea.citation_excerpt_ids)}",
                f"- Known overlap: {idea.known_overlap or 'Unknown from supplied excerpts'}",
                f"- Falsifiable question: {idea.falsifiable_question}",
                f"- Smallest test: {idea.smallest_test}",
                f"- Data assumptions: {idea.data_assumptions or 'Unknown'}",
                f"- Model assumptions: {idea.model_assumptions or 'Unknown'}",
                f"- Compute assumptions: {idea.compute_assumptions or 'Unknown'}",
                f"- Feasibility uncertainty: {idea.feasibility_uncertainty}",
                f"- Critic verdict: `{review.verdict.value}` - {review.rationale}",
                f"- Critic overlap: {review.overlap or 'None identified from supplied evidence'}",
                f"- Critic contradiction: {review.contradiction or 'None identified'}",
                f"- Critic uncertainty: {review.uncertainty}",
                f"- Critic evidence: {', '.join(review.evidence_excerpt_ids) or 'none'}",
                f"- Duplicate of: {review.duplicate_of or 'none'}",
            ]
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "This report uses bounded excerpts, not full-text review or an exhaustive "
            "literature search. Ideas are drafts, critic verdicts are advisory, and neither "
            "constitutes human approval.",
        ]
    )
    return "\n".join(lines) + "\n"

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from papers.domain.ideation import EvidenceExcerpt, EvidenceMap, PaperInventory

_HEADING: Final = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")


def build_evidence_map(
    project_id: str,
    project_name: str,
    paper_ids: Sequence[str],
    papers: Mapping[str, tuple[str, Path | None]],
    *,
    excerpt_bytes: int,
    max_excerpts_per_paper: int,
) -> EvidenceMap:
    inventory: list[PaperInventory] = []
    excerpts: list[EvidenceExcerpt] = []
    for paper_id in paper_ids:
        title, path = papers[paper_id]
        if path is None or not path.exists():
            inventory.append(
                PaperInventory(
                    paper_id=paper_id,
                    title=title,
                    markdown_missing=True,
                    partial=False,
                    markdown_bytes=0,
                    selected_bytes=0,
                    selected_excerpt_ids=(),
                )
            )
            continue
        markdown = path.read_text()
        markdown_bytes = len(markdown.encode())
        selected = _section_excerpts(markdown, excerpt_bytes, max_excerpts_per_paper)
        paper_excerpts: list[EvidenceExcerpt] = []
        for index, (section, start, end, quote) in enumerate(selected, start=1):
            excerpt_id = f"{paper_id}:e{index:03d}"
            quote_bytes = quote.encode()
            paper_excerpts.append(
                EvidenceExcerpt(
                    excerpt_id=excerpt_id,
                    paper_id=paper_id,
                    title=title,
                    section=section,
                    byte_start=start,
                    byte_end=end,
                    sha256=hashlib.sha256(quote_bytes).hexdigest(),
                    quote=quote,
                )
            )
        excerpts.extend(paper_excerpts)
        selected_bytes = sum(len(excerpt.quote.encode()) for excerpt in paper_excerpts)
        inventory.append(
            PaperInventory(
                paper_id=paper_id,
                title=title,
                markdown_missing=False,
                partial=selected_bytes < markdown_bytes,
                markdown_bytes=markdown_bytes,
                selected_bytes=selected_bytes,
                selected_excerpt_ids=tuple(excerpt.excerpt_id for excerpt in paper_excerpts),
            )
        )
    return EvidenceMap(
        project_id=project_id,
        project_name=project_name,
        inventory=tuple(inventory),
        excerpts=tuple(excerpts),
        coverage_note=(
            "Only selected excerpts, chosen section-by-section, were supplied to the model; "
            "entries "
            "marked partial were not analyzed in full, and missing Markdown was not analyzed."
        ),
    )


def _section_excerpts(
    markdown: str, excerpt_bytes: int, maximum: int
) -> list[tuple[str, int, int, str]]:
    headings = list(_HEADING.finditer(markdown))
    sections: list[tuple[str, int, int]] = []
    if headings and headings[0].start() > 0:
        sections.append(("Preamble", 0, headings[0].start()))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        sections.append((heading.group(1).strip(), heading.end(), end))
    if not headings:
        sections.append(("Document", 0, len(markdown)))
    selected: list[tuple[str, int, int, str]] = []
    for section, char_start, char_end in sections:
        raw = markdown[char_start:char_end]
        leading = len(raw) - len(raw.lstrip())
        quote = raw.lstrip().rstrip()
        if not quote:
            continue
        quote = _truncate_utf8(quote, excerpt_bytes)
        exact_start = char_start + leading
        byte_start = len(markdown[:exact_start].encode())
        byte_end = byte_start + len(quote.encode())
        selected.append((section, byte_start, byte_end, quote))
        if len(selected) == maximum:
            break
    return selected


def _truncate_utf8(value: str, maximum_bytes: int) -> str:
    encoded = value.encode()
    if len(encoded) <= maximum_bytes:
        return value
    return encoded[:maximum_bytes].decode(errors="ignore").rstrip()

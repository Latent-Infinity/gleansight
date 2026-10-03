"""Render metadata without guessing absent fields or author name structure."""

import csv
import io
import json
import re
from typing import assert_never

from papers.domain.citations import Citation, ExportFormat, ExtractionRow


def _tex(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in " ".join(value.splitlines()))


def render(
    papers: tuple[Citation, ...], format: ExportFormat, extractions: tuple[ExtractionRow, ...]
) -> tuple[str, str]:
    match format:
        case "bibtex":
            entries = []
            for paper in papers:
                key = "paper" + paper.paper_id.encode("utf-8").hex()
                fields = [
                    ("title", paper.title),
                    ("year", str(paper.year) if paper.year else None),
                    ("journal", paper.venue),
                    ("doi", paper.doi),
                    ("ids", paper.paper_id),
                ]
                rows = [f"  {name} = {{{_tex(value)}}}" for name, value in fields if value]
                if paper.authors:
                    authors = " and ".join("{" + _tex(author) + "}" for author in paper.authors)
                    rows.append(f"  author = {{{authors}}}")
                entries.append("@misc{" + key + ",\n" + ",\n".join(rows) + "\n}")
            return "\n\n".join(entries) + "\n", "bib"
        case "ris":
            entries = []
            for paper in papers:
                fields = [
                    ("TY", "GEN"),
                    ("ID", paper.paper_id),
                    ("TI", paper.title),
                    *(("AU", author) for author in paper.authors),
                    ("PY", str(paper.year) if paper.year else None),
                    ("JO", paper.venue),
                    ("DO", paper.doi),
                ]
                rows = [f"{tag}  - {re.sub(r'\s+', ' ', value)}" for tag, value in fields if value]
                entries.append("\n".join([*rows, "ER  - "]))
            return "\n\n".join(entries) + "\n", "ris"
        case "csv":
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["paper_id", "title", "authors", "year", "venue", "doi"])
            for paper in papers:
                writer.writerow(
                    [
                        paper.paper_id,
                        paper.title,
                        json.dumps(paper.authors, ensure_ascii=False),
                        paper.year,
                        paper.venue,
                        paper.doi,
                    ]
                )
            return output.getvalue(), "csv"
        case "extractions":
            return json.dumps(
                [row.model_dump(mode="json") for row in extractions], ensure_ascii=False, indent=2
            ) + "\n", "json"
        case unreachable:
            assert_never(unreachable)

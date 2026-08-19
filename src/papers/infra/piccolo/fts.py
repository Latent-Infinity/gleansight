from __future__ import annotations


def literal_fts_query(query: str) -> str:
    """Encode whitespace-delimited user terms as literal FTS5 tokens."""
    terms = []
    for term in query.split():
        escaped = term.replace('"', '""')
        terms.append(f'"{escaped}"')
    return " ".join(terms)

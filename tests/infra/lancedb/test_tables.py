from __future__ import annotations

from dataclasses import dataclass

import pytest

from papers.infra.lancedb.tables import table_exists


@dataclass(frozen=True)
class _Page:
    tables: list[str]
    page_token: str | None


class _Catalog:
    def __init__(self) -> None:
        self.tokens: list[str | None] = []

    def list_tables(self, *, page_token: str | None = None) -> _Page:
        self.tokens.append(page_token)
        if page_token is None:
            return _Page(["first"], "next")
        return _Page(["last"], None)


@pytest.mark.parametrize(
    "name, expected, tokens",
    [
        ("first", True, [None]),
        ("last", True, [None, "next"]),
        ("absent", False, [None, "next"]),
    ],
)
def test_catalog_lookup_checks_all_pages(
    name: str, expected: bool, tokens: list[str | None]
) -> None:
    catalog = _Catalog()
    assert table_exists(catalog, name) is expected
    assert catalog.tokens == tokens


def test_catalog_lookup_propagates_io_errors() -> None:
    class FailingCatalog:
        def list_tables(self, *, page_token: str | None = None) -> _Page:
            raise OSError("catalog is unreadable")

    with pytest.raises(OSError, match="unreadable"):
        table_exists(FailingCatalog(), "absent")

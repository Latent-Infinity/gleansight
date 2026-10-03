from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class MissingTableError(LookupError):
    pass


class _TablePage(Protocol):
    @property
    def tables(self) -> Sequence[str]: ...

    @property
    def page_token(self) -> str | None: ...


class _TableCatalog(Protocol):
    def list_tables(self, *, page_token: str | None = None) -> _TablePage: ...


def table_exists(catalog: _TableCatalog, name: str) -> bool:
    token: str | None = None
    while True:
        page = catalog.list_tables(page_token=token)
        if name in page.tables:
            return True
        token = page.page_token
        if token is None:
            return False

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile

from research.catalog.comparison import compare_runs
from research.catalog.models import CatalogError, CatalogItem, RunComparison, VerifiedRun
from research.catalog.store import CatalogStore, StoredRun
from research.catalog.verify import verify_bundle


@dataclass(frozen=True, slots=True)
class ResearchCatalog:
    store: CatalogStore
    repo_root: Path

    def resolve(self, path: Path) -> Path:
        requested = path if path.is_absolute() else self.repo_root / path
        resolved = requested.resolve()
        if requested.is_symlink() or not resolved.is_relative_to(
            (self.repo_root / "output").resolve()
        ):
            raise CatalogError(
                "Select an owned research bundle under this workspace's output directory"
            )
        return resolved

    def verify(self, path: Path) -> CatalogItem:
        resolved = self.resolve(path)
        record = verify_bundle(resolved)
        return CatalogItem(
            run_id=record.run_id,
            bundle_path=str(resolved.relative_to(self.repo_root.resolve())),
            verified=True,
            record=record,
        )

    def index(self, path: Path) -> CatalogItem:
        item = self.verify(path)
        if item.record is None:
            raise CatalogError("Only a verified record may be indexed")
        self.store.put(item.bundle_path, item.record)
        return item

    def _current(self, stored: StoredRun) -> VerifiedRun:
        record = verify_bundle(self.resolve(Path(stored.bundle_path)))
        if record != stored.record or record.run_id != stored.run_id:
            raise CatalogError(
                "Indexed research bundle identity changed; explicitly reindex the new artifact"
            )
        return record

    def list(self, *, limit: int = 50, offset: int = 0) -> tuple[CatalogItem, ...]:
        items: list[CatalogItem] = []
        for stored in self.store.list(limit=limit, offset=offset):
            try:
                record = self._current(stored)
                items.append(
                    CatalogItem(
                        run_id=stored.run_id,
                        bundle_path=stored.bundle_path,
                        verified=True,
                        record=record,
                    )
                )
            except (ValueError, OSError, BadZipFile) as exc:
                items.append(
                    CatalogItem(
                        run_id=stored.run_id,
                        bundle_path=stored.bundle_path,
                        verified=False,
                        record=None,
                        problem=str(exc),
                    )
                )
        return tuple(items)

    def compare(self, run_ids: tuple[str, ...]) -> RunComparison:
        if not 2 <= len(run_ids) <= 10 or len(set(run_ids)) != len(run_ids):
            raise CatalogError("Choose 2 to 10 distinct indexed research runs")
        return compare_runs(tuple(self._current(self.store.get(run_id)) for run_id in run_ids))

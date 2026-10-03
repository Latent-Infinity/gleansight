from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from papers.infra.piccolo.database import PiccoloDatabase
from research.catalog.service import ResearchCatalog
from research.catalog.store import CatalogStore
from research.catalog.verify import verify_bundle
from tests.research.test_financial_jepa_diagnostics import _run_bundle


def controlled_bundle(root: Path, name: str) -> Path:
    with TemporaryDirectory(prefix="gleansight-catalog-controlled-") as directory:
        source = _run_bundle(Path(directory).resolve())
        destination = root / "output/financial-jepa-diagnostics" / name
        shutil.copytree(source, destination)
    return destination


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    return controlled_bundle(tmp_path, "controlled-a"), controlled_bundle(tmp_path, "controlled-b")


def catalog(root: Path) -> ResearchCatalog:
    return ResearchCatalog(CatalogStore(PiccoloDatabase(root / "papers.sqlite")), root)


def test_actual_controlled_runs_preserve_pairing_and_compare_without_winner(
    tmp_path: Path, pair: tuple[Path, Path]
) -> None:
    first, second = (catalog(tmp_path).index(path) for path in pair)
    result = catalog(tmp_path).compare((first.run_id, second.run_id))
    assert result.comparable
    assert result.winner is None
    assert result.runs[0].classification == "smoke"
    assert result.runs[0].verification == "reconstructed_forecasts"
    assert result.runs[0].origin_dates == result.runs[1].origin_dates
    assert result.runs[0].target_dates == result.runs[1].target_dates
    assert result.runs[0].seeds == result.runs[1].seeds == (17,)
    assert result.pairs and all(row.seed in (17, None) for row in result.pairs)
    assert result.runs[0].metrics[0].definition.unit == "basis_points"
    assert len(catalog(tmp_path).list()) == 2
    assert catalog(tmp_path).index(pair[0]).run_id == first.run_id


def test_stale_index_cannot_compare_and_source_artifacts_are_not_rewritten(
    tmp_path: Path, pair: tuple[Path, Path]
) -> None:
    original = {path.name: path.read_bytes() for path in pair[0].iterdir()}
    first, second = (catalog(tmp_path).index(path) for path in pair)
    catalog(tmp_path).compare((first.run_id, second.run_id))
    assert {path.name: path.read_bytes() for path in pair[0].iterdir()} == original
    (pair[0] / "results.json").write_text("{}")
    with pytest.raises(ValueError):
        catalog(tmp_path).compare((first.run_id, second.run_id))
    listed = catalog(tmp_path).list()
    assert sum(item.verified for item in listed) == 1
    assert any(item.problem for item in listed)
    with pytest.raises(ValueError):
        verify_bundle(pair[0])


def test_catalog_integrity_error_survives_resource_context_unwinding() -> None:
    from collections.abc import Iterator
    from contextlib import contextmanager

    from research.catalog.models import CatalogError

    @contextmanager
    def resource() -> Iterator[None]:
        yield

    with pytest.raises(CatalogError, match="changed"):
        with resource():
            raise CatalogError("changed")

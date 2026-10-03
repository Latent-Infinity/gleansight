from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from research.financial_jepa.contracts import Deadline, ExperimentConfig, YieldRow
from research.financial_jepa.dataset import prepare_splits
from research.financial_jepa.experiment import ExperimentRequest, run_prepared_experiment
from tests.research.test_financial_jepa_diagnostics import _rows, _source


def baseline_bundle(root: Path) -> Path:
    config = ExperimentConfig.synthetic(
        context_length=3, future_length=2, batch_size=2, epochs=1
    ).model_copy(
        update={
            "context_length": 3,
            "future_length": 2,
            "epochs": 1,
            "seeds": (17,),
            "batch_size": 2,
            "deadline_seconds": 60.0,
        }
    )
    existing = _rows()
    test = tuple(
        YieldRow(row.observed_on.replace(year=2022), row.yields, False)
        for row in existing
        if row.observed_on.year == 2017
    )
    prepared = prepare_splits((*existing, *test), config)
    with TemporaryDirectory(prefix="gleansight-catalog-baseline-") as directory:
        source = run_prepared_experiment(
            ExperimentRequest(
                Path(__file__).resolve().parents[2],
                Path(directory).resolve() / "baseline",
                config,
                prepared,
                _source(),
                Deadline.start(60.0),
            )
        )
        destination = root / "output/financial-jepa/synthetic-baseline"
        shutil.copytree(source, destination)
    return destination

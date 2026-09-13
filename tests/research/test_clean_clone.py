from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_source_clone_without_agent_goal_runs_nine_fits_with_protocol_identity(
    tmp_path: Path,
) -> None:
    clone = tmp_path / "clone"
    shutil.copytree(REPO_ROOT / "src/research", clone / "src/research")
    shutil.copytree(REPO_ROOT / "src/nsqd", clone / "src/nsqd")
    (clone / "scripts").mkdir()
    shutil.copy2(REPO_ROOT / "scripts/run_financial_jepa.py", clone / "scripts")
    shutil.copy2(REPO_ROOT / "uv.lock", clone)
    assert not (clone / ".omo").exists()
    driver = textwrap.dedent(
        """
        from datetime import date, timedelta
        from pathlib import Path
        from research.financial_jepa.contracts import Deadline, ExperimentConfig, YieldRow
        from research.financial_jepa.dataset import prepare_splits
        from research.financial_jepa.experiment import ExperimentRequest, run_prepared_experiment

        def curve(level: float) -> tuple[float, float, float, float, float, float, float, float]:
            return tuple(level + 0.05 * index for index in range(8))

        repo = Path.cwd()
        config = ExperimentConfig.synthetic(
            context_length=3, future_length=2, batch_size=2, epochs=1
        )
        rows = tuple(
            YieldRow(date(year, 1, 1) + timedelta(days=index), curve(base + 0.03 * index), False)
            for year, base in ((2017, 1.0), (2018, 2.0), (2022, 3.0))
            for index in range(22)
        )
        run_prepared_experiment(
            ExperimentRequest(
                repo,
                repo / "output/financial-jepa/clean-clone",
                config,
                prepare_splits(rows, config),
                {"fixture": "clean_clone_synthetic_test_only"},
                Deadline.start(60.0),
            )
        )
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=clone,
        env={**os.environ, "PYTHONPATH": str(clone / "src"), "UV_NO_SYNC": "1"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    output = clone / "output/financial-jepa/clean-clone"
    results = json.loads((output / "results.json").read_text())
    protocol = json.loads((output / "protocol.json").read_text())
    metadata = json.loads((output / "run-metadata.json").read_text())
    assert len(results["fits"]) == 9
    assert protocol["protocol_version"] == "yield-jepa/1"
    assert metadata["frozen_protocol_identity"] == {
        "protocol_version": "yield-jepa/1",
        "protocol_sha256": metadata["protocol_sha256"],
    }
    expected_code_files = {
        path.relative_to(clone).as_posix()
        for path in (clone / "src/research/financial_jepa").glob("*.py")
    } | {"scripts/run_financial_jepa.py", "uv.lock"}
    assert set(metadata["code_identity"]["files"]) == expected_code_files

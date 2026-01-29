from __future__ import annotations

from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloAnalysisRunStore


def test_mark_started_and_finished(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "analysis.sqlite")
    db.initialize_schema()
    store = PiccoloAnalysisRunStore()
    store.create_run("run", "paper", "prompt", "profile", "model")
    store.mark_started("run")
    store.mark_finished(
        "run",
        output_md="/tmp/output.md",
        output_json=None,
        validation_issues_json=None,
        error_message=None,
        tokens_in=1,
        tokens_out=2,
        cost_usd=0.1,
    )
    row = db.fetchone("SELECT * FROM analysis_runs WHERE run_id = ?", ["run"])
    assert row is not None
    assert row["output_blob_path_md"] == "/tmp/output.md"

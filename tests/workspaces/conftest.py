import json
from pathlib import Path

import pytest

from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloPaperProjectStore,
    PiccoloPaperStore,
    PiccoloProjectStore,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    runtime = ApiRuntime(ApiConfiguration(repo_root=root))
    db = runtime.paper_database
    PiccoloPaperStore().create_paper({"paper_id": "paper-1", "title": "Preserved research"})
    blobs = FileSystemBlobStore(runtime.settings.data.blobs_dir)
    _, fingerprint = blobs.put_markdown("paper-1", "# Source evidence\nUnicode 研究")
    db.execute(
        "UPDATE papers SET md_fingerprint_xxh64 = ? WHERE paper_id = ?", [fingerprint, "paper-1"]
    )
    PiccoloProjectStore().create_project("project-1", "Preserved cohort")
    PiccoloPaperProjectStore().attach("paper-1", "project-1")
    runs = PiccoloAnalysisRunStore()
    runs.create_run("run-1", "paper-1", "prompt-1", "profile", "model")
    paths = blobs.put_analysis_artifacts("run-1", "# Answer", {"score": 1}, {"model": "model"})
    runs.mark_finished(
        "run-1", output_md=str(paths["output_md"]), output_json=str(paths["output_json"])
    )
    runtime.nsqd_db.parent.mkdir(parents=True)
    nsqd = PiccoloDatabase(runtime.nsqd_db, bind_on_init=False)
    nsqd.initialize_schema()
    nsqd.execute(
        "INSERT INTO nsqd_corpus_records (record_id, payload_json) VALUES (?, ?)",
        [
            "record-1",
            json.dumps(
                {
                    "domain_policy_id": "finance/1",
                    "paper_id": "paper-1",
                    "source_path": "evidence/source.md",
                }
            ),
        ],
    )
    nsqd.execute(
        "INSERT INTO nsqd_approved_projection_digests VALUES (?, ?)",
        ["a" * 64, "2026-10-03T00:00:00+00:00"],
    )
    (root / "evidence").mkdir()
    (root / "evidence" / "source.md").write_text("Approved evidence bytes\n")
    (root / ".env").write_text("PROVIDER_API_KEY=never-copy-me\n")
    (root / "data" / "blobs" / ".env").write_text("SECRET=never-copy-me\n")
    return root

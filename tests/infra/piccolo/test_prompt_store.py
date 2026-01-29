from __future__ import annotations

from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloPromptStore


def test_prompt_version_latest(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "prompt.sqlite")
    db.initialize_schema()
    store = PiccoloPromptStore()
    store.create_prompt("prompt", "Prompt")
    store.create_version("pv1", "prompt", 1, "body1", "markdown_only")
    store.create_version("pv2", "prompt", 2, "body2", "markdown_only")
    latest = store.get_latest_version("prompt")
    assert latest is not None
    assert latest["prompt_version_id"] == "pv2"

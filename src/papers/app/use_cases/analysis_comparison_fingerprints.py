from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from papers.app.use_cases.analysis_comparison_artifacts import bounded_text
from papers.domain.analysis_comparison import RunInspection


def fingerprint(run: RunInspection, version: Literal[1, 2]) -> str:
    if version == 1:
        return hashlib.sha256(run.model_dump_json().encode()).hexdigest()
    semantic = run.model_dump(mode="json", exclude={"output_md": {"path"}, "output_json": {"path"}})
    metadata = {
        name: hashlib.sha256(
            bounded_text(Path(artifact.path).parent / "meta.json").encode()
        ).hexdigest()
        if artifact.path is not None and artifact.state in {"available", "empty"}
        else None
        for name, artifact in (("output_md", run.output_md), ("output_json", run.output_json))
    }
    document = {"version": 2, "inspection": semantic, "metadata_sha256": metadata}
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()

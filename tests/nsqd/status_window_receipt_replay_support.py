from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import cast

from nsqd.domain.snapshot import canonical_json, sha256_hex
from nsqd.domain.status import STATUS_WINDOW_DAYS
from nsqd.domain.status_window_replay import (
    BOUNDARY_SENSITIVITY_SCENARIO_NOTE,
    CURRENT_AS_OF_SCENARIO_NOTE,
    PROVENANCE_CAVEAT,
    SEALED_AT_UTC,
    STATUS_WINDOW_REPLAY_PACKET_KIND,
    compare_status_window_semantics,
    status_window_replay_artifact_digest,
)

HARVESTED_AT = "2026-09-02T06:45:00+00:00"
REPO_ROOT = Path(__file__).resolve().parents[2]
SEALED_ARTIFACT_PATH = (
    REPO_ROOT
    / "docs"
    / "reviews"
    / "nsqd-status-window-calendar-replay-2026-09-02"
    / "calendar-replay-artifact.json"
)


def _records() -> list[dict[str, object]]:
    artifact = json.loads(SEALED_ARTIFACT_PATH.read_text(encoding="utf-8"))
    return cast(list[dict[str, object]], artifact["extracted_records"])


def _artifact(*, current_as_of: datetime, boundary_as_of: datetime) -> dict[str, object]:
    records = _records()
    report = {
        "schema_version": 1,
        "packet_kind": STATUS_WINDOW_REPLAY_PACKET_KIND,
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "evidence_sufficient": True,
        "evidence_sufficient_scope": "human_decision_only",
        "runtime_status_window_days": STATUS_WINDOW_DAYS,
        "sealed_at_utc": SEALED_AT_UTC,
        "harvested_at_provenance_caveat": PROVENANCE_CAVEAT,
        "extracted_records_digest": sha256_hex(canonical_json(records)),
        "source_receipt": {
            "snapshot_id": "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5",
            "corpus_version": 11,
            "record_count": 11,
            "sqlite_sha256": "ab339287d8e9fcea662a1b8cb9557302bde356573cb4834a9b374a4cd375a2b7",
            "harvested_at_utc": HARVESTED_AT,
            "receipt_verified_exact": True,
        },
        "extracted_records": records,
        "scenarios": [
            {
                "scenario_id": "current_as_of",
                "scenario_kind": "observed_current_as_of",
                "as_of_utc": current_as_of.isoformat(),
                "scenario_note": CURRENT_AS_OF_SCENARIO_NOTE,
                "policy_results": {
                    "finance/1": compare_status_window_semantics(
                        records,
                        domain_policy_id="finance/1",
                        as_of=current_as_of,
                        snapshot_state="production_valid",
                    ),
                    "optimization/1": compare_status_window_semantics(
                        records,
                        domain_policy_id="optimization/1",
                        as_of=current_as_of,
                        snapshot_state="production_valid",
                    ),
                },
            },
            {
                "scenario_id": "boundary_sensitivity",
                "scenario_kind": "boundary_sensitivity",
                "as_of_utc": boundary_as_of.isoformat(),
                "scenario_note": BOUNDARY_SENSITIVITY_SCENARIO_NOTE,
                "policy_results": {
                    "finance/1": compare_status_window_semantics(
                        records,
                        domain_policy_id="finance/1",
                        as_of=boundary_as_of,
                        snapshot_state="production_valid",
                    ),
                    "optimization/1": compare_status_window_semantics(
                        records,
                        domain_policy_id="optimization/1",
                        as_of=boundary_as_of,
                        snapshot_state="production_valid",
                    ),
                },
            },
        ],
    }
    report["artifact_digest"] = status_window_replay_artifact_digest(report)
    return report


def _load_replay_module():
    spec = importlib.util.spec_from_file_location(
        "status_window_replay_script", REPO_ROOT / "scripts" / "replay_status_window_ablation.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("expected replay script spec with loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

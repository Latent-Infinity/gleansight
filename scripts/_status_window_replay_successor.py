from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def build_successor_metadata(artifact_bytes: Mapping[str, bytes]) -> tuple[bytes, bytes]:
    succession = {
        "schema_version": 1,
        "packet_kind": "status_window_command_sync_succession",
        "review_status": "review_pending",
        "predecessor": {
            "path": "../nsqd-status-window-calendar-replay-2026-09-02",
            "packet_digest": "f81a9eed5d12f12a77d7252e234ff7a1e409ebb8a6d32bb709f0980e5b95ffd4",
        },
        "prior_summary_validity": "valid_for_predecessor_evidence_bytes_only",
        "authorization_state": "report_only",
        "runtime_authorized": False,
    }
    succession_bytes = (json.dumps(succession, indent=2, sort_keys=True) + "\n").encode("utf-8")
    artifacts = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in (*artifact_bytes.items(), ("succession.json", succession_bytes))
    }
    manifest = {
        "schema_version": 1,
        "artifact_sha256": artifacts,
        "packet_digest": hashlib.sha256(
            json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return succession_bytes, manifest_bytes

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Final, Literal, assert_never

import pytest

from nsqd.domain.artifact_paths import resolve_artifact_path
from nsqd.domain.operator_g_types import StructuredValue
from tests.nsqd.test_operator_f_full_binding_successor import (
    F_SOURCE_PATHS,
    FORMULAS,
    REPO_ROOT,
    _assert_manifest_replays,
    _json,
    _sha256,
    _transitive_local_import_closure,
)

SOURCE: Final = "tests/nsqd/test_operator_f_metric_redundancy_semantics.py"
HISTORICAL_SOURCE: Final = (
    "tests/fixtures/source-history/nsqd/operator-f/redundancy-semantics-2026-09-12.py.txt"
)
OLD_SHA: Final = "3b369b478ccdc2f04cc49607563d13d8b5a4341b9d9927079e09c81baba8e688"
NEW_SHA: Final = "862128854feedeaec5a3b842038c7fbb5bd3b076cbc10ee4260309b5202cdee9"
PREDECESSOR: Final = (
    "evidence/archive/reviews/v1/"
    "nsqd-operator-f-readiness-2026-09-12-implementation-binding/packet-manifest.json"
)
PREDECESSOR_SHA: Final = "7aefc06baace0604ca994eecaae04c1508aae9487ff64d1aa1fbfcef446fc245"
PREDECESSOR_DIGEST: Final = "e82490162af6f8da4507aef5cfe019869a2caecdaa3cf985a0751e794c8d62fe"
ARTIFACTS: Final = {
    "readiness.json",
    "historical-source-bindings.json",
    "predecessor-redundancy-test.py.txt",
}


def validate_typing_binding_packet(repo_root: Path, packet_root: Path) -> None:
    """Assert historical and current artifact bindings using explicit filesystem roots."""
    assert {path.name for path in packet_root.iterdir()} == ARTIFACTS | {"packet-manifest.json"}
    manifest = _assert_manifest_replays(packet_root)
    assert set(manifest) == {"schema_version", "artifact_sha256", "packet_digest"}
    assert manifest["schema_version"] == 1
    predecessor_path = resolve_artifact_path(repo_root, Path(PREDECESSOR))
    assert _sha256(predecessor_path) == PREDECESSOR_SHA
    assert _assert_manifest_replays(predecessor_path.parent)["packet_digest"] == PREDECESSOR_DIGEST
    previous = _json(predecessor_path.parent / "readiness.json")
    readiness = _json(packet_root / "readiness.json")
    history = _json(packet_root / "historical-source-bindings.json")
    assert set(readiness) == set(previous)
    assert readiness["predecessor"] == {
        "manifest": PREDECESSOR,
        "manifest_sha256": PREDECESSOR_SHA,
        "packet_digest": PREDECESSOR_DIGEST,
        "review_validity": "valid_for_predecessor_only",
    }
    for field in ("schema_version", "packet_kind", "proposal_id", "approval_scope"):
        assert readiness[field] == previous[field]
    assert readiness["review_status"] == "review_pending"
    assert readiness["authorization_state"] == "report_only"
    assert readiness["trust_evidence"] == "absent"
    assert (
        readiness["approved_non_authorizing_formulas"]
        == previous["approved_non_authorizing_formulas"]
        == FORMULAS
    )
    authority = readiness["authority"]
    assert isinstance(authority, dict)
    assert authority == previous["authority"] and all(flag is False for flag in authority.values())
    old = previous["source_bindings"]
    current = readiness["source_bindings"]
    historical = history["source_bindings"]
    assert history == {
        "schema_version": 1,
        "predecessor_packet_digest": PREDECESSOR_DIGEST,
        "predecessor_manifest_sha256": PREDECESSOR_SHA,
        "source_bindings": historical,
    }
    assert isinstance(old, list) and isinstance(current, list) and isinstance(historical, list)
    assert len(old) == len(current) == len(historical) == 18
    bound_paths: set[str] = set()
    for before, after, preserved in zip(old, current, historical, strict=True):
        assert isinstance(before, dict) and isinstance(after, dict)
        path = before["path"]
        assert isinstance(path, str)
        bound_paths.add(path)
        changed = path == SOURCE
        assert after == {**before, "sha256": NEW_SHA if changed else before["sha256"]}
        assert preserved == {**before, "preserved_source": HISTORICAL_SOURCE if changed else None}
        assert _sha256(repo_root / path) == after["sha256"]
        assert not changed or before["sha256"] == OLD_SHA
    assert bound_paths == F_SOURCE_PATHS == _transitive_local_import_closure(bound_paths, repo_root)
    fixture = repo_root / HISTORICAL_SOURCE
    assert _sha256(fixture) == OLD_SHA
    assert (packet_root / "predecessor-redundancy-test.py.txt").read_bytes() == fixture.read_bytes()


def _write_json(path: Path, value: StructuredValue) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _seal_test_packet(packet_root: Path) -> None:
    artifacts: dict[str, StructuredValue] = {
        name: _sha256(packet_root / name) for name in sorted(ARTIFACTS)
    }
    _write_json(
        packet_root / "packet-manifest.json",
        {
            "schema_version": 1,
            "artifact_sha256": artifacts,
            "packet_digest": hashlib.sha256(
                json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        },
    )


@pytest.fixture
def packet(tmp_path: Path) -> Path:
    previous = _json(REPO_ROOT / Path(PREDECESSOR).parent / "readiness.json")
    rows = previous["source_bindings"]
    assert isinstance(rows, list)
    bindings: list[StructuredValue] = []
    history: list[StructuredValue] = []
    for row in rows:
        assert isinstance(row, dict)
        changed = row["path"] == SOURCE
        bindings.append({**row, "sha256": NEW_SHA if changed else row["sha256"]})
        history.append({**row, "preserved_source": HISTORICAL_SOURCE if changed else None})
    previous["created_at_utc"] = "2026-10-03T02:46:20Z"
    previous["source_bindings"] = bindings
    previous["predecessor"] = {
        "manifest": PREDECESSOR,
        "manifest_sha256": PREDECESSOR_SHA,
        "packet_digest": PREDECESSOR_DIGEST,
        "review_validity": "valid_for_predecessor_only",
    }
    packet_root = tmp_path / "packet"
    packet_root.mkdir()
    _write_json(packet_root / "readiness.json", previous)
    _write_json(
        packet_root / "historical-source-bindings.json",
        {
            "schema_version": 1,
            "predecessor_packet_digest": PREDECESSOR_DIGEST,
            "predecessor_manifest_sha256": PREDECESSOR_SHA,
            "source_bindings": history,
        },
    )
    shutil.copyfile(
        REPO_ROOT / HISTORICAL_SOURCE, packet_root / "predecessor-redundancy-test.py.txt"
    )
    _seal_test_packet(packet_root)
    return packet_root


def test_current_packet_binds_all_sources_and_preserved_history(packet: Path) -> None:
    validate_typing_binding_packet(REPO_ROOT, packet)


@pytest.mark.parametrize(
    ("filename", "keys", "replacement"),
    [
        ("readiness.json", "source_bindings.17.sha256", OLD_SHA),
        ("readiness.json", "source_bindings.0.role", "forged_role"),
        ("readiness.json", "source_bindings.0.sha256", "0" * 64),
        ("historical-source-bindings.json", "source_bindings.17.sha256", NEW_SHA),
        ("historical-source-bindings.json", "source_bindings.17.preserved_source", SOURCE),
        (
            "historical-source-bindings.json",
            "source_bindings.0.preserved_source",
            HISTORICAL_SOURCE,
        ),
        ("historical-source-bindings.json", "predecessor_packet_digest", "0" * 64),
        ("historical-source-bindings.json", "predecessor_manifest_sha256", "0" * 64),
        ("readiness.json", "predecessor.manifest", "docs/reviews/forged/packet-manifest.json"),
        ("readiness.json", "predecessor.manifest_sha256", "0" * 64),
        ("readiness.json", "predecessor.packet_digest", "0" * 64),
        ("readiness.json", "predecessor.review_validity", "valid_for_successor"),
        (
            "readiness.json",
            "approved_non_authorizing_formulas.redundancy_with_existing_axes",
            "refit_held_out",
        ),
        ("readiness.json", "review_status", "approved"),
        ("readiness.json", "authorization_state", "authorized"),
        ("readiness.json", "approval_scope", "runtime_activation"),
        ("readiness.json", "trust_evidence", "present"),
        ("readiness.json", "authority.runtime_authorized", True),
        ("readiness.json", "authority.evidence_sufficient", True),
        ("readiness.json", "authority.schema_admission_authorized", True),
    ],
)
def test_resealed_semantic_tampering_is_rejected(
    packet: Path,
    filename: str,
    keys: str,
    replacement: StructuredValue,
) -> None:
    value = _json(packet / filename)
    target: StructuredValue = value
    for key in keys.split(".")[:-1]:
        match target:
            case dict():
                target = target[key]
            case list():
                target = target[int(key)]
            case _:
                pytest.fail("tamper target must be a JSON container")
    assert isinstance(target, dict)
    target[keys.rsplit(".", 1)[-1]] = replacement
    _write_json(packet / filename, value)
    _seal_test_packet(packet)
    with pytest.raises(AssertionError):
        validate_typing_binding_packet(REPO_ROOT, packet)


@pytest.mark.parametrize("filename", ["readiness.json", "historical-source-bindings.json"])
@pytest.mark.parametrize("change", ["missing", "extra", "duplicate"])
def test_resealed_binding_set_tampering_is_rejected(
    packet: Path,
    filename: str,
    change: Literal["missing", "extra", "duplicate"],
) -> None:
    value = _json(packet / filename)
    rows = value["source_bindings"]
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    match change:
        case "missing":
            rows.pop()
        case "extra":
            rows.append({**rows[0], "path": "src/unbound.py"})
        case "duplicate":
            rows[-1] = rows[0]
        case unreachable:
            assert_never(unreachable)
    _write_json(packet / filename, value)
    _seal_test_packet(packet)
    with pytest.raises(AssertionError):
        validate_typing_binding_packet(REPO_ROOT, packet)


@pytest.mark.parametrize(
    "filename", ["predecessor-redundancy-test.py.txt", "technical-review-seal.json"]
)
def test_snapshot_corruption_or_detached_seal_is_rejected(packet: Path, filename: str) -> None:
    (packet / filename).write_text("forged\n", encoding="utf-8")
    _seal_test_packet(packet)
    with pytest.raises(AssertionError):
        validate_typing_binding_packet(REPO_ROOT, packet)


@pytest.mark.parametrize("path", [SOURCE, HISTORICAL_SOURCE])
def test_changed_repository_bytes_are_rejected(packet: Path, tmp_path: Path, path: str) -> None:
    repo = tmp_path / "repo"
    for name in F_SOURCE_PATHS | {HISTORICAL_SOURCE}:
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / name, destination)
    predecessor = Path(PREDECESSOR).parent
    (repo / predecessor).mkdir(parents=True)
    for name in ("packet-manifest.json", "readiness.json"):
        shutil.copyfile(REPO_ROOT / predecessor / name, repo / predecessor / name)
    validate_typing_binding_packet(repo, packet)
    with (repo / path).open("a", encoding="utf-8") as stream:
        stream.write("\n# corrupted source bytes\n")
    with pytest.raises(AssertionError):
        validate_typing_binding_packet(repo, packet)

from __future__ import annotations

import argparse
import json
import math
import tempfile
import tomllib
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

from nsqd.app.use_cases import DivergeUseCase, GroundUseCase, ProjectPaperUseCase, ScoreUseCase
from nsqd.composition import build_container, build_local_ollama_embedder
from nsqd.domain.operator_baselines import lancedb_tree_digest, verify_scratch_execution_receipt
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.domain.snapshot import canonical_json, sha256_hex
from nsqd.domain.tau_measurement import (
    TAU_MEASUREMENT_ARTIFACT_FIELDS,
    tau_measurement_artifact_digest,
)
from nsqd.domain.trusted_files import (
    load_verified_yaml_mapping,
    read_verified_repo_file,
    sha256_file_digest,
)
from nsqd.null_adapters import FixedClock
from papers.config.settings import load_settings, packaged_defaults_path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKET_DIR = REPO_ROOT / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01"
PROJECTION_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-projection-review-2026-08-28" / "final"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "approved" / "nsqd"
APPROVED_ORDER = [
    "DATA-NSQD-03",
    "N11-FIN-01",
    "N11-FIN-02",
    "N11-FIN-03",
    "N11-FIN-04",
    "N11-FIN-05",
    "N11-OPT-01",
    "N11-OPT-02",
    "N11-OPT-03",
    "N11-OPT-04",
    "N11-OPT-05",
]
SEALED_AT = datetime(2026, 9, 2, 6, 45, tzinfo=UTC)
EXPECTED_MANIFEST_DIGEST = "64b933495768fbd3b87c20583d379728a07471e0c66733a9df87cd1901b3c44b"
EXPECTED_BLOB_DIGEST = "3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85"
FRESH_LOGICAL_FLOAT_TOLERANCE = 1e-3

PROTECTED_PATHS = (
    Path.home(),
    REPO_ROOT,
    PACKET_DIR,
)
ALLOWED_SCRATCH_PREFIX = "nsqd-jepa-baselines-"
ALLOWED_TEMP_ROOTS = tuple(
    {
        Path(tempfile.gettempdir()).resolve(strict=False),
        Path("/tmp").resolve(strict=False),
        Path("/tmp"),
    }
)


def _guard_scratch_dir(scratch_dir: Path) -> Path:
    expanded = scratch_dir.expanduser()
    resolved = expanded.resolve(strict=False)
    if resolved == Path("/"):
        raise ValueError("scratch_dir points to a protected location")
    for protected in PROTECTED_PATHS:
        protected_resolved = protected.resolve(strict=False)
        if resolved == protected_resolved or protected_resolved in resolved.parents:
            raise ValueError("scratch_dir points to a protected location")
        if resolved in protected_resolved.parents:
            raise ValueError("scratch_dir is an unsafe ancestor of a protected location")
    if _contains_unapproved_symlink_alias(expanded):
        raise ValueError("scratch_dir must not resolve through a symlink alias")
    if not resolved.name.startswith(ALLOWED_SCRATCH_PREFIX):
        raise ValueError("scratch_dir must use the dedicated nsqd-jepa-baselines- prefix")
    if expanded.parent not in ALLOWED_TEMP_ROOTS and resolved.parent not in {
        root.resolve(strict=False) for root in ALLOWED_TEMP_ROOTS
    }:
        raise ValueError("scratch_dir must be a direct child of an existing temp root")
    if not _is_under_allowed_temp_root(expanded, resolved):
        raise ValueError("scratch_dir must stay under an allowlisted system temp root")
    return resolved


def _is_under_allowed_temp_root(expanded: Path, resolved: Path) -> bool:
    expanded_abs = expanded if expanded.is_absolute() else expanded.resolve(strict=False)
    for root in ALLOWED_TEMP_ROOTS:
        root_resolved = root.resolve(strict=False)
        if expanded_abs == root or root in expanded_abs.parents:
            return True
        if resolved == root_resolved or root_resolved in resolved.parents:
            return True
    return False


def _contains_unapproved_symlink_alias(path: Path) -> bool:
    current = path if path.is_absolute() else path.resolve(strict=False)
    for candidate in [current, *current.parents]:
        if candidate in {Path("/tmp"), Path(tempfile.gettempdir())}:
            return False
        if candidate.exists() and candidate.is_symlink():
            return True
    return False


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _prepare_embedder() -> tuple[object, dict[str, str]]:
    settings = load_settings(defaults_path=packaged_defaults_path(), base_dir=REPO_ROOT)
    embedder = build_local_ollama_embedder(settings.embeddings)
    metadata = _ollama_model_metadata(
        base_url=str(settings.embeddings.base_url),
        model_name=str(settings.embeddings.model),
        timeout_s=5.0,
    )
    if metadata["manifest_digest"] != EXPECTED_MANIFEST_DIGEST:
        raise ValueError("configured Ollama service manifest digest does not match the packet")
    if metadata["blob_digest"] != EXPECTED_BLOB_DIGEST:
        raise ValueError("configured Ollama service parent blob digest does not match the packet")
    return embedder, metadata


def _ollama_model_metadata(*, base_url: str, model_name: str, timeout_s: float) -> dict[str, str]:
    tags_url = f"{str(base_url).rstrip('/')}/api/tags"
    try:
        with urllib_request.urlopen(tags_url, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise ValueError("configured Ollama service tags request failed") from None
    if not isinstance(payload, dict):
        raise ValueError("configured Ollama service tags payload is invalid")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError("configured Ollama service tags payload is invalid")
    for row in models:
        if not isinstance(row, dict):
            continue
        names = {str(row.get("name") or "").strip(), str(row.get("model") or "").strip()}
        if model_name not in names:
            continue
        manifest_digest = str(row.get("digest") or "").strip()
        if len(manifest_digest) != 64 or any(
            ch not in "0123456789abcdef" for ch in manifest_digest
        ):
            raise ValueError("configured Ollama service returned an invalid model digest")
        details = row.get("details")
        if not isinstance(details, dict):
            raise ValueError("configured Ollama service did not return parent blob metadata")
        parent_model = str(details.get("parent_model") or "").strip()
        prefix = "sha256-"
        if prefix not in parent_model:
            raise ValueError("configured Ollama service returned an invalid parent blob reference")
        blob_digest = parent_model.rsplit(prefix, 1)[-1].strip()
        if len(blob_digest) != 64 or any(ch not in "0123456789abcdef" for ch in blob_digest):
            raise ValueError("configured Ollama service returned an invalid parent blob reference")
        return {"manifest_digest": manifest_digest, "blob_digest": blob_digest}
    raise ValueError("configured Ollama service does not expose the requested embedding model")


def _project_inputs() -> list[tuple[str, str, dict[str, Any]]]:
    final_manifest = tomllib.loads(
        read_verified_repo_file(
            repo_root=REPO_ROOT,
            relative_path=Path(
                "docs/reviews/nsqd-projection-review-2026-08-28/final/manifest.toml"
            ),
            expected_root=Path("docs/reviews/nsqd-projection-review-2026-08-28/final"),
            field="manifest_path",
        ).decode("utf-8")
    )["fixture"]
    fixture_manifest = tomllib.loads(
        read_verified_repo_file(
            repo_root=REPO_ROOT,
            relative_path=Path("tests/fixtures/approved/nsqd/manifest.toml"),
            expected_root=Path("tests/fixtures/approved/nsqd"),
            field="manifest_path",
        ).decode("utf-8")
    )["fixture"]
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for record_id in APPROVED_ORDER:
        if record_id.startswith("DATA-"):
            manifest = fixture_manifest[record_id]
            path = FIXTURE_ROOT / manifest["path"]
        else:
            manifest = final_manifest[record_id]
            path = PROJECTION_ROOT / manifest["path"]
        relative_path = path.relative_to(REPO_ROOT)
        root = (
            FIXTURE_ROOT.relative_to(REPO_ROOT)
            if record_id.startswith("DATA-")
            else PROJECTION_ROOT.relative_to(REPO_ROOT)
        )
        payload = load_verified_yaml_mapping(
            repo_root=REPO_ROOT,
            relative_path=relative_path,
            expected_root=root,
            field="projection_path",
        )
        rows.append((record_id, str(manifest["domain_policy_id"]), payload))
    return rows


def _build_container(scratch_dir: Path, embedder: object):
    scratch_dir = _guard_scratch_dir(scratch_dir)
    if scratch_dir.exists():
        raise ValueError("scratch_dir must be a fresh non-existent directory")
    parent = scratch_dir.parent
    if not parent.exists():
        raise ValueError("scratch_dir must be a direct child of an existing temp root")
    if parent.is_symlink():
        raise ValueError("scratch_dir parent must not be a symlink")
    if _contains_unapproved_symlink_alias(parent):
        raise ValueError("scratch_dir parent must not resolve through a symlink alias")
    try:
        scratch_dir.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError("scratch_dir must be a fresh non-existent directory") from exc
    if scratch_dir.is_symlink() or not scratch_dir.is_dir():
        raise ValueError("scratch_dir must resolve to a regular directory")
    if scratch_dir.parent != parent:
        raise ValueError("scratch_dir parent changed during creation")
    return build_container(
        db_path=scratch_dir / "nsqd.sqlite",
        index_path=scratch_dir / "index",
        clock=FixedClock(SEALED_AT),
        embedder=embedder,
        enabled_operators=frozenset({"A", "B"}),
    )


def _payload_sha256(payload: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(payload))


def _local_execution_receipt(scratch_dir: Path, container) -> dict[str, Any]:
    candidate_hashes = sorted(
        container.ctx.candidates._db.fetchall(
            "SELECT artifact_hash, payload_json FROM nsqd_candidates ORDER BY artifact_hash"
        ),
        key=lambda row: str(row["artifact_hash"]),
    )
    card_hashes = sorted(
        container.ctx.candidates._db.fetchall(
            "SELECT card_id, payload_json FROM nsqd_frontier_cards ORDER BY card_id"
        ),
        key=lambda row: str(row["card_id"]),
    )
    candidate_payload_sha256: dict[str, str] = {}
    frontier_card_payload_sha256: dict[str, str] = {}
    for row in candidate_hashes:
        payload = json.loads(str(row["payload_json"]))
        candidate_payload_sha256[str(row["artifact_hash"])] = _payload_sha256(payload)
    for row in card_hashes:
        payload = json.loads(str(row["payload_json"]))
        frontier_card_payload_sha256[str(row["card_id"])] = _payload_sha256(payload)
    return {
        "sqlite_sha256": sha256_file_digest(
            scratch_dir / "nsqd.sqlite", max_bytes=512 * 1024 * 1024
        ),
        "lancedb_tree_sha256": lancedb_tree_digest(scratch_dir / "index"),
        "candidate_count": len(candidate_hashes),
        "card_count": len(card_hashes),
        "candidate_artifact_hashes": [str(row["artifact_hash"]) for row in candidate_hashes],
        "frontier_card_hashes": [str(row["card_id"]) for row in card_hashes],
        "candidate_payload_sha256": candidate_payload_sha256,
        "frontier_card_payload_sha256": frontier_card_payload_sha256,
    }


def _compare_generated_to_packet(
    current: dict[str, Any],
    generated_a: list[dict[str, Any]],
    generated_b: list[dict[str, Any]],
    local_receipt: dict[str, Any],
) -> None:
    packet_a = current["operator_a_artifacts"]
    packet_b = current["operator_b_artifacts"]
    if [row["candidate_id"] for row in generated_a] != [row["candidate_id"] for row in packet_a]:
        raise ValueError("replayed Operator A candidate ids do not match the packet")
    if [row["candidate_artifact_hash"] for row in generated_a] != [
        row["candidate_artifact_hash"] for row in packet_a
    ]:
        raise ValueError("replayed Operator A artifact hashes do not match the packet")
    if [row["candidate_id"] for row in generated_b] != [row["candidate_id"] for row in packet_b]:
        raise ValueError("replayed Operator B candidate ids do not match the packet")
    if [row["candidate_artifact_hash"] for row in generated_b] != [
        row["candidate_artifact_hash"] for row in packet_b
    ]:
        raise ValueError("replayed Operator B artifact hashes do not match the packet")
    for generated, packet_row in zip(generated_a, packet_a, strict=True):
        for field in ("candidate_artifact", "grounding", "scored_card"):
            _assert_fresh_logical_match(
                candidate_id=str(generated["candidate_id"]),
                field=field,
                generated=generated[field],
                packet_value=packet_row[field],
            )
    for generated, packet_row in zip(generated_b, packet_b, strict=True):
        for field in ("candidate_artifact", "grounding", "scored_card"):
            _assert_fresh_logical_match(
                candidate_id=str(generated["candidate_id"]),
                field=field,
                generated=generated[field],
                packet_value=packet_row[field],
            )
    packet_receipt = current["execution_receipt"]
    if local_receipt["candidate_count"] != packet_receipt["candidate_count"]:
        raise ValueError("replayed candidate count does not match the packet receipt")
    if local_receipt["card_count"] != packet_receipt["card_count"]:
        raise ValueError("replayed card count does not match the packet receipt")
    if local_receipt["candidate_artifact_hashes"] != packet_receipt["candidate_artifact_hashes"]:
        raise ValueError("replayed candidate hash set does not match the packet receipt")
    if local_receipt["frontier_card_hashes"] != packet_receipt["frontier_card_hashes"]:
        raise ValueError("replayed card hash set does not match the packet receipt")


def _assert_fresh_logical_match(
    *, candidate_id: str, field: str, generated: Any, packet_value: Any
) -> None:
    difference = _find_first_logical_difference(
        generated,
        packet_value,
        path=field,
        tolerance=FRESH_LOGICAL_FLOAT_TOLERANCE,
    )
    if difference is None:
        return
    path, generated_value, packet_expected = difference
    raise ValueError(
        f"fresh logical replay mismatch for {candidate_id} {field} at {path}: "
        f"generated={generated_value!r} packet={packet_expected!r}"
    )


def _find_first_logical_difference(
    generated: Any,
    packet_value: Any,
    *,
    path: str,
    tolerance: float,
) -> tuple[str, Any, Any] | None:
    if type(generated) is not type(packet_value):
        return path, generated, packet_value
    if isinstance(generated, bool) or generated is None or isinstance(generated, (str, int)):
        return None if generated == packet_value else (path, generated, packet_value)
    if isinstance(generated, float):
        if not math.isfinite(generated) or not math.isfinite(packet_value):
            return path, generated, packet_value
        scale = max(abs(generated), abs(packet_value), 1.0)
        if abs(generated - packet_value) <= tolerance:
            return None
        if abs(generated - packet_value) / scale <= tolerance:
            return None
        return path, generated, packet_value
    if isinstance(generated, list):
        if len(generated) != len(packet_value):
            return f"{path}.length", len(generated), len(packet_value)
        for index, (left, right) in enumerate(zip(generated, packet_value, strict=True)):
            difference = _find_first_logical_difference(
                left,
                right,
                path=f"{path}[{index}]",
                tolerance=tolerance,
            )
            if difference is not None:
                return difference
        return None
    if isinstance(generated, dict):
        generated_keys = list(generated)
        packet_keys = list(packet_value)
        if generated_keys != packet_keys:
            return f"{path}.keys", generated_keys, packet_keys
        is_canonical_tau_measurement = (
            "measurement_artifact_digest" in generated
            and "measurement_artifact_digest" in packet_value
            and all(
                field in generated and field in packet_value
                for field in TAU_MEASUREMENT_ARTIFACT_FIELDS
            )
        )
        for key in generated_keys:
            if key == "measurement_artifact_digest" and is_canonical_tau_measurement:
                continue
            difference = _find_first_logical_difference(
                generated[key],
                packet_value[key],
                path=f"{path}.{key}",
                tolerance=tolerance,
            )
            if difference is not None:
                return difference
        if is_canonical_tau_measurement:
            generated_digest_issue = _validate_measurement_artifact_digest_side(
                generated,
                path=f"{path}.measurement_artifact_digest",
            )
            if generated_digest_issue is not None:
                return generated_digest_issue
            packet_digest_issue = _validate_measurement_artifact_digest_side(
                packet_value,
                path=f"{path}.measurement_artifact_digest",
            )
            if packet_digest_issue is not None:
                return packet_digest_issue
        return None
    return None if generated == packet_value else (path, generated, packet_value)


def _validate_measurement_artifact_digest_side(
    value: dict[str, Any], *, path: str
) -> tuple[str, Any, Any] | None:
    digest = value.get("measurement_artifact_digest")
    if not isinstance(digest, str):
        return path, digest, "valid measurement_artifact_digest"
    expected = tau_measurement_artifact_digest(value)
    if digest != expected:
        return path, digest, expected
    return None


def _replay(packet_dir: Path, scratch_dir: Path, *, verify_current_receipt: bool) -> dict[str, Any]:
    baseline = _load_json(packet_dir / "baseline-evidence.json")
    embedder, model = _prepare_embedder()
    container = _build_container(scratch_dir, embedder)
    project_inputs = _project_inputs()
    approved_digests = frozenset(
        canonical_reviewed_projection_digest(row[2]) for row in project_inputs
    )
    project = ProjectPaperUseCase(
        harvest=container.ctx.harvest,
        records=container.ctx.records,
        snapshots=container.ctx.snapshots,
        clock=container.ctx.clock,
        approved_projection_digests=approved_digests,
        index=container.ctx.index,
        embedder=embedder,
    )
    last = None
    for _record_id, policy_id, payload in project_inputs:
        last = project.run(domain_policy_id=policy_id, projection=payload)
    assert last is not None
    snapshot_id = str(last["snapshot_id"])
    corpus_version = int(last["corpus_version"])

    generated_a: list[dict[str, Any]] = []
    generated_b: list[dict[str, Any]] = []
    for section_name, operator, target in (
        ("operator_a_artifacts", "A", generated_a),
        ("operator_b_artifacts", "B", generated_b),
    ):
        for row in baseline[section_name]:
            candidate = deepcopy(row["candidate_artifact"]["candidate"])
            candidate.pop("dval", None)
            kwargs = {
                "candidate": candidate,
                "generator_run_id": str(row["candidate_artifact"]["generator_run_id"]),
                "axioms": deepcopy(row["candidate_artifact"]["axioms"]),
                "operator": operator,
            }
            if operator == "B":
                kwargs["target_cell_id"] = str(row["diverge_proof"]["selected_target_cell"])
                kwargs["cell_statuses"] = deepcopy(row["diverge_proof"]["cell_statuses"])
            artifact_hash = DivergeUseCase(
                candidates=container.ctx.candidates,
                cards=container.ctx.cards,
                clock=container.ctx.clock,
                enabled_operators=frozenset({"A", "B"}),
            ).run(**kwargs)
            grounding = GroundUseCase(
                snapshots=container.ctx.snapshots,
                records=container.ctx.records,
                index=container.ctx.index,
                candidates=container.ctx.candidates,
                embedder=embedder,
                clock=FixedClock(SEALED_AT),
            ).run(
                candidate_artifact_hash=artifact_hash,
                snapshot_id=snapshot_id,
                corpus_version=corpus_version,
                snapshot_state="production_valid",
            )
            scored = ScoreUseCase(
                candidates=container.ctx.candidates,
                cards=container.ctx.cards,
                snapshots=container.ctx.snapshots,
                records=container.ctx.records,
            ).run(
                candidate_artifact_hash=artifact_hash,
                evaluator_run_id=str(row["scored_card"]["evaluator_run_id"]),
                snapshot_id=snapshot_id,
                corpus_version=corpus_version,
                snapshot_state="production_valid",
            )
            stored = container.ctx.candidates.get_artifact(artifact_hash)
            assert stored is not None
            generated_row = {
                "candidate_id": row["candidate_id"],
                "candidate_artifact_hash": artifact_hash,
                "candidate_artifact": stored,
                "grounding": grounding,
                "scored_card": scored["card"],
            }
            target.append(generated_row)

    current = _load_json(packet_dir / "baseline-evidence.json")
    if any(
        row["scored_card"]["dval"] != 0 or row["scored_card"]["card_decision"] != "rejected"
        for row in [*generated_a, *generated_b]
    ):
        raise ValueError("replayed baseline cards must remain dval=0 and rejected")
    local_receipt = _local_execution_receipt(scratch_dir, container)
    local_runtime = verify_scratch_execution_receipt(
        local_receipt,
        scratch_runtime={
            "db_path": str(scratch_dir / "nsqd.sqlite"),
            "index_path": str(scratch_dir / "index"),
            "no_production_writes": True,
            "production_write_paths": [],
        },
    )
    _compare_generated_to_packet(current, generated_a, generated_b, local_receipt)
    if verify_current_receipt:
        verify_scratch_execution_receipt(
            current["execution_receipt"], scratch_runtime=current["scratch_runtime"]
        )
    return {
        "snapshot_id": snapshot_id,
        "corpus_version": corpus_version,
        "model": model,
        "generated_operator_a": generated_a,
        "generated_operator_b": generated_b,
        "receipt_runtime": local_runtime,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch-dir", type=Path)
    parser.add_argument("--packet-dir", type=Path, default=PACKET_DIR)
    parser.add_argument("--write-generated-json", action="store_true")
    parser.add_argument("--verify-current-receipt", action="store_true")
    args = parser.parse_args()

    if args.verify_current_receipt:
        current = _load_json(args.packet_dir / "baseline-evidence.json")
        runtime = verify_scratch_execution_receipt(
            current["execution_receipt"],
            scratch_runtime=current["scratch_runtime"],
        )
        print(
            json.dumps(
                {
                    "candidate_count": len(runtime["candidate_payloads"]),
                    "card_count": len(runtime["frontier_card_payloads"]),
                    "verified_current_receipt": True,
                },
                sort_keys=True,
            )
        )
        return 0

    if args.scratch_dir is None:
        parser.error("--scratch-dir is required unless --verify-current-receipt is set")
    result = _replay(args.packet_dir, args.scratch_dir, verify_current_receipt=False)
    if args.write_generated_json:
        output = args.scratch_dir / "replay-summary.json"
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "snapshot_id": result["snapshot_id"],
                "corpus_version": result["corpus_version"],
                "operator_a_count": len(result["generated_operator_a"]),
                "operator_b_count": len(result["generated_operator_b"]),
                "verified_current_receipt": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

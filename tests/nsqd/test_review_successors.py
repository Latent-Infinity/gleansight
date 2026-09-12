from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import yaml

from nsqd.domain.operator_g_types import StructuredValue

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWS_ROOT = REPO_ROOT / "docs" / "reviews"
C_PREDECESSOR = REVIEWS_ROOT / "nsqd-operator-c-evidence-resolution-2026-09-09"
C_SUCCESSOR = REVIEWS_ROOT / "nsqd-operator-c-evidence-resolution-2026-09-11-readme-correction"
F_PREDECESSOR = REVIEWS_ROOT / "nsqd-operator-f-readiness-2026-09-08"
F_SUCCESSOR = REVIEWS_ROOT / "nsqd-operator-f-readiness-2026-09-11-formula-correction"
STATUS_PREDECESSOR = REVIEWS_ROOT / "nsqd-status-window-calendar-replay-2026-09-02"
STATUS_SUCCESSOR = REVIEWS_ROOT / "nsqd-status-window-calendar-replay-2026-09-11-command-sync"
ACTIVATION_PREDECESSOR = REVIEWS_ROOT / "nsqd-operator-activation-2026-08-30"
ACTIVATION_SUCCESSOR = REVIEWS_ROOT / "nsqd-operator-activation-2026-09-11-remediation"
G_CODE_CORRECTION = REVIEWS_ROOT / "nsqd-operator-g-readiness-census-2026-09-11-code-correction"
G_TYPED_SUCCESSOR = (
    REVIEWS_ROOT / "nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup"
)
G_CURRENT = REVIEWS_ROOT / "nsqd-operator-g-readiness-census-2026-09-12-schema-closure"
G_V2_CONTRACT = REVIEWS_ROOT / "nsqd-operator-g-failure-record-contract-2026-09-11-v2"
DETACHED_TECHNICAL_REVIEW_ARTIFACTS = {
    "technical-review-summary.json",
    "technical-review-seal.json",
}


def _json(path: Path) -> dict[str, StructuredValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_digest(directories: tuple[Path, ...]) -> str:
    payload = bytearray()
    for directory in sorted(directories):
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            payload.extend(path.relative_to(REVIEWS_ROOT).as_posix().encode())
            payload.extend(b"\0")
            payload.extend(_sha256(path).encode())
            payload.extend(b"\0")
    return hashlib.sha256(payload).hexdigest()


def _assert_manifest_closure(packet_root: Path) -> dict[str, StructuredValue]:
    manifest = _json(packet_root / "packet-manifest.json")
    artifacts = manifest["artifact_sha256"]
    assert isinstance(artifacts, dict)
    assert set(artifacts) == {
        path.name
        for path in packet_root.iterdir()
        if path.name not in {"packet-manifest.json", *DETACHED_TECHNICAL_REVIEW_ARTIFACTS}
    }
    assert artifacts == {name: _sha256(packet_root / name) for name in sorted(artifacts)}
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    assert manifest["packet_digest"] == hashlib.sha256(preimage).hexdigest()
    return manifest


def test_historical_packet_trees_remain_byte_identical() -> None:
    c_directories = tuple(
        path
        for path in REVIEWS_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("nsqd-operator-c-") and path != C_SUCCESSOR
    )
    g_directories = tuple(
        path
        for path in REVIEWS_ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith("nsqd-operator-g-")
        and path not in {G_CODE_CORRECTION, G_TYPED_SUCCESSOR, G_CURRENT, G_V2_CONTRACT}
    )

    assert _tree_digest(c_directories) == (
        "26e90d8b3a71acdd56cbd7eeaa9da0d39460da0a0d56972ab6b6111f37eabfd5"
    )
    assert _tree_digest((F_PREDECESSOR,)) == (
        "01315629477b9785bdd0582101796f82d8980d0c9d0157be6780cd96180f9ea6"
    )
    assert _tree_digest(g_directories) == (
        "941c559cde4d2657789f9135dbac7ff471a82ae275944dfdf9e42b3534465a53"
    )
    assert _sha256(G_CODE_CORRECTION / "readiness.json") == (
        "6f628870c42b80d2ffaafb877310a22f31203c5e5513be640d3fc0f21b9d33d0"
    )
    assert _sha256(G_CODE_CORRECTION / "packet-manifest.json") == (
        "656a47b33a699a7d6609defc6745a1e168c4be96dd92ab7503ebeee70768c2f2"
    )
    assert _tree_digest((ACTIVATION_PREDECESSOR,)) == (
        "34dccff0d4c15c2bf193e66a79c933963af51c7553a4159f00a506f0906e0709"
    )
    assert {
        path.name: _sha256(path) for path in STATUS_PREDECESSOR.iterdir() if path.is_file()
    } == {
        "README.md": "f1335a594fa30ee33ce56ef33657596889972d2b22c95f396d782b8422f514b4",
        "calendar-replay-artifact.json": (
            "a99be18d9fe18fafe6893c97c2105d256d8ecdd4484643447874ec3f1c3964fd"
        ),
        "extracted-timestamp-rows.json": (
            "44b6debd95715a14b78d3ffc8ef0bb134cdbf2fffc729ed709318a12f7a9afef"
        ),
        "review-summary.json": "f2bd201776cc31021c43fa554a60110f9ea3e283c19f9dd0a562b2d1e69359a2",
    }


def test_operator_g_v2_contract_is_verified_outside_historical_packet_tree() -> None:
    contract_path = G_V2_CONTRACT / "failure-record-contract-v2.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))

    assert isinstance(contract, dict)
    assert contract["schema_version"] == 2
    assert contract["template_only"] is True
    assert contract["operator_g_eligible_by_default"] is False
    assert _sha256(contract_path) == (
        "7188368fa5ca00d9e7c526cdbb06688c768b863e26730f882e951b72f42fd1d2"
    )


def test_c_readme_successor_is_closed_and_prior_review_does_not_transfer() -> None:
    manifest = _assert_manifest_closure(C_SUCCESSOR)
    succession = _json(C_SUCCESSOR / "succession.json")
    assert succession == {
        "schema_version": 1,
        "packet_kind": "operator_c_readme_correction_succession",
        "review_status": "review_pending",
        "predecessor": {
            "manifest": "../nsqd-operator-c-evidence-resolution-2026-09-09/packet-manifest.json",
            "packet_digest": "8bec12564b873d1ae59a60ed0988b766e66909e7efa62a11a3fc027cfe06dd90",
            "manifest_sha256": "baf5ab583e294c4eebee2fcaa2cc73c5e4a985cfd74005af7cf21a39e4aa0abf",
            "review_summary_sha256": (
                "643fc415cc2f6b266a7a8bf4c04fdf11e34ede3947dd3be090ad241d3a5f04d4"
            ),
            "review_seal_sha256": (
                "43119d95b784fa587ae640815b8b71f6c96ccbc6f12d72ab1875edaff39971f2"
            ),
            "review_validity": "valid_for_predecessor_only",
        },
        "authority": {
            "accepted_bridge": False,
            "evidence_sufficient": False,
            "schema_admission_authorized": False,
            "runtime_authorized": False,
            "todo_7_advancement_authorized": False,
        },
    }
    predecessor = succession["predecessor"]
    assert isinstance(predecessor, dict)
    assert manifest["packet_digest"] != predecessor["packet_digest"]
    for name in (
        "acquisition-receipts.json",
        "bibliographic-query-receipts.json",
        "evidence-ledger.json",
        "source-extracts.jsonl",
        "typed-relations.json",
    ):
        assert (C_SUCCESSOR / name).read_bytes() == (C_PREDECESSOR / name).read_bytes()
    readme = (C_SUCCESSOR / "README.md").read_text(encoding="utf-8")
    assert "review_pending" in readme
    assert "valid_for_predecessor_only" in readme
    assert not any(line.endswith((" ", "\t")) for line in readme.splitlines())
    assert not (C_SUCCESSOR / "review-summary.json").exists()
    assert not (C_SUCCESSOR / "review-seal.json").exists()


def test_f_formula_successor_binds_approved_semantics_and_implementations() -> None:
    _assert_manifest_closure(F_SUCCESSOR)
    readiness = _json(F_SUCCESSOR / "readiness.json")
    assert readiness["review_status"] == "review_pending"
    assert readiness["predecessor"] == {
        "manifest": "../nsqd-operator-f-readiness-2026-09-08/packet-manifest.json",
        "packet_digest": "939e528b276c2065499bd724af4e88916da1b4927ef4a0ae8eb8ace6cd0cc9d8",
        "manifest_sha256": "3f1de41608d7a25283b08427334ab560c63e40470d469971127b83e8e4f2b9b3",
    }
    formulas = readiness["approved_non_authorizing_formulas"]
    assert formulas == {
        "quality_weighted_diversity": (
            "per_held_out_fold(sum(max_trusted_quality_weight_per_occupied_track_specific_cell)"
            "/sum(all_held_out_record_trusted_quality_weights));finite_nonnegative_weights_required;"
            "zero_total=typed_unavailable"
        ),
        "redundancy_with_existing_axes": (
            "per_held_out_rotation(max(bias_corrected_cramers_v(candidate_label,registered_axis)"
            "_fit_on_other_four_training_folds));aggregate=arithmetic_mean_of_five_rotations;"
            "held_out_frequencies_never_refit"
        ),
    }
    bindings = readiness["source_bindings"]
    assert isinstance(bindings, list)
    for binding in bindings:
        assert isinstance(binding, dict)
        assert _sha256(REPO_ROOT / str(binding["path"])) == binding["sha256"]
    assert readiness["evidence_sufficient"] is False
    assert readiness["schema_admission_authorized"] is False
    assert readiness["runtime_authorized"] is False


def test_status_successor_preserves_evidence_and_replay_targets_successor() -> None:
    _assert_manifest_closure(STATUS_SUCCESSOR)
    for name in (
        "calendar-replay-artifact.json",
        "extracted-timestamp-rows.json",
        "review-summary.json",
    ):
        assert (STATUS_SUCCESSOR / name).read_bytes() == (STATUS_PREDECESSOR / name).read_bytes()
    succession = _json(STATUS_SUCCESSOR / "succession.json")
    assert succession["review_status"] == "review_pending"
    assert succession["predecessor"] == {
        "path": "../nsqd-status-window-calendar-replay-2026-09-02",
        "packet_digest": "f81a9eed5d12f12a77d7252e234ff7a1e409ebb8a6d32bb709f0980e5b95ffd4",
    }
    assert succession["prior_summary_validity"] == "valid_for_predecessor_evidence_bytes_only"
    readme = (STATUS_SUCCESSOR / "README.md").read_text(encoding="utf-8")
    assert "nsqd-status-window-calendar-replay-2026-09-11-command-sync" in readme
    assert "--verify-retained-replay" in readme

    spec = importlib.util.spec_from_file_location(
        "status_window_replay_io", REPO_ROOT / "scripts" / "_status_window_replay_io.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.RETAINED_SOURCE_DIR == STATUS_PREDECESSOR
    assert module.OUTPUT_DIR == STATUS_SUCCESSOR


def test_activation_overlay_references_successors_without_g_reverse_binding() -> None:
    _assert_manifest_closure(ACTIVATION_SUCCESSOR)
    overlay = yaml.safe_load((ACTIVATION_SUCCESSOR / "activation-status.yaml").read_text())
    assert isinstance(overlay, dict)
    assert overlay["review_status"] == "review_pending"
    assert overlay["authorization_state"] == "report_only"
    assert overlay["operator_status"] == {
        "C": {"enabled": False, "runtime_authorized": False},
        "D": {"enabled": False, "runtime_authorized": False},
        "E": {"enabled": False, "runtime_authorized": False},
        "F": {"enabled": False, "runtime_authorized": False},
        "G": {"enabled": False, "runtime_authorized": False},
    }
    bindings = overlay["source_bindings"]
    assert isinstance(bindings, list)
    paths = {str(binding["path"]) for binding in bindings}
    assert (
        "../nsqd-operator-c-evidence-resolution-2026-09-11-readme-correction/packet-manifest.json"
    ) in paths
    assert (
        "../nsqd-operator-f-readiness-2026-09-11-formula-correction/packet-manifest.json"
    ) in paths
    assert (
        "../nsqd-status-window-calendar-replay-2026-09-11-command-sync/packet-manifest.json"
    ) in paths
    assert all("nsqd-operator-g-readiness-census-2026-09-11" not in path for path in paths)
    for binding in bindings:
        assert isinstance(binding, dict)
        assert _sha256(ACTIVATION_SUCCESSOR / str(binding["path"])) == binding["sha256"]
    authority = overlay["authority"]
    assert isinstance(authority, dict)
    assert authority and all(value is False for value in authority.values())

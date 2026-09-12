from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import yaml

from nsqd.domain.operator_g_types import StructuredValue

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWS_ROOT = REPO_ROOT / "docs" / "reviews"
F_SUCCESSOR = REVIEWS_ROOT / "nsqd-operator-f-readiness-2026-09-12-implementation-binding"
ACTIVATION_SUCCESSOR = REVIEWS_ROOT / "nsqd-operator-activation-2026-09-12-pointer-sync"
AUTHORITY_CLARIFICATION = (
    REVIEWS_ROOT / "nsqd-operator-activation-2026-09-11-authority-clarification"
)
F_SOURCE_PATHS = {
    "src/nsqd/domain/operator_approval.py",
    "src/nsqd/domain/operator_approval_errors.py",
    "src/nsqd/domain/operator_f.py",
    "src/nsqd/domain/operator_f_evaluation.py",
    "src/nsqd/domain/operator_f_evaluation_metrics.py",
    "src/nsqd/domain/operator_f_evaluation_metrics_basic.py",
    "src/nsqd/domain/operator_f_evaluation_metrics_stats.py",
    "src/nsqd/domain/operator_f_evaluation_readiness.py",
    "src/nsqd/domain/operator_f_evaluation_support.py",
    "src/nsqd/domain/operator_f_evaluation_trust.py",
    "src/nsqd/domain/operator_f_evaluation_trust_rules.py",
    "src/nsqd/domain/operator_f_evaluation_types.py",
    "src/nsqd/domain/operator_f_evaluation_validation.py",
    "src/nsqd/domain/snapshot.py",
    "tests/nsqd/operator_f_evaluation_remediation_support.py",
    "tests/nsqd/operator_f_evaluation_support.py",
    "tests/nsqd/test_operator_f_metric_diversity_semantics.py",
    "tests/nsqd/test_operator_f_metric_redundancy_semantics.py",
}
FORMULAS = {
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, StructuredValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _assert_manifest_replays(packet_root: Path) -> dict[str, StructuredValue]:
    manifest = _json(packet_root / "packet-manifest.json")
    artifacts = manifest["artifact_sha256"]
    assert isinstance(artifacts, dict)
    detached = {"technical-review-summary.json", "technical-review-seal.json"}
    assert set(artifacts) == {
        path.name
        for path in packet_root.iterdir()
        if path.name != "packet-manifest.json" and path.name not in detached
    }
    assert artifacts == {name: _sha256(packet_root / name) for name in sorted(artifacts)}
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    assert manifest["packet_digest"] == hashlib.sha256(preimage).hexdigest()
    return manifest


def _local_module_path(module_parts: tuple[str, ...]) -> Path | None:
    for root in (REPO_ROOT / "src", REPO_ROOT):
        module_path = root.joinpath(*module_parts).with_suffix(".py")
        if module_path.is_file():
            return module_path
        package_path = root.joinpath(*module_parts, "__init__.py")
        if package_path.is_file():
            tree = ast.parse(package_path.read_text(encoding="utf-8"))
            if any(
                not isinstance(node, ast.Expr)
                or not isinstance(node.value, ast.Constant)
                or not isinstance(node.value.value, str)
                for node in tree.body
            ):
                return package_path
    return None


def _local_imports(path: Path) -> set[Path]:
    try:
        relative = path.relative_to(REPO_ROOT / "src")
    except ValueError:
        relative = path.relative_to(REPO_ROOT)
    module_parts = relative.with_suffix("").parts
    package_parts = module_parts[:-1]
    imports: set[Path] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        targets: list[tuple[str, ...]] = []
        if isinstance(node, ast.Import):
            targets.extend(tuple(alias.name.split(".")) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                retained = len(package_parts) - node.level + 1
                base = package_parts[:retained]
            else:
                base = ()
            if node.module:
                base += tuple(node.module.split("."))
            targets.append(base)
            targets.extend(base + tuple(alias.name.split(".")) for alias in node.names)
        for target in targets:
            imported = _local_module_path(target)
            if imported is not None:
                imports.add(imported)
    return imports


def _transitive_local_import_closure(bound_paths: set[str]) -> set[str]:
    closure = set(bound_paths)
    pending = [REPO_ROOT / path for path in bound_paths if path.endswith(".py")]
    while pending:
        path = pending.pop()
        for imported in _local_imports(path):
            relative = imported.relative_to(REPO_ROOT).as_posix()
            if relative not in closure:
                closure.add(relative)
                pending.append(imported)
    return closure


def test_f_successor_binds_complete_current_implementation_and_exact_metric_tests() -> None:
    _assert_manifest_replays(F_SUCCESSOR)
    readiness = _json(F_SUCCESSOR / "readiness.json")

    assert readiness["review_status"] == "review_pending"
    assert readiness["authorization_state"] == "report_only"
    assert readiness["predecessor"] == {
        "manifest": (
            "../nsqd-operator-f-readiness-2026-09-11-formula-correction/packet-manifest.json"
        ),
        "manifest_sha256": "72e21375a988d73dcc4781e44739cccdd87ffc37f9eae22e83bf754543773b96",
        "packet_digest": "677932da4b0ecfeea26a0a80558314e1ee1a11b635877e15860cc9fc88775a2b",
        "review_validity": "valid_for_predecessor_only",
    }
    assert readiness["approved_non_authorizing_formulas"] == FORMULAS
    assert readiness["trust_evidence"] == "absent"
    bindings = readiness["source_bindings"]
    assert isinstance(bindings, list)
    bound_paths = {str(binding["path"]) for binding in bindings if isinstance(binding, dict)}
    assert bound_paths == F_SOURCE_PATHS
    assert bound_paths == _transitive_local_import_closure(bound_paths)
    for binding in bindings:
        assert isinstance(binding, dict)
        assert _sha256(REPO_ROOT / str(binding["path"])) == binding["sha256"]
    authority = readiness["authority"]
    assert isinstance(authority, dict)
    assert authority and all(value is False for value in authority.values())


def test_activation_successor_syncs_current_pointers_without_authority() -> None:
    _assert_manifest_replays(ACTIVATION_SUCCESSOR)
    status = yaml.safe_load((ACTIVATION_SUCCESSOR / "activation-status.yaml").read_text())
    assert isinstance(status, dict)

    assert status["review_status"] == "review_pending"
    assert status["authorization_state"] == "report_only"
    assert status["predecessor"] == {
        "manifest": (
            "../nsqd-operator-activation-2026-09-11-authority-clarification/packet-manifest.json"
        ),
        "manifest_sha256": "fb44c79f87002e48c46f4d00647fc289e72579726f33b187fc59160b05180ee6",
        "packet_digest": "5b4b50dddca913a2425eb1f965e2dc6f152dd700050379fd65ee8e4e6e9840b8",
        "review_validity": "valid_for_predecessor_only",
    }
    assert status["inherited_activation_tree"] == {
        "path": "../nsqd-operator-activation-2026-08-30",
        "tree_sha256": "34dccff0d4c15c2bf193e66a79c933963af51c7553a4159f00a506f0906e0709",
        "disposition": "inherited_user_owned_staged_baseline",
        "endorsement": "none",
    }
    assert status["base_reference"]["commit"] == "e29685b92d2f8ee88fcf0584556e5e8bc9df31aa"
    assert status["historical_claim"]["current_trust_status"] == "historical_claim_unverified"
    bindings = status["source_bindings"]
    assert isinstance(bindings, list)
    assert {str(binding["role"]) for binding in bindings if isinstance(binding, dict)} == {
        "operator_c_readme_integrity_successor",
        "operator_f_full_implementation_binding_successor",
        "status_replay_command_successor",
    }
    for binding in bindings:
        assert isinstance(binding, dict)
        assert _sha256(ACTIVATION_SUCCESSOR / str(binding["path"])) == binding["sha256"]
    operator_status = status["operator_status"]
    authority = status["authority"]
    assert isinstance(operator_status, dict)
    assert all(
        isinstance(value, dict)
        and value["enabled"] is False
        and value["runtime_authorized"] is False
        for value in operator_status.values()
    )
    assert isinstance(authority, dict)
    assert authority and all(value is False for value in authority.values())


def test_authority_clarification_detached_review_binds_exact_oracle_review() -> None:
    summary_path = AUTHORITY_CLARIFICATION / "technical-review-summary.json"
    summary = _json(summary_path)
    reviewer = summary["reviewer"]
    reviewed_packet = summary["reviewed_packet"]
    limitations = summary["limitations"]
    authority = summary["authority"]
    assert isinstance(reviewer, dict)
    assert isinstance(reviewed_packet, dict)
    assert isinstance(limitations, list)

    assert summary["verdict"] == "PASS"
    assert summary["reviewed_at_utc"] == "2026-09-12T01:42:09Z"
    assert reviewer == {
        "identity": "Oracle / independent technical reviewer",
        "session_id": "ses_f6cbe3052ffeHmvNkJlVdvCefV",
        "model": "openai/gpt-5.6-sol",
        "executor_session_id": "ses_f6ccc8768ffeFibA9O6p59k3xV",
        "reviewer_differs_from_executor": True,
    }
    assert reviewed_packet == {
        "manifest_sha256": "fb44c79f87002e48c46f4d00647fc289e72579726f33b187fc59160b05180ee6",
        "packet_digest": "5b4b50dddca913a2425eb1f965e2dc6f152dd700050379fd65ee8e4e6e9840b8",
    }
    assert limitations == [
        "Inherited staging time is not independently provable.",
        "The historical SQLite source is unavailable.",
        "This technical review is not human acceptance.",
    ]
    assert isinstance(authority, dict)
    assert authority and all(value is False for value in authority.values())

    seal = _json(AUTHORITY_CLARIFICATION / "technical-review-seal.json")
    assert seal["verdict"] == "PASS"
    assert seal["technical_review_summary_sha256"] == _sha256(summary_path)
    assert seal["packet_manifest_sha256"] == reviewed_packet["manifest_sha256"]
    assert seal["packet_digest"] == reviewed_packet["packet_digest"]
    assert seal["reviewed_at_utc"] == summary["reviewed_at_utc"]
    assert seal["reviewer"] == reviewer
    assert seal["limitations"] == limitations
    assert seal["authority"] == authority

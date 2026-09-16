from __future__ import annotations

from pathlib import Path
from typing import Any

from nsqd.app.use_cases import AutonomousTauPacketEvaluationUseCase, TauMeasurementEvidenceUseCase
from nsqd.cli import (
    _build_autonomous_tau_use_case,
    _canonical_json_text,
    _load_autonomous_tau_rows,
    _tau_report_output,
)
from nsqd.composition import NsqdContainer
from papers.config.settings import Settings
from papers.ui.path_policy import resolve_report_input, resolve_report_output
from papers.ui.workflow_services import WorkflowCallback


def build_tau_callback(
    nsqd: NsqdContainer,
    settings: Settings,
    *,
    repo_root: Path,
    db_path: Path,
    index_path: Path,
    config_path: Path | None,
) -> WorkflowCallback:
    def tau_command(
        *,
        hashes: list[str],
        action: str,
        output_path: str | None,
        input_paths: list[str],
        require_balanced: bool,
    ) -> dict[str, Any]:
        evidence = TauMeasurementEvidenceUseCase(
            candidates=nsqd.ctx.candidates,
            approved_projection_digests=nsqd.ctx.approved_projection_digests,
        )
        if action == "export":
            payload = evidence.export_jsonl(hashes)
            text = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
            return {"action": action, "jsonl": text}
        if action == "inventory":
            return {"action": action, "inventory": evidence.inventory(hashes)}
        report = _report_path(
            action,
            output_path=output_path,
            repo_root=repo_root,
        )
        if action == "review":
            result = _build_autonomous_tau_use_case(
                db=db_path, index=index_path, config=config_path
            ).run(hashes)
            report.write_text(_canonical_json_text(result), encoding="utf-8")
            packet = result["packet"]
            return {
                "action": action,
                "output": str(report),
                "packet_digest": result["packet_digest"],
                "approved_pair_count": packet["approved_pair_count"],
            }
        if action != "evaluate":
            raise ValueError("Action must be export, inventory, review, or evaluate.")
        if not input_paths:
            raise ValueError("evaluate requires review input paths")
        rows = _load_autonomous_tau_rows(
            [
                resolve_report_input(path, repo_root=repo_root, field="input_path")
                for path in input_paths
            ]
        )
        audit = settings.nsqd.autonomous_tau.audit
        result = AutonomousTauPacketEvaluationUseCase(
            measurement_evidence=evidence,
            audit_policy_revision=audit.policy_revision,
            audit_sample_rate=audit.sample_rate,
        ).run(hashes, rows, require_balanced=require_balanced)
        report.write_text(_canonical_json_text(result), encoding="utf-8")
        return {"action": action, "output": str(report), "result": result}

    return tau_command


def _report_path(action: str, *, output_path: str | None, repo_root: Path) -> Path:
    if action not in {"review", "evaluate"}:
        raise ValueError("Action must be export, inventory, review, or evaluate.")
    output = (
        resolve_report_output(output_path, repo_root=repo_root, field="output_path")
        if output_path
        else None
    )
    return _tau_report_output(
        output,
        workflow="autonomous-tau-review"
        if action == "review"
        else "evaluate-autonomous-tau-reviews",
        filename="review.json" if action == "review" else "evaluation.json",
    )
